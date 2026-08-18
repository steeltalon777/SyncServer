"""Operation domain service with strict server-side validation.

Submit flow uses the OperationSubmitError envelope. See ADR-0025
(`docs/adr/0025-operation-submit-domain-errors.md`).
"""

from __future__ import annotations

import hashlib
import json

import structlog
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE, UNCATEGORIZED_CATEGORY_NAME
from app.core.identity import Identity
from app.core.search_utils import normalize_for_storage
from app.models.audit_item_effect import AuditItemEffect
from app.models.category import Category
from app.models.item import Item
from app.models.operation import Operation
from app.schemas.asset_register import OperationAcceptLinePayload
from app.schemas.catalog import ItemsResolveRequest
from app.schemas.operation import (
    OperationCreate,
    OperationType,
    OperationUpdate,
    SourceDocumentOperationCreate,
)
from app.services.catalog_read_service import CatalogReadService
from app.services.document_service import DocumentService, draft_document_type_for_operation, submit_document_type_for_operation, _compute_operation_display_number
from app.services.audit_helper import record_audit_event
from app.services.operation_line_errors import OperationLinesInvalidError
from app.schemas.operation_line_error import OperationLineError
from app.services.operation_submit_errors import (
    InsufficientIssuedBalanceError,
    InsufficientStockError,
    IssuedStockDeficit,
    OperationInWrongStateError,
    OperationNotFoundError,
    RoleNotPermittedError,
    StaleVersionError,
    StockDeficit,
)
from app.services.operations_policy import OperationsPolicy
from app.services.operations_workflow_policy import OperationsWorkflowPolicy
from app.services.uow import UnitOfWork
from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

logger = structlog.get_logger()

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
    def _extract_user_message(exc: IntegrityError) -> str:
        return str(exc.orig) if exc.orig else str(exc)

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
    async def _batch_resolve_and_validate_lines(
        uow: UnitOfWork,
        lines: list,
        operation_id: UUID | None = None,
    ) -> dict[int, int]:
        """Batch resolve all persisted item_ids, canonicalize, detect duplicates.

        Returns mapping: requested_item_id -> canonical_item_id.
        Raises OperationLinesInvalidError if any line is invalid.
        Temporary lines are skipped (they have no item_id).
        """
        # Collect persisted item_ids with their line numbers
        line_map: dict[int, list[int]] = {}  # item_id -> [line_numbers]
        for line in lines:
            if line.item_id is not None and line.temporary_item is None:
                line_map.setdefault(line.item_id, []).append(line.line_number)

        if not line_map:
            return {}

        requested_ids = list(line_map.keys())

        # Batch resolve via CatalogReadService
        resolve_result = await CatalogReadService.resolve_items(
            uow, ItemsResolveRequest(item_ids=requested_ids)
        )

        errors: list[OperationLineError] = []
        canonical_map: dict[int, int] = {}  # requested_id -> canonical_id
        canonical_to_lines: dict[int, list[int]] = {}  # canonical_id -> [line_numbers]

        for resolved in resolve_result.items:
            line_numbers = line_map.get(resolved.requested_id, [])
            first_line = line_numbers[0] if line_numbers else 0

            if resolved.status == "missing":
                for ln in line_numbers:
                    errors.append(OperationLineError(
                        line_number=ln,
                        item_id=resolved.requested_id,
                        reason="item_not_found",
                    ))
                continue

            if resolved.status == "deleted":
                for ln in line_numbers:
                    errors.append(OperationLineError(
                        line_number=ln,
                        item_id=resolved.requested_id,
                        reason="deleted",
                    ))
                continue

            if resolved.status == "inactive":
                for ln in line_numbers:
                    errors.append(OperationLineError(
                        line_number=ln,
                        item_id=resolved.requested_id,
                        reason="inactive",
                    ))
                continue

            if resolved.status == "merged" and resolved.canonical_item_id is None:
                # Merged but canonical is unusable
                for ln in line_numbers:
                    errors.append(OperationLineError(
                        line_number=ln,
                        item_id=resolved.requested_id,
                        reason="inactive" if resolved.reason and "inactive" in resolved.reason else "item_not_found",
                    ))
                continue

            # Active or merged-to-canonical
            canonical_id = resolved.canonical_item_id
            if canonical_id is None:
                for ln in line_numbers:
                    errors.append(OperationLineError(
                        line_number=ln,
                        item_id=resolved.requested_id,
                        reason="item_not_found",
                    ))
                continue

            canonical_map[resolved.requested_id] = canonical_id

            # Track canonical duplicates
            for ln in line_numbers:
                if canonical_id in canonical_to_lines:
                    first = canonical_to_lines[canonical_id][0]
                    errors.append(OperationLineError(
                        line_number=ln,
                        item_id=resolved.requested_id,
                        reason="duplicate_item",
                        first_line_number=first,
                    ))
                else:
                    canonical_to_lines.setdefault(canonical_id, []).append(ln)

        # Direct duplicate check (same requested_id in multiple lines)
        for item_id, line_numbers in line_map.items():
            if len(line_numbers) > 1:
                first = line_numbers[0]
                for ln in line_numbers[1:]:
                    # Only add if not already reported as canonical duplicate
                    already_reported = any(
                        e.line_number == ln and e.reason == "duplicate_item"
                        for e in errors
                    )
                    if not already_reported:
                        errors.append(OperationLineError(
                            line_number=ln,
                            item_id=item_id,
                            reason="duplicate_item",
                            first_line_number=first,
                        ))

        if errors:
            raise OperationLinesInvalidError(
                errors=errors,
                operation_id=operation_id,
            )

        return canonical_map

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
    async def _ensure_sufficient_issued_balance(
        uow: UnitOfWork,
        *,
        issue_object_id: int,
        inventory_subject_id: int,
        required_qty: Decimal,
        error_message: str,
    ) -> None:
        balance = await uow.asset_registers.get_issued_balance(
            issue_object_id=issue_object_id,
            inventory_subject_id=inventory_subject_id,
        )
        current_qty = balance.qty if balance is not None else Decimal("0")
        if current_qty < required_qty:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)

    # ─── Submit-boundary guards (ADR-0025 §4, TZ §7.1) ─────────────────────
    #
    # OperationsPolicy / OperationsWorkflowPolicy keep raising HTTPException
    # for non-submit flows. The submit service converts those HTTP-level
    # errors into the domain exceptions handled by the registered envelope
    # handler, so the actual submit flow never leaks a raw HTTPException
    # from these sources.

    @staticmethod
    def _require_draft_for_submit_boundary(operation) -> None:
        """State guard for submit: convert HTTPException into OperationInWrongStateError."""
        try:
            OperationsWorkflowPolicy.require_draft_for_submit(operation)
        except HTTPException as exc:
            raise OperationInWrongStateError(
                current_state=operation.status,
                allowed_states=["draft"],
                problem_class="operation-submit-rejected",
            ) from exc

    @staticmethod
    def _require_submit_permission(identity: Identity, operation) -> None:
        """Authorisation for submit: convert policy HTTPException(403) into RoleNotPermittedError.

        Called twice per submit — before taking the operation lock (TZ §7.1
        step 3) and again on the locked operation (step 7). Non-403 errors
        (e.g. MOVE without source/destination) are re-raised unchanged.
        """
        try:
            OperationsPolicy.require_operate_site(identity, operation.site_id)
        except (HTTPException, RoleNotPermittedError) as exc:
            if isinstance(exc, RoleNotPermittedError):
                raise RoleNotPermittedError(problem_class="operation-submit-rejected") from exc
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise RoleNotPermittedError(problem_class="operation-submit-rejected") from exc
            raise
        try:
            OperationsPolicy.require_operation_submit_permission(identity, operation)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise RoleNotPermittedError(problem_class="operation-submit-rejected") from exc
            raise
        if operation.operation_type == "MOVE":
            try:
                OperationsPolicy.require_move_access(identity, operation.source_site_id, operation.destination_site_id)
            except (HTTPException, RoleNotPermittedError) as exc:
                if isinstance(exc, RoleNotPermittedError):
                    raise RoleNotPermittedError(problem_class="operation-submit-rejected") from exc
                if exc.status_code == status.HTTP_403_FORBIDDEN:
                    raise RoleNotPermittedError(problem_class="operation-submit-rejected") from exc
                raise

    @staticmethod
    async def _lock_operation(uow: UnitOfWork, operation_id: UUID, operation) -> object:
        """Take the row lock on the operation (TZ §7.1 step 4).

        Falls back to the read-only snapshot when the UoW does not expose
        the lock method (unit-test mocks).
        """
        lock_method = getattr(uow.operations, "get_operation_by_id_for_update", None)
        if lock_method is None:
            return operation
        locked = await lock_method(operation_id)
        if locked is None:
            raise OperationNotFoundError(operation_id)
        return locked

    # ─── Two-phase aggregated balance check (ADR-0025 §5, TZ §5) ───────────

    @staticmethod
    async def _lookup_subject_display(
        uow: UnitOfWork,
        subject_id: int,
        subject_cache: dict[int, object],
        unit_cache: dict[int, object],
    ) -> tuple[int | None, str, int | None, str | None, str | None]:
        """Best-effort display lookup for a deficit group.

        Returns (item_id, item_name, unit_id, unit_name, unit_symbol).
        Falls back to "(неизвестно)" / None when lookups fail.
        """
        subject = subject_cache.get(subject_id)
        if subject is None:
            try:
                subject = await uow.inventory_subjects.get_by_id(subject_id)
            except Exception:
                subject = None
            subject_cache[subject_id] = subject

        item_id = getattr(subject, "item_id", None) if subject is not None else None
        item_name = "(неизвестно)"
        unit_id: int | None = None
        if item_id is not None:
            try:
                item = await uow.catalog.get_item_by_id(item_id)
            except Exception:
                item = None
            if item is not None:
                item_name = getattr(item, "name", None) or "(неизвестно)"
                unit_id = getattr(item, "unit_id", None)

        unit_name: str | None = None
        unit_symbol: str | None = None
        if unit_id is not None:
            unit = unit_cache.get(unit_id)
            if unit is None:
                try:
                    unit = await uow.catalog.get_unit_by_id(unit_id)
                except Exception:
                    unit = None
                unit_cache[unit_id] = unit
            if unit is not None:
                unit_name = getattr(unit, "name", None)
                unit_symbol = getattr(unit, "symbol", None)
        return item_id, item_name, unit_id, unit_name, unit_symbol

    @staticmethod
    async def _build_stock_deficit(
        uow: UnitOfWork,
        *,
        site_id: int,
        subject_id: int,
        lines: list,
        available: Decimal,
        site_name_cache: dict[int, str],
        subject_cache: dict[int, object],
        unit_cache: dict[int, object],
    ) -> StockDeficit:
        if site_id not in site_name_cache:
            try:
                site = await uow.sites.get_by_id(site_id)
            except Exception:
                site = None
            site_name_cache[site_id] = getattr(site, "name", None) or "(неизвестно)"
        item_id, item_name, unit_id, unit_name, unit_symbol = await OperationsService._lookup_subject_display(
            uow,
            subject_id,
            subject_cache,
            unit_cache,
        )
        return StockDeficit(
            stock_site_id=site_id,
            stock_site_name=site_name_cache[site_id],
            item_id=item_id,
            item_name=item_name,
            unit_id=unit_id,
            unit_name=unit_name,
            unit_symbol=unit_symbol,
            required_qty=sum((qty for _, qty in lines), Decimal("0")),
            available_qty=available,
            operation_line_ids=[int(line.id) for line, _ in lines],
        )

    @staticmethod
    async def _build_issued_stock_deficit(
        uow: UnitOfWork,
        *,
        issue_object_id: int,
        subject_id: int,
        lines: list,
        available: Decimal,
        subject_cache: dict[int, object],
        unit_cache: dict[int, object],
    ) -> IssuedStockDeficit:
        issue_object_name = "(неизвестно)"
        try:
            issue_object = await uow.issue_objects.get_by_id(issue_object_id)
        except Exception:
            issue_object = None
        if issue_object is not None:
            issue_object_name = getattr(issue_object, "display_name", None) or "(неизвестно)"
        item_id, item_name, unit_id, unit_name, unit_symbol = await OperationsService._lookup_subject_display(
            uow,
            subject_id,
            subject_cache,
            unit_cache,
        )
        return IssuedStockDeficit(
            issue_object_id=issue_object_id,
            issue_object_name=issue_object_name,
            item_id=item_id,
            item_name=item_name,
            unit_id=unit_id,
            unit_name=unit_name,
            unit_symbol=unit_symbol,
            required_qty=sum((qty for _, qty in lines), Decimal("0")),
            available_qty=available,
            operation_line_ids=[int(line.id) for line, _ in lines],
        )

    @staticmethod
    async def _check_submit_balance_sufficiency(uow: UnitOfWork, operation) -> None:
        """Two-phase aggregated balance check for submit (TZ §5, ADR-0025 §5).

        Phase 1 collects every balance-consuming line effect grouped by
        balance key — `(site_id, inventory_subject_id)` for warehouse and
        `(issue_object_id, inventory_subject_id)` for issued. RECEIVE and
        positive ADJUSTMENT lines do not consume balance and are skipped.

        Phase 2 locks each unique key exactly once in global order
        (`sorted(keys)`) and compares the summed required quantity against
        the available quantity read inside the lock. All deficient groups
        are collected into a single domain error, ordered by the line_number
        of the first line of each group.
        """
        warehouse_effects: dict[tuple[int, int], list] = {}
        issued_effects: dict[tuple[int, int], list] = {}
        op_type = operation.operation_type

        def _line_sort_key(line):
            line_number = getattr(line, "line_number", None)
            if line_number is not None:
                return (False, int(line_number))
            return (True, int(getattr(line, "id", 0)))

        # Phase 1: one pass over lines ordered by line_number.
        for line in sorted(operation.lines, key=_line_sort_key):
            if line.inventory_subject_id is None:
                continue
            subject_id = int(line.inventory_subject_id)
            quantity = Decimal(line.qty)
            if op_type == "RECEIVE":
                continue
            if op_type == "ADJUSTMENT":
                if quantity < 0:
                    warehouse_effects.setdefault((operation.site_id, subject_id), []).append((line, abs(quantity)))
                continue
            if op_type == "WRITE_OFF" and operation.issue_object_id is not None:
                issued_effects.setdefault((operation.issue_object_id, subject_id), []).append((line, quantity))
                continue
            if op_type == "MOVE":
                if operation.source_site_id is not None:
                    warehouse_effects.setdefault((operation.source_site_id, subject_id), []).append((line, quantity))
                continue
            if op_type == "ISSUE_RETURN":
                if operation.issue_object_id is not None:
                    issued_effects.setdefault((operation.issue_object_id, subject_id), []).append((line, quantity))
                continue
            # EXPENSE, WRITE_OFF (no issue object), ISSUE
            warehouse_effects.setdefault((operation.site_id, subject_id), []).append((line, quantity))

        deficits: list[tuple[int, StockDeficit]] = []
        issued_deficits: list[tuple[int, IssuedStockDeficit]] = []
        site_name_cache: dict[int, str] = {}
        subject_cache: dict[int, object] = {}
        unit_cache: dict[int, object] = {}

        # Phase 2: global key order → one lock per unique key, no deadlock.
        for key in sorted(warehouse_effects.keys()):
            site_id, subject_id = key
            balance = await uow.balances.get_for_update(site_id=site_id, inventory_subject_id=subject_id)
            available = Decimal(balance.qty) if balance is not None else Decimal("0")
            lines = warehouse_effects[key]
            sum_required = sum((qty for _, qty in lines), Decimal("0"))
            if sum_required > available:
                first_line_number = min(int(getattr(line, "line_number", 0)) for line, _ in lines)
                deficit = await OperationsService._build_stock_deficit(
                    uow,
                    site_id=site_id,
                    subject_id=subject_id,
                    lines=lines,
                    available=available,
                    site_name_cache=site_name_cache,
                    subject_cache=subject_cache,
                    unit_cache=unit_cache,
                )
                deficits.append((first_line_number, deficit))

        for key in sorted(issued_effects.keys()):
            issue_object_id, subject_id = key
            balance = await uow.asset_registers.get_issued_balance(
                issue_object_id=issue_object_id,
                inventory_subject_id=subject_id,
            )
            available = Decimal(balance.qty) if balance is not None else Decimal("0")
            lines = issued_effects[key]
            sum_required = sum((qty for _, qty in lines), Decimal("0"))
            if sum_required > available:
                first_line_number = min(int(getattr(line, "line_number", 0)) for line, _ in lines)
                issued_deficits.append((
                    first_line_number,
                    await OperationsService._build_issued_stock_deficit(
                        uow,
                        issue_object_id=issue_object_id,
                        subject_id=subject_id,
                        lines=lines,
                        available=available,
                        subject_cache=subject_cache,
                        unit_cache=unit_cache,
                    ),
                ))

        deficits.sort(key=lambda item: item[0])
        issued_deficits.sort(key=lambda item: item[0])

        if deficits or issued_deficits:
            if deficits:
                raise InsufficientStockError(
                    deficits=[deficit for _, deficit in deficits],
                    problem_class="operation-submit-rejected",
                )
            # Warehouse deficits have priority (TZ §5.1). Issued-only flows
            # (ISSUE_RETURN) land here; if both ever co-occur the warehouse
            # error is raised above and the issued deficits are dropped for
            # debug logging only.
            raise InsufficientIssuedBalanceError(
                deficits=[deficit for _, deficit in issued_deficits],
                problem_class="operation-submit-rejected",
            )

    @staticmethod
    async def _check_cancel_balance_sufficiency(uow: UnitOfWork, *, operation: Operation) -> None:
        """Two-phase aggregated balance check for cancel-flow rollback.

        Mirror of _check_submit_balance_sufficiency with inverse deltas:
        - RECEIVE rollback decreases warehouse at operation.site_id
        - EXPENSE/WRITE_OFF rollback increases warehouse at operation.site_id
        - ADJUSTMENT rollback inverts the original delta
        - MOVE rollback increases warehouse at source_site_id, decreases at destination_site_id
        - ISSUE/ISSUE_RETURN rollback: warehouse at operation.site_id AND issued at issue_object_id
        - WRITE_OFF with issue_object_id rollback: issued only

        Raises InsufficientStockError / InsufficientIssuedBalanceError with
        StockDeficit / IssuedStockDeficit (item.name, site.name,
        operation_line_ids[]). Called by cancel_operation BEFORE
        _apply_balance_delta / _upsert_issued / direct _ensure_sufficient_balance.
        """
        dict_warehouse: dict[tuple[int, int], list] = {}
        dict_issued: dict[tuple[int, int], list] = {}
        op_type = operation.operation_type

        def _line_sort_key(line):
            line_number = getattr(line, "line_number", None)
            if line_number is not None:
                return (False, int(line_number))
            return (True, int(getattr(line, "id", 0)))

        # Phase 1: one pass over lines ordered by line_number.
        for line in sorted(operation.lines, key=_line_sort_key):
            if line.inventory_subject_id is None:
                continue
            subject_id = int(line.inventory_subject_id)
            quantity = Decimal(line.qty)
            accepted_qty = Decimal(line.accepted_qty)
            if op_type == "RECEIVE":
                if operation.acceptance_required:
                    if accepted_qty > 0:
                        dict_warehouse.setdefault((operation.site_id, subject_id), []).append((line, accepted_qty))
                else:
                    dict_warehouse.setdefault((operation.site_id, subject_id), []).append((line, quantity))
                continue
            if op_type == "WRITE_OFF" and operation.issue_object_id is not None:
                # Rollback restores the issued register (`_upsert_issued` with
                # positive delta); a warehouse/issued deficit is impossible.
                continue
            if op_type in DECREMENT_OPERATION_TYPES:
                # Rollback increases the warehouse balance.
                continue
            if op_type == "ADJUSTMENT":
                dict_warehouse.setdefault((operation.site_id, subject_id), []).append((line, quantity))
                continue
            if op_type == "MOVE":
                if operation.acceptance_required:
                    if accepted_qty > 0:
                        dict_warehouse.setdefault((operation.destination_site_id, subject_id), []).append(
                            (line, accepted_qty)
                        )
                else:
                    dict_warehouse.setdefault((operation.destination_site_id, subject_id), []).append((line, quantity))
                continue
            if op_type == "ISSUE":
                if operation.issue_object_id is None:
                    # Invariant violation — caught later inside cancel_operation.
                    continue
                dict_issued.setdefault((operation.issue_object_id, subject_id), []).append((line, quantity))
                continue
            if op_type == "ISSUE_RETURN":
                dict_warehouse.setdefault((operation.site_id, subject_id), []).append((line, quantity))
                continue

        deficits: list[tuple[int, StockDeficit]] = []
        issued_deficits: list[tuple[int, IssuedStockDeficit]] = []
        site_name_cache: dict[int, str] = {}
        subject_cache: dict[int, object] = {}
        unit_cache: dict[int, object] = {}

        # Phase 2: global key order → one lock per unique key, no deadlock.
        for key in sorted(dict_warehouse.keys()):
            site_id, subject_id = key
            balance = await uow.balances.get_for_update(site_id=site_id, inventory_subject_id=subject_id)
            available = Decimal(balance.qty) if balance is not None else Decimal("0")
            lines = dict_warehouse[key]
            sum_required = sum((qty for _, qty in lines), Decimal("0"))
            if sum_required > available:
                first_line_number = min(int(getattr(line, "line_number", 0)) for line, _ in lines)
                deficit = await OperationsService._build_stock_deficit(
                    uow,
                    site_id=site_id,
                    subject_id=subject_id,
                    lines=lines,
                    available=available,
                    site_name_cache=site_name_cache,
                    subject_cache=subject_cache,
                    unit_cache=unit_cache,
                )
                deficits.append((first_line_number, deficit))

        for key in sorted(dict_issued.keys()):
            issue_object_id, subject_id = key
            balance = await uow.asset_registers.get_issued_balance(
                issue_object_id=issue_object_id,
                inventory_subject_id=subject_id,
            )
            available = Decimal(balance.qty) if balance is not None else Decimal("0")
            lines = dict_issued[key]
            sum_required = sum((qty for _, qty in lines), Decimal("0"))
            if sum_required > available:
                first_line_number = min(int(getattr(line, "line_number", 0)) for line, _ in lines)
                issued_deficits.append((
                    first_line_number,
                    await OperationsService._build_issued_stock_deficit(
                        uow,
                        issue_object_id=issue_object_id,
                        subject_id=subject_id,
                        lines=lines,
                        available=available,
                        subject_cache=subject_cache,
                        unit_cache=unit_cache,
                    ),
                ))

        deficits.sort(key=lambda item: item[0])
        issued_deficits.sort(key=lambda item: item[0])

        if deficits or issued_deficits:
            if deficits:
                raise InsufficientStockError(
                    deficits=[deficit for _, deficit in deficits],
                    problem_class="operation-cancel-rejected",
                )
            # Warehouse deficits have priority (TZ §5.1); issued-only flows
            # land here.
            raise InsufficientIssuedBalanceError(
                deficits=[deficit for _, deficit in issued_deficits],
                problem_class="operation-cancel-rejected",
            )

    @staticmethod
    async def _validate_operation_type(operation_type: OperationType) -> None:
        if operation_type not in SUPPORTED_OPERATION_TYPES:
            supported = ", ".join(sorted(SUPPORTED_OPERATION_TYPES))
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unsupported operation_type '{operation_type}', supported: {supported}",
            )

    @staticmethod
    async def _validate_inline_sku_unique(uow: UnitOfWork, lines: list[OperationLineCreate] | None) -> None:
        if lines is None:
            return
        for line in lines:
            if line.temporary_item is None:
                continue
            payload = line.temporary_item
            if not payload.sku:
                continue
            existing = await uow.catalog.get_item_by_sku(payload.sku)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"SKU «{payload.sku}» уже занят товаром «{existing.name}»",
                )

    @staticmethod
    async def _apply_balance_delta(
        uow: UnitOfWork,
        *,
        site_id: int,
        inventory_subject_id: int,
        quantity_delta: Decimal,
        error_context: str,
        capture: list[dict] | None = None,
        effect_type: str | None = None,
        note: str | None = None,
    ) -> None:
        """Apply a balance delta, optionally capturing it for audit_item_effects.

        Pass `capture` (a shared list) and `effect_type` to register the
        delta as an effect candidate. The caller is responsible for
        persisting captured effects via `_write_captured_effects` once it
        has an audit event id to reference.
        """
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

        balance_before_row = await uow.balances.get_for_update(
            site_id=site_id,
            inventory_subject_id=inventory_subject_id,
        )
        raw_qty_before = getattr(balance_before_row, "qty", None) if balance_before_row is not None else None
        if raw_qty_before is None:
            quantity_before = Decimal("0")
        else:
            try:
                quantity_before = Decimal(raw_qty_before)
            except Exception:
                # Defensive: tests may use SimpleNamespace/AsyncMock without
                # a real Decimal. Captured effect keeps the value as None
                # rather than blowing up the submit path.
                quantity_before = Decimal("0")
        if quantity_delta != 0:
            await uow.balances.update_balance_quantity(
                site_id=site_id,
                inventory_subject_id=inventory_subject_id,
                quantity_delta=quantity_delta,
            )
        quantity_after = quantity_before + Decimal(quantity_delta)

        if capture is not None:
            capture.append(
                {
                    "site_id": site_id,
                    "inventory_subject_id": int(inventory_subject_id) if inventory_subject_id is not None else None,
                    "quantity_before": quantity_before,
                    "quantity_delta": Decimal(quantity_delta),
                    "quantity_after": quantity_after,
                    "effect_type": effect_type or "adjustment",
                    "operation_line_id": None,
                    "note": note or error_context,
                }
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

    # ─── Balance-change capture used for audit_item_effects ────────────────

    @staticmethod
    def _effect_type_for_operation(operation_type: str) -> str:
        """Map an operation type to its canonical audit effect type."""
        return {
            "RECEIVE": "receipt",
            "EXPENSE": "expense",
            "WRITE_OFF": "write_off",
            "MOVE": "move_out",  # default; updated per-side for MOVE within capture
            "ADJUSTMENT": "adjustment",
            "ISSUE": "issue",
            "ISSUE_RETURN": "issue_return",
        }.get(operation_type, "adjustment")

    @staticmethod
    async def _capture_balance_change(
        uow: UnitOfWork,
        *,
        capture: list[dict],
        site_id: int | None,
        inventory_subject_id: int,
        quantity_delta: Decimal,
        effect_type: str,
        operation_line_id: int | None = None,
        note: str | None = None,
    ) -> None:
        """Apply a balance delta and capture the change as a candidate effect.

        Captured effects are later written to `audit_item_effects` by
        `_write_captured_effects` once an `operation.submit` or
        `operation.cancel` audit event has been emitted. This keeps the
        effect journal row-aligned with the journal event that caused it.

        The before/after quantities are computed in the same UoW transaction
        so they remain consistent with the actual balance update. We do
        the row lock and the update directly against the session — calling
        `BalancesRepo.update_balance_quantity` here would double-lock the
        row, which both breaks pre-existing unit tests that assert on
        mock call counts and adds a redundant round-trip.
        """
        from app.models.balance import Balance
        from datetime import datetime as _dt
        from datetime import UTC as _UTC

        balance_before_row = await uow.balances.get_for_update(
            site_id=site_id,
            inventory_subject_id=inventory_subject_id,
        )
        raw_qty_before = (
            getattr(balance_before_row, "qty", None)
            if balance_before_row is not None else None
        )
        try:
            quantity_before = Decimal(raw_qty_before) if raw_qty_before is not None else Decimal("0")
        except Exception:
            quantity_before = Decimal("0")

        if quantity_delta != 0:
            if balance_before_row is None:
                # Look up the canonical item_id for the inventory subject so
                # that the new balance row carries the denormalised FK.
                inventory_subject = await uow.inventory_subjects.get_by_id(inventory_subject_id)
                item_id = getattr(inventory_subject, "item_id", None) if inventory_subject is not None else None
                new_row = Balance(
                    site_id=site_id,
                    inventory_subject_id=inventory_subject_id,
                    item_id=item_id,
                    qty=quantity_before + Decimal(quantity_delta),
                )
                uow.session.add(new_row)
            else:
                balance_before_row.qty = quantity_before + Decimal(quantity_delta)
                try:
                    balance_before_row.updated_at = _dt.now(_UTC)
                except AttributeError:
                    pass
            session = getattr(uow, "session", None)
            if session is not None and hasattr(session, "flush"):
                await session.flush()

        quantity_after = quantity_before + Decimal(quantity_delta)
        capture.append(
            {
                "site_id": site_id,
                "inventory_subject_id": int(inventory_subject_id),
                "quantity_before": quantity_before,
                "quantity_delta": Decimal(quantity_delta),
                "quantity_after": quantity_after,
                "effect_type": effect_type,
                "operation_line_id": operation_line_id,
                "note": note,
            }
        )

    @staticmethod
    async def _write_captured_effects(
        uow: UnitOfWork,
        *,
        capture: list[dict],
        audit_event_id: int,
        operation_id: UUID,
        is_system_generated: bool,
        caused_by_event_id: int | None = None,
        effective_at: datetime | None = None,
    ) -> list[AuditItemEffect]:
        """Persist captured balance changes as audit_item_effects rows.

        Looks up the inventory subject for snapshot fields (item, name, sku,
        subject_type) and writes one effect row per captured change.
        Returns the inserted effects for tests/inspection.

        ADR-0028 §4.3 mandates fail-closed semantics: empty capture is a
        valid no-op, but a non-empty capture without a configured
        ``audit_events.insert_effect`` hook is an invariant violation and
        MUST abort the UoW. Unit test doubles that assert against a mock
        UoW without effect persistence must monkey-patch insert_effect.

        ADR-0028 §5 mandates an explicit cause timestamp: ``effective_at``
        is the business timestamp of the balance mutation, distinct from
        ``created_at`` (physical insert). Each captured row may carry its
        own ``cause_timestamp``/``effective_at`` key (acceptance/lost
        paths) or the caller passes a single ``effective_at`` for the whole
        batch (submit/cancel/correction). A missing timestamp falls back to
        ``datetime.now(UTC)`` as a safety net only; relying on the server
        default alone is forbidden by tests.
        """
        written: list[AuditItemEffect] = []
        if not capture:
            return written
        repo = getattr(uow, "audit_events", None)
        insert_effect = getattr(repo, "insert_effect", None) if repo is not None else None
        if insert_effect is None:
            raise RuntimeError(
                "audit_items_effects hook missing: non-empty capture requires "
                "uow.audit_events.insert_effect (ADR-0028 §4.3)"
            )

        # Snapshot enrichment is best-effort. Tests may mock the UoW and not
        # expose the inventory_subjects repo — in that case we simply skip
        # the subject lookup and emit effects with item_id=None.
        subject_cache: dict[int, object] = {}
        inventory_subjects_repo = getattr(uow, "inventory_subjects", None)
        if inventory_subjects_repo is not None:
            subject_ids = {c["inventory_subject_id"] for c in capture}
            for sid in subject_ids:
                try:
                    subject_cache[sid] = await inventory_subjects_repo.get_by_id(sid)
                except Exception:
                    subject_cache[sid] = None
        for c in capture:
            subject = subject_cache.get(c["inventory_subject_id"])
            item_id: int | None = None
            item_name: str | None = None
            item_sku: str | None = None
            subject_type: str | None = None
            if subject is not None:
                item_id = getattr(subject, "item_id", None)
                subject_type = getattr(subject, "subject_type", None)
                if subject_type == "catalog_item" and getattr(subject, "item", None) is not None:
                    item_name = getattr(subject.item, "name", None)
                    item_sku = getattr(subject.item, "sku", None)
                elif subject_type == "temporary_item" and getattr(subject, "temporary_item", None) is not None:
                    temp_item = subject.temporary_item
                    item_name = getattr(temp_item, "name", None)
                    item_sku = getattr(temp_item, "sku", None)
            # Per-row cause timestamp wins; batch-level effective_at is the
            # submit/cancel/correction producer contract. UTC now() is a
            # safety net, not the production contract (ADR-0028 §5).
            row_effective_at = (
                c.get("effective_at") or c.get("cause_timestamp") or effective_at
            )
            if row_effective_at is None:
                row_effective_at = datetime.now(UTC)
            effect = AuditItemEffect(
                audit_event_id=audit_event_id,
                operation_id=operation_id,
                inventory_subject_id=c["inventory_subject_id"],
                item_id=item_id,
                item_name_snapshot=item_name,
                item_sku_snapshot=item_sku,
                subject_type=subject_type,
                site_id=c["site_id"],
                quantity_before=c["quantity_before"],
                quantity_delta=c["quantity_delta"],
                quantity_after=c["quantity_after"],
                effect_type=c["effect_type"],
                is_system_generated=is_system_generated,
                caused_by_event_id=caused_by_event_id,
                effective_at=row_effective_at,
                note=c.get("note"),
            )
            written.append(await uow.audit_events.insert_effect(effect))
        return written

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
        issue_object_id: int,
        inventory_subject_id: int,
        qty_delta: Decimal,
        error_context: str,
    ) -> None:
        try:
            await uow.asset_registers.upsert_issued(
                issue_object_id=issue_object_id,
                inventory_subject_id=inventory_subject_id,
                qty_delta=qty_delta,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"issued asset quantity conflict for {error_context}",
            ) from exc

    @staticmethod
    async def _validate_operation_sites(uow: UnitOfWork, operation_data: BaseModel) -> None:
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
    def _compute_client_request_hash(payload: BaseModel) -> str:
        lines_normalized = []
        for line in payload.lines:
            line_dict = {
                "line_number": line.line_number,
                "item_id": line.item_id,
                "qty": str(line.qty) if line.qty is not None else None,
                "batch": line.batch.strip().lower() if line.batch else None,
                "comment": line.comment.strip().lower() if line.comment else None,
            }
            temporary_item = getattr(line, 'temporary_item', None)
            if temporary_item is not None:
                t = temporary_item
                line_dict["temporary_item"] = {
                    "client_key": t.client_key,
                    "name": t.name.strip().lower() if t.name else None,
                    "sku": t.sku.strip().lower() if t.sku else None,
                    "unit_id": t.unit_id,
                    "category_id": t.category_id,
                    "description": t.description.strip().lower() if t.description else None,
                    "hashtags": sorted([h.strip().lower() for h in t.hashtags]) if t.hashtags else None,
                }
            lines_normalized.append(line_dict)
        canonical = {
            "operation_type": payload.operation_type,
            "site_id": payload.site_id,
            "source_site_id": payload.source_site_id,
            "destination_site_id": payload.destination_site_id,
            "issue_object_id": payload.issue_object_id,
            "issue_object_name_snapshot": payload.issue_object_name_snapshot.strip().lower() if payload.issue_object_name_snapshot else None,
            "issued_to_user_id": str(payload.issued_to_user_id) if payload.issued_to_user_id else None,
            "issued_to_name": payload.issued_to_name.strip().lower() if payload.issued_to_name else None,
            "effective_at": payload.effective_at.isoformat() if payload.effective_at else None,
            "notes": payload.notes.strip().lower() if payload.notes else None,
            # Source-document fields for content comparison
            "source_ref": getattr(payload, 'source_ref', None),
            "source_document_type": getattr(payload, 'source_document_type', None),
            "lines": lines_normalized,
        }
        raw = json.dumps(canonical, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    async def _resolve_issue_object(
        uow: UnitOfWork,
        *,
        operation_type: OperationType,
        issue_object_id: int | None,
        issue_object_name_snapshot: str | None,
        issued_to_name: str | None,
    ) -> tuple[int | None, str | None]:
        if operation_type == "WRITE_OFF":
            if issue_object_id is not None:
                issue_object = await uow.issue_objects.get_by_id(issue_object_id)
                if issue_object is None or issue_object.merged_into_id is not None or not issue_object.is_active:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue_object not found")
                return issue_object.id, issue_object.display_name
            return None, None

        if operation_type in ISSUE_OPERATION_TYPES:
            if issue_object_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="ISSUE and ISSUE_RETURN require issue_object_id (free-text names not accepted)",
                )
            issue_object = await uow.issue_objects.get_by_id(issue_object_id)
            if issue_object is None or issue_object.merged_into_id is not None or not issue_object.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue_object not found")
            return issue_object.id, issue_object.display_name

        return issue_object_id, issue_object_name_snapshot

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

        client_request_hash = None
        if operation_data.client_request_id:
            client_request_hash = OperationsService._compute_client_request_hash(operation_data)

        # Idempotency: try insert, handle unique constraint collision at DB level
        if operation_data.client_request_id:
            existing = await uow.operations.get_by_client_request_id(
                created_by_user_id=user_id,
                client_request_id=operation_data.client_request_id,
            )
            if existing is not None:
                if existing.client_request_hash == client_request_hash:
                    return {"operation": existing}
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "idempotency_payload_conflict",
                        "message": (
                            f"Idempotency conflict: client_request_id "
                            f"'{operation_data.client_request_id}' "
                            f"was already used with a different payload"
                        ),
                    },
                )

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

        if has_temporary_items:
            if operation_data.operation_type != "RECEIVE":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Phase 1 supports inline temporary_item creation only for RECEIVE operations",
                )

        # Batch canonicalization: resolve all persisted item_ids, detect duplicates
        canonical_map = await OperationsService._batch_resolve_and_validate_lines(
            uow, operation_data.lines,
        )

        issue_object_id, issue_object_name_snapshot = await OperationsService._resolve_issue_object(
            uow,
            operation_type=operation_data.operation_type,
            issue_object_id=operation_data.issue_object_id,
            issue_object_name_snapshot=operation_data.issue_object_name_snapshot,
            issued_to_name=operation_data.issued_to_name,
        )

        # honour explicit acceptance_required from client, otherwise use type default
        fields_set = getattr(operation_data, "model_fields_set", set())
        if "acceptance_required" in fields_set:
            acceptance_required = operation_data.acceptance_required
        else:
            acceptance_required = operation_data.operation_type in ACCEPTANCE_REQUIRED_TYPES
        effective_at = operation_data.effective_at or datetime.now(UTC)
        display_number = _compute_operation_display_number(operation_data.site_id, effective_at)
        operation = await uow.operations.create_operation(
            site_id=operation_data.site_id,
            operation_type=operation_data.operation_type,
            effective_at=effective_at,
            source_site_id=operation_data.source_site_id,
            destination_site_id=operation_data.destination_site_id,
            issued_to_user_id=operation_data.issued_to_user_id,
            issued_to_name=issue_object_name_snapshot or operation_data.issued_to_name,
            issue_object_id=issue_object_id,
            issue_object_name_snapshot=issue_object_name_snapshot,
            acceptance_required=acceptance_required,
            created_by_user_id=user_id,
            notes=operation_data.notes,
            client_request_id=operation_data.client_request_id,
            client_request_hash=client_request_hash,
            display_number=display_number,
        )
        # TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING §10.4:
        # Новые manual операции через generic endpoint получают creation_source='manual' явно.
        # legacy-значение сохраняется только для исторических операций (backfill).
        operation.creation_source = "manual"

        # Для temporary строк нормализуем category_id и собираем snapshot-поля
        # без materialization сущностей. Реальные temporary/backing/inventory_subject
        # будут созданы только при submit.
        for line_data in operation_data.lines:
            if line_data.temporary_item is not None:
                payload = line_data.temporary_item
                # Нормализация category_id
                if payload.category_id is None:
                    uncategorized = await OperationsService._get_or_create_uncategorized_category(uow)
                    category_id_value = uncategorized.id
                    category_name = uncategorized.name
                else:
                    category_id_value = payload.category_id
                    category = await uow.catalog.get_category_by_id(category_id_value)
                    if category is None:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"category with id {category_id_value} not found",
                        )
                    category_name = category.name

                unit = await uow.catalog.get_unit_by_id(payload.unit_id)
                if unit is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unit with id {payload.unit_id} not found")

                # Сохраняем draft-temporary payload в строке операции
                draft_payload = {
                    "client_key": payload.client_key,
                    "name": payload.name.strip(),
                    "sku": payload.sku,
                    "unit_id": payload.unit_id,
                    "category_id": category_id_value,
                    "description": payload.description,
                    "hashtags": payload.hashtags,
                }

                await uow.operations.create_operation_line(
                    operation_id=operation.id,
                    line_number=line_data.line_number,
                    inventory_subject_id=None,  # Будет проставлено при submit
                    item_id=None,  # Будет проставлено при submit
                    qty=line_data.qty,
                    batch=line_data.batch,
                    comment=line_data.comment,
                    item_name_snapshot=payload.name.strip(),
                    item_sku_snapshot=payload.sku,
                    unit_name_snapshot=unit.name,
                    unit_symbol_snapshot=unit.symbol,
                    category_name_snapshot=category_name,
                    temporary_draft_payload=draft_payload,
                )
            else:
                # Каталожная строка — используем canonical ID из batch resolve
                line_item_id = canonical_map.get(line_data.item_id, line_data.item_id) if line_data.item_id else line_data.item_id
                if line_item_id is None:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="line item resolution failed")

                item = await uow.catalog.get_item_by_id(line_item_id)
                if not item:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"item with id {line_item_id} not found",
                    )

                unit = await uow.catalog.get_unit_by_id(item.unit_id)
                if not unit:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"unit with id {item.unit_id} not found",
                    )

                category = await uow.catalog.get_category_by_id(item.category_id)
                if not category:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"category with id {item.category_id} not found",
                    )

                line_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=line_item_id)

                await uow.operations.create_operation_line(
                    operation_id=operation.id,
                    line_number=line_data.line_number,
                    inventory_subject_id=line_subject.id,
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

        # TZ-V3.1I rev. 2 (I3.2, closes warning #8/#9): auto-generate draft
        # waybill для типов с waybill-документом. Вставка ПОСЛЕ
        # get_operation_by_id (см. warning #9) — иначе waybill получит нулевые
        # строки. Savepoint (begin_nested) — иначе DB-ошибка отравляет
        # транзакцию create_operation. created_by_user_id=user_id — audit
        # parity с submit_operation (warning #9).
        draft_doc_type = draft_document_type_for_operation(created_operation.operation_type)
        if draft_doc_type:
            try:
                async with uow.session.begin_nested():
                    await DocumentService.generate_from_operation(
                        uow=uow,
                        operation_id=created_operation.id,
                        document_type=draft_doc_type,
                        auto_finalize=False,
                        created_by_user_id=user_id,
                    )
            except Exception as exc:
                logger.warning(
                    "waybill_auto_create_failed",
                    operation_id=str(created_operation.id),
                    operation_type=created_operation.operation_type,
                    error=str(exc),
                )
                # savepoint уже откатил генерацию; create_operation продолжается

        await record_audit_event(
            uow,
            event_type="operation.create",
            actor_user_id=user_id,
            site_id=operation_data.site_id,
            entity_type="operation",
            entity_id=str(created_operation.id),
            summary=(
                f"Пользователь создал черновик операции №{created_operation.short_id} "
                f"({created_operation.operation_type})"
                if hasattr(created_operation, "short_id") and created_operation.short_id
                else f"Создан черновик операции ({created_operation.operation_type})"
            ),
        )
        return {"operation": created_operation}

    @staticmethod
    async def create_operation_from_source_document(
        uow: UnitOfWork,
        payload: SourceDocumentOperationCreate,
        user_id: UUID,
    ) -> dict[str, object]:
        """Создать draft операцию из source-document.

        Schema физически не допускает temporary_item.
        Каждая строка обязана иметь item_id.
        Endpoint самостоятельно проставляет creation_source='source_document'.

        Gate A1: базовая имплементация без canonical resolution
        (будет добавлена в Gate A2).
        """
        # Idempotency: проверка по source_ref + content hash
        if payload.source_ref:
            existing = await uow.operations.get_by_source_ref(
                source_ref=payload.source_ref,
                creation_source="source_document",
                created_by_user_id=user_id,
            )
            if existing is not None:
                # Всегда вычисляем hash для сравнения контента
                new_hash = OperationsService._compute_client_request_hash(payload)
                if existing.client_request_hash is None:
                    # Существующая операция без hash (legacy) — возвращаем как есть
                    return {"operation": existing}
                if existing.client_request_hash == new_hash:
                    # Тот же payload — idempotent response
                    return {"operation": existing}
                # Разный payload — 409 conflict
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "source_document_idempotency_conflict",
                        "message": (
                            f"Source document with source_ref "
                            f"'{payload.source_ref}' was already used with a different payload"
                        ),
                    },
                )

        # Валидация operation_type и sites
        await OperationsService._validate_operation_type(payload.operation_type)
        await OperationsService._validate_operation_sites(uow, payload)

        # Валидация item_id для каждой строки
        for line_data in payload.lines:
            item = await uow.catalog.get_item_by_id(line_data.item_id)
            if item is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "source_document_line_unresolvable",
                        "line_number": line_data.line_number,
                        "item_id": line_data.item_id,
                        "reason": "item_not_found",
                    },
                )
            if not item.is_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "source_document_line_inactive",
                        "line_number": line_data.line_number,
                        "item_id": line_data.item_id,
                        "canonical_item_id": item.id,
                    },
                )
            if item.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "source_document_line_deleted",
                        "line_number": line_data.line_number,
                        "item_id": line_data.item_id,
                        "canonical_item_id": item.id,
                    },
                )

        # Создание операции
        effective_at = payload.effective_at or datetime.now(UTC)
        display_number = _compute_operation_display_number(payload.site_id, effective_at)

        client_request_hash = None
        if payload.client_request_id:
            client_request_hash = OperationsService._compute_client_request_hash(payload)

        operation = await uow.operations.create_operation(
            site_id=payload.site_id,
            operation_type=payload.operation_type,
            created_by_user_id=user_id,
            effective_at=effective_at,
            source_site_id=payload.source_site_id,
            destination_site_id=payload.destination_site_id,
            issued_to_user_id=payload.issued_to_user_id,
            issued_to_name=payload.issued_to_name,
            issue_object_id=payload.issue_object_id,
            issue_object_name_snapshot=payload.issue_object_name_snapshot,
            acceptance_required=payload.operation_type in ACCEPTANCE_REQUIRED_TYPES,
            notes=payload.notes,
            client_request_id=payload.client_request_id,
            client_request_hash=client_request_hash,
            display_number=display_number,
            origin="user",  # backward compat
        )
        # Проставляем creation_source и source_ref напрямую
        operation.creation_source = "source_document"
        operation.source_ref = payload.source_ref

        # Создаём строки с SOURCE snapshot
        for line_data in payload.lines:
            item = await uow.catalog.get_item_by_id(line_data.item_id)
            if item is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"item with id {line_data.item_id} not found",
                )

            unit = await uow.catalog.get_unit_by_id(item.unit_id)
            category = await uow.catalog.get_category_by_id(item.category_id)

            # Сначала SOURCE snapshot (от исходного документа)
            # Потом catalog snapshot (от draft-времени — будет перезаписан на submit)
            await uow.operations.create_operation_line(
                operation_id=operation.id,
                line_number=line_data.line_number,
                inventory_subject_id=None,  # будет создан на submit
                item_id=line_data.item_id,  # уже валидирован
                qty=line_data.qty,
                batch=line_data.batch,
                comment=line_data.comment,
                source_item_name=line_data.source_item_name,
                source_item_sku=line_data.source_item_sku,
                source_unit_name=line_data.source_unit_name,
                source_category_name=line_data.source_category_name,
                item_name_snapshot=item.name,
                item_sku_snapshot=item.sku,
                unit_name_snapshot=unit.name if unit else None,
                unit_symbol_snapshot=unit.symbol if unit else None,
                category_name_snapshot=category.name if category else None,
            )

        created_operation = await uow.operations.get_operation_by_id(operation.id)

        # Draft waybill
        draft_doc_type = draft_document_type_for_operation(created_operation.operation_type)
        if draft_doc_type:
            try:
                async with uow.session.begin_nested():
                    await DocumentService.generate_from_operation(
                        uow=uow,
                        operation_id=created_operation.id,
                        document_type=draft_doc_type,
                        auto_finalize=False,
                        created_by_user_id=user_id,
                    )
            except Exception as exc:
                logger.warning(
                    "waybill_auto_create_failed",
                    operation_id=str(created_operation.id),
                    operation_type=created_operation.operation_type,
                    error=str(exc),
                )

        # Audit
        await record_audit_event(
            uow,
            event_type="operation.create",
            actor_user_id=user_id,
            site_id=payload.site_id,
            entity_type="operation",
            entity_id=str(created_operation.id),
            summary=(
                f"Пользователь создал черновик операции №{created_operation.short_id} "
                f"из source-document ({payload.source_document_type})"
                if hasattr(created_operation, "short_id") and created_operation.short_id
                else f"Создан черновик операции из source-document ({payload.source_document_type})"
            ),
            changes={
                "creation_source": "source_document",
                "source_ref": payload.source_ref,
                "source_document_type": payload.source_document_type,
                "lines_count": len(payload.lines),
            },
        )
        return {"operation": created_operation}

    @staticmethod
    async def update_operation_effective_at(
        uow: UnitOfWork,
        operation_id: UUID,
        *,
        effective_at: datetime,
        user_id: UUID | None = None,
    ):
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_draft_for_effective_at_change(operation)
        previous_effective_at = operation.effective_at

        updated = await uow.operations.update_operation(
            operation_id=operation_id,
            effective_at=effective_at,
            fields_set={"effective_at"},
        )

        if user_id is not None:
            await record_audit_event(
                uow,
                event_type="operation.update",
                actor_user_id=user_id,
                site_id=updated.site_id,
                entity_type="operation",
                entity_id=str(updated.id),
                summary=(
                    f"Изменена дата действия операции №{updated.short_id}"
                    if hasattr(updated, "short_id") and updated.short_id
                    else "Изменена дата действия операции"
                ),
                changes={
                    "fields_changed": ["effective_at"],
                    "diff": {
                        "effective_at": {
                            "old": previous_effective_at.isoformat() if previous_effective_at else None,
                            "new": effective_at.isoformat(),
                        },
                    },
                    "lines_count_before": len(updated.lines),
                    "lines_count_after": len(updated.lines),
                },
                outcome="success",
            )

        return await uow.operations.get_operation_by_id(updated.id)

    @staticmethod
    async def update_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        update_data: OperationUpdate,
        *,
        user_id: UUID | None = None,
    ):
        # Snapshot the pre-update line count so we can record the diff in
        # the operation.update audit event without doing an extra round-trip
        # after the lines are rewritten.
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_draft_for_update(operation)
        # ADR-0028 §2: effective_at is draft-only mutable. Explicit guard
        # clarifies the failure even when other draft-only guards (e.g. lines,
        # operation_type) could also trip.
        if "effective_at" in update_data.model_fields_set:
            OperationsWorkflowPolicy.require_draft_for_effective_at_change(operation)
        lines_count_before = len(operation.lines)

        # При смене типа: валидировать, что operation_type допустим
        if "operation_type" in update_data.model_fields_set and update_data.operation_type is not None:
            new_type = update_data.operation_type

            if new_type in ISSUE_OPERATION_TYPES and not operation.issue_object_id:
                if operation.operation_type not in ISSUE_OPERATION_TYPES:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"cannot change type to {new_type} without an issue object",
                    )

            if new_type != "RECEIVE" and update_data.lines is not None:
                if any(line.temporary_item is not None for line in update_data.lines):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="temporary items are only allowed for RECEIVE operations",
                    )

            operation.operation_type = new_type

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

        issue_object_id = operation.issue_object_id
        issue_object_name_snapshot = operation.issue_object_name_snapshot
        if operation.operation_type in ISSUE_OPERATION_TYPES:
            desired_issue_object_id = update_data.issue_object_id if "issue_object_id" in update_data.model_fields_set else operation.issue_object_id
            desired_snapshot = (
                update_data.issue_object_name_snapshot
                if "issue_object_name_snapshot" in update_data.model_fields_set
                else operation.issue_object_name_snapshot
            )
            desired_issued_to_name = (
                update_data.issued_to_name
                if "issued_to_name" in update_data.model_fields_set
                else operation.issued_to_name
            )
            issue_object_id, issue_object_name_snapshot = await OperationsService._resolve_issue_object(
                uow,
                operation_type=operation.operation_type,
                issue_object_id=desired_issue_object_id,
                issue_object_name_snapshot=desired_snapshot,
                issued_to_name=desired_issued_to_name,
            )

        updated = await uow.operations.update_operation(
            operation_id=operation_id,
            notes=update_data.notes,
            effective_at=update_data.effective_at,
            source_site_id=source_site_id,
            destination_site_id=destination_site_id,
            issued_to_user_id=update_data.issued_to_user_id,
            issued_to_name=issue_object_name_snapshot or update_data.issued_to_name,
            issue_object_id=issue_object_id,
            issue_object_name_snapshot=issue_object_name_snapshot,
            expected_version=update_data.expected_version,
            fields_set=update_data.model_fields_set,
        )

        # B5+batch: catalog guard — batch resolve, canonicalize, detect duplicates
        canonical_map: dict[int, int] = {}
        if update_data.lines is not None:
            canonical_map = await OperationsService._batch_resolve_and_validate_lines(
                uow, update_data.lines, operation_id=operation_id,
            )

            await uow.operations.delete_operation_lines(operation_id)

            has_temporary_items = any(line.temporary_item is not None for line in update_data.lines)
            if has_temporary_items and operation.operation_type != "RECEIVE":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Phase 1 supports inline temporary_item creation only for RECEIVE operations",
                )

            temporary_batch: dict[str, object] = {}
            for line in update_data.lines:
                if line.temporary_item is not None:
                    OperationsService._ensure_temporary_payload_consistent(
                        temporary_batch,
                        line.temporary_item.client_key,
                        line.temporary_item,
                    )
                    payload = line.temporary_item

                    # Resolve category
                    if payload.category_id is None:
                        uncategorized = await OperationsService._get_or_create_uncategorized_category(uow)
                        category_id_value = uncategorized.id
                        category_name = uncategorized.name
                    else:
                        category_id_value = payload.category_id
                        category = await uow.catalog.get_category_by_id(category_id_value)
                        if category is None:
                            raise HTTPException(
                                status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"category with id {category_id_value} not found",
                            )
                        category_name = category.name

                    unit = await uow.catalog.get_unit_by_id(payload.unit_id)
                    if unit is None:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"unit with id {payload.unit_id} not found",
                        )

                    draft_payload = {
                        "client_key": payload.client_key,
                        "name": payload.name.strip(),
                        "sku": payload.sku,
                        "unit_id": payload.unit_id,
                        "category_id": category_id_value,
                        "description": payload.description,
                        "hashtags": payload.hashtags,
                    }

                    await uow.operations.create_operation_line(
                        operation_id=operation_id,
                        line_number=line.line_number,
                        inventory_subject_id=None,  # Will be set on submit
                        item_id=None,  # Will be set on submit
                        qty=line.qty,
                        batch=line.batch,
                        comment=line.comment,
                        item_name_snapshot=payload.name.strip(),
                        item_sku_snapshot=payload.sku,
                        unit_name_snapshot=unit.name,
                        unit_symbol_snapshot=unit.symbol,
                        category_name_snapshot=category_name,
                        temporary_draft_payload=draft_payload,
                    )
                else:
                    if line.item_id is None:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="item_id is required",
                        )
                    # Use canonical ID from batch resolve
                    effective_item_id = canonical_map.get(line.item_id, line.item_id)
                    item = await OperationsService._ensure_item_usable(uow, effective_item_id)
                    unit = await uow.catalog.get_unit_by_id(item.unit_id)
                    if not unit:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"unit with id {item.unit_id} not found",
                        )
                    category = await uow.catalog.get_category_by_id(item.category_id)
                    if not category:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"category with id {item.category_id} not found",
                        )
                    line_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=effective_item_id)
                    await uow.operations.create_operation_line(
                        operation_id=operation_id,
                        line_number=line.line_number,
                        inventory_subject_id=line_subject.id,
                        item_id=effective_item_id,
                        qty=line.qty,
                        batch=line.batch,
                        comment=line.comment,
                        item_name_snapshot=item.name,
                        item_sku_snapshot=item.sku,
                        unit_name_snapshot=unit.name,
                        unit_symbol_snapshot=unit.symbol,
                        category_name_snapshot=category.name,
                    )

            # Refresh operation to avoid stale line data from identity map cache
            await uow.session.refresh(updated)

        # TZ-V3.1I rev. 2 (I3.3, closes warning #2): H1 теперь идёт через
        # helper — create и update согласованы. Для типов, чей финальный
        # документ — не waybill (EXPENSE/WRITE_OFF/RECEIVE/ADJUSTMENT),
        # helper возвращает None и waybill НЕ создаётся (что и требуется
        # после I3.1). Savepoint (begin_nested) — иначе DB-ошибка в
        # generate_from_operation отравит транзакцию update_operation.
        if operation.status == "draft":
            draft_doc_type = draft_document_type_for_operation(operation.operation_type)
            if draft_doc_type:
                try:
                    async with uow.session.begin_nested():
                        await DocumentService.generate_from_operation(
                            uow=uow,
                            operation_id=operation_id,
                            document_type=draft_doc_type,
                            auto_finalize=False,
                        )
                except Exception as exc:
                    logger.warning("waybill_auto_update_failed", operation_id=str(operation.id), error=str(exc))
                    # не абортим update_operation

        refreshed_after = await uow.operations.get_operation_by_id(updated.id)
        lines_count_after = len(refreshed_after.lines) if refreshed_after is not None else lines_count_before
        if user_id is not None:
            changed_fields = sorted(update_data.model_fields_set or [])
            await record_audit_event(
                uow,
                event_type="operation.update",
                actor_user_id=user_id,
                site_id=updated.site_id,
                entity_type="operation",
                entity_id=str(updated.id),
                summary=(
                    f"Изменён черновик операции №{updated.short_id}"
                    if hasattr(updated, "short_id") and updated.short_id
                    else "Изменён черновик операции"
                ),
                changes={
                    "fields_changed": changed_fields,
                    "lines_count_before": lines_count_before,
                    "lines_count_after": lines_count_after,
                },
                outcome="success",
            )

        return refreshed_after

    @staticmethod
    async def _materialize_deferred_temporary_lines(
        uow: UnitOfWork,
        operation,
        user_id: UUID,
    ) -> None:
        """Materialize deferred temporary lines: create a permanent catalog Item
        with requires_review=true, create inventory subject, and set references
        on operation lines.

        This replaces the old flow that created an inactive backing Item + TemporaryItem
        + temporary_item InventorySubject. New flow creates a permanent catalog item
        directly (as per TZ: permanent ТМЦ requiring review).

        All changes happen within the current UoW transaction.
        """
        from app.models.item import Item

        deferred_lines = [line for line in operation.lines if line.temporary_draft_payload is not None]
        if not deferred_lines:
            return

        # Группируем по client_key (один review-required item на уникальный ключ)
        from collections import OrderedDict
        grouped: OrderedDict[str, list] = OrderedDict()
        for line in deferred_lines:
            payload = line.temporary_draft_payload
            ck = payload["client_key"]
            if ck not in grouped:
                grouped[ck] = []
            grouped[ck].append(line)

        materialized_by_key: dict[str, dict[str, object]] = {}

        for client_key, lines in grouped.items():
            payload = lines[0].temporary_draft_payload

            category_id_value = payload["category_id"]
            unit_id_value = payload["unit_id"]

            # Create a permanent catalog Item with requires_review=true
            review_item = Item(
                sku=payload.get("sku"),
                name=payload["name"].strip(),
                normalized_name=normalize_for_storage(payload["name"]),
                category_id=category_id_value,
                unit_id=unit_id_value,
                description=payload.get("description"),
                hashtags=payload.get("hashtags"),
                is_active=True,
                requires_review=True,
                review_status="needs_review",
                review_created_by_user_id=user_id,
                source_system="operation_inline",
                source_ref=client_key,
            )
            try:
                review_item = await uow.catalog.create_item(review_item)
            except IntegrityError as exc:
                if "items_sku_key" in str(exc):
                    sku = payload.get("sku") or "(без SKU)"
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"SKU «{sku}» уже занят. Укажите другой SKU или оставьте поле пустым для автоматической генерации.",
                    )
                raise

            # Create inventory subject for the catalog item
            review_subject = await uow.inventory_subjects.get_or_create_for_item(
                item_id=review_item.id,
            )

            materialized_by_key[client_key] = {
                "item_id": review_item.id,
                "inventory_subject_id": review_subject.id,
            }

        # Set references on lines and clear draft payload
        for line in deferred_lines:
            ck = line.temporary_draft_payload["client_key"]
            refs = materialized_by_key[ck]
            line.item_id = refs["item_id"]
            line.inventory_subject_id = refs["inventory_subject_id"]
            line.temporary_draft_payload = None

        await uow.session.flush()

    @staticmethod
    async def _validate_resolved_lines_on_submit(
        uow: UnitOfWork,
        operation,
    ) -> None:
        """Повторная валидация resolved lines на submit.

        Проверяет:
        - item_id != null (для source_document гарантировано, для manual тоже
          теперь обязательно после _materialize_deferred_temporary_lines)
        - canonical_id через merge chain
        - canonical.is_active
        - canonical.deleted_at IS NULL
        """
        from app.services.catalog_read_service import CatalogReadService

        unresolved = []
        for line in operation.lines:
            if line.item_id is None:
                unresolved.append({
                    "line_id": line.id,
                    "line_number": line.line_number,
                    "reason": "missing_item_id",
                })
                continue

            item = await uow.catalog.get_item_by_id(line.item_id)
            if item is None:
                unresolved.append({
                    "line_id": line.id,
                    "line_number": line.line_number,
                    "previous_item_id": line.item_id,
                    "reason": "item_not_found",
                })
                continue

            canonical, reason = await CatalogReadService._follow_merge_chain(
                uow, item, depth=0,
            )
            if canonical is None:
                unresolved.append({
                    "line_id": line.id,
                    "line_number": line.line_number,
                    "previous_item_id": line.item_id,
                    "reason": reason or "unresolvable",
                })
                continue

            if canonical.deleted_at is not None:
                unresolved.append({
                    "line_id": line.id,
                    "line_number": line.line_number,
                    "previous_item_id": line.item_id,
                    "canonical_item_id": canonical.id,
                    "reason": "deleted",
                })
                continue

            if not canonical.is_active:
                unresolved.append({
                    "line_id": line.id,
                    "line_number": line.line_number,
                    "previous_item_id": line.item_id,
                    "canonical_item_id": canonical.id,
                    "reason": "inactive",
                })
                continue

        if unresolved:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "operation_lines_unresolved",
                    "operation_id": str(operation.id),
                    "lines": unresolved,
                },
            )

    @staticmethod
    async def _freeze_catalog_snapshot(
        uow: UnitOfWork,
        operation,
    ) -> list[dict]:
        """Зафиксировать catalog snapshot на момент submit.

        Перезаписывает item_name_snapshot, item_sku_snapshot, unit_*_snapshot,
        category_name_snapshot актуальными canonical значениями.
        Также обновляет OperationLine.item_id на canonical_id (если отличается).
        Возвращает список изменений для audit resource links.
        """
        from app.services.catalog_read_service import CatalogReadService

        catalog_changes = []
        for line in operation.lines:
            if line.item_id is None:
                continue  # temporary_item будет materialized отдельно (manual only)

            item = await uow.catalog.get_item_by_id(line.item_id)
            if item is None:
                continue

            canonical, _ = await CatalogReadService._follow_merge_chain(
                uow, item, depth=0,
            )
            if canonical is None:
                continue  # уже провалидировано в _validate_resolved_lines_on_submit

            old_id = line.item_id
            new_id = canonical.id

            if old_id != new_id:
                catalog_changes.append({
                    "line_id": line.id,
                    "line_number": line.line_number,
                    "previous_item_id": old_id,
                    "canonical_item_id": new_id,
                    "reason": "merged",
                })

            line.item_id = new_id
            line.item_name_snapshot = canonical.name
            line.item_sku_snapshot = canonical.sku
            if canonical.unit:
                line.unit_name_snapshot = canonical.unit.name
                line.unit_symbol_snapshot = canonical.unit.symbol
            if canonical.category:
                line.category_name_snapshot = canonical.category.name

        await uow.session.flush()
        return catalog_changes

    @staticmethod
    async def submit_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
        expected_version: int | None = None,
        identity: Identity | None = None,
    ) -> dict[str, object]:
        """Submit an operation with the authoritative guard order (TZ §7.1).

        Steps inside the transaction:
          2. primary read-only load (OperationNotFoundError on missing);
          3. primary authorisation (RoleNotPermittedError) before the lock;
          4. row lock on the operation;
          5. state check on the locked operation (state-before-version);
          6. optimistic expected_version check on the locked operation;
          7. re-authorisation on the locked operation;
          8. line materialization / validation;
          9. two-phase aggregated balance check;
         10. single InsufficientStockError / InsufficientIssuedBalanceError;
         11. atomic application (capture, repo submit, audit).

        `identity` is optional: system flows (merge, review resolution, sync)
        call submit without an actor identity and skip authorisation steps.
        """
        try:
            # Step 2: primary safe load (no lock).
            operation = await uow.operations.get_operation_by_id(operation_id)
            if operation is None:
                raise OperationNotFoundError(operation_id)

            # Step 3: primary authorisation before taking the lock.
            if identity is not None:
                OperationsService._require_submit_permission(identity, operation)

            # Step 4: take the operation row lock for authoritative checks.
            operation = await OperationsService._lock_operation(uow, operation_id, operation)

            # Step 5: state check on the locked operation (state-before-version).
            OperationsService._require_draft_for_submit_boundary(operation)

            # Step 6: optimistic version check (skipped only when the client
            # did not pass expected_version; state/rights checks never skip).
            if expected_version is not None and int(operation.version) != expected_version:
                raise StaleVersionError(
                    expected_version,
                    int(operation.version),
                    problem_class="operation-submit-rejected",
                )

            # Step 7: re-authorisation on the locked operation.
            if identity is not None:
                OperationsService._require_submit_permission(identity, operation)

            # Step 8: validate resolved lines for source_document operations
            # (у source_document temporary_item невозможен, поэтому validate ДО materialize)
            ops_cs = getattr(operation, 'creation_source', 'legacy')
            if ops_cs == "source_document":
                await OperationsService._validate_resolved_lines_on_submit(uow, operation)

            # Materialize deferred temporary lines before balance/register workflow
            # Для source_document: temporary_draft_payload гарантированно null (schema запрещает)
            if ops_cs != "source_document":
                await OperationsService._materialize_deferred_temporary_lines(
                    uow, operation, user_id,
                )

            # Для manual: после materialize — validate resolved lines
            # (созданный Item может сам быть merged или inactive)
            # Legacy операции (без creation_source) пропускают эту проверку
            if ops_cs in ("source_document", "manual"):
                await OperationsService._validate_resolved_lines_on_submit(uow, operation)

            # NEW: freeze catalog snapshot на момент submit (перезаписывает draft-time snapshot)
            # Для legacy операций (без creation_source) snapshot не перезаписываем
            catalog_changes = []
            if ops_cs in ("source_document", "manual"):
                catalog_changes = await OperationsService._freeze_catalog_snapshot(uow, operation)

            # Submit-time duplicate guard: after canonical freeze, before balance effects.
            # Two lines may now point to the same canonical item_id due to post-save merges.
            seen_canonical: dict[int, int] = {}  # item_id -> first line_number
            submit_duplicate_errors: list[OperationLineError] = []
            for line in operation.lines:
                if line.item_id is None:
                    continue
                if line.item_id in seen_canonical:
                    submit_duplicate_errors.append(OperationLineError(
                        line_number=line.line_number,
                        item_id=line.item_id,
                        reason="duplicate_item",
                        first_line_number=seen_canonical[line.item_id],
                    ))
                else:
                    seen_canonical[line.item_id] = line.line_number
            if submit_duplicate_errors:
                raise OperationLinesInvalidError(
                    errors=submit_duplicate_errors,
                    operation_id=operation.id,
                    message="Canonical duplicate detected after catalog freeze",
                )

            # Ensure every line has an inventory subject before the aggregate
            # balance check groups lines by (site_id, inventory_subject_id).
            for line in operation.lines:
                await OperationsService._ensure_line_inventory_subject(uow, line)

            # Step 9 + 10: two-phase aggregated balance check. Raises a single
            # InsufficientStockError / InsufficientIssuedBalanceError when any
            # group's summed requirement exceeds its locked available quantity.
            await OperationsService._check_submit_balance_sufficiency(uow, operation)

            # Step 11: apply effects. Sufficiency was already verified in the
            # aggregated check, so per-line _ensure_sufficient_* calls are no
            # longer needed on the submit path.
            balance_effects_capture: list[dict] = []

            for line in operation.lines:
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
                        await OperationsService._capture_balance_change(
                            uow,
                            capture=balance_effects_capture,
                            site_id=operation.site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            quantity_delta=quantity,
                            effect_type="receipt",
                            operation_line_id=line.id,
                            note=getattr(operation, "notes", None),
                        )
                elif operation.operation_type == "WRITE_OFF" and operation.issue_object_id is not None:
                    # Object write-off: decrement issued register (sufficiency
                    # verified in the aggregated check).
                    await OperationsService._upsert_issued(
                        uow,
                        issue_object_id=operation.issue_object_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=-quantity,
                        error_context="WRITE_OFF from issue object",
                    )
                elif operation.operation_type in DECREMENT_OPERATION_TYPES:
                    await OperationsService._capture_balance_change(
                        uow,
                        capture=balance_effects_capture,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=-quantity,
                        effect_type=OperationsService._effect_type_for_operation(operation.operation_type),
                        operation_line_id=line.id,
                        note=getattr(operation, "notes", None),
                    )
                elif operation.operation_type == "ADJUSTMENT":
                    await OperationsService._capture_balance_change(
                        uow,
                        capture=balance_effects_capture,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                        effect_type=getattr(uow, "audit_effect_type_override", None) or "adjustment",
                        operation_line_id=line.id,
                        note=getattr(operation, "notes", None),
                    )
                elif operation.operation_type == "MOVE":
                    if operation.source_site_id is None or operation.destination_site_id is None:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="MOVE operation requires source_site_id and destination_site_id",
                        )

                    await OperationsService._capture_balance_change(
                        uow,
                        capture=balance_effects_capture,
                        site_id=operation.source_site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=-quantity,
                        effect_type="move_out",
                        operation_line_id=line.id,
                        note=getattr(operation, "notes", None),
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
                        await OperationsService._capture_balance_change(
                            uow,
                            capture=balance_effects_capture,
                            site_id=operation.destination_site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            quantity_delta=quantity,
                            effect_type="move_in",
                            operation_line_id=line.id,
                            note=getattr(operation, "notes", None),
                        )
                elif operation.operation_type == "ISSUE":
                    if operation.issue_object_id is None:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="ISSUE requires issue_object_id",
                        )
                    await OperationsService._capture_balance_change(
                        uow,
                        capture=balance_effects_capture,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=-quantity,
                        effect_type="issue",
                        operation_line_id=line.id,
                        note=getattr(operation, "notes", None),
                    )
                    await OperationsService._upsert_issued(
                        uow,
                        issue_object_id=operation.issue_object_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=quantity,
                        error_context="ISSUE submit",
                    )
                elif operation.operation_type == "ISSUE_RETURN":
                    if operation.issue_object_id is None:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="ISSUE_RETURN requires issue_object_id",
                        )
                    await OperationsService._upsert_issued(
                        uow,
                        issue_object_id=operation.issue_object_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=-quantity,
                        error_context="ISSUE_RETURN submit",
                    )
                    await OperationsService._capture_balance_change(
                        uow,
                        capture=balance_effects_capture,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                        effect_type="issue_return",
                        operation_line_id=line.id,
                        note=getattr(operation, "notes", None),
                    )

            submitted_operation = await uow.operations.submit_operation(
                operation_id=operation_id,
                submitted_by_user_id=user_id,
                expected_version=expected_version,
            )

            # TZ-OPERATION_CORRECTION_BY_DIFF: Create revision 0 on initial submit
            # INV-C5: Initial submit создаёт revision 0
            revisions_repo = getattr(uow, "operation_revisions", None)
            if revisions_repo is not None:
                # Check if revision 0 already exists (e.g., after restore)
                existing_revisions = await revisions_repo.get_revisions_for_operation(operation_id)
                next_rev_number = max((r.revision_number for r in existing_revisions), default=-1) + 1
                revision_0 = await revisions_repo.create_revision(
                    operation_id=operation_id,
                    revision_number=next_rev_number,
                    created_by_user_id=user_id,
                )
                for line in operation.lines:
                    await revisions_repo.create_revision_line(
                        revision_id=revision_0.id,
                        line_uuid=line.line_uuid or uuid4(),
                        line_number=line.line_number,
                        item_id=line.item_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty=line.qty,
                        accepted_qty=line.accepted_qty,
                        lost_qty=line.lost_qty,
                        batch=line.batch,
                        comment=line.comment,
                        source_item_name=line.source_item_name,
                        source_item_sku=line.source_item_sku,
                        source_unit_name=line.source_unit_name,
                        source_category_name=line.source_category_name,
                        item_name_snapshot=line.item_name_snapshot,
                        item_sku_snapshot=line.item_sku_snapshot,
                        unit_name_snapshot=line.unit_name_snapshot,
                        unit_symbol_snapshot=line.unit_symbol_snapshot,
                        category_name_snapshot=line.category_name_snapshot,
                    )
                # Set current_revision_id on operation
                submitted_operation.current_revision_id = revision_0.id
                await uow.session.flush()

            # Автоматически создаём документ для операции (если включено в конфиге)
            # Пока создаём только для определённых типов операций
            document_created = None
            try:
                # TZ-V3.1I rev. 2 (I3.5, closes warning #10): войдировать draft
                # waybills, если финальный тип — не waybill. Иначе draft waybills
                # от H1 (MOVE/ISSUE/ISSUE_RETURN до сужения карты) или от старого
                # кода болтаются как осиротевшие после submit.
                submit_doc_type = submit_document_type_for_operation(submitted_operation.operation_type)
                if submit_doc_type and submit_doc_type != "waybill":
                    await DocumentService._void_existing_documents(
                        uow=uow,
                        operation_id=operation_id,
                        document_type="waybill",
                        template_name="waybill_v1",
                    )

                # TZ-V3.1I rev. 2 (I3.4): submit-карта — submit_document_type_for_operation
                if submit_doc_type:
                    # Генерируем документ с автоматической финализацией
                    result = await DocumentService.generate_from_operation(
                        uow=uow,
                        operation_id=operation_id,
                        document_type=submit_doc_type,
                        auto_finalize=True,
                        created_by_user_id=user_id,
                    )
                    document_created = result["document"]
                    logger.info(
                        "auto_generated_document",
                        document_id=document_created.id,
                        operation_id=str(operation_id),
                        operation_type=submitted_operation.operation_type,
                    )
            except Exception as e:
                # Логируем ошибку, но не прерываем выполнение
                logger.warning(
                    "failed_to_auto_generate_document",
                    operation_id=str(operation_id),
                    error=str(e),
                )

            submit_event = await record_audit_event(
                uow,
                event_type="operation.submit",
                actor_user_id=user_id,
                site_id=submitted_operation.site_id,
                entity_type="operation",
                entity_id=str(submitted_operation.id),
                summary=f"Пользователь подтвердил операцию №{submitted_operation.short_id} ({submitted_operation.operation_type})"
                if hasattr(submitted_operation, "short_id") and submitted_operation.short_id
                else f"Операция подтверждена ({submitted_operation.operation_type})",
                changes={
                    "operation_type": submitted_operation.operation_type,
                    "lines_count": len(balance_effects_capture),
                    "total_qty": str(sum(
                        (c["quantity_delta"] for c in balance_effects_capture),
                        Decimal("0"),
                    )),
                },
                parent_event_id=getattr(uow, "audit_parent_event_id", None),
                outcome="success",
            )

            # TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING §7.2:
            # Audit resource links for catalog resolution (canonical item_id replacement)
            if catalog_changes:
                for change in catalog_changes:
                    try:
                        await uow.audit_events.insert_resource(
                            audit_event_id=int(submit_event.id),
                            resource_type="operation_line",
                            resource_id=str(change["line_id"]),
                            relation="catalog_resolved",
                            snapshot_before={"item_id": change["previous_item_id"]},
                            snapshot_after={"item_id": change["canonical_item_id"]},
                            extra_metadata={"reason": change["reason"]},
                        )
                    except Exception as exc:
                        logger.warning(
                            "audit_resource_link_failed",
                            operation_id=str(operation_id),
                            line_id=change["line_id"],
                            error=str(exc),
                        )

            # Persist captured effects — each row references the operation.submit
            # event so reverse lookups remain cheap.
            is_system = (getattr(submitted_operation, "origin", "user") == "system")
            await OperationsService._write_captured_effects(
                uow,
                capture=balance_effects_capture,
                audit_event_id=int(submit_event.id),
                operation_id=submitted_operation.id,
                is_system_generated=is_system,
                caused_by_event_id=getattr(uow, "audit_caused_by_event_id", None),
                effective_at=submitted_operation.effective_at,
            )

            response = {"operation": submitted_operation}
            if document_created:
                response["document"] = document_created

            return response
        except HTTPException:
            raise
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Конфликт данных при подтверждении операции: {OperationsService._extract_user_message(exc)}",
            )

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
                line_progress_before = (
                    Decimal(line.accepted_qty),
                    Decimal(line.lost_qty),
                )
                balance_before_row = await uow.balances.get_for_update(
                    site_id=destination_site_id,
                    inventory_subject_id=line.inventory_subject_id,
                )
                balance_before_qty = Decimal(getattr(balance_before_row, "qty", 0) or 0)
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
                action = await uow.asset_registers.create_acceptance_action(
                    operation_id=operation.id,
                    operation_line_id=line.id,
                    action_type="accept",
                    qty=accepted_delta,
                    performed_by_user_id=user_id,
                    notes=update.note,
                )

                # A-4 / ADR-0028 §4.1: per-action event + warehouse effect.
                # The event explicitly references the OperationAcceptanceAction
                # id; the effect is bound to the event (1:1 ownership) and
                # carries the action.performed_at as cause timestamp.
                accept_event = await record_audit_event(
                    uow,
                    event_type="operation.line_accepted",
                    actor_user_id=user_id,
                    site_id=destination_site_id,
                    entity_type="operation_line",
                    entity_id=str(line.id),
                    summary=(
                        f"Принято {accepted_delta} {getattr(line, 'unit_symbol_snapshot', '') or ''} "
                        f"по строке операции №{getattr(line, 'line_number', '?')}"
                    ).strip(),
                    changes={
                        "operation_id": str(operation.id),
                        "operation_line_id": int(line.id),
                        "action_id": int(action.id),
                        "action_type": "accept",
                        "inventory_subject_id": int(line.inventory_subject_id),
                        "item_id": int(line.item_id) if line.item_id is not None else None,
                        "item_name_snapshot": getattr(line, "item_name_snapshot", None),
                        "item_sku_snapshot": getattr(line, "item_sku_snapshot", None),
                        "destination_site_id": int(destination_site_id),
                        "qty": str(accepted_delta),
                        "line_progress_before": {
                            "accepted_qty": str(line_progress_before[0]),
                            "lost_qty": str(line_progress_before[1]),
                        },
                        "line_progress_after": {
                            "accepted_qty": str(line_progress_before[0] + accepted_delta),
                            "lost_qty": str(line_progress_before[1]),
                        },
                    },
                    outcome="success",
                )
                capture_for_accept: list[dict] = [
                    {
                        "site_id": destination_site_id,
                        "inventory_subject_id": int(line.inventory_subject_id),
                        "quantity_before": balance_before_qty,
                        "quantity_delta": Decimal(accepted_delta),
                        "quantity_after": balance_before_qty + Decimal(accepted_delta),
                        "effect_type": "acceptance",
                        "operation_line_id": int(line.id),
                        "note": update.note or "acceptance",
                        "cause_timestamp": action.performed_at,
                    }
                ]
                await OperationsService._write_captured_effects(
                    uow,
                    capture=capture_for_accept,
                    audit_event_id=int(accept_event.id),
                    operation_id=operation.id,
                    is_system_generated=False,
                    caused_by_event_id=None,
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
                line_progress_before_lost = (
                    Decimal(line.accepted_qty),
                    Decimal(line.lost_qty),
                )
                await uow.operations.update_operation_line_progress(
                    operation_line_id=line.id,
                    accepted_delta=Decimal("0"),
                    lost_delta=lost_delta,
                )
                action_lost = await uow.asset_registers.create_acceptance_action(
                    operation_id=operation.id,
                    operation_line_id=line.id,
                    action_type="mark_lost",
                    qty=lost_delta,
                    performed_by_user_id=user_id,
                    notes=update.note,
                )

                # A-4 / ADR-0028 §4.1: per-action event, NO warehouse effect.
                # mark_lost only moves qty between pending and the lost
                # register; balances.qty does not change.
                await record_audit_event(
                    uow,
                    event_type="operation.line_mark_lost",
                    actor_user_id=user_id,
                    site_id=destination_site_id,
                    entity_type="operation_line",
                    entity_id=str(line.id),
                    summary=(
                        f"Отмечено как утерянное {lost_delta} по строке операции "
                        f"№{getattr(line, 'line_number', '?')}"
                    ),
                    changes={
                        "operation_id": str(operation.id),
                        "operation_line_id": int(line.id),
                        "action_id": int(action_lost.id),
                        "action_type": "mark_lost",
                        "inventory_subject_id": int(line.inventory_subject_id),
                        "item_id": int(line.item_id) if line.item_id is not None else None,
                        "item_name_snapshot": getattr(line, "item_name_snapshot", None),
                        "item_sku_snapshot": getattr(line, "item_sku_snapshot", None),
                        "destination_site_id": int(destination_site_id),
                        "qty": str(lost_delta),
                        "line_progress_before": {
                            "accepted_qty": str(line_progress_before_lost[0]),
                            "lost_qty": str(line_progress_before_lost[1]),
                        },
                        "line_progress_after": {
                            "accepted_qty": str(line_progress_before_lost[0]),
                            "lost_qty": str(line_progress_before_lost[1] + lost_delta),
                        },
                    },
                    outcome="success",
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
        completed_operation = await uow.operations.get_operation_by_id(operation_id)
        if next_state == "resolved":
            await record_audit_event(
                uow,
                event_type="operation.acceptance_complete",
                actor_user_id=user_id,
                site_id=completed_operation.site_id,
                entity_type="operation",
                entity_id=str(operation_id),
                summary=(
                    f"Завершена приёмка по операции №{completed_operation.short_id}"
                    if hasattr(completed_operation, "short_id") and completed_operation.short_id
                    else "Приёмка завершена"
                ),
            )
        return {"operation": completed_operation}

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

        warehouse_target_site_id: int | None = None
        if action == "found_to_destination":
            destination_site_id = OperationsService._destination_site_for_acceptance(operation)
            balance_before_row = await uow.balances.get_for_update(
                site_id=destination_site_id,
                inventory_subject_id=lost_row.inventory_subject_id,
            )
            balance_before_qty = Decimal(getattr(balance_before_row, "qty", 0) or 0)
            await uow.balances.update_balance_quantity(
                site_id=destination_site_id,
                inventory_subject_id=lost_row.inventory_subject_id,
                quantity_delta=qty,
            )
            warehouse_target_site_id = int(destination_site_id)
        elif action == "return_to_source":
            if lost_row.source_site_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="source_site_id is required for return_to_source",
                )
            balance_before_row = await uow.balances.get_for_update(
                site_id=lost_row.source_site_id,
                inventory_subject_id=lost_row.inventory_subject_id,
            )
            balance_before_qty = Decimal(getattr(balance_before_row, "qty", 0) or 0)
            await uow.balances.update_balance_quantity(
                site_id=lost_row.source_site_id,
                inventory_subject_id=lost_row.inventory_subject_id,
                quantity_delta=qty,
            )
            warehouse_target_site_id = int(lost_row.source_site_id)
        elif action == "write_off":
            # Inventory is removed from temporary lost register only;
            # responsibility is linked via responsible_recipient_id in action
            # log. balances.qty does NOT change.
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
        action_row = await uow.asset_registers.create_acceptance_action(
            operation_id=lost_row.operation_id,
            operation_line_id=lost_row.operation_line_id,
            action_type=action,
            qty=qty,
            performed_by_user_id=user_id,
            recipient_id=responsible_recipient_id,
            notes=note,
        )

        # A-4 / ADR-0028 §4.2: per-action event with `action_type`.
        # For found_to_destination and return_to_source, a warehouse effect
        # is also persisted with the action.performed_at as the captured
        # cause timestamp (effective_at wiring lands in A-5).
        lost_resolved_event = await record_audit_event(
            uow,
            event_type="operation.line_lost_resolved",
            actor_user_id=user_id,
            site_id=getattr(operation, "site_id", None),
            entity_type="operation_line",
            entity_id=str(lost_row.operation_line_id),
            summary=(
                f"Решение по утерянному имуществу ({action}): {qty}"
            ),
            changes={
                "operation_id": str(lost_row.operation_id),
                "operation_line_id": int(lost_row.operation_line_id),
                "action_id": int(action_row.id),
                "action_type": action,
                "qty": str(qty),
                "inventory_subject_id": int(lost_row.inventory_subject_id),
                "site_id": int(lost_row.site_id),
                "source_site_id": (
                    int(lost_row.source_site_id) if lost_row.source_site_id is not None else None
                ),
            },
            outcome="success",
        )

        if warehouse_target_site_id is not None:
            capture_resolve: list[dict] = [
                {
                    "site_id": int(warehouse_target_site_id),
                    "inventory_subject_id": int(lost_row.inventory_subject_id),
                    "quantity_before": balance_before_qty,
                    "quantity_delta": Decimal(qty),
                    "quantity_after": balance_before_qty + Decimal(qty),
                    "effect_type": "acceptance",
                    "operation_line_id": int(lost_row.operation_line_id),
                    "note": note or action,
                    "cause_timestamp": action_row.performed_at,
                }
            ]
            await OperationsService._write_captured_effects(
                uow,
                capture=capture_resolve,
                audit_event_id=int(lost_resolved_event.id),
                operation_id=lost_row.operation_id,
                is_system_generated=False,
                caused_by_event_id=None,
            )

        return {"status": "ok"}

    @staticmethod
    async def delete_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
    ) -> None:
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        # Route checks workflow first; keep service guard as defense in depth.
        OperationsWorkflowPolicy.require_cancelled_for_delete(operation)

        await uow.operations.soft_delete_operation(
            operation_id=operation_id,
            deleted_by_user_id=user_id,
        )

        await record_audit_event(
            uow,
            event_type="operation.delete",
            actor_user_id=user_id,
            site_id=operation.site_id,
            entity_type="operation",
            entity_id=str(operation_id),
            summary=(
                f"Пользователь удалил операцию №{operation.short_id}"
                if hasattr(operation, "short_id") and operation.short_id
                else f"Операция удалена"
            ),
        )

        logger.info("deleted operation=%s by user=%s", operation_id, user_id)

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

        # Capture per-line inverse balance changes so we can persist
        # audit_item_effects rows once the operation.cancel audit event is
        # written.
        balance_effects_capture: list[dict] = []

        if operation.status == "submitted":
            # PHASE 0: aggregated read-only pre-check (TZ-OPERATION_CANCEL_DOMAIN_ERRORS §5).
            # Raises InsufficientStockError / InsufficientIssuedBalanceError → envelope.
            await OperationsService._check_cancel_balance_sufficiency(uow, operation=operation)

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
                                capture=balance_effects_capture,
                                effect_type="cancel_reversal",
                                note=reason,
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
                            capture=balance_effects_capture,
                            effect_type="cancel_reversal",
                            note=reason,
                        )
                elif operation.operation_type == "WRITE_OFF" and operation.issue_object_id is not None:
                    # Object write-off rollback: restore issued register
                    await OperationsService._upsert_issued(
                        uow,
                        issue_object_id=operation.issue_object_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=quantity,
                        error_context="WRITE_OFF from issue object rollback",
                    )
                elif operation.operation_type in DECREMENT_OPERATION_TYPES:
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                        error_context=f"{operation.operation_type} rollback",
                        capture=balance_effects_capture,
                        effect_type="cancel_reversal",
                        note=reason,
                    )
                elif operation.operation_type == "ADJUSTMENT":
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=-quantity,
                        error_context="ADJUSTMENT rollback",
                        capture=balance_effects_capture,
                        effect_type="cancel_reversal",
                        note=reason,
                    )
                elif operation.operation_type == "MOVE":
                    if operation.source_site_id is None or operation.destination_site_id is None:
                        raise OperationInWrongStateError(
                            current_state="invalid",
                            allowed_states=["draft", "submitted"],
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
                                capture=balance_effects_capture,
                                effect_type="cancel_reversal",
                                note=reason,
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
                            capture=balance_effects_capture,
                            effect_type="cancel_reversal",
                            note=reason,
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
                            capture=balance_effects_capture,
                            effect_type="cancel_reversal",
                            note=reason,
                        )
                        await OperationsService._apply_balance_delta(
                            uow,
                            site_id=operation.destination_site_id,
                            inventory_subject_id=line.inventory_subject_id,
                            quantity_delta=-quantity,
                            error_context="MOVE rollback from destination",
                            capture=balance_effects_capture,
                            effect_type="cancel_reversal",
                            note=reason,
                        )
                elif operation.operation_type == "ISSUE":
                    if operation.issue_object_id is None:
                        raise OperationInWrongStateError(
                            current_state="invalid",
                            allowed_states=["draft", "submitted"],
                        )
                    await OperationsService._upsert_issued(
                        uow,
                        issue_object_id=operation.issue_object_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=-quantity,
                        error_context="ISSUE rollback from issue_object",
                    )
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=quantity,
                        error_context="ISSUE rollback to stock",
                        capture=balance_effects_capture,
                        effect_type="cancel_reversal",
                        note=reason,
                    )
                elif operation.operation_type == "ISSUE_RETURN":
                    if operation.issue_object_id is None:
                        raise OperationInWrongStateError(
                            current_state="invalid",
                            allowed_states=["draft", "submitted"],
                        )
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        inventory_subject_id=line.inventory_subject_id,
                        quantity_delta=-quantity,
                        error_context="ISSUE_RETURN rollback from stock",
                        capture=balance_effects_capture,
                        effect_type="cancel_reversal",
                        note=reason,
                    )
                    await OperationsService._upsert_issued(
                        uow,
                        issue_object_id=operation.issue_object_id,
                        inventory_subject_id=line.inventory_subject_id,
                        qty_delta=quantity,
                        error_context="ISSUE_RETURN rollback to issue_object",
                    )

        cancelled_operation = await uow.operations.cancel_operation(
            operation_id=operation_id,
            cancelled_by_user_id=user_id,
        )

        # Удалить временные ТМЦ, связанные с операцией
        await OperationsService._delete_temporary_items_of_operation(
            uow, operation_id=operation_id, user_id=user_id,
        )

        cancel_event = await record_audit_event(
            uow,
            event_type="operation.cancel",
            actor_user_id=user_id,
            site_id=operation.site_id,
            entity_type="operation",
            entity_id=str(operation_id),
            summary=(
                f"Пользователь отменил операцию №{operation.short_id}"
                if hasattr(operation, "short_id") and operation.short_id
                else f"Операция отменена"
            ),
            changes={
                "reason": reason,
                "was_submitted": (operation.status == "submitted"),
                "reversal_lines_count": len(balance_effects_capture),
            },
            outcome="success",
            parent_event_id=getattr(uow, "audit_parent_event_id", None),
        )

        is_system = (getattr(cancelled_operation, "origin", "user") == "system")
        await OperationsService._write_captured_effects(
            uow,
            capture=balance_effects_capture,
            audit_event_id=int(cancel_event.id),
            operation_id=cancelled_operation.id,
            is_system_generated=is_system,
            caused_by_event_id=getattr(uow, "audit_caused_by_event_id", None),
            effective_at=cancelled_operation.cancelled_at,
        )

        logger.info("cancelled operation=%s by user=%s reason=%s", operation_id, user_id, reason)
        return {"operation": cancelled_operation}

    @staticmethod
    async def restore_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
    ) -> dict:
        operation = await uow.operations.get_operation_by_id(operation_id)
        OperationsWorkflowPolicy.require_exists(operation)
        OperationsWorkflowPolicy.require_cancelled_for_restore(operation)

        # Snapshot the cancelled-side metadata BEFORE the repo clears it so
        # the audit row reflects the actual cancel state.
        cancelled_at_before = getattr(operation, "cancelled_at", None)
        cancelled_by_user_id_before = getattr(operation, "cancelled_by_user_id", None)
        cancel_reason_before = getattr(operation, "cancel_reason", None)
        previous_version = int(operation.version)
        previous_status = "cancelled"

        restored = await uow.operations.restore_operation(
            operation_id=operation_id,
            restored_by_user_id=user_id,
        )

        # Defensive: workflow guard already enforces status==cancelled, but
        # an external caller (or future replay) may try to restore an
        # already-restored op. In that case no version bump happened and no
        # duplicate audit row should be written.
        if restored is not None and int(restored.version) == previous_version:
            logger.info(
                "restore_operation_noop",
                operation_id=str(operation_id),
                user_id=str(user_id),
                previous_version=previous_version,
            )
            return {"operation": restored}

        # ADR-0028 §3.1: causal link to the latest successful
        # operation.cancel event (if any). Legacy operations without a
        # cancel event remain observable through cancel_event_missing=true.
        parent_cancel_event = await uow.audit_events.find_latest_event_for_entity(
            event_type="operation.cancel",
            entity_type="operation",
            entity_id=str(operation_id),
            outcome="success",
        )
        parent_event_id = parent_cancel_event.event_id if parent_cancel_event is not None else None

        changes: dict[str, object] = {
            "previous_status": previous_status,
            "new_status": getattr(restored, "status", "draft"),
            "previous_version": previous_version,
            "new_version": int(restored.version) if restored is not None else previous_version,
            "cancelled_at_before": cancelled_at_before.isoformat() if cancelled_at_before else None,
            "cancelled_by_user_id_before": (
                str(cancelled_by_user_id_before) if cancelled_by_user_id_before else None
            ),
            "cancel_reason_before": cancel_reason_before,
            "restored_by_user_id": str(user_id),
        }
        if parent_event_id is None:
            changes["cancel_event_missing"] = True

        await record_audit_event(
            uow,
            event_type="operation.restore",
            actor_user_id=user_id,
            site_id=getattr(restored, "site_id", None) or getattr(operation, "site_id", None),
            entity_type="operation",
            entity_id=str(operation_id),
            summary=(
                f"Пользователь восстановил операцию №{getattr(restored, 'short_id', '')}"
                if getattr(restored, "short_id", None)
                else "Операция восстановлена из отмены"
            ),
            changes=changes,
            outcome="success",
            parent_event_id=parent_event_id,
        )

        logger.info(
            "restore_operation",
            operation_id=str(operation_id),
            user_id=str(user_id),
            parent_event_id=str(parent_event_id) if parent_event_id else None,
            cancel_event_missing=parent_event_id is None,
        )
        return {"operation": restored}

    @staticmethod
    async def _delete_temporary_items_of_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
    ) -> None:
        """Soft-delete review-required items associated with the cancelled operation.

        Works with both:
        - new flow: catalog Item with requires_review=true
        - legacy flow: TemporaryItem records (for already-existing data)
        """
        from app.services.temporary_items_resolution_service import (
            TemporaryItemsResolutionService,
        )

        operation = await uow.operations.get_operation_by_id(operation_id)
        if operation is None:
            return

        seen_item_ids: set[int] = set()

        for line in operation.lines:
            if line.inventory_subject_id is None:
                continue

            subject = await uow.inventory_subjects.get_by_id(line.inventory_subject_id)
            if subject is None:
                continue

            # New flow: catalog item with requires_review
            if subject.subject_type == "catalog_item" and subject.item_id is not None:
                item_id = subject.item_id
                if item_id in seen_item_ids:
                    continue
                seen_item_ids.add(item_id)

                item = await uow.catalog.get_item_by_id(item_id)
                if item is None or item.deleted_at is not None:
                    continue
                if not item.requires_review:
                    continue
                if item.review_status not in (None, "needs_review"):
                    continue

                # Soft-delete the review-required item
                try:
                    await uow.catalog.soft_delete_item(item_id, user_id)
                except ValueError:
                    # If deletion is blocked (e.g. non-zero balance), skip
                    pass
                continue

            # Legacy flow: temporary_item_id subject
            if subject.temporary_item_id is not None:
                from app.models.temporary_item import TemporaryItem

                temp_id = subject.temporary_item_id
                if temp_id in seen_item_ids:
                    continue
                seen_item_ids.add(temp_id)

                temp_item = await uow.temporary_items.get_by_id(temp_id)
                if temp_item is None:
                    continue
                if temp_item.status != TemporaryItem.STATUS_ACTIVE:
                    continue

                await TemporaryItemsResolutionService.delete_temporary_item(
                    uow,
                    temporary_item_id=temp_id,
                    resolved_by_user_id=user_id,
                    resolution_note=(
                        f"Auto-deleted on cancel of operation {operation_id}"
                    ),
                )

    @staticmethod
    async def _get_or_create_uncategorized_category(uow: UnitOfWork) -> Category:
        """Найти или создать категорию 'Без категории'."""
        categories = await uow.catalog.list_categories_by_code(UNCATEGORIZED_CATEGORY_CODE)
        if len(categories) > 1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="multiple uncategorized categories configured",
            )
        if categories:
            category = categories[0]
            category.name = UNCATEGORIZED_CATEGORY_NAME
            category.parent_id = None
            category.is_active = True
            await uow.catalog.update_category(category)
            return category

        category = Category(
            name=UNCATEGORIZED_CATEGORY_NAME,
            code=UNCATEGORIZED_CATEGORY_CODE,
            parent_id=None,
            sort_order=9999,
            is_active=True,
        )
        return await uow.catalog.create_category(category)
