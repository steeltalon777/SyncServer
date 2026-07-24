from __future__ import annotations

import structlog
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.models.operation import OperationRevisionLine
from app.services.audit_helper import record_audit_event
from app.services.uow import UnitOfWork
from fastapi import HTTPException, status

logger = structlog.get_logger()

V1_SUPPORTED_OPERATION_TYPES = {"RECEIVE"}
CORRECTION_KIND_UNCHANGED = "unchanged"
CORRECTION_KIND_METADATA_CHANGED = "metadata_changed"
CORRECTION_KIND_QUANTITY_CHANGED = "quantity_changed_same_item"
CORRECTION_KIND_ITEM_REPLACED = "item_replaced"
CORRECTION_KIND_ADDED = "added"
CORRECTION_KIND_REMOVED = "removed"


class ComputedDiff:
    """Server-computed correction diff between baseline and target."""

    def __init__(self):
        self.unchanged: list[dict] = []
        self.metadata_changed: list[dict] = []
        self.quantity_changed: list[dict] = []
        self.item_replaced: list[dict] = []
        self.added: list[dict] = []
        self.removed: list[dict] = []

    @property
    def deltas(self) -> list[dict]:
        """Return all non-unchanged deltas for effect application."""
        result = []
        result.extend(self.quantity_changed)
        result.extend(self.item_replaced)
        result.extend(self.added)
        result.extend(self.removed)
        for md in self.metadata_changed:
            result.append({**md, "kind": CORRECTION_KIND_METADATA_CHANGED, "diff_qty": 0})
        return result

    @property
    def has_changes(self) -> bool:
        return bool(
            self.quantity_changed or self.item_replaced
            or self.added or self.removed or self.metadata_changed
        )


class CorrectionValidationError(Exception):
    def __init__(self, code: str, detail: dict):
        self.code = code
        self.detail = detail


class CorrectionsService:
    """Service for operation correction business logic.

    V1 scope: only RECEIVE without acceptance_required.
    """

    @staticmethod
    def _ensure_v1_scope(operation) -> None:
        if operation.operation_type not in V1_SUPPORTED_OPERATION_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "correction_operation_type_not_supported",
                    "operation_type": operation.operation_type,
                    "v1_scope": list(V1_SUPPORTED_OPERATION_TYPES),
                    "phase": "C1",
                },
            )
        if operation.acceptance_required:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "correction_acceptance_required_not_supported",
                    "message": "V1 does not support operations with acceptance_required=true",
                    "phase": "C2",
                },
            )

    @staticmethod
    async def begin_correction(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
    ) -> dict:
        """Begin a new correction draft by cloning the current baseline.

        INV-C7: Correction draft начинается со всех baseline lines (не пустой).
        INV-C19: Partial unique index: одна active draft на operation.
        """
        operation = await uow.operations.get_operation_by_id(operation_id)
        if operation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        if operation.status != "submitted":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="correction can only be started on submitted operations",
            )

        CorrectionsService._ensure_v1_scope(operation)

        # Check no active draft already exists
        existing = await uow.corrections.get_active_draft_for_operation(operation_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "concurrent_correction_exists",
                    "operation_id": str(operation_id),
                    "existing_correction_id": str(existing.id),
                },
            )

        # Get the current (latest) revision as baseline
        current_revision_id = operation.current_revision_id
        if current_revision_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="operation has no current revision; cannot begin correction",
            )

        baseline = await uow.operation_revisions.get_revision_by_id(current_revision_id)
        if baseline is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="baseline revision not found",
            )

        # Create correction
        correction = await uow.corrections.create_correction(
            operation_id=operation_id,
            base_operation_revision_id=current_revision_id,
            created_by_user_id=user_id,
        )

        # Clone all baseline lines into correction lines
        for bl in baseline.lines:
            await uow.corrections.create_correction_line(
                correction_id=correction.id,
                line_uuid=bl.line_uuid,
                line_number=bl.line_number,
                item_id=bl.item_id,
                qty=bl.qty,
                batch=bl.batch,
                comment=bl.comment,
            )

        # Reload to get lines
        result = await uow.corrections.get_correction_by_id(correction.id)
        return CorrectionsService._correction_to_dict(result)

    @staticmethod
    async def update_correction_put(
        uow: UnitOfWork,
        correction_id: UUID,
        expected_version: int,
        lines: list[dict],
    ) -> dict:
        """PUT full target state for a correction draft.

        INV-C9: PUT full target state. Отсутствие строки = REMOVED.
        """
        correction = await uow.corrections.get_correction_by_id(correction_id)
        if correction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction not found")
        if correction.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="can only update draft corrections",
            )

        if int(correction.version) != expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "correction_version_conflict",
                    "current_version": int(correction.version),
                },
            )

        # Validate no duplicate line_uuid in request
        seen_uuids = set()
        for line_data in lines:
            lu = line_data.get("line_uuid")
            if lu is not None:
                if lu in seen_uuids:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "code": "correction_duplicate_line_uuid",
                            "line_uuid": str(lu),
                        },
                    )
                seen_uuids.add(lu)

        # Validate no correction_kind in request (client must not send it)
        for line_data in lines:
            if "correction_kind" in line_data:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "correction_kind_not_allowed_in_request",
                        "message": "correction_kind is computed server-side, do not send",
                    },
                )

        # Build normalized lines: ensure line_uuid for added lines
        # If client passes line_uuid for a line not in baseline → 422
        baseline_lines = set()
        if hasattr(correction, 'base_operation_revision_id') and correction.base_operation_revision_id:
            baseline_rev = await uow.operation_revisions.get_revision_by_id(
                correction.base_operation_revision_id,
            )
            if baseline_rev:
                baseline_lines = {bl.line_uuid for bl in baseline_rev.lines}

        normalized_lines = []
        for line_data in lines:
            client_lu = line_data.get("line_uuid")
            if client_lu is not None and client_lu not in baseline_lines:
                # Client supplied a UUID for what looks like an added line → 422
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "correction_added_line_uuid_prohibited",
                        "message": "client must not supply line_uuid for added lines; server generates it",
                    },
                )
            if "line_uuid" not in line_data or line_data["line_uuid"] is None:
                line_data["line_uuid"] = uuid4()
            if line_data.get("item_id") is not None:
                await CorrectionsService._validate_new_item(uow, line_data["item_id"])
            normalized_lines.append(line_data)

        # Replace all lines
        new_lines = await uow.corrections.replace_all_lines(correction_id, normalized_lines)

        # Bump version on the correction
        await uow.corrections.update_correction_status(
            correction_id, "draft", expected_version=expected_version,
        )

        result = await uow.corrections.get_correction_by_id(correction_id)
        return CorrectionsService._correction_to_dict(result)

    @staticmethod
    async def add_correction_line(
        uow: UnitOfWork,
        correction_id: UUID,
        expected_version: int,
        line_data: dict,
    ) -> dict:
        """POST /corrections/{cid}/lines — add a new line."""
        correction = await uow.corrections.get_correction_by_id(correction_id)
        if correction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction not found")
        if correction.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="can only modify draft corrections")
        if int(correction.version) != expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "correction_version_conflict", "current_version": int(correction.version)},
            )

        line_uuid = uuid4()
        if line_data.get("item_id") is not None:
            await CorrectionsService._validate_new_item(uow, line_data["item_id"])

        await uow.corrections.create_correction_line(
            correction_id=correction_id,
            line_uuid=line_uuid,
            line_number=line_data["line_number"],
            item_id=line_data.get("item_id"),
            qty=line_data["qty"],
            batch=line_data.get("batch"),
            comment=line_data.get("comment"),
        )
        await uow.corrections.update_correction_status(correction_id, "draft", expected_version=expected_version)

        return {
            "line_uuid": str(line_uuid),
            "line_number": line_data["line_number"],
            "item_id": line_data.get("item_id"),
            "qty": line_data["qty"],
            "batch": line_data.get("batch"),
            "comment": line_data.get("comment"),
        }

    @staticmethod
    async def update_correction_line(
        uow: UnitOfWork,
        correction_id: UUID,
        line_uuid: UUID,
        expected_version: int,
        updates: dict,
    ) -> dict:
        """PATCH /corrections/{cid}/lines/{line_uuid} — update a line."""
        correction = await uow.corrections.get_correction_by_id(correction_id)
        if correction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction not found")
        if correction.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="can only modify draft corrections")
        if int(correction.version) != expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "correction_version_conflict", "current_version": int(correction.version)},
            )

        line = await uow.corrections.get_correction_line_by_uuid(correction_id, line_uuid)
        if line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction line not found")

        if "qty" in updates:
            line.qty = Decimal(str(updates["qty"]))
        if "item_id" in updates:
            await CorrectionsService._validate_new_item(uow, updates["item_id"])
            line.item_id = updates["item_id"]
        if "batch" in updates:
            line.batch = updates.get("batch")
        if "comment" in updates:
            line.comment = updates.get("comment")
        if "line_number" in updates:
            line.line_number = updates["line_number"]

        await uow.session.flush()
        await uow.corrections.update_correction_status(correction_id, "draft", expected_version=expected_version)

        result = await uow.corrections.get_correction_line_by_uuid(correction_id, line_uuid)
        return {
            "line_uuid": str(result.line_uuid),
            "line_number": result.line_number,
            "item_id": result.item_id,
            "qty": result.qty,
            "batch": result.batch,
            "comment": result.comment,
        }

    @staticmethod
    async def delete_correction_line(
        uow: UnitOfWork,
        correction_id: UUID,
        line_uuid: UUID,
        expected_version: int,
    ) -> None:
        """DELETE /corrections/{cid}/lines/{line_uuid} — remove a line."""
        correction = await uow.corrections.get_correction_by_id(correction_id)
        if correction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction not found")
        if correction.status != "draft":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="can only modify draft corrections")
        if int(correction.version) != expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "correction_version_conflict", "current_version": int(correction.version)},
            )

        deleted = await uow.corrections.delete_correction_line(correction_id, line_uuid)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction line not found")

        await uow.corrections.update_correction_status(correction_id, "draft", expected_version=expected_version)

    @staticmethod
    async def abandon_correction(
        uow: UnitOfWork,
        correction_id: UUID,
        expected_version: int,
        user_id: UUID,
    ) -> dict:
        """DELETE /corrections/{cid} — abandon a draft correction."""
        correction = await uow.corrections.get_correction_by_id(correction_id)
        if correction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction not found")
        if correction.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="only draft corrections can be abandoned",
            )
        if int(correction.version) != expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "correction_version_conflict", "current_version": int(correction.version)},
            )

        await uow.corrections.update_correction_status(correction_id, "abandoned", expected_version=expected_version)

        await record_audit_event(
            uow,
            event_type="operation.correction.abandoned",
            actor_user_id=user_id,
            entity_type="operation_correction",
            entity_id=str(correction_id),
            summary=f"Correction abandoned",
            changes={
                "correction_id": str(correction_id),
                "operation_id": str(correction.operation_id),
                "abandoned_by_user_id": str(user_id),
            },
        )

        return {"status": "abandoned", "correction_id": str(correction_id)}

    @staticmethod
    async def submit_correction(
        uow: UnitOfWork,
        correction_id: UUID,
        user_id: UUID,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> dict:
        """Submit a correction: compute diff, validate, apply effects atomically.

        Lock order (INV-C18):
        Correction → Operation → inventory_subject_id ASC → balances → Documents
        """
        # Idempotency check (MUST come before status check — INV-C13)
        if idempotency_key:
            existing_by_key = await uow.corrections.get_correction_by_idempotency_key(
                correction.operation_id, idempotency_key,
            )
            if existing_by_key is not None:
                if existing_by_key.id != correction_id:
                    # Different correction with same key
                    if existing_by_key.status == "applied":
                        return await CorrectionsService._build_submit_response(
                            uow, existing_by_key,
                        )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "code": "idempotency_key_conflict",
                            "existing_correction_id": str(existing_by_key.id),
                            "existing_status": existing_by_key.status,
                        },
                    )
                if existing_by_key.status == "applied":
                    # Same correction already applied — idempotent retry
                    return await CorrectionsService._build_submit_response(
                        uow, existing_by_key,
                    )

        # Lock 1: Correction
        correction = await uow.corrections.get_correction_by_id_for_update(correction_id)
        if correction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction not found")
        if correction.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"correction is already {correction.status}",
            )
        if int(correction.version) != expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "correction_version_conflict", "current_version": int(correction.version)},
            )

        # Lock 2: Operation
        operation = await uow.operations.get_operation_by_id_for_update(correction.operation_id)
        if operation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        if operation.status != "submitted":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="operation must be in submitted status for correction",
            )

        CorrectionsService._ensure_v1_scope(operation)

        # Check baseline is still current
        baseline_revision_id = operation.current_revision_id
        if baseline_revision_id != correction.base_operation_revision_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "correction_stale_base_revision",
                    "current_base_revision_id": str(baseline_revision_id),
                    "submitted_base_revision_id": str(correction.base_operation_revision_id),
                },
            )

        baseline = await uow.operation_revisions.get_revision_by_id(baseline_revision_id)
        if baseline is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="baseline revision not found")

        # Compute diff server-side
        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        # Validate each delta
        await CorrectionsService._validate_deltas(uow, operation, diff, baseline)

        # If no changes, nothing to do
        if not diff.has_changes:
            return await CorrectionsService._build_submit_response(
                uow, correction,
                extra={"computed_diff": CorrectionsService._diff_to_dict(diff)},
            )

        # Lock 3: inventory_subjects in ASC order (INV-C18)
        affected_subjects = await CorrectionsService._collect_affected_subjects(uow, diff)
        for subject_id in sorted(affected_subjects):
            await uow.inventory_subjects.get_for_update(subject_id)

        # Apply delta effects and capture for audit
        balance_effects_capture: list[dict] = []
        await CorrectionsService._apply_deltas(
            uow, operation, diff, balance_effects_capture,
        )

        # Create new revision (immutable)
        new_revision_number = baseline.revision_number + 1
        new_revision = await uow.operation_revisions.create_revision(
            operation_id=operation.id,
            revision_number=new_revision_number,
            created_by_user_id=user_id,
            created_by_correction_id=correction.id,
        )

        # Build final state lines from the correction target + unchanged baseline lines
        final_lines = await CorrectionsService._build_final_state_lines(
            uow, baseline, correction, diff,
        )

        # Insert revision lines
        for fl in final_lines:
            await uow.operation_revisions.create_revision_line(
                revision_id=new_revision.id,
                line_uuid=fl["line_uuid"],
                line_number=fl["line_number"],
                item_id=fl["item_id"],
                inventory_subject_id=fl.get("inventory_subject_id"),
                qty=fl["qty"],
                accepted_qty=fl.get("accepted_qty", Decimal("0")),
                lost_qty=fl.get("lost_qty", Decimal("0")),
                batch=fl.get("batch"),
                comment=fl.get("comment"),
                source_item_name=fl.get("source_item_name"),
                source_item_sku=fl.get("source_item_sku"),
                source_unit_name=fl.get("source_unit_name"),
                source_category_name=fl.get("source_category_name"),
                item_name_snapshot=fl.get("item_name_snapshot"),
                item_sku_snapshot=fl.get("item_sku_snapshot"),
                unit_name_snapshot=fl.get("unit_name_snapshot"),
                unit_symbol_snapshot=fl.get("unit_symbol_snapshot"),
                category_name_snapshot=fl.get("category_name_snapshot"),
            )

        # Rebuild OperationLine current projection (INV-C2)
        # Uses UPDATE for existing lines to avoid FK violations
        await uow.operations.rebuild_operation_lines(operation.id, final_lines)

        # Update operation.current_revision_id
        await uow.operations.update_operation_correction_fields(
            operation.id,
            current_revision_id=new_revision.id,
            expected_version=int(operation.version),
        )

        # Generate documents (INV-C16: from OperationRevisionLine, NOT OperationLine)
        from app.services.document_service import DocumentService, submit_document_type_for_operation
        old_active_docs = await CorrectionsService._get_active_documents(
            uow, correction.operation_id,
        )

        doc_type = submit_document_type_for_operation(operation.operation_type)
        new_documents = []
        if doc_type:
            result = await DocumentService.generate_from_operation(
                uow=uow,
                operation_id=operation.id,
                document_type=doc_type,
                auto_finalize=True,
                created_by_user_id=user_id,
                operation_revision_id=new_revision.id,
            )
            new_doc = result["document"]
            new_doc.operation_revision_id = new_revision.id
            await uow.session.flush()
            new_documents.append(new_doc)

            # Supersede old documents after new one is created
            superseded_docs = []
            for old_doc in old_active_docs:
                if old_doc.id != new_doc.id and old_doc.status not in ("void", "superseded"):
                    old_doc.status = "superseded"
                    superseded_docs.append(old_doc)
            await uow.session.flush()

            # Audit: document.revision_created
            for nd in new_documents:
                await record_audit_event(
                    uow,
                    event_type="document.revision_created",
                    actor_user_id=user_id,
                    site_id=operation.site_id,
                    entity_type="document",
                    entity_id=str(nd.id),
                    summary=f"Document revision created for operation correction",
                    changes={
                        "document_id": str(nd.id),
                        "document_type": nd.document_type,
                        "revision": nd.revision,
                        "operation_revision_id": str(new_revision.id),
                        "correction_id": str(correction.id),
                    },
                )
            # Audit: document.superseded
            for old_doc in superseded_docs:
                await record_audit_event(
                    uow,
                    event_type="document.superseded",
                    actor_user_id=user_id,
                    site_id=operation.site_id,
                    entity_type="document",
                    entity_id=str(old_doc.id),
                    summary=f"Document superseded by correction",
                    changes={
                        "old_document_id": str(old_doc.id),
                        "reason": "correction_applied",
                    },
                )

        # Write audit effects
        audit_event = await record_audit_event(
            uow,
            event_type="operation.correction.applied",
            actor_user_id=user_id,
            site_id=operation.site_id,
            entity_type="operation_correction",
            entity_id=str(correction.id),
            summary=f"Correction applied to operation #{getattr(operation, 'short_id', str(operation.id)[:8])}",
            changes={
                "correction_id": str(correction.id),
                "baseline_revision_id": str(baseline.id),
                "new_revision_id": str(new_revision.id),
                "new_revision_number": new_revision_number,
                "delta_count": len(diff.deltas),
                "added_count": len(diff.added),
                "removed_count": len(diff.removed),
                "changed_count": len(diff.quantity_changed) + len(diff.item_replaced),
                "unchanged_count": len(diff.unchanged),
            },
        )

        from app.services.operations_service import OperationsService
        await OperationsService._write_captured_effects(
            uow,
            capture=balance_effects_capture,
            audit_event_id=int(audit_event.id),
            operation_id=operation.id,
            is_system_generated=False,
        )

        # Update correction status
        correction.idempotency_key = idempotency_key or correction.idempotency_key
        await uow.corrections.update_correction_status(
            correction_id, "applied",
            expected_version=expected_version,
            submitted_by_user_id=user_id,
        )

        return await CorrectionsService._build_submit_response(
            uow, correction,
            extra={
                "operation": {
                    "id": str(operation.id),
                    "status": operation.status,
                    "current_revision_id": str(new_revision.id),
                    "current_revision_number": new_revision_number,
                    "correction_count": int(operation.correction_count),
                    "last_corrected_at": operation.last_corrected_at.isoformat() if operation.last_corrected_at else None,
                    "version": int(operation.version),
                },
                "new_operation_revision": {
                    "id": str(new_revision.id),
                    "revision_number": new_revision_number,
                    "lines": [
                        {
                            "line_uuid": str(fl["line_uuid"]),
                            "line_number": fl["line_number"],
                            "item_id": fl["item_id"],
                            "qty": float(fl["qty"]),
                        }
                        for fl in final_lines
                    ],
                },
                "new_documents": [
                    {
                        "id": str(d.id),
                        "document_type": d.document_type,
                        "revision": d.revision,
                        "status": d.status,
                        "operation_revision_id": str(d.operation_revision_id) if d.operation_revision_id else None,
                    }
                    for d in new_documents
                ],
                "computed_diff": CorrectionsService._diff_to_dict(diff),
            },
        )

    # ─── Private helpers ──────────────────────────────────────────────

    @staticmethod
    async def _compute_diff(
        uow: UnitOfWork,
        baseline: OperationRevisionLine | None,
        correction,
    ) -> ComputedDiff:
        """Compute server-side diff between baseline revision and correction target.

        INV-C8: Client не передаёт correction_kind (вычисляется сервером на submit).
        """
        diff = ComputedDiff()

        # Build baseline line map (by line_uuid)
        baseline_lines: dict[UUID, OperationRevisionLine] = {}
        if baseline is not None:
            for bl in baseline.lines:
                baseline_lines[bl.line_uuid] = bl

        # Build target line map
        target_lines: dict[UUID, dict] = {}
        for cl in correction.lines:
            target_lines[cl.line_uuid] = {
                "line_uuid": cl.line_uuid,
                "line_number": cl.line_number,
                "item_id": cl.item_id,
                "qty": cl.qty,
                "batch": cl.batch,
                "comment": cl.comment,
            }

        # Check each target line against baseline
        for lu, tl in target_lines.items():
            bl = baseline_lines.get(lu)

            if bl is None:
                # New line (added)
                diff.added.append({
                    "line_uuid": lu,
                    "line_number": tl["line_number"],
                    "item_id": tl["item_id"],
                    "qty": tl["qty"],
                    "batch": tl.get("batch"),
                    "comment": tl.get("comment"),
                    "kind": CORRECTION_KIND_ADDED,
                    "diff_qty": tl["qty"],
                })
                continue

            # Existing line — compare
            item_changed = (bl.item_id != tl["item_id"])
            qty_changed = (bl.qty != tl["qty"])
            batch_changed = (bl.batch != tl.get("batch"))
            comment_changed = (bl.comment != tl.get("comment"))
            metadata_changed = batch_changed or comment_changed

            if item_changed:
                diff.item_replaced.append({
                    "line_uuid": lu,
                    "old_item_id": bl.item_id,
                    "new_item_id": tl["item_id"],
                    "old_qty": bl.qty,
                    "new_qty": tl["qty"],
                    "diff_qty": tl["qty"] - bl.qty,
                    "kind": CORRECTION_KIND_ITEM_REPLACED,
                })
            elif qty_changed:
                diff_qty = tl["qty"] - bl.qty
                diff.quantity_changed.append({
                    "line_uuid": lu,
                    "item_id": bl.item_id,
                    "old_qty": bl.qty,
                    "new_qty": tl["qty"],
                    "diff_qty": diff_qty,
                    "kind": CORRECTION_KIND_QUANTITY_CHANGED,
                })
            elif metadata_changed:
                diff.metadata_changed.append({
                    "line_uuid": lu,
                    "old_batch": bl.batch,
                    "new_batch": tl.get("batch"),
                    "kind": CORRECTION_KIND_METADATA_CHANGED,
                })
            else:
                diff.unchanged.append({
                    "line_uuid": lu,
                    "kind": CORRECTION_KIND_UNCHANGED,
                })

        # Check baseline lines not in target (removed)
        baseline_uuids = set(baseline_lines.keys())
        target_uuids = set(target_lines.keys())
        removed_uuids = baseline_uuids - target_uuids
        for lu in removed_uuids:
            bl = baseline_lines[lu]
            diff.removed.append({
                "line_uuid": lu,
                "item_id": bl.item_id,
                "old_qty": bl.qty,
                "diff_qty": -bl.qty,
                "kind": CORRECTION_KIND_REMOVED,
            })

        return diff

    @staticmethod
    async def _validate_deltas(
        uow: UnitOfWork,
        operation,
        diff: ComputedDiff,
        baseline,
    ) -> None:
        """Validate each delta against the safe-delete matrix (V1).

        See TZ §6 Safe-delete policy matrix.
        """
        # Build baseline item map
        baseline_items: dict[UUID, int | None] = {}
        if baseline is not None:
            for bl in baseline.lines:
                baseline_items[bl.line_uuid] = bl.item_id

        # Validate new items for added lines
        for added in diff.added:
            if added["item_id"] is not None:
                await CorrectionsService._validate_new_item(uow, added["item_id"])

        # Validate removed lines: sufficient balance check
        for removed in diff.removed:
            lu = removed["line_uuid"]
            removed_qty = abs(removed["diff_qty"])
            if removed_qty > 0:
                await CorrectionsService._validate_sufficient_balance(
                    uow, operation, removed["item_id"], removed_qty, lu,
                )

        # Validate quantity reductions and item replacements
        for qc in diff.quantity_changed:
            if qc["diff_qty"] < 0:
                await CorrectionsService._validate_sufficient_balance(
                    uow, operation, qc["item_id"], abs(qc["diff_qty"]), qc["line_uuid"],
                )

        for ir in diff.item_replaced:
            # New item must be active
            if ir["new_item_id"] is not None:
                await CorrectionsService._validate_new_item(uow, ir["new_item_id"])
            # Old side reversal: sufficient balance of FULL old_qty (not just diff_qty)
            if ir["old_item_id"] is not None and ir["old_qty"] > 0:
                await CorrectionsService._validate_sufficient_balance(
                    uow, operation, ir["old_item_id"], ir["old_qty"], ir["line_uuid"],
                )

    @staticmethod
    async def _validate_new_item(uow: UnitOfWork, item_id: int) -> None:
        """Validate new Item for added/replaced: active, deleted_at IS NULL (INV-C14)."""
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "correction_new_item_invalid",
                    "item_id": item_id,
                    "reason": "not_found",
                },
            )
        if item.deleted_at is not None or not item.is_active:
            reason = "soft_deleted" if item.deleted_at is not None else "inactive"
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "correction_new_item_invalid",
                    "item_id": item_id,
                    "reason": reason,
                },
            )

    @staticmethod
    async def _validate_sufficient_balance(
        uow: UnitOfWork,
        operation,
        item_id: int | None,
        required_qty: Decimal,
        line_uuid: UUID,
    ) -> None:
        if item_id is None or required_qty <= 0:
            return

        # Get inventory_subject_id for the item
        subject = await uow.inventory_subjects.get_by_item_id(item_id)
        if subject is None:
            return

        balance = await uow.balances.get_for_update(
            site_id=operation.site_id,
            inventory_subject_id=subject.id,
        )
        current_qty = balance.qty if balance is not None else Decimal("0")
        if current_qty < required_qty:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "correction_insufficient_balance",
                    "delta": {
                        "line_uuid": str(line_uuid),
                        "kind": "removed" if required_qty > 0 else "quantity_changed",
                        "diff_qty": float(-required_qty),
                        "current_balance": float(current_qty),
                    },
                },
            )

    @staticmethod
    async def _collect_affected_subjects(
        uow: UnitOfWork, diff: ComputedDiff,
    ) -> set[int]:
        """Collect all inventory_subject_ids affected by the diff."""
        subjects: set[int] = set()
        item_ids: set[int] = set()
        for d in diff.deltas:
            item_id = d.get("item_id") or d.get("new_item_id") or d.get("old_item_id")
            if item_id is not None:
                item_ids.add(item_id)
        for item_id in item_ids:
            subject = await uow.inventory_subjects.get_by_item_id(item_id)
            if subject is not None:
                subjects.add(subject.id)
        return subjects

    @staticmethod
    async def _apply_deltas(
        uow: UnitOfWork,
        operation,
        diff: ComputedDiff,
        capture: list[dict],
    ) -> None:
        """Apply delta effects: balance changes for each delta.

        Only V1: RECEIVE without acceptance_required.
        Balance effects: receipt for positive deltas, nothing for negative
        (negative deltas are validated against sufficient balance earlier).
        """
        from app.services.operations_service import OperationsService

        for delta in diff.deltas:
            kind = delta["kind"]
            diff_qty = delta.get("diff_qty", 0)
            item_id = delta.get("item_id") or delta.get("new_item_id")
            line_uuid = delta["line_uuid"]

            if diff_qty == 0:
                continue

            # Resolve inventory_subject_id for the item
            inv_subject_id = None
            if item_id is not None:
                subject = await uow.inventory_subjects.get_by_item_id(item_id)
                if subject is not None:
                    inv_subject_id = subject.id

            if inv_subject_id is None:
                continue

            if kind == CORRECTION_KIND_ADDED or (
                kind == CORRECTION_KIND_QUANTITY_CHANGED and diff_qty > 0
            ):
                # Positive delta: receipt
                await OperationsService._capture_balance_change(
                    uow,
                    capture=capture,
                    site_id=operation.site_id,
                    inventory_subject_id=inv_subject_id,
                    quantity_delta=diff_qty,
                    effect_type="receipt",
                    note=f"correction delta ({kind})",
                )
            elif kind == CORRECTION_KIND_REMOVED or (
                kind == CORRECTION_KIND_QUANTITY_CHANGED and diff_qty < 0
            ):
                # Negative delta: expense
                await OperationsService._capture_balance_change(
                    uow,
                    capture=capture,
                    site_id=operation.site_id,
                    inventory_subject_id=inv_subject_id,
                    quantity_delta=diff_qty,
                    effect_type="expense",
                    note=f"correction delta ({kind})",
                )
            elif kind == CORRECTION_KIND_ITEM_REPLACED:
                old_item_id = delta.get("old_item_id")
                new_item_id = delta.get("new_item_id")
                old_qty = delta.get("old_qty", 0)
                new_qty = delta.get("new_qty", 0)

                # Reversal of old item
                if old_item_id is not None and old_qty > 0:
                    old_subject = await uow.inventory_subjects.get_by_item_id(old_item_id)
                    if old_subject is not None:
                        await OperationsService._capture_balance_change(
                            uow,
                            capture=capture,
                            site_id=operation.site_id,
                            inventory_subject_id=old_subject.id,
                            quantity_delta=-old_qty,
                            effect_type="expense",
                            note=f"correction item_replaced reversal",
                        )

                # Application of new item
                if new_item_id is not None and new_qty > 0:
                    new_subject = await uow.inventory_subjects.get_by_item_id(new_item_id)
                    if new_subject is not None:
                        await OperationsService._capture_balance_change(
                            uow,
                            capture=capture,
                            site_id=operation.site_id,
                            inventory_subject_id=new_subject.id,
                            quantity_delta=new_qty,
                            effect_type="receipt",
                            note=f"correction item_replaced apply",
                        )

    @staticmethod
    async def _build_final_state_lines(
        uow: UnitOfWork,
        baseline,
        correction,
        diff: ComputedDiff,
    ) -> list[dict]:
        """Build final state lines from baseline + correction diff.

        Returns the cumulative lines after correction.
        """
        # Start with baseline lines map
        baseline_map: dict[UUID, dict] = {}
        for bl in baseline.lines:
            baseline_map[bl.line_uuid] = {
                "line_uuid": bl.line_uuid,
                "line_number": bl.line_number,
                "item_id": bl.item_id,
                "inventory_subject_id": bl.inventory_subject_id,
                "qty": bl.qty,
                "accepted_qty": bl.accepted_qty,
                "lost_qty": bl.lost_qty,
                "batch": bl.batch,
                "comment": bl.comment,
                "source_item_name": bl.source_item_name,
                "source_item_sku": bl.source_item_sku,
                "source_unit_name": bl.source_unit_name,
                "source_category_name": bl.source_category_name,
                "item_name_snapshot": bl.item_name_snapshot,
                "item_sku_snapshot": bl.item_sku_snapshot,
                "unit_name_snapshot": bl.unit_name_snapshot,
                "unit_symbol_snapshot": bl.unit_symbol_snapshot,
                "category_name_snapshot": bl.category_name_snapshot,
            }

        removed_uuids = {r["line_uuid"] for r in diff.removed}

        # Apply target state from correction lines
        for cl in correction.lines:
            if cl.line_uuid in removed_uuids:
                continue
            if cl.line_uuid in baseline_map:
                # Update existing baseline line with correction target
                baseline_map[cl.line_uuid]["item_id"] = cl.item_id
                baseline_map[cl.line_uuid]["qty"] = cl.qty
                baseline_map[cl.line_uuid]["batch"] = cl.batch
                baseline_map[cl.line_uuid]["comment"] = cl.comment
                # Re-fetch snapshots for new items
                if cl.item_id is not None:
                    item = await uow.catalog.get_item_by_id(cl.item_id)
                    if item is not None:
                        baseline_map[cl.line_uuid]["item_name_snapshot"] = item.name
                        baseline_map[cl.line_uuid]["item_sku_snapshot"] = item.sku
            else:
                # New line from correction
                entry = {
                    "line_uuid": cl.line_uuid,
                    "line_number": cl.line_number,
                    "item_id": cl.item_id,
                    "inventory_subject_id": None,
                    "qty": cl.qty,
                    "accepted_qty": Decimal("0"),
                    "lost_qty": Decimal("0"),
                    "batch": cl.batch,
                    "comment": cl.comment,
                    "source_item_name": None,
                    "source_item_sku": None,
                    "source_unit_name": None,
                    "source_category_name": None,
                    "item_name_snapshot": None,
                    "item_sku_snapshot": None,
                    "unit_name_snapshot": None,
                    "unit_symbol_snapshot": None,
                    "category_name_snapshot": None,
                }
                if cl.item_id is not None:
                    item = await uow.catalog.get_item_by_id(cl.item_id)
                    if item is not None:
                        entry["item_name_snapshot"] = item.name
                        entry["item_sku_snapshot"] = item.sku
                        if item.unit:
                            entry["unit_name_snapshot"] = item.unit.name
                            entry["unit_symbol_snapshot"] = item.unit.symbol
                        if item.category:
                            entry["category_name_snapshot"] = item.category.name
                baseline_map[cl.line_uuid] = entry

        # Remove deleted lines
        for ru in removed_uuids:
            baseline_map.pop(ru, None)

        # Return sorted by line_number
        return sorted(baseline_map.values(), key=lambda x: x["line_number"])

    @staticmethod
    async def _get_active_documents(
        uow: UnitOfWork,
        operation_id: UUID,
    ):
        """Get active (non-void, non-superseded) documents for an operation."""
        docs = await uow.documents.get_documents_by_operation(operation_id)
        return [d for d in docs if d.status not in ("void", "superseded")]

    @staticmethod
    def _diff_to_dict(diff: ComputedDiff) -> dict:
        return {
            "unchanged": [{"line_uuid": str(d["line_uuid"]), "kind": CORRECTION_KIND_UNCHANGED} for d in diff.unchanged],
            "metadata_changed": [dict(d, line_uuid=str(d["line_uuid"])) for d in diff.metadata_changed],
            "quantity_changed": [dict(d, line_uuid=str(d["line_uuid"])) for d in diff.quantity_changed],
            "item_replaced": [dict(d, line_uuid=str(d["line_uuid"])) for d in diff.item_replaced],
            "added": [dict(d, line_uuid=str(d["line_uuid"])) for d in diff.added],
            "removed": [dict(d, line_uuid=str(d["line_uuid"])) for d in diff.removed],
        }

    @staticmethod
    def _correction_to_dict(correction) -> dict:
        return {
            "id": str(correction.id),
            "operation_id": str(correction.operation_id),
            "status": correction.status,
            "base_operation_revision_id": str(correction.base_operation_revision_id),
            "version": int(correction.version),
            "idempotency_key": correction.idempotency_key,
            "created_by_user_id": str(correction.created_by_user_id),
            "created_at": correction.created_at.isoformat() if correction.created_at else None,
            "lines": [
                {
                    "line_uuid": str(l.line_uuid),
                    "line_number": l.line_number,
                    "item_id": l.item_id,
                    "qty": float(l.qty),
                    "batch": l.batch,
                    "comment": l.comment,
                }
                for l in correction.lines
            ],
        }

    @staticmethod
    async def _build_submit_response(
        uow: UnitOfWork,
        correction,
        extra: dict | None = None,
    ) -> dict:
        result = {
            "correction": {
                "id": str(correction.id),
                "status": correction.status,
                "version": int(correction.version),
                "applied_at": correction.applied_at.isoformat() if correction.applied_at else None,
            },
        }
        if extra:
            result.update(extra)
        return result
