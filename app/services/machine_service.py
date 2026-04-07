from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.api.exceptions import SyncServerException
from app.core.identity import Identity
from app.models.category import Category
from app.models.item import Item
from app.models.operation import Operation
from app.schemas.machine import MachineBatchEnvelope
from app.schemas.operation import OperationCreate, OperationUpdate
from app.services.operations_service import OperationsService
from app.services.uow import UnitOfWork


MACHINE_SCHEMA_VERSION = "2026-04-07"
SNAPSHOT_DATASETS = [
    "catalog.items",
    "catalog.categories",
    "catalog.units",
    "operations",
]

READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}
WRITE_ROLES = {"chief_storekeeper", "storekeeper"}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def make_snapshot_id() -> str:
    return f"snap_{datetime.now(UTC).strftime('%Y_%m_%d_%H%M%S')}_{uuid4().hex[:6]}"


def make_report_id() -> str:
    return f"rpt_{datetime.now(UTC).strftime('%Y%m%d')}_{uuid4().hex[:8]}"


def make_batch_id(domain: str) -> str:
    return f"bat_{domain}_{uuid4().hex[:8]}"


def make_plan_id(domain: str) -> str:
    return f"plan_{domain}_{uuid4().hex[:8]}"


def parse_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(cursor)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor") from exc
    if offset < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor")
    return offset


def next_cursor(*, offset: int, returned_count: int, limit: int) -> str | None:
    if returned_count < limit:
        return None
    return str(offset + returned_count)


def apply_field_selection(
    records: list[dict],
    *,
    fields: str | None,
    allowed_fields: set[str],
) -> list[dict]:
    if fields is None or not fields.strip():
        return records
    selected_fields = {value.strip() for value in fields.split(",") if value.strip()}
    invalid = selected_fields - allowed_fields
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unsupported fields: {', '.join(sorted(invalid))}",
        )
    return [{key: value for key, value in record.items() if key in selected_fields} for record in records]


def to_jsonl(meta: dict, records: list[dict]) -> str:
    lines = [json.dumps({"meta": meta}, ensure_ascii=False, default=str)]
    lines.extend(json.dumps(record, ensure_ascii=False, default=str) for record in records)
    return "\n".join(lines)


def payload_hash(data: dict) -> str:
    dumped = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


class MachineService:
    @staticmethod
    def require_read_access(identity: Identity) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in READ_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="machine read access denied",
            )

    @staticmethod
    def require_catalog_batch_access(identity: Identity, scopes: list) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in WRITE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="machine catalog batch access denied",
            )
        has_manage_scope = any(
            scope.is_active and scope.can_view and scope.can_operate and scope.can_manage_catalog
            for scope in scopes
        )
        if not has_manage_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="machine catalog batch access denied",
            )

    @staticmethod
    def require_operations_batch_access(identity: Identity, scopes: list) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in WRITE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="machine operations batch access denied",
            )
        has_operate_scope = any(scope.is_active and scope.can_view and scope.can_operate for scope in scopes)
        if not has_operate_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="machine operations batch access denied",
            )

    @staticmethod
    async def resolve_scopes(uow: UnitOfWork, identity: Identity) -> list:
        return list(await uow.user_access_scopes.list_user_scopes(identity.user_id))

    @staticmethod
    async def resolve_visible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
        if identity.has_global_business_access:
            from app.schemas.admin import SiteFilter

            sites, _ = await uow.sites.list_sites(
                filter=SiteFilter(is_active=None),
                user_site_ids=None,
                page=1,
                page_size=1000,
            )
            return [site.id for site in sites]
        scopes = list(await uow.user_access_scopes.list_user_scopes(identity.user_id))
        return [scope.site_id for scope in scopes if scope.is_active and scope.can_view]

    @staticmethod
    async def resolve_snapshot(
        uow: UnitOfWork,
        *,
        requested_snapshot_id: str | None,
        created_by_user_id: UUID | None,
    ):
        if requested_snapshot_id:
            snapshot = await uow.machine.get_snapshot(requested_snapshot_id)
            if snapshot is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found")
            return snapshot

        snapshot_id = make_snapshot_id()
        snapshot_at = datetime.now(UTC)
        counts = await uow.machine.build_dataset_counts(snapshot_at)
        snapshot = await uow.machine.create_snapshot(
            snapshot_id=snapshot_id,
            schema_version=MACHINE_SCHEMA_VERSION,
            datasets=SNAPSHOT_DATASETS,
            counts=counts,
            created_by_user_id=created_by_user_id,
        )
        return snapshot

    @staticmethod
    async def ensure_latest_snapshot(
        uow: UnitOfWork,
        *,
        created_by_user_id: UUID | None,
    ):
        latest = await uow.machine.get_latest_snapshot()
        if latest is not None:
            return latest
        return await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=None,
            created_by_user_id=created_by_user_id,
        )

    @staticmethod
    async def preview_catalog_batch(
        uow: UnitOfWork,
        *,
        envelope: MachineBatchEnvelope,
        identity: Identity,
        source_client: str | None,
    ):
        if envelope.domain != "catalog":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="domain must be catalog")

        existing = await uow.machine.get_batch_by_idempotency_key(envelope.idempotency_key)
        envelope_data = envelope.model_dump(mode="json")
        envelope_hash = payload_hash(envelope_data)
        if existing is not None:
            if existing.payload_hash != envelope_hash:
                raise SyncServerException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used with different payload",
                    error_code="idempotency_key_conflict",
                    details={"idempotency_key": envelope.idempotency_key, "batch_id": existing.batch_id},
                )
            return existing

        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=None,
            created_by_user_id=identity.user_id,
        )

        payload = envelope.payload
        categories = payload.get("categories", [])
        items = payload.get("items", [])
        meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
        source_system = meta.get("source") or "machine_batch"

        records: list[dict] = []
        warnings: list[dict] = []
        errors: list[dict] = []

        category_codes: dict[str, dict] = {}
        category_refs: dict[str, dict] = {}
        for idx, category in enumerate(categories):
            input_path = f"categories[{idx}]"
            code = (category.get("code") or "").strip()
            name = (category.get("name") or "").strip()
            ref = (category.get("ref") or "").strip()
            if not code or not name or not ref:
                errors.append({"input_path": input_path, "code": "invalid_category", "message": "ref, code and name are required"})
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "category",
                        "match_key": f"code={code}" if code else None,
                    }
                )
                continue
            if code in category_codes:
                errors.append({"input_path": input_path, "code": "duplicate_category_code", "message": f"duplicate code {code}"})
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "category",
                        "match_key": f"code={code}",
                    }
                )
                continue
            if ref in category_refs:
                errors.append({"input_path": input_path, "code": "duplicate_category_ref", "message": f"duplicate ref {ref}"})
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "category",
                        "match_key": f"ref={ref}",
                    }
                )
                continue
            category_codes[code] = category
            category_refs[ref] = category

        for idx, category in enumerate(categories):
            input_path = f"categories[{idx}]"
            if any(record["input_path"] == input_path and record["action"] == "error" for record in records):
                continue
            code = category["code"].strip()
            existing_category_list = await uow.catalog.list_categories_by_code(code)
            existing_category = existing_category_list[0] if existing_category_list else None
            action = "update" if existing_category is not None else "create"
            records.append(
                {
                    "input_path": input_path,
                    "action": action,
                    "entity_type": "category",
                    "match_key": f"code={code}",
                    "data": {
                        "ref": category.get("ref"),
                        "code": code,
                        "name": category.get("name"),
                        "parent_ref": category.get("parent_ref"),
                        "existing_id": existing_category.id if existing_category is not None else None,
                    },
                }
            )

        item_skus: set[str] = set()
        for idx, item in enumerate(items):
            input_path = f"items[{idx}]"
            sku = (item.get("sku") or "").strip()
            name = (item.get("name") or "").strip()
            category_ref = (item.get("category_ref") or "").strip()
            unit_code = (item.get("unit_code") or "").strip()
            if not sku or not name or not category_ref or not unit_code:
                errors.append({"input_path": input_path, "code": "invalid_item", "message": "sku, name, category_ref and unit_code are required"})
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "item",
                        "match_key": f"sku={sku}" if sku else None,
                    }
                )
                continue
            if sku in item_skus:
                errors.append({"input_path": input_path, "code": "duplicate_item_sku", "message": f"duplicate sku {sku}"})
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "item",
                        "match_key": f"sku={sku}",
                    }
                )
                continue
            item_skus.add(sku)

            if category_ref not in category_refs:
                errors.append({"input_path": input_path, "code": "category_ref_not_found", "message": f"unknown category_ref {category_ref}"})
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "item",
                        "match_key": f"sku={sku}",
                    }
                )
                continue

            unit = await uow.catalog.get_unit_by_code(unit_code)
            if unit is None:
                unit = await uow.catalog.get_unit_by_symbol(unit_code)
            if unit is None:
                errors.append({"input_path": input_path, "code": "unit_not_found", "message": f"unknown unit_code {unit_code}"})
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "item",
                        "match_key": f"sku={sku}",
                    }
                )
                continue

            existing_item = await uow.catalog.get_item_by_sku(sku)
            action = "update" if existing_item is not None else "create"
            records.append(
                {
                    "input_path": input_path,
                    "action": action,
                    "entity_type": "item",
                    "match_key": f"sku={sku}",
                    "data": {
                        "ref": item.get("ref"),
                        "sku": sku,
                        "name": item.get("name"),
                        "category_ref": category_ref,
                        "unit_code": unit_code,
                        "is_active": bool(item.get("is_active", True)),
                        "existing_id": existing_item.id if existing_item is not None else None,
                        "source_system": source_system,
                        "source_ref": item.get("ref"),
                    },
                }
            )

        summary = {"create": 0, "update": 0, "skip": 0, "error": 0}
        for record in records:
            action = record["action"]
            summary[action] = summary.get(action, 0) + 1

        batch = await uow.machine.create_batch(
            batch_id=make_batch_id("catalog"),
            plan_id=make_plan_id("catalog"),
            domain="catalog",
            payload_format=envelope.payload_format,
            mode=envelope.mode,
            client_request_id=envelope.client_request_id,
            idempotency_key=envelope.idempotency_key,
            snapshot_id=snapshot.snapshot_id,
            status="preview_ready",
            source_client=source_client,
            payload_hash=envelope_hash,
            payload=envelope_data,
            plan={"summary": summary, "records": records},
            warnings=warnings,
            errors=errors,
            created_by_user_id=identity.user_id,
        )
        return batch

    @staticmethod
    async def apply_operations_batch(
        uow: UnitOfWork,
        *,
        batch_id: str,
        plan_id: str,
        identity: Identity,
    ):
        batch = await uow.machine.get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
        if batch.domain != "operations":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="batch domain mismatch")
        if batch.plan_id != plan_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan_id mismatch")
        if batch.status == "applied":
            return batch
        if batch.status != "preview_ready":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"batch status {batch.status} is not applicable")
        if batch.errors:
            raise SyncServerException(
                status_code=status.HTTP_409_CONFLICT,
                detail="batch preview contains errors",
                error_code="batch_plan_invalid",
                details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
            )

        batch.status = "applying"
        await uow.machine.update_batch(batch)

        summary = {"create": 0, "update": 0, "skip": 0, "error": 0}
        applied_records: list[dict] = []

        for record in batch.plan.get("records", []):
            if record.get("action") not in {"create", "update"}:
                continue
            data = record.get("data", {})
            action_name = data.get("action")
            if action_name == "operation.create_draft":
                operation_data = OperationCreate.model_validate(data.get("operation_data", {}))
                result = await OperationsService.create_operation(
                    uow=uow,
                    operation_data=operation_data,
                    user_id=identity.user_id,
                )
                operation = result["operation"]
                operation.machine_last_batch_id = batch.batch_id
                summary["create"] += 1
                applied_records.append(
                    {
                        "input_path": record.get("input_path"),
                        "action": "create",
                        "entity_type": "operation",
                        "entity_id": str(operation.id),
                        "version": operation.version,
                    }
                )
                continue

            operation_id = UUID(data["operation_id"])
            expected_version = int(data["expected_version"])
            operation = await uow.machine.get_operation_for_update(operation_id)
            if operation is None:
                raise SyncServerException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Batch plan is no longer valid for current data version.",
                    error_code="batch_plan_stale",
                    details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
                )
            if int(operation.version) != expected_version:
                raise SyncServerException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Batch plan is no longer valid for current data version.",
                    error_code="batch_plan_stale",
                    details={"batch_id": batch.batch_id, "plan_id": batch.plan_id, "operation_id": str(operation.id)},
                )

            if action_name == "operation.update_draft":
                updated_operation = await OperationsService.update_operation(
                    uow=uow,
                    operation_id=operation_id,
                    update_data=OperationUpdate.model_validate(data.get("changes", {})),
                )
                updated_operation.machine_last_batch_id = batch.batch_id
                summary["update"] += 1
                applied_records.append(
                    {
                        "input_path": record.get("input_path"),
                        "action": "update",
                        "entity_type": "operation",
                        "entity_id": str(updated_operation.id),
                        "version": updated_operation.version,
                    }
                )
                continue

            if action_name == "operation.submit":
                submitted = await OperationsService.submit_operation(
                    uow=uow,
                    operation_id=operation_id,
                    user_id=identity.user_id,
                )
                operation_obj = submitted["operation"]
                operation_obj.machine_last_batch_id = batch.batch_id
                summary["update"] += 1
                applied_records.append(
                    {
                        "input_path": record.get("input_path"),
                        "action": "update",
                        "entity_type": "operation",
                        "entity_id": str(operation_obj.id),
                        "version": operation_obj.version,
                    }
                )
                continue

            if action_name == "operation.cancel":
                cancelled = await OperationsService.cancel_operation(
                    uow=uow,
                    operation_id=operation_id,
                    user_id=identity.user_id,
                    reason=data.get("reason"),
                )
                operation_obj = cancelled["operation"]
                operation_obj.machine_last_batch_id = batch.batch_id
                summary["update"] += 1
                applied_records.append(
                    {
                        "input_path": record.get("input_path"),
                        "action": "update",
                        "entity_type": "operation",
                        "entity_id": str(operation_obj.id),
                        "version": operation_obj.version,
                    }
                )
                continue

        batch.status = "applied"
        batch.applied_at = datetime.now(UTC)
        batch.applied_by_user_id = identity.user_id
        batch.result = {"summary": summary, "records": applied_records}
        await uow.machine.update_batch(batch)
        return batch

    @staticmethod
    def batch_response_payload(batch) -> dict:
        plan = batch.plan or {}
        summary = plan.get("summary", {"create": 0, "update": 0, "skip": 0, "error": 0})
        records = plan.get("records", [])
        if batch.result and isinstance(batch.result, dict):
            summary = batch.result.get("summary", summary)
            records = batch.result.get("records", records)
        return {
            "batch_id": batch.batch_id,
            "plan_id": batch.plan_id,
            "snapshot_id": batch.snapshot_id,
            "status": batch.status,
            "summary": summary,
            "records": records,
            "warnings": batch.warnings or [],
            "errors": batch.errors or [],
            "result": batch.result,
        }

    @staticmethod
    def _can_operate_site(identity: Identity, site_id: int) -> bool:
        if identity.has_global_business_access:
            return True
        if identity.role not in WRITE_ROLES:
            return False
        return identity.can_operate_at_site(site_id)

    @staticmethod
    def _can_update_draft(identity: Identity, operation: Operation) -> bool:
        if identity.has_global_business_access:
            return True
        if not MachineService._can_operate_site(identity, operation.site_id):
            return False
        return operation.created_by_user_id == identity.user_id

    @staticmethod
    def _can_submit(identity: Identity) -> bool:
        if identity.has_global_business_access:
            return True
        return False

    @staticmethod
    def _can_cancel(identity: Identity, operation: Operation) -> bool:
        if identity.has_global_business_access:
            return True
        if operation.status == "draft" and operation.created_by_user_id == identity.user_id:
            return MachineService._can_operate_site(identity, operation.site_id)
        return False

    @staticmethod
    async def apply_catalog_batch(
        uow: UnitOfWork,
        *,
        batch_id: str,
        plan_id: str,
        identity: Identity,
    ):
        batch = await uow.machine.get_batch(batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="batch not found")
        if batch.domain != "catalog":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="batch domain mismatch")
        if batch.plan_id != plan_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="plan_id mismatch")
        if batch.status == "applied":
            return batch
        if batch.status != "preview_ready":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"batch status {batch.status} is not applicable")
        if batch.errors:
            raise SyncServerException(
                status_code=status.HTTP_409_CONFLICT,
                detail="batch preview contains errors",
                error_code="batch_plan_invalid",
                details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
            )

        snapshot = await uow.machine.get_snapshot(batch.snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found")

        batch.status = "applying"
        await uow.machine.update_batch(batch)

        summary = {"create": 0, "update": 0, "skip": 0, "error": 0}
        applied_records: list[dict] = []
        records = list(batch.plan.get("records", []))
        category_records = [record for record in records if record.get("entity_type") == "category" and record.get("action") in {"create", "update"}]
        item_records = [record for record in records if record.get("entity_type") == "item" and record.get("action") in {"create", "update"}]
        ref_to_category_id: dict[str, int] = {}

        pending_records = list(category_records)
        while pending_records:
            progressed = False
            still_pending: list[dict] = []
            for record in pending_records:
                data = record.get("data", {})
                parent_ref = data.get("parent_ref")
                if parent_ref and parent_ref not in ref_to_category_id:
                    still_pending.append(record)
                    continue

                existing_id = data.get("existing_id")
                if existing_id is not None:
                    category = await uow.catalog.get_category_by_id(existing_id)
                    if category is None or category.updated_at > snapshot.created_at:
                        raise SyncServerException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Batch plan is no longer valid for current data version.",
                            error_code="batch_plan_stale",
                            details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
                        )
                    category.name = data.get("name")
                    category.normalized_name = normalize_text(category.name)
                    category.code = data.get("code")
                    category.parent_id = ref_to_category_id.get(parent_ref) if parent_ref else None
                    category.machine_last_batch_id = batch.batch_id
                    await uow.catalog.update_category(category)
                    action = "update"
                else:
                    category = Category(
                        name=data.get("name"),
                        normalized_name=normalize_text(data.get("name")),
                        code=data.get("code"),
                        parent_id=ref_to_category_id.get(parent_ref) if parent_ref else None,
                        is_active=True,
                        machine_last_batch_id=batch.batch_id,
                    )
                    category = await uow.catalog.create_category(category)
                    action = "create"

                ref = data.get("ref")
                if ref:
                    ref_to_category_id[ref] = int(category.id)
                summary[action] += 1
                applied_records.append(
                    {
                        "input_path": record["input_path"],
                        "action": action,
                        "entity_type": "category",
                        "entity_id": category.id,
                    }
                )
                progressed = True
            if not progressed and still_pending:
                raise SyncServerException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Unresolved category dependencies in batch payload",
                    error_code="batch_plan_invalid",
                    details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
                )
            pending_records = still_pending

        for record in item_records:
            data = record.get("data", {})
            existing_id = data.get("existing_id")
            category_ref = data.get("category_ref")
            category_id = ref_to_category_id.get(category_ref)
            if category_id is None:
                raise SyncServerException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Batch plan is no longer valid for current data version.",
                    error_code="batch_plan_stale",
                    details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
                )

            unit_code = data.get("unit_code")
            unit = await uow.catalog.get_unit_by_code(unit_code)
            if unit is None:
                unit = await uow.catalog.get_unit_by_symbol(unit_code)
            if unit is None:
                raise SyncServerException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Unit not found for code={unit_code}",
                    error_code="batch_plan_invalid",
                    details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
                )

            if existing_id is not None:
                item = await uow.catalog.get_item_by_id(existing_id)
                if item is None or item.updated_at > snapshot.created_at:
                    raise SyncServerException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Batch plan is no longer valid for current data version.",
                        error_code="batch_plan_stale",
                        details={"batch_id": batch.batch_id, "plan_id": batch.plan_id},
                    )
                item.sku = data.get("sku")
                item.name = data.get("name")
                item.normalized_name = normalize_text(data.get("name"))
                item.category_id = category_id
                item.unit_id = unit.id
                item.is_active = bool(data.get("is_active", True))
                item.source_system = data.get("source_system")
                item.source_ref = data.get("source_ref")
                item.import_batch_id = batch.batch_id
                item.machine_last_batch_id = batch.batch_id
                await uow.catalog.update_item(item)
                action = "update"
                entity_id = item.id
            else:
                item = Item(
                    sku=data.get("sku"),
                    name=data.get("name"),
                    normalized_name=normalize_text(data.get("name")),
                    category_id=category_id,
                    unit_id=unit.id,
                    is_active=bool(data.get("is_active", True)),
                    source_system=data.get("source_system"),
                    source_ref=data.get("source_ref"),
                    import_batch_id=batch.batch_id,
                    machine_last_batch_id=batch.batch_id,
                )
                item = await uow.catalog.create_item(item)
                action = "create"
                entity_id = item.id

            summary[action] += 1
            applied_records.append(
                {
                    "input_path": record["input_path"],
                    "action": action,
                    "entity_type": "item",
                    "entity_id": entity_id,
                }
            )

        batch.status = "applied"
        batch.applied_at = datetime.now(UTC)
        batch.applied_by_user_id = identity.user_id
        batch.result = {
            "summary": summary,
            "records": applied_records,
        }
        await uow.machine.update_batch(batch)
        return batch

    @staticmethod
    async def preview_operations_batch(
        uow: UnitOfWork,
        *,
        envelope: MachineBatchEnvelope,
        identity: Identity,
        source_client: str | None,
    ):
        if envelope.domain != "operations":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="domain must be operations")

        existing = await uow.machine.get_batch_by_idempotency_key(envelope.idempotency_key)
        envelope_data = envelope.model_dump(mode="json")
        envelope_hash = payload_hash(envelope_data)
        if existing is not None:
            if existing.payload_hash != envelope_hash:
                raise SyncServerException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used with different payload",
                    error_code="idempotency_key_conflict",
                    details={"idempotency_key": envelope.idempotency_key, "batch_id": existing.batch_id},
                )
            return existing

        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=None,
            created_by_user_id=identity.user_id,
        )

        actions = envelope.payload.get("actions", [])
        records: list[dict] = []
        warnings: list[dict] = []
        errors: list[dict] = []
        summary = {"create": 0, "update": 0, "skip": 0, "error": 0}

        for index, action in enumerate(actions):
            input_path = f"actions[{index}]"
            action_name = action.get("action")
            if action_name not in {"operation.create_draft", "operation.update_draft", "operation.submit", "operation.cancel"}:
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "operation",
                        "match_key": None,
                    }
                )
                errors.append({"input_path": input_path, "code": "unsupported_action", "message": f"unsupported action {action_name}"})
                summary["error"] += 1
                continue

            if action_name == "operation.create_draft":
                try:
                    operation_data = OperationCreate.model_validate(action.get("data", {}))
                except Exception as exc:  # noqa: BLE001
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": None,
                        }
                    )
                    errors.append({"input_path": input_path, "code": "invalid_operation_data", "message": str(exc)})
                    summary["error"] += 1
                    continue

                if not MachineService._can_operate_site(identity, operation_data.site_id):
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": f"site_id={operation_data.site_id}",
                        }
                    )
                    errors.append({"input_path": input_path, "code": "permission_denied", "message": "no operate access to site"})
                    summary["error"] += 1
                    continue

                records.append(
                    {
                        "input_path": input_path,
                        "action": "create",
                        "entity_type": "operation",
                        "match_key": None,
                        "data": {"action": action_name, "operation_data": action.get("data", {})},
                    }
                )
                summary["create"] += 1
                continue

            operation_id = action.get("operation_id")
            expected_version = action.get("expected_version")
            if not operation_id or expected_version is None:
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "operation",
                        "match_key": f"operation_id={operation_id}",
                    }
                )
                errors.append(
                    {"input_path": input_path, "code": "missing_required_fields", "message": "operation_id and expected_version are required"}
                )
                summary["error"] += 1
                continue
            try:
                operation_uuid = UUID(operation_id)
            except ValueError:
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "operation",
                        "match_key": f"operation_id={operation_id}",
                    }
                )
                errors.append({"input_path": input_path, "code": "invalid_operation_id", "message": "operation_id must be UUID"})
                summary["error"] += 1
                continue

            operation = await uow.operations.get_operation_by_id(operation_uuid)
            if operation is None:
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "operation",
                        "match_key": f"operation_id={operation_id}",
                    }
                )
                errors.append({"input_path": input_path, "code": "operation_not_found", "message": "operation not found"})
                summary["error"] += 1
                continue

            if int(operation.version) != int(expected_version):
                records.append(
                    {
                        "input_path": input_path,
                        "action": "error",
                        "entity_type": "operation",
                        "match_key": f"operation_id={operation_id}",
                    }
                )
                errors.append(
                    {
                        "input_path": input_path,
                        "code": "optimistic_lock_failed",
                        "message": f"expected_version={expected_version}, actual_version={operation.version}",
                    }
                )
                summary["error"] += 1
                continue

            if action_name == "operation.update_draft":
                if operation.status != "draft":
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": f"operation_id={operation_id}",
                        }
                    )
                    errors.append({"input_path": input_path, "code": "invalid_status", "message": "only draft operations can be updated"})
                    summary["error"] += 1
                    continue
                if not MachineService._can_update_draft(identity, operation):
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": f"operation_id={operation_id}",
                        }
                    )
                    errors.append({"input_path": input_path, "code": "permission_denied", "message": "cannot update this draft operation"})
                    summary["error"] += 1
                    continue
                records.append(
                    {
                        "input_path": input_path,
                        "action": "update",
                        "entity_type": "operation",
                        "match_key": f"operation_id={operation_id}",
                        "data": {
                            "action": action_name,
                            "operation_id": operation_id,
                            "expected_version": expected_version,
                            "changes": action.get("changes", {}),
                        },
                    }
                )
                summary["update"] += 1
                continue

            if action_name == "operation.submit":
                if operation.status != "draft":
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": f"operation_id={operation_id}",
                        }
                    )
                    errors.append({"input_path": input_path, "code": "invalid_status", "message": "only draft operations can be submitted"})
                    summary["error"] += 1
                    continue
                if not MachineService._can_submit(identity):
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": f"operation_id={operation_id}",
                        }
                    )
                    errors.append({"input_path": input_path, "code": "permission_denied", "message": "submit requires chief_storekeeper or root"})
                    summary["error"] += 1
                    continue
                records.append(
                    {
                        "input_path": input_path,
                        "action": "update",
                        "entity_type": "operation",
                        "match_key": f"operation_id={operation_id}",
                        "data": {
                            "action": action_name,
                            "operation_id": operation_id,
                            "expected_version": expected_version,
                        },
                    }
                )
                summary["update"] += 1
                continue

            if action_name == "operation.cancel":
                if operation.status not in {"draft", "submitted"}:
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": f"operation_id={operation_id}",
                        }
                    )
                    errors.append({"input_path": input_path, "code": "invalid_status", "message": "only draft/submitted operations can be cancelled"})
                    summary["error"] += 1
                    continue
                if not MachineService._can_cancel(identity, operation):
                    records.append(
                        {
                            "input_path": input_path,
                            "action": "error",
                            "entity_type": "operation",
                            "match_key": f"operation_id={operation_id}",
                        }
                    )
                    errors.append({"input_path": input_path, "code": "permission_denied", "message": "cancel permission denied"})
                    summary["error"] += 1
                    continue
                records.append(
                    {
                        "input_path": input_path,
                        "action": "update",
                        "entity_type": "operation",
                        "match_key": f"operation_id={operation_id}",
                        "data": {
                            "action": action_name,
                            "operation_id": operation_id,
                            "expected_version": expected_version,
                            "reason": action.get("reason"),
                        },
                    }
                )
                summary["update"] += 1

        batch = await uow.machine.create_batch(
            batch_id=make_batch_id("operations"),
            plan_id=make_plan_id("operations"),
            domain="operations",
            payload_format=envelope.payload_format,
            mode=envelope.mode,
            client_request_id=envelope.client_request_id,
            idempotency_key=envelope.idempotency_key,
            snapshot_id=snapshot.snapshot_id,
            status="preview_ready",
            source_client=source_client,
            payload_hash=envelope_hash,
            payload=envelope_data,
            plan={"summary": summary, "records": records},
            warnings=warnings,
            errors=errors,
            created_by_user_id=identity.user_id,
        )
        return batch
