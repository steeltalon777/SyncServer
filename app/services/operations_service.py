from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status

from app.models.item import Item
from app.repos.recipients_repo import normalize_recipient_name
from app.schemas.asset_register import OperationAcceptLinePayload
from app.schemas.operation import OperationCreate, OperationType, OperationUpdate
from app.services.document_service import DocumentService
from app.services.uow import UnitOfWork
from app.services.operations_workflow_policy import OperationsWorkflowPolicy

logger = logging.getLogger(__name__)

SUPPORTED_OPERATION_TYPES: set[OperationType] = {
    "RECEIVE",
    "EXPENSE",
    "WRITE_OFF",
    "MOVE",
    "ADJUSTMENT",
    "ISSUE",
    "ISSUE_RETURN",
}
DECREMENT_OPERATION_TYPES: set[OperationType] = {"EXPENSE", "WRITE_OFF"}
ACCEPTANCE_REQUIRED_TYPES: set[OperationType] = {"RECEIVE", "MOVE"}
ISSUE_OPERATION_TYPES: set[OperationType] = {"ISSUE", "ISSUE_RETURN"}


class OperationsService:
    """Operation domain service with strict server-side validation."""

    @staticmethod
    def _normalize_name(value: str) -> str:
        return " ".join(value.strip().lower().split())

    @staticmethod
    async def _ensure_item_usable(uow: UnitOfWork, item_id: int):
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None or item.deleted_at is not None or not item.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"item with id {item_id} not found")
        temporary_item = await uow.temporary_items.get_by_item_id(item_id)
        if temporary_item is not None and temporary_item.status != "approved_as_item":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="temporary backing item cannot be used directly via item_id",
            )
        return item

    @staticmethod
    def _ensure_temporary_payload_consistent(batch: dict[str, object], client_key: str, payload) -> None:
        existing = batch.get(client_key)
        if existing is None:
            batch[client_key] = payload
            return
        if existing.model_dump() != payload.model_dump():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"temporary_item client_key '{client_key}' is reused with different payload",
            )

    @staticmethod
    async def _ensure_sufficient_balance(
        uow: UnitOfWork,
        *,
        site_id: int,
        inventory_subject_id: int,
        required_qty: Decimal,
        error_message: str,
    ) -> None:
        balance = await uow.balances.get_for_update(
            site_id=site_id,
            inventory_subject_id=inventory_subject_id,
        )
        current_qty = balance.qty if balance is not None else Decimal("0")
        if current_qty < required_qty:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)

    @staticmethod
    async def _validate_operation_type(operation_type: OperationType) -> None:
        if operation_type not in SUPPORTED_OPERATION_TYPES:
            supported = ", ".join(sorted(SUPPORTED_OPERATION_TYPES))
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unsupported operation_type '{operation_type}', supported: {supported}",
            )

    @staticmethod
    async def _apply_balance_delta(
        uow: UnitOfWork,
        *,
        site_id: int,
        inventory_subject_id: int,
        quantity_delta: Decimal,
        error_context: str,
    ) -> None:
        if quantity_delta < 0:
            await OperationsService._ensure_sufficient_balance(
                uow,
                site_id=site_id,
                inventory_subject_id=inventory_subject_id,
                required_qty=abs(quantity_delta),
                error_message=(
                    f"insufficient stock for {error_context}: "
                    f"inventory_subject={inventory_subject_id}, site={site_id}, required={abs(quantity_delta)}"
                ),
            )
        await uow.balances.update_balance_quantity(
            site_id=site_id,
            inventory_subject_id=inventory_subject_id,
            quantity_delta=quantity_delta,
        )

    @staticmethod
    async def _upsert_pending(
        uow: UnitOfWork,
        *,
        operation_id,
        operation_line_id: int,
        destination_site_id: int,
        source_site_id: int | None,
        inventory_subject_id: int,
        qty_delta: Decimal,
        error_context: str,
    ) -> None:
        try:
            await uow.asset_registers.upsert_pending(
                operation_id=operation_id,
                operation_line_id=operation_line_id,
                destination_site_id=destination_site_id,
                source_site_id=source_site_id,
                inventory_subject_id=inventory_subject_id,
                qty_delta=qty_delta,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"pending acceptance quantity conflict for {error_context}",
            ) from exc

    @staticmethod
    async def _upsert_lost(
        uow: UnitOfWork,
        *,
        operation_id,
        operation_line_id: int,
        site_id: int,
        source_site_id: int | None,
        inventory_subject_id: int,
        qty_delta: Decimal,
        error_context: str,
    ) -> None:
        try:
            await uow.asset_registers.upsert_lost(
                operation_id=operation_id,
                operation_line_id=operation_line_id,
                site_id=site_id,
                source_site_id=source_site_id,
                inventory_subject_id=inventory_subject_id,
                qty_delta=qty_delta,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"lost asset quantity conflict for {error_context}",
            ) from exc

    @staticmethod
    async def _upsert_issued(
        uow: UnitOfWork,
        *,
        recipient_id: int,
        inventory_subject_id: int,
        qty_delta: Decimal,
        error_context: str,
    ) -> None:
        try:
            await uow.asset_registers.upsert_issued(
                recipient_id=recipient_id,
                inventory_subject_id=inventory_subject_id,
                qty_delta=qty_delta,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"issued asset quantity conflict for {error_context}",
            ) from exc

    @staticmethod
    async def _validate_operation_sites(uow: UnitOfWork, operation_data: OperationCreate) -> None:
        site = await uow.sites.get_by_id(operation_data.site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

        if operation_data.operation_type == "MOVE":
            if operation_data.source_site_id is None or operation_data.destination_site_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE operation requires source_site_id and destination_site_id",
                )
            if operation_data.source_site_id == operation_data.destination_site_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE source and destination must be different",
                )
            if operation_data.site_id != operation_data.source_site_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE operation site_id must match source_site_id",
                )

            source = await uow.sites.get_by_id(operation_data.source_site_id)
            if not source:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source site not found")
            destination = await uow.sites.get_by_id(operation_data.destination_site_id)
            if not destination:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="destination site not found")

    @staticmethod
    def _validate_line_quantities(
        operation_type: OperationType,
        lines,
    ) -> None:
        if operation_type == "ADJUSTMENT":
            return
        for line in lines:
            if line.qty <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{operation_type} operations require positive qty values",
                )

    @staticmethod
    async def _resolve_recipient(
        uow: UnitOfWork,
        *,
        operation_type: OperationType,
        recipient_id: int | None,
        recipient_name_snapshot: str | None,
        issued_to_name: str | None,
    ) -> tuple[int | None, str | None]:
        if operation_type not in ISSUE_OPERATION_TYPES:
            return recipient_id, recipient_name_snapshot

        if recipient_id is not None:
            recipient = await uow.recipients.get_by_id(recipient_id)
            if recipient is None or recipient.merged_into_id is not None or not recipient.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recipient not found")
            return recipient.id, recipient.display_name

        candidate_name = recipient_name_snapshot or issued_to_name
        if candidate_name is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ISSUE and ISSUE_RETURN require recipient_id or recipient_name",
            )
        normalized = normalize_recipient_name(candidate_name)
        if not normalized:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="recipient_name is empty after normalization",
            )

        recipient = await uow.recipients.get_or_create_by_name(
            display_name=candidate_name,
            recipient_type="person",
        )
        return recipient.id, recipient.display_name

    @staticmethod
    def _destination_site_for_acceptance(operation) -> int:
        if operation.operation_type == "MOVE":
            if operation.destination_site_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE operation requires destination_site_id",
                )
            return operation.destination_site_id
        return operation.site_id

    @staticmethod
    async def _ensure_line_inventory_subject(uow: UnitOfWork, line) -> int:
        if line.inventory_subject_id is not None:
            return int(line.inventory_subject_id)
        if line.item_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"operation line {line.id} has neither inventory_subject_id nor item_id",
            )
        subject = await uow.inventory_subjects.get_or_create_for_item(item_id=int(line.item_id))
        line.inventory_subject_id = subject.id
        await uow.session.flush()
        return int(subject.id)

    @staticmethod
    async def create_operation(
        uow: UnitOfWork,
        operation_data: OperationCreate,
        user_id: UUID,
    ) -> dict[str, object]:
        await OperationsService._validate_operation_type(operation_data.operation_type)
        await OperationsService._validate_operation_sites(uow, operation_data)
        OperationsService._validate_line_quantities(operation_data.operation_type, operation_data.lines)

        temporary_batch = {}
        has_temporary_items = False
        for line in operation_data.lines:
            if line.temporary_item is not None:
                has_temporary_items = True
                OperationsService._ensure_temporary_payload_consistent(
                    temporary_batch,
                    line.temporary_item.client_key,
                    line.temporary_item,
                )
            elif line.item_id is not None:
                await OperationsService._ensure_item_usable(uow, line.item_id)

        if has_temporary_items:
            if operation_data.operation_type != "RECEIVE":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Phase 1 supports inline temporary_item creation only for RECEIVE operations",
                )
            existing_operation = await uow.operations.get_by_client_request_id(
                created_by_user_id=user_id,
                client_request_id=operation_data.client_request_id or "",
            )
            if existing_operation is not None:
                # Idempotency replay: if payload matches, return existing operation.
                # If payload differs, return 409 Conflict per spec §7.4.
                # Compare by line_number, qty, batch, comment and snapshot name
                # (item_id differs after creation for temporary items).
                # Normalize comparison for idempotency, especially for temporary items
                def normalize_qty(q):
                    # Convert to Decimal for consistent comparison
                    from decimal import Decimal
                    if isinstance(q, (int, float, str)):
                        return Decimal(str(q))
                    return q if isinstance(q, Decimal) else Decimal("0")

                def normalize_str(s):
                    if s is None:
                        return None
                    return s.strip().lower()

                existing_lines = []
                for line in existing_operation.lines:
                    existing_lines.append({
                        "line_number": line.line_number,
                        "qty": normalize_qty(line.qty),
                        "batch": normalize_str(line.batch),
                        "comment": normalize_str(line.comment),
                        "item_name_snapshot": normalize_str(line.item_name_snapshot),
                    })

                incoming_lines = []
                for line in operation_data.lines:
                    incoming_lines.append({
                        "line_number": line.line_number,
                        "qty": normalize_qty(line.qty),
                        "batch": normalize_str(line.batch),
                        "comment": normalize_str(line.comment),
                        "item_name_snapshot": normalize_str(
                            line.temporary_item.name.strip() if line.temporary_item is not None else None
                        ),
                    })

                if existing_lines != incoming_lines:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            f"Idempotency conflict: client_request_id '{operation_data.client_request_id}' "
                            f"was already used with a different payload. "
                            f"Existing operation id={existing_operation.id}."
                        ),
                    )
                return {"operation": existing_operation}

        recipient_id, recipient_name_snapshot = await OperationsService._resolve_recipient(
            uow,
            operation_type=operation_data.operation_type,
            recipient_id=operation_data.recipient_id,
            recipient_name_snapshot=operation_data.recipient_name_snapshot,
            issued_to_name=operation_data.issued_to_name,
        )

        acceptance_required = operation_data.operation_type in ACCEPTANCE_REQUIRED_TYPES
        operation = await uow.operations.create_operation(
            site_id=operation_data.site_id,
            operation_type=operation_data.operation_type,
            effective_at=operation_data.effective_at or datetime.now(UTC),
            source_site_id=operation_data.source_site_id,
            destination_site_id=operation_data.destination_site_id,
            issued_to_user_id=operation_data.issued_to_user_id,
            issued_to_name=recipient_name_snapshot or operation_data.issued_to_name,
            recipient_id=recipient_id,
            recipient_name_snapshot=recipient_name_snapshot,
            acceptance_required=acceptance_required,
            created_by_user_id=user_id,
            notes=operation_data.notes,
            client_request_id=operation_data.client_request_id,
        )

        item_cache = {}
        unit_cache = {}
        category_cache = {}
        temporary_created_by_key = {}
        temporary_subject_by_key = {}

        for client_key, payload in temporary_batch.items():
            if payload.category_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"temporary_item '{client_key}' requires category_id in Phase 1 because current item model is category-bound"
                    ),
                )
            unit = await uow.catalog.get_unit_by_id(payload.unit_id)
            if unit is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unit with id {payload.unit_id} not found")
            category = await uow.catalog.get_category_by_id(payload.category_id)
            if category is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"category with id {payload.category_id} not found",
                )

            backing_item = Item(
                sku=payload.sku,
                name=payload.name.strip(),
                normalized_name=OperationsService._normalize_name(payload.name),
                category_id=payload.category_id,
                unit_id=payload.unit_id,
                description=payload.description,
                hashtags=payload.hashtags,
                is_active=False,
                source_system="temporary_item",
                source_ref=payload.client_key,
            )
            backing_item = await uow.catalog.create_item(backing_item)
            temporary_item = await uow.temporary_items.create(
                item_id=backing_item.id,
                name=payload.name.strip(),
                normalized_name=OperationsService._normalize_name(payload.name),
                sku=payload.sku,
                unit_id=payload.unit_id,
                category_id=payload.category_id,
                description=payload.description,
                hashtags=payload.hashtags,
                created_by_user_id=user_id,
            )
            temporary_subject = await uow.inventory_subjects.get_or_create_for_temporary_item(
                temporary_item_id=temporary_item.id,
                item_id=backing_item.id,
            )
            item_cache[backing_item.id] = backing_item
            unit_cache[payload.unit_id] = unit
            category_cache[payload.category_id] = category
            temporary_created_by_key[client_key] = temporary_item
            temporary_subject_by_key[client_key] = temporary_subject

        for line_data in operation_data.lines:
            line_item_id = line_data.item_id
            line_subject_id: int | None = None
            if line_data.temporary_item is not None:
                line_item_id = temporary_created_by_key[line_data.temporary_item.client_key].item_id
                line_subject_id = temporary_subject_by_key[line_data.temporary_item.client_key].id

            if line_item_id is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="line item resolution failed")

            if line_subject_id is None:
                line_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=line_item_id)
                line_subject_id = line_subject.id

            item = item_cache.get(line_item_id)
            if item is None:
                item = await uow.catalog.get_item_by_id(line_item_id)
                if not item:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"item with id {line_item_id} not found",
                    )
                item_cache[line_item_id] = item

            unit = unit_cache.get(item.unit_id)
            if unit is None:
                unit = await uow.catalog.get_unit_by_id(item.unit_id)
                if not unit:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"unit with id {item.unit_id} not found",
                    )
                unit_cache[item.unit_id] = unit

            # Получаем category
            category = category_cache.get(item.category_id)
            if category is None:
                category = await uow.catalog.get_category_by_id(item.category_id)
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"category with id {item.category_id} not found",
                    )
                category_cache[item.category_id] = category

            await uow.operations.create_operation_line(
                operation_id=operation.id,
                line_number=line_data.line_number,
                inventory_subject_id=line_subject_id,
                item_id=line_item_id,
                qty=line_data.qty,
                batch=line_data.batch,
                comment=line_data.comment,
                item_name_snapshot=item.name,
                item_sku_snapshot=item.sku,
                unit_name_snapshot=unit.name,
                unit_symbol_snapshot=unit.symbol,
                category_name_snapshot=category.name,
            )

        created_operation = await uow.operations.get_operation_by_id(operation.id)
        return {"operation": created_operation}

    @staticmethod
    async def update_operation_effective_at(
        uow: UnitOfWork,
        operation_id: UUID,
        *,
        effective_at: datetime,
    ):
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_not_cancelled_for_effective_at_change(operation)

        updated = await uow.operations.update_operation(
            operation_id=operation_id,
            effective_at=effective_at,
            fields_set={"effective_at"},
        )
        return await uow.operations.get_operation_by_id(updated.id)

    @staticmethod
    async def update_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        update_data: OperationUpdate,
    ):
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_draft_for_update(operation)

        source_site_id = operation.source_site_id
        destination_site_id = operation.destination_site_id
        if "source_site_id" in update_data.model_fields_set:
            source_site_id = update_data.source_site_id
        if "destination_site_id" in update_data.model_fields_set:
            destination_site_id = update_data.destination_site_id

        if operation.operation_type == "MOVE":
            if source_site_id is None or destination_site_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE operation requires source_site_id and destination_site_id",
                )
            if source_site_id == destination_site_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE source and destination must be different",
                )
            if operation.site_id != source_site_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE operation site_id must match source_site_id",
                )
        if update_data.lines is not None:
            OperationsService._validate_line_quantities(operation.operation_type, update_data.lines)

        recipient_id = operation.recipient_id
        recipient_name_snapshot = operation.recipient_name_snapshot
        if operation.operation_type in ISSUE_OPERATION_TYPES:
            desired_recipient_id = update_data.recipient_id if "recipient_id" in update_data.model_fields_set else operation.recipient_id
            desired_snapshot = (
                update_data.recipient_name_snapshot
                if "recipient_name_snapshot" in update_data.model_fields_set
                else operation.recipient_name_snapshot
            )
            desired_issued_to_name = (
                update_data.issued_to_name
                if "issued_to_name" in update_data.model_fields_set
                else operation.issued_to_name
            )
            recipient_id, recipient_name_snapshot = await OperationsService._resolve_recipient(
                uow,
                operation_type=operation.operation_type,
                recipient_id=desired_recipient_id,
                recipient_name_snapshot=desired_snapshot,
                issued_to_name=desired_issued_to_name,
            )

        updated = await uow.operations.update_operation(
            operation_id=operation_id,
            notes=update_data.notes,
            effective_at=update_data.effective_at,
            source_site_id=source_site_id,
            destination_site_id=destination_site_id,
            issued_to_user_id=update_data.issued_to_user_id,
            issued_to_name=recipient_name_snapshot or update_data.issued_to_name,
            recipient_id=recipient_id,
            recipient_name_snapshot=recipient_name_snapshot,
            fields_set=update_data.model_fields_set,
        )

        if update_data.lines is not None:
            await uow.operations.delete_operation_lines(operation_id)
            for line in update_data.lines:
                if line.temporary_item is not None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="temporary_item lines are not supported in PATCH /operations in Phase 1",
                    )
                if line.item_id is None:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="item_id is required")
                await OperationsService._ensure_item_usable(uow, line.item_id)
                line_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=line.item_id)
                await uow.operations.create_operation_line(
                    operation_id=operation_id,
                    line_number=line.line_number,
                    inventory_subject_id=line_subject.id,
                    item_id=line.item_id,
                    qty=line.qty,
                    batch=line.batch,
                    comment=line.comment,
                )

        return await uow.operations.get_operation_by_id(updated.id)

    @staticmethod
    async def submit_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
    ) -> dict[str, object]:
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_draft_for_submit(operation)

        for line in operation.lines:
            await OperationsService._ensure_line_inventory_subject(uow, line)
            quantity = Decimal(line.qty)
            if operation.operation_type == "RECEIVE":
                if operation.acceptance_required:
                    await OperationsService._upsert_pending(
                        uow,
                        operation_id=operation.id,
                        operation_line_id=line.id,
                        destination_site_id=operation.site_id,
                        source_site_id=None,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=quantity,
                        error_context="RECEIVE submit",
                    )
                else:
                    await uow.balances.update_balance_quantity(
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                    )
            elif operation.operation_type in DECREMENT_OPERATION_TYPES:
                await OperationsService._ensure_sufficient_balance(
                    uow,
                    site_id=operation.site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    required_qty=quantity,
                    error_message=(
                        f"insufficient stock for {operation.operation_type}: inventory_subject={line.inventory_subject_id}, "
                        f"site={operation.site_id}, required={line.qty}"
                    ),
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    quantity_delta=-quantity,
                )
            elif operation.operation_type == "ADJUSTMENT":
                if quantity < 0:
                    await OperationsService._ensure_sufficient_balance(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        required_qty=abs(quantity),
                        error_message=(
                            f"insufficient stock for ADJUSTMENT: inventory_subject={line.inventory_subject_id}, "
                            f"site={operation.site_id}, delta={line.qty}"
                        ),
                    )
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    quantity_delta=quantity,
                )
            elif operation.operation_type == "MOVE":
                if operation.source_site_id is None or operation.destination_site_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="MOVE operation requires source_site_id and destination_site_id",
                    )

                await OperationsService._ensure_sufficient_balance(
                    uow,
                    site_id=operation.source_site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    required_qty=quantity,
                    error_message=(
                        f"insufficient stock for MOVE: inventory_subject={line.inventory_subject_id}, "
                        f"source_site={operation.source_site_id}, required={line.qty}"
                    ),
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.source_site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    quantity_delta=-quantity,
                )
                if operation.acceptance_required:
                    await OperationsService._upsert_pending(
                        uow,
                        operation_id=operation.id,
                        operation_line_id=line.id,
                        destination_site_id=operation.destination_site_id,
                        source_site_id=operation.source_site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=quantity,
                        error_context="MOVE submit",
                    )
                else:
                    await uow.balances.update_balance_quantity(
                        site_id=operation.destination_site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                    )
            elif operation.operation_type == "ISSUE":
                if operation.recipient_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="ISSUE requires recipient_id",
                    )
                await OperationsService._ensure_sufficient_balance(
                    uow,
                    site_id=operation.site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    required_qty=quantity,
                    error_message=(
                        f"insufficient stock for ISSUE: inventory_subject={line.inventory_subject_id}, "
                        f"site={operation.site_id}, required={line.qty}"
                    ),
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    quantity_delta=-quantity,
                )
                await OperationsService._upsert_issued(
                    uow,
                    recipient_id=operation.recipient_id,
                    inventory_subject_id=line.inventory_subject_id,
                    qty_delta=quantity,
                    error_context="ISSUE submit",
                )
            elif operation.operation_type == "ISSUE_RETURN":
                if operation.recipient_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="ISSUE_RETURN requires recipient_id",
                    )
                await OperationsService._upsert_issued(
                    uow,
                    recipient_id=operation.recipient_id,
                    inventory_subject_id=line.inventory_subject_id,
                    qty_delta=-quantity,
                    error_context="ISSUE_RETURN submit",
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    quantity_delta=quantity,
                )

        submitted_operation = await uow.operations.submit_operation(
            operation_id=operation_id,
            submitted_by_user_id=user_id,
        )

        # Автоматически создаём документ для операции (если включено в конфиге)
        # Пока создаём только для определённых типов операций
        document_created = None
        try:
            # Определяем тип документа на основе типа операции
            document_type_map = {
                "RECEIVE": "acceptance_certificate",
                "MOVE": "waybill",
                "ISSUE": "waybill",
                "ISSUE_RETURN": "waybill",
                "EXPENSE": "act",
                "WRITE_OFF": "act",
                "ADJUSTMENT": "act",
            }

            document_type = document_type_map.get(submitted_operation.operation_type)
            if document_type:
                # Генерируем документ с автоматической финализацией
                result = await DocumentService.generate_from_operation(
                    uow=uow,
                    operation_id=operation_id,
                    document_type=document_type,
                    auto_finalize=True,
                    created_by_user_id=user_id,
                )
                document_created = result["document"]
                logger.info(
                    "Auto-generated document id=%s for operation id=%s type=%s",
                    document_created.id,
                    operation_id,
                    submitted_operation.operation_type,
                )
        except Exception as e:
            # Логируем ошибку, но не прерываем выполнение
            logger.warning(
                "Failed to auto-generate document for operation id=%s: %s",
                operation_id,
                str(e),
            )

        response = {"operation": submitted_operation}
        if document_created:
            response["document"] = document_created

        return response

    @staticmethod
    async def accept_operation_lines(
        uow: UnitOfWork,
        *,
        operation_id,
        user_id: UUID,
        line_updates: list[OperationAcceptLinePayload],
    ) -> dict[str, object]:
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_submitted_for_acceptance(operation)
        OperationsWorkflowPolicy.require_acceptance_required(operation)
        OperationsWorkflowPolicy.require_acceptance_not_resolved(operation)

        destination_site_id = OperationsService._destination_site_for_acceptance(operation)
        source_site_id = operation.source_site_id if operation.operation_type == "MOVE" else None
        lines_by_id = {int(line.id): line for line in operation.lines}

        for update in line_updates:
            accepted_delta = Decimal(update.accepted_qty)
            lost_delta = Decimal(update.lost_qty)
            if accepted_delta == 0 and lost_delta == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="accepted_qty and lost_qty cannot both be zero",
                )

            line = lines_by_id.get(update.line_id)
            if line is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"operation line {update.line_id} not found",
                )
            await OperationsService._ensure_line_inventory_subject(uow, line)

            remaining = Decimal(line.qty) - Decimal(line.accepted_qty) - Decimal(line.lost_qty)
            if accepted_delta + lost_delta > remaining:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"acceptance quantity exceeds remaining for line {line.id}: "
                        f"remaining={remaining}, requested={accepted_delta + lost_delta}"
                    ),
                )

            if accepted_delta > 0:
                await OperationsService._upsert_pending(
                    uow,
                    operation_id=operation.id,
                    operation_line_id=line.id,
                    destination_site_id=destination_site_id,
                    source_site_id=source_site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    qty_delta=-accepted_delta,
                    error_context="accept line",
                )
                await uow.balances.update_balance_quantity(
                    site_id=destination_site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    quantity_delta=accepted_delta,
                )
                await uow.operations.update_operation_line_progress(
                    operation_line_id=line.id,
                    accepted_delta=accepted_delta,
                    lost_delta=Decimal("0"),
                )
                await uow.asset_registers.create_acceptance_action(
                    operation_id=operation.id,
                    operation_line_id=line.id,
                    action_type="accept",
                    qty=accepted_delta,
                    performed_by_user_id=user_id,
                    notes=update.note,
                )

            if lost_delta > 0:
                await OperationsService._upsert_pending(
                    uow,
                    operation_id=operation.id,
                    operation_line_id=line.id,
                    destination_site_id=destination_site_id,
                    source_site_id=source_site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    qty_delta=-lost_delta,
                    error_context="mark lost",
                )
                await OperationsService._upsert_lost(
                    uow,
                    operation_id=operation.id,
                    operation_line_id=line.id,
                    site_id=destination_site_id,
                    source_site_id=source_site_id,
                    inventory_subject_id=line.inventory_subject_id,
                    qty_delta=lost_delta,
                    error_context="mark lost",
                )
                await uow.operations.update_operation_line_progress(
                    operation_line_id=line.id,
                    accepted_delta=Decimal("0"),
                    lost_delta=lost_delta,
                )
                await uow.asset_registers.create_acceptance_action(
                    operation_id=operation.id,
                    operation_line_id=line.id,
                    action_type="mark_lost",
                    qty=lost_delta,
                    performed_by_user_id=user_id,
                    notes=update.note,
                )

        refreshed = await uow.operations.get_operation_by_id(operation_id)
        assert refreshed is not None
        unresolved = [
            line
            for line in refreshed.lines
            if Decimal(line.qty) - Decimal(line.accepted_qty) - Decimal(line.lost_qty) > 0
        ]
        next_state = "resolved" if not unresolved else "in_progress"
        await uow.operations.set_operation_acceptance_state(
            operation_id=operation_id,
            acceptance_state=next_state,
            resolved_by_user_id=user_id if next_state == "resolved" else None,
        )
        return {"operation": await uow.operations.get_operation_by_id(operation_id)}

    @staticmethod
    async def resolve_lost_asset(
        uow: UnitOfWork,
        *,
        operation_line_id: int,
        action: str,
        qty: Decimal,
        user_id: UUID,
        note: str | None,
        responsible_recipient_id: int | None,
    ) -> dict[str, object]:
        lost_row = await uow.asset_registers.get_lost_row_for_update(operation_line_id)
        if lost_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lost asset row not found")
        if Decimal(lost_row.qty) < qty:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"insufficient lost quantity: available={lost_row.qty}, requested={qty}",
            )

        operation = await uow.operations.get_operation_by_id(lost_row.operation_id)
        if operation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")

        if action == "found_to_destination":
            destination_site_id = OperationsService._destination_site_for_acceptance(operation)
            await uow.balances.update_balance_quantity(
                site_id=destination_site_id,
                inventory_subject_id=lost_row.inventory_subject_id,
                quantity_delta=qty,
            )
        elif action == "return_to_source":
            if lost_row.source_site_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="source_site_id is required for return_to_source",
                )
            await uow.balances.update_balance_quantity(
                site_id=lost_row.source_site_id,
                inventory_subject_id=lost_row.inventory_subject_id,
                quantity_delta=qty,
            )
        elif action == "write_off":
            # Inventory is removed from temporary lost register.
            # Responsibility is linked via responsible_recipient_id in action log.
            pass
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported action")

        await OperationsService._upsert_lost(
            uow,
            operation_id=lost_row.operation_id,
            operation_line_id=lost_row.operation_line_id,
            site_id=lost_row.site_id,
            source_site_id=lost_row.source_site_id,
            inventory_subject_id=lost_row.inventory_subject_id,
            qty_delta=-qty,
            error_context=action,
        )
        await uow.asset_registers.create_acceptance_action(
            operation_id=lost_row.operation_id,
            operation_line_id=lost_row.operation_line_id,
            action_type=action,
            qty=qty,
            performed_by_user_id=user_id,
            recipient_id=responsible_recipient_id,
            notes=note,
        )
        return {"status": "ok"}

    @staticmethod
    async def cancel_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
        reason: str | None = None,
    ) -> dict[str, object]:
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_not_cancelled_for_cancel(operation)

        if operation.status == "submitted":
            for line in operation.lines:
                await OperationsService._ensure_line_inventory_subject(uow, line)
                quantity = Decimal(line.qty)
                accepted_qty = Decimal(line.accepted_qty)
                lost_qty = Decimal(line.lost_qty)
                pending_qty = quantity - accepted_qty - lost_qty

                if operation.operation_type == "RECEIVE":
                    if operation.acceptance_required:
                        if pending_qty > 0:
                            await OperationsService._upsert_pending(
                                uow,
                                operation_id=operation.id,
                                operation_line_id=line.id,
                                destination_site_id=operation.site_id,
                                source_site_id=None,
                                inventory_subject_id=line.inventory_subject_id,
                                qty_delta=-pending_qty,
                                error_context="RECEIVE rollback pending",
                            )
                        if accepted_qty > 0:
                            await OperationsService._apply_balance_delta(
                                uow,
                                site_id=operation.site_id,
                                inventory_subject_id=line.inventory_subject_id,
                                quantity_delta=-accepted_qty,
                                error_context="RECEIVE rollback accepted",
                            )
                        if lost_qty > 0:
                            await OperationsService._upsert_lost(
                                uow,
                                operation_id=operation.id,
                                operation_line_id=line.id,
                                site_id=operation.site_id,
                                source_site_id=None,
                                inventory_subject_id=line.inventory_subject_id,
                                qty_delta=-lost_qty,
                                error_context="RECEIVE rollback lost",
                            )
                    else:
                        await OperationsService._apply_balance_delta(
                            uow,
                            site_id=operation.site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            quantity_delta=-quantity,
                            error_context="RECEIVE rollback",
                        )
                elif operation.operation_type in DECREMENT_OPERATION_TYPES:
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                        error_context=f"{operation.operation_type} rollback",
                    )
                elif operation.operation_type == "ADJUSTMENT":
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=-quantity,
                        error_context="ADJUSTMENT rollback",
                    )
                elif operation.operation_type == "MOVE":
                    if operation.source_site_id is None or operation.destination_site_id is None:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="MOVE operation requires source_site_id and destination_site_id",
                        )
                    if operation.acceptance_required:
                        if pending_qty > 0:
                            await OperationsService._upsert_pending(
                                uow,
                                operation_id=operation.id,
                                operation_line_id=line.id,
                                destination_site_id=operation.destination_site_id,
                                source_site_id=operation.source_site_id,
                                inventory_subject_id=line.inventory_subject_id,
                                qty_delta=-pending_qty,
                                error_context="MOVE rollback pending",
                            )
                        if accepted_qty > 0:
                            await OperationsService._apply_balance_delta(
                                uow,
                                site_id=operation.destination_site_id,
                                inventory_subject_id=line.inventory_subject_id,
                                quantity_delta=-accepted_qty,
                                error_context="MOVE rollback accepted from destination",
                            )
                        if lost_qty > 0:
                            await OperationsService._upsert_lost(
                                uow,
                                operation_id=operation.id,
                                operation_line_id=line.id,
                                site_id=operation.destination_site_id,
                                source_site_id=operation.source_site_id,
                                inventory_subject_id=line.inventory_subject_id,
                                qty_delta=-lost_qty,
                                error_context="MOVE rollback lost",
                            )
                        await OperationsService._apply_balance_delta(
                            uow,
                            site_id=operation.source_site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            quantity_delta=quantity,
                            error_context="MOVE rollback to source",
                        )
                    else:
                        await OperationsService._ensure_sufficient_balance(
                            uow,
                            site_id=operation.destination_site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            required_qty=quantity,
                            error_message=(
                                f"insufficient stock for MOVE rollback from destination: "
                                f"inventory_subject={line.inventory_subject_id}, site={operation.destination_site_id}, required={line.qty}"
                            ),
                        )
                        await OperationsService._apply_balance_delta(
                            uow,
                            site_id=operation.source_site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            quantity_delta=quantity,
                            error_context="MOVE rollback to source",
                        )
                        await OperationsService._apply_balance_delta(
                            uow,
                            site_id=operation.destination_site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            quantity_delta=-quantity,
                            error_context="MOVE rollback from destination",
                        )
                elif operation.operation_type == "ISSUE":
                    if operation.recipient_id is None:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ISSUE requires recipient_id")
                    await OperationsService._upsert_issued(
                        uow,
                        recipient_id=operation.recipient_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=-quantity,
                        error_context="ISSUE rollback from recipient",
                    )
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                        error_context="ISSUE rollback to stock",
                    )
                elif operation.operation_type == "ISSUE_RETURN":
                    if operation.recipient_id is None:
                        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ISSUE_RETURN requires recipient_id")
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=-quantity,
                        error_context="ISSUE_RETURN rollback from stock",
                    )
                    await OperationsService._upsert_issued(
                        uow,
                        recipient_id=operation.recipient_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=quantity,
                        error_context="ISSUE_RETURN rollback to recipient",
                    )

        cancelled_operation = await uow.operations.cancel_operation(
            operation_id=operation_id,
            cancelled_by_user_id=user_id,
        )
        logger.info("cancelled operation=%s by user=%s reason=%s", operation_id, user_id, reason)
        return {"operation": cancelled_operation}
