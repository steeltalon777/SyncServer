from __future__ import annotations

import structlog
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.schemas.review_item import (
    ReviewItemConfirmRequest,
)
from app.services.audit_helper import record_audit_event
from app.services.operations_service import OperationsService
from app.services.uow import UnitOfWork
from fastapi import HTTPException, status

logger = structlog.get_logger()


class ReviewItemsService:
    """Service for managing catalog items that require review.

    These are permanent catalog items (Item.requires_review=True) that were
    fast-created from operations and need confirmation/fix by a responsible user.
    """

    @staticmethod
    async def confirm_review_item(
        uow: UnitOfWork,
        *,
        item_id: int,
        resolved_by_user_id: UUID,
        payload: ReviewItemConfirmRequest,
    ) -> dict:
        """Confirm a review-required item: validate required fields, clear requires_review.

        Steps:
        1. Load item and verify it requires review.
        2. Apply any field corrections from payload.
        3. Validate that required catalog fields are filled (name, category_id, unit_id).
        4. Clear requires_review, set review_status='confirmed', audit metadata.
        """
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
        if item.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="item is deleted",
            )
        if not item.requires_review:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="item does not require review",
            )
        if item.review_status not in (None, "needs_review"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"item review already resolved (status={item.review_status})",
            )

        # Apply field corrections from payload
        if payload.name is not None:
            item.name = payload.name
        if payload.sku is not None:
            item.sku = payload.sku
        if payload.category_id is not None:
            category = await uow.catalog.get_category_by_id(payload.category_id)
            if category is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
            item.category_id = payload.category_id
        if payload.unit_id is not None:
            unit = await uow.catalog.get_unit_by_id(payload.unit_id)
            if unit is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")
            item.unit_id = payload.unit_id
        if payload.description is not None:
            item.description = payload.description
        if payload.hashtags is not None:
            item.hashtags = payload.hashtags

        # Validate required fields
        if not item.name or not item.name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="item name is required for confirmation",
            )

        # Clear review state
        item.requires_review = False
        item.review_status = "confirmed"
        item.review_resolved_by_user_id = resolved_by_user_id
        item.review_resolved_at = datetime.now(UTC)

        await uow.session.flush()

        # TZ-AUDIT_BACKEND_FOUNDATION §8.3 — record a review_item.confirm
        # audit event so the chronicle distinguishes review confirmations
        # from regular item updates.
        await record_audit_event(
            uow,
            event_type="review_item.confirm",
            event_version=2,
            actor_user_id=resolved_by_user_id,
            entity_type="item",
            entity_id=str(item_id),
            summary=f"ТМЦ #{item_id} подтверждён после проверки",
            changes={
                "item_id": item_id,
                "resolution_type": "confirmed",
                "corrections": {
                    "name": payload.name is not None,
                    "sku": payload.sku is not None,
                    "category_id": payload.category_id is not None,
                    "unit_id": payload.unit_id is not None,
                },
            },
            outcome="success",
        )

        logger.info(
            "review_item_confirmed",
            item_id=item_id,
            user_id=str(resolved_by_user_id),
        )

        return {"item_id": item_id, "resolution_type": "confirmed"}

    @staticmethod
    async def merge_review_item(
        uow: UnitOfWork,
        *,
        item_id: int,
        target_item_id: int,
        resolved_by_user_id: UUID,
        resolution_note: str | None,
    ) -> dict:
        """Merge a review-required item into an existing catalog item.

        Uses the balance transfer logic from TemporaryItemsResolutionService
        to move balances from the review item to the target.
        """
        from app.services.temporary_items_resolution_service import (
            TemporaryItemsResolutionService,
        )

        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review item not found")
        if not item.requires_review:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="item does not require review",
            )
        if item.review_status not in (None, "needs_review"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"item review already resolved (status={item.review_status})",
            )

        target_item = await uow.catalog.get_item_by_id(target_item_id)
        if target_item is None or target_item.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target item not found")
        if target_item_id == item_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target item must differ from source item",
            )
        if not target_item.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target item not found")

        # Get inventory subjects
        source_subject = await uow.inventory_subjects.get_by_item_id(item_id)
        if source_subject is None or source_subject.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="review item has no active inventory subject",
            )

        target_subject = await uow.inventory_subjects.get_or_create_for_item(
            item_id=target_item_id,
        )

        # ── Audit: parent event first so transfers can attach ─────
        parent_event = await record_audit_event(
            uow,
            event_type="review_item.merge",
            event_version=2,
            actor_user_id=resolved_by_user_id,
            entity_type="item",
            entity_id=str(target_item_id),
            summary=f"Review item #{item_id} слит с ТМЦ #{target_item_id}",
            changes={
                "item_id": item_id,
                "target_item_id": target_item_id,
                "resolution_note": resolution_note,
            },
            outcome="success",
        )
        saved_parent = getattr(uow, "audit_parent_event_id", None)
        saved_caused = getattr(uow, "audit_caused_by_event_id", None)
        uow.audit_parent_event_id = parent_event.event_id
        uow.audit_caused_by_event_id = int(parent_event.id)
        generated_ids: list = []
        try:
            # Transfer balances via service operations
            source_balances = await uow.balances.get_all_by_inventory_subject(int(source_subject.id))
            for balance_row in source_balances:
                qty = balance_row.qty
                if qty == 0:
                    continue

                qty_dec = Decimal(str(qty))
                site_id = int(balance_row.site_id)
                note = (
                    f"[review merge] item={item_id} -> item={target_item_id}: "
                    f"balance transfer site={site_id} qty={qty}"
                )

                uow.audit_effect_type_override = "review_write_off"
                write_off = await uow.operations.create_operation(
                    site_id=site_id,
                    operation_type="ADJUSTMENT",
                    created_by_user_id=resolved_by_user_id,
                    notes=note,
                    effective_at=datetime.now(UTC),
                    origin="system",
                    system_reason="review_merge",
                    initiated_by_user_id=resolved_by_user_id,
                )
                await uow.operations.create_operation_line(
                    operation_id=write_off.id,
                    line_number=1,
                    inventory_subject_id=int(source_subject.id),
                    item_id=item_id,
                    qty=-qty_dec,
                    comment=note,
                )
                await OperationsService.submit_operation(
                    uow=uow,
                    operation_id=write_off.id,
                    user_id=resolved_by_user_id,
                )
                generated_ids.append(write_off.id)

                uow.audit_effect_type_override = "review_receipt"
                receipt_op = await uow.operations.create_operation(
                    site_id=site_id,
                    operation_type="ADJUSTMENT",
                    created_by_user_id=resolved_by_user_id,
                    notes=note,
                    effective_at=datetime.now(UTC),
                    origin="system",
                    system_reason="review_merge",
                    initiated_by_user_id=resolved_by_user_id,
                )
                await uow.operations.create_operation_line(
                    operation_id=receipt_op.id,
                    line_number=1,
                    inventory_subject_id=int(target_subject.id),
                    item_id=target_item_id,
                    qty=qty_dec,
                    comment=note,
                )
                await OperationsService.submit_operation(
                    uow=uow,
                    operation_id=receipt_op.id,
                    user_id=resolved_by_user_id,
                )
                generated_ids.append(receipt_op.id)
        finally:
            uow.audit_parent_event_id = saved_parent
            uow.audit_caused_by_event_id = saved_caused
            uow.audit_effect_type_override = None

        # Archive source inventory subject
        await uow.inventory_subjects.archive(int(source_subject.id))

        # Deactivate source item
        item.is_active = False

        # Mark review as merged
        item.requires_review = False
        item.review_status = "merged"
        item.review_resolved_by_user_id = resolved_by_user_id
        item.review_resolved_at = datetime.now(UTC)
        item.review_note = resolution_note or f"Merged into item {target_item_id}"

        await uow.session.flush()

        # Resource links for the parent merge event
        await uow.audit_events.insert_resource(
            audit_event_id=int(parent_event.id),
            resource_type="item",
            resource_id=str(item_id),
            relation="merge_source",
        )
        await uow.audit_events.insert_resource(
            audit_event_id=int(parent_event.id),
            resource_type="item",
            resource_id=str(target_item_id),
            relation="merge_target",
        )
        for op_id in generated_ids:
            await uow.audit_events.insert_resource(
                audit_event_id=int(parent_event.id),
                resource_type="operation",
                resource_id=str(op_id),
                relation="generated",
            )

        logger.info(
            "review_item_merged",
            item_id=item_id,
            target_item_id=target_item_id,
            user_id=str(resolved_by_user_id),
        )

        return {"resolved_item_id": target_item_id, "resolution_type": "merge"}

    @staticmethod
    async def delete_review_item(
        uow: UnitOfWork,
        *,
        item_id: int,
        resolved_by_user_id: UUID,
        resolution_note: str | None,
    ) -> dict:
        """Delete an unused review-required item.

        Only allowed when:
        - Item requires review and is not yet resolved.
        - No non-zero balances.
        - No active registers.
        """
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review item not found")
        if not item.requires_review:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="item does not require review",
            )
        if item.review_status not in (None, "needs_review"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"item review already resolved (status={item.review_status})",
            )

        # Check inventory subject and balances
        subject = await uow.inventory_subjects.get_by_item_id(item_id)
        if subject is not None:
            # Check active registers
            has_active = await uow.asset_registers.has_active_registers(int(subject.id))
            if has_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="review item has active pending/lost/issued registers",
                )

            # Check balances
            balances = await uow.balances.get_all_by_inventory_subject(int(subject.id))
            for br in balances:
                if br.qty != 0:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="review item has non-zero balances; cannot delete",
                    )

            # Archive inventory subject
            await uow.inventory_subjects.archive(int(subject.id))

        # Soft-delete item
        item.deleted_at = datetime.now(UTC)
        item.deleted_by_user_id = resolved_by_user_id
        item.is_active = False
        item.review_status = "archived"
        item.review_resolved_by_user_id = resolved_by_user_id
        item.review_resolved_at = datetime.now(UTC)
        item.review_note = resolution_note or "Deleted by user"

        await uow.session.flush()

        logger.info(
            "review_item_deleted",
            item_id=item_id,
            user_id=str(resolved_by_user_id),
        )

        return {"resolution_type": "deleted"}
