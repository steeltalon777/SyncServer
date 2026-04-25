from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.models.item import Item
from app.services.operations_service import OperationsService
from app.services.uow import UnitOfWork
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class TemporaryItemsResolutionService:
    """Stage 3A resolution logic for temporary items: approve and merge with safe balance transfer."""

    RESOLUTION_SITE_ID_KEY = "resolution"

    @staticmethod
    async def _check_no_active_registers(
        uow: UnitOfWork,
        inventory_subject_id: int,
        temporary_item_id: int,
    ) -> None:
        """Block resolution if temporary item has active pending/lost/issued registers."""
        has_active = await uow.asset_registers.has_active_registers(inventory_subject_id)
        if has_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"temporary item {temporary_item_id} has active pending/lost/issued registers; "
                    "resolve them before approve/merge"
                ),
            )

    @staticmethod
    async def _transfer_balances_via_service_operations(
        uow: UnitOfWork,
        *,
        source_inventory_subject_id: int,
        source_item_id: int,
        target_inventory_subject_id: int,
        target_item_id: int,
        resolved_by_user_id: UUID,
        resolution_type: str,
        temporary_item_id: int,
    ) -> None:
        """Transfer current balances from source subject to target subject using service ADJUSTMENT operations.

        For each site with non-zero balance on the source subject, creates a pair of
        ADJUSTMENT operations: one negative (write-off from source) and one positive (receipt to target).
        Both operations are submitted immediately to update balance projections.
        """
        source_balances = await uow.balances.get_all_by_inventory_subject(source_inventory_subject_id)

        for balance_row in source_balances:
            qty = Decimal(str(balance_row.qty))
            if qty == 0:
                continue

            site_id = int(balance_row.site_id)
            resolution_note = (
                f"[resolution] {resolution_type} temporary_item={temporary_item_id}: "
                f"balance transfer site={site_id} qty={qty}"
            )

            # 1. Service write-off from source subject
            write_off_op = await uow.operations.create_operation(
                site_id=site_id,
                operation_type="ADJUSTMENT",
                created_by_user_id=resolved_by_user_id,
                notes=resolution_note,
                effective_at=datetime.now(UTC),
            )
            await uow.operations.create_operation_line(
                operation_id=write_off_op.id,
                line_number=1,
                inventory_subject_id=source_inventory_subject_id,
                item_id=source_item_id,
                qty=-qty,
                comment=resolution_note,
            )
            # Use OperationsService.submit_operation to trigger balance updates
            await OperationsService.submit_operation(
                uow=uow,
                operation_id=write_off_op.id,
                user_id=resolved_by_user_id,
            )

            # 2. Service receipt to target subject
            receipt_op = await uow.operations.create_operation(
                site_id=site_id,
                operation_type="ADJUSTMENT",
                created_by_user_id=resolved_by_user_id,
                notes=resolution_note,
                effective_at=datetime.now(UTC),
            )
            await uow.operations.create_operation_line(
                operation_id=receipt_op.id,
                line_number=1,
                inventory_subject_id=target_inventory_subject_id,
                item_id=target_item_id,
                qty=qty,
                comment=resolution_note,
            )
            # Use OperationsService.submit_operation to trigger balance updates
            await OperationsService.submit_operation(
                uow=uow,
                operation_id=receipt_op.id,
                user_id=resolved_by_user_id,
            )

    @staticmethod
    async def approve_as_item(
        uow: UnitOfWork,
        *,
        temporary_item_id: int,
        resolved_by_user_id: UUID,
    ) -> dict:
        """Approve temporary item as a new permanent catalog item.

        Steps:
        1. Load temporary item with relations.
        2. Check no active registers.
        3. Create a new permanent Item (active).
        4. Create a new InventorySubject for the new item.
        5. Transfer balances via service operations.
        6. Resolve the temporary item (status=approved_as_item).
        """
        from app.repos.temporary_items_repo import TemporaryItemsRepo

        temp_item = await uow.temporary_items.get_by_id(temporary_item_id)
        if temp_item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="temporary item not found")
        if temp_item.status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary item is already resolved",
            )

        # Get the inventory subject for the temporary item
        temp_subject = await uow.inventory_subjects.get_by_temporary_item_id(temporary_item_id)
        if temp_subject is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary item has no inventory subject",
            )

        # Block if active registers exist
        await TemporaryItemsResolutionService._check_no_active_registers(
            uow, int(temp_subject.id), temporary_item_id,
        )

        # Create a new permanent catalog item (copy from backing item)
        new_item = Item(
            sku=temp_item.sku,
            name=temp_item.name,
            normalized_name=temp_item.normalized_name,
            category_id=temp_item.category_id,
            unit_id=temp_item.unit_id,
            description=temp_item.description,
            hashtags=temp_item.hashtags,
            is_active=True,
            source_system="temporary_item_resolution",
            source_ref=f"approve_as_item:{temporary_item_id}",
        )
        new_item = await uow.catalog.create_item(new_item)

        # Create a new inventory subject for the new permanent item
        new_subject = await uow.inventory_subjects.create_for_item(item_id=new_item.id)

        # Transfer balances via service operations
        if temp_item.item_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary item has no backing item",
            )
        await TemporaryItemsResolutionService._transfer_balances_via_service_operations(
            uow,
            source_inventory_subject_id=int(temp_subject.id),
            source_item_id=temp_item.item_id,
            target_inventory_subject_id=int(new_subject.id),
            target_item_id=new_item.id,
            resolved_by_user_id=resolved_by_user_id,
            resolution_type="approve_as_item",
            temporary_item_id=temporary_item_id,
        )

        # Resolve the temporary item
        await uow.temporary_items.resolve_as_item(
            temporary_item_id=temporary_item_id,
            resolved_item_id=new_item.id,
            resolved_by_user_id=resolved_by_user_id,
            resolution_type="approve_as_item",
            resolution_note="Stage 3A approve: new catalog item created, balances transferred",
        )

        return {"resolved_item_id": new_item.id, "resolution_type": "approve_as_item"}

    @staticmethod
    async def merge_to_item(
        uow: UnitOfWork,
        *,
        temporary_item_id: int,
        target_item_id: int,
        resolved_by_user_id: UUID,
        resolution_note: str | None,
    ) -> dict:
        """Merge temporary item into an existing permanent catalog item.

        Steps:
        1. Load temporary item with relations.
        2. Validate target item exists and is active.
        3. Check no active registers.
        4. Transfer balances via service operations.
        5. Archive the temporary inventory subject.
        6. Resolve the temporary item (status=merged_to_item).
        """
        temp_item = await uow.temporary_items.get_by_id(temporary_item_id)
        if temp_item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="temporary item not found")
        if temp_item.status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary item is already resolved",
            )

        target_item = await uow.catalog.get_item_by_id(target_item_id)
        if target_item is None or target_item.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target item not found")
        # Check "must differ" BEFORE checking is_active, because the backing item
        # has is_active=False and we want a clear 422 for self-merge attempts.
        if target_item_id == temp_item.item_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target item must differ from backing item",
            )
        if not target_item.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target item not found")

        # Get the inventory subject for the temporary item
        temp_subject = await uow.inventory_subjects.get_by_temporary_item_id(temporary_item_id)
        if temp_subject is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary item has no inventory subject",
            )

        # Block if active registers exist
        await TemporaryItemsResolutionService._check_no_active_registers(
            uow, int(temp_subject.id), temporary_item_id,
        )

        # Get or create inventory subject for target item
        target_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=target_item_id)

        # Transfer balances via service operations
        if temp_item.item_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary item has no backing item",
            )
        await TemporaryItemsResolutionService._transfer_balances_via_service_operations(
            uow,
            source_inventory_subject_id=int(temp_subject.id),
            source_item_id=temp_item.item_id,
            target_inventory_subject_id=int(target_subject.id),
            target_item_id=target_item_id,
            resolved_by_user_id=resolved_by_user_id,
            resolution_type="merge",
            temporary_item_id=temporary_item_id,
        )

        # Archive the temporary inventory subject
        await uow.inventory_subjects.archive(int(temp_subject.id))

        # Deactivate backing item
        if temp_item.item is not None:
            temp_item.item.is_active = False

        # Resolve the temporary item
        await uow.temporary_items.merge_to_item(
            temporary_item_id=temporary_item_id,
            target_item_id=target_item_id,
            resolved_by_user_id=resolved_by_user_id,
            resolution_note=resolution_note or "Stage 3A merge: balances transferred to target item",
        )

        return {"resolved_item_id": target_item_id, "resolution_type": "merge"}

    @staticmethod
    async def delete_temporary_item(
        uow: UnitOfWork,
        *,
        temporary_item_id: int,
        resolved_by_user_id: UUID,
        resolution_note: str | None,
    ) -> dict:
        """Удалить временный ТМЦ (мягкое удаление).

        Проверки:
        1. Временный ТМЦ существует и имеет статус "active".
        2. Нет активных регистров (pending/lost/issued с ненулевым количеством).
        3. Нулевые остатки (balances) по всем сайтам.
        4. Архивировать inventory_subject (если существует).
        5. Деактивировать backing item (если существует).

        Возвращает:
            {"resolution_type": "deleted"}
        """
        from app.models.temporary_item import TemporaryItem

        temp_item = await uow.temporary_items.get_by_id(temporary_item_id)
        if temp_item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="temporary item not found")
        if temp_item.status != TemporaryItem.STATUS_ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary item is already resolved",
            )

        # Получить inventory subject для временного ТМЦ
        temp_subject = await uow.inventory_subjects.get_by_temporary_item_id(temporary_item_id)
        if temp_subject is not None:
            # Проверить активные регистры
            await TemporaryItemsResolutionService._check_no_active_registers(
                uow, int(temp_subject.id), temporary_item_id,
            )

            # Проверить нулевые остатки
            balances = await uow.balances.get_all_by_inventory_subject(int(temp_subject.id))
            for balance_row in balances:
                if balance_row.qty != 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="temporary item has non-zero balances; cannot delete",
                    )

            # Архивировать inventory subject
            await uow.inventory_subjects.archive(int(temp_subject.id))

        # Деактивировать backing item
        if temp_item.item is not None:
            temp_item.item.is_active = False

        # Пометить временный ТМЦ как удалённый
        await uow.temporary_items.mark_deleted(
            temporary_item_id=temporary_item_id,
            resolved_by_user_id=resolved_by_user_id,
            resolution_note=resolution_note or "Удалён пользователем",
        )

        return {"resolution_type": "deleted"}
