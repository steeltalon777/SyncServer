from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models.category import Category
from app.models.item import Item
from app.models.machine import MachineBatch, MachineReport, MachineSnapshot
from app.models.operation import Operation
from app.models.unit import Unit


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


class MachineRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_dataset_counts(self, snapshot_at: datetime) -> dict[str, int]:
        items_count = (
            await self.session.execute(select(func.count()).select_from(Item).where(Item.updated_at <= snapshot_at))
        ).scalar_one()
        categories_count = (
            await self.session.execute(select(func.count()).select_from(Category).where(Category.updated_at <= snapshot_at))
        ).scalar_one()
        units_count = (
            await self.session.execute(select(func.count()).select_from(Unit).where(Unit.updated_at <= snapshot_at))
        ).scalar_one()
        operations_count = (
            await self.session.execute(select(func.count()).select_from(Operation).where(Operation.updated_at <= snapshot_at))
        ).scalar_one()
        return {
            "items": int(items_count),
            "categories": int(categories_count),
            "units": int(units_count),
            "operations": int(operations_count),
        }

    async def create_snapshot(
        self,
        *,
        snapshot_id: str,
        schema_version: str,
        datasets: list[str],
        counts: dict[str, int],
        created_by_user_id: UUID | None,
    ) -> MachineSnapshot:
        snapshot = MachineSnapshot(
            snapshot_id=snapshot_id,
            schema_version=schema_version,
            datasets=datasets,
            counts=counts,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> MachineSnapshot | None:
        result = await self.session.execute(
            select(MachineSnapshot).where(MachineSnapshot.snapshot_id == snapshot_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_snapshot(self) -> MachineSnapshot | None:
        result = await self.session.execute(
            select(MachineSnapshot).order_by(MachineSnapshot.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def create_report(
        self,
        *,
        report_id: str,
        report_type: str,
        snapshot_id: str,
        created_by_user_id: UUID,
        summary: str,
        findings: list[dict],
        references: list[str],
    ) -> MachineReport:
        report = MachineReport(
            report_id=report_id,
            report_type=report_type,
            snapshot_id=snapshot_id,
            created_by_user_id=created_by_user_id,
            summary=summary,
            findings=findings,
            references=references,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def get_report(self, report_id: str) -> MachineReport | None:
        result = await self.session.execute(
            select(MachineReport).where(MachineReport.report_id == report_id)
        )
        return result.scalar_one_or_none()

    async def create_batch(
        self,
        *,
        batch_id: str,
        plan_id: str,
        domain: str,
        payload_format: str,
        mode: str,
        client_request_id: str | None,
        idempotency_key: str,
        snapshot_id: str,
        status: str,
        source_client: str | None,
        payload_hash: str,
        payload: dict,
        plan: dict,
        warnings: list[dict],
        errors: list[dict],
        created_by_user_id: UUID,
    ) -> MachineBatch:
        batch = MachineBatch(
            batch_id=batch_id,
            plan_id=plan_id,
            domain=domain,
            payload_format=payload_format,
            mode=mode,
            client_request_id=client_request_id,
            idempotency_key=idempotency_key,
            snapshot_id=snapshot_id,
            status=status,
            source_client=source_client,
            payload_hash=payload_hash,
            payload=payload,
            plan=plan,
            warnings=warnings,
            errors=errors,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(batch)
        await self.session.flush()
        return batch

    async def get_batch(self, batch_id: str) -> MachineBatch | None:
        result = await self.session.execute(select(MachineBatch).where(MachineBatch.batch_id == batch_id))
        return result.scalar_one_or_none()

    async def get_batch_by_idempotency_key(self, idempotency_key: str) -> MachineBatch | None:
        result = await self.session.execute(
            select(MachineBatch).where(MachineBatch.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def update_batch(self, batch: MachineBatch) -> MachineBatch:
        await self.session.flush()
        return batch

    async def list_machine_items(
        self,
        *,
        snapshot_at: datetime,
        limit: int,
        offset: int,
    ) -> list[dict]:
        stmt = (
            select(
                Item.id.label("id"),
                Item.sku.label("sku"),
                Item.name.label("name"),
                Item.normalized_name.label("normalized_name"),
                Item.unit_id.label("unit_id"),
                Unit.code.label("unit_code"),
                Unit.symbol.label("unit_symbol"),
                Unit.name.label("unit_name"),
                Item.category_id.label("category_id"),
                Category.code.label("category_code"),
                Category.name.label("category_name"),
                Item.is_active.label("is_active"),
                Item.updated_at.label("updated_at"),
                Item.source_system.label("source_system"),
                Item.source_ref.label("source_ref"),
                Item.import_batch_id.label("import_batch_id"),
            )
            .select_from(Item)
            .join(Unit, Unit.id == Item.unit_id)
            .join(Category, Category.id == Item.category_id)
            .where(Item.updated_at <= snapshot_at)
            .order_by(Item.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        category_path_map = await self._build_category_path_map(
            [int(row.category_id) for row in rows],
            snapshot_at=snapshot_at,
        )
        payload: list[dict] = []
        for row in rows:
            payload.append(
                {
                    "id": int(row.id),
                    "sku": row.sku,
                    "name": row.name,
                    "normalized_name": row.normalized_name or normalize_text(row.name),
                    "unit_id": int(row.unit_id),
                    "unit_code": row.unit_code or row.unit_symbol,
                    "unit_name": row.unit_name,
                    "category_id": int(row.category_id),
                    "category_code": row.category_code,
                    "category_name": row.category_name,
                    "category_path": category_path_map.get(int(row.category_id), row.category_name),
                    "is_active": bool(row.is_active),
                    "updated_at": row.updated_at,
                    "source_system": row.source_system,
                    "source_ref": row.source_ref,
                    "import_batch_id": row.import_batch_id,
                }
            )
        return payload

    async def list_machine_categories(
        self,
        *,
        snapshot_at: datetime,
        limit: int,
        offset: int,
    ) -> list[dict]:
        parent = aliased(Category)
        stmt = (
            select(
                Category.id.label("id"),
                Category.code.label("code"),
                Category.name.label("name"),
                Category.normalized_name.label("normalized_name"),
                Category.parent_id.label("parent_id"),
                parent.code.label("parent_code"),
                Category.is_active.label("is_active"),
                Category.updated_at.label("updated_at"),
            )
            .select_from(Category)
            .outerjoin(parent, parent.id == Category.parent_id)
            .where(Category.updated_at <= snapshot_at)
            .order_by(Category.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        category_ids = [int(row.id) for row in rows]
        path_map = await self._build_category_path_map(category_ids, snapshot_at=snapshot_at)
        payload: list[dict] = []
        for row in rows:
            path = path_map.get(int(row.id), row.name)
            payload.append(
                {
                    "id": int(row.id),
                    "code": row.code,
                    "name": row.name,
                    "normalized_name": row.normalized_name or normalize_text(row.name),
                    "parent_id": int(row.parent_id) if row.parent_id is not None else None,
                    "parent_code": row.parent_code,
                    "path": path,
                    "level": max(path.count(" / "), 0),
                    "is_active": bool(row.is_active),
                    "updated_at": row.updated_at,
                }
            )
        return payload

    async def list_machine_units(
        self,
        *,
        snapshot_at: datetime,
        limit: int,
        offset: int,
    ) -> list[dict]:
        stmt = (
            select(
                Unit.id.label("id"),
                Unit.code.label("code"),
                Unit.name.label("name"),
                Unit.symbol.label("symbol"),
                Unit.is_active.label("is_active"),
                Unit.updated_at.label("updated_at"),
            )
            .where(Unit.updated_at <= snapshot_at)
            .order_by(Unit.id)
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "id": int(row.id),
                "code": row.code or row.symbol,
                "name": row.name,
                "symbol": row.symbol,
                "is_active": bool(row.is_active),
                "updated_at": row.updated_at,
            }
            for row in rows
        ]

    async def list_machine_operations(
        self,
        *,
        snapshot_at: datetime,
        user_site_ids: list[int] | None,
        limit: int,
        offset: int,
    ) -> list[dict]:
        stmt = (
            select(Operation)
            .options(selectinload(Operation.lines))
            .where(Operation.updated_at <= snapshot_at)
            .order_by(Operation.created_at.desc(), Operation.id)
            .offset(offset)
            .limit(limit)
        )
        if user_site_ids is not None:
            if not user_site_ids:
                return []
            stmt = stmt.where(Operation.site_id.in_(user_site_ids))
        operations = list((await self.session.execute(stmt)).scalars().all())
        return [self._operation_to_record(operation) for operation in operations]

    async def get_machine_operation(
        self,
        *,
        operation_id: UUID,
        snapshot_at: datetime,
    ) -> dict | None:
        stmt = (
            select(Operation)
            .options(selectinload(Operation.lines))
            .where(Operation.id == operation_id, Operation.updated_at <= snapshot_at)
        )
        operation = (await self.session.execute(stmt)).scalar_one_or_none()
        if operation is None:
            return None
        return self._operation_to_record(operation)

    async def find_duplicate_item_candidates(
        self,
        *,
        snapshot_at: datetime,
        limit: int,
        offset: int,
    ) -> list[dict]:
        stmt = (
            select(
                Item.id.label("id"),
                Item.sku.label("sku"),
                Item.name.label("name"),
                Item.normalized_name.label("normalized_name"),
                Item.unit_id.label("unit_id"),
                Item.category_id.label("category_id"),
                Category.code.label("category_code"),
                Unit.code.label("unit_code"),
                Unit.symbol.label("unit_symbol"),
            )
            .select_from(Item)
            .join(Category, Category.id == Item.category_id)
            .join(Unit, Unit.id == Item.unit_id)
            .where(Item.updated_at <= snapshot_at)
            .order_by(Item.id)
        )
        rows = (await self.session.execute(stmt)).all()
        groups: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
        for row in rows:
            normalized_name = row.normalized_name or normalize_text(row.name)
            key = (normalized_name, int(row.unit_id), int(row.category_id))
            groups[key].append(
                {
                    "id": int(row.id),
                    "sku": row.sku,
                    "name": row.name,
                    "category_code": row.category_code,
                    "unit_code": row.unit_code or row.unit_symbol,
                }
            )

        payload: list[dict] = []
        for (normalized_name, _unit_id, _category_id), records in sorted(groups.items(), key=lambda value: value[0]):
            if len(records) < 2:
                continue
            digest = hashlib.sha1("|".join(str(record["id"]) for record in records).encode("utf-8")).hexdigest()[:12]
            payload.append(
                {
                    "group_id": f"dup_items_{digest}",
                    "score": 0.97,
                    "reason_codes": [
                        "same_normalized_name",
                        "same_unit",
                        "same_category_branch",
                    ],
                    "normalized_name": normalized_name,
                    "records": records,
                }
            )
        return payload[offset:offset + limit]

    async def find_duplicate_category_candidates(
        self,
        *,
        snapshot_at: datetime,
        limit: int,
        offset: int,
    ) -> list[dict]:
        stmt = (
            select(
                Category.id.label("id"),
                Category.code.label("code"),
                Category.name.label("name"),
                Category.normalized_name.label("normalized_name"),
                Category.parent_id.label("parent_id"),
            )
            .where(Category.updated_at <= snapshot_at)
            .order_by(Category.id)
        )
        rows = (await self.session.execute(stmt)).all()
        groups: dict[tuple[str, int | None], list[dict]] = defaultdict(list)
        for row in rows:
            normalized_name = row.normalized_name or normalize_text(row.name)
            key = (normalized_name, int(row.parent_id) if row.parent_id is not None else None)
            groups[key].append(
                {
                    "id": int(row.id),
                    "code": row.code,
                    "name": row.name,
                    "parent_id": int(row.parent_id) if row.parent_id is not None else None,
                }
            )

        payload: list[dict] = []
        for (_normalized_name, _parent_id), records in sorted(groups.items(), key=lambda value: (value[0][0], value[0][1] or 0)):
            if len(records) < 2:
                continue
            digest = hashlib.sha1("|".join(str(record["id"]) for record in records).encode("utf-8")).hexdigest()[:12]
            payload.append(
                {
                    "group_id": f"dup_categories_{digest}",
                    "score": 0.96,
                    "reason_codes": [
                        "same_normalized_name",
                        "same_parent",
                    ],
                    "records": records,
                }
            )
        return payload[offset:offset + limit]

    async def find_integrity_issues(
        self,
        *,
        snapshot_at: datetime,
        limit: int,
        offset: int,
    ) -> list[dict]:
        issues: list[dict] = []

        active_item_with_inactive_unit_rows = (
            await self.session.execute(
                select(Item.id, Unit.id)
                .select_from(Item)
                .join(Unit, Unit.id == Item.unit_id)
                .where(
                    Item.updated_at <= snapshot_at,
                    Unit.updated_at <= snapshot_at,
                    Item.is_active.is_(True),
                    Unit.is_active.is_(False),
                )
            )
        ).all()
        for row in active_item_with_inactive_unit_rows:
            issues.append(
                {
                    "issue_id": f"active_item_inactive_unit_{row.id}",
                    "issue_type": "active_item_with_inactive_unit",
                    "severity": "high",
                    "ref_ids": [f"item:{int(row.id)}", f"unit:{int(row[1])}"],
                }
            )

        conflicting_import_key_rows = (
            await self.session.execute(
                select(Item.source_system, Item.source_ref, func.count(Item.id))
                .where(
                    Item.updated_at <= snapshot_at,
                    Item.source_system.is_not(None),
                    Item.source_ref.is_not(None),
                )
                .group_by(Item.source_system, Item.source_ref)
                .having(func.count(Item.id) > 1)
            )
        ).all()
        for source_system, source_ref, count in conflicting_import_key_rows:
            key = hashlib.sha1(f"{source_system}|{source_ref}".encode("utf-8")).hexdigest()[:10]
            issues.append(
                {
                    "issue_id": f"conflicting_import_keys_{key}",
                    "issue_type": "conflicting_import_keys",
                    "severity": "medium",
                    "ref_ids": [f"source:{source_system}:{source_ref}"],
                    "details": {"count": int(count)},
                }
            )

        categories = list(
            (
                await self.session.execute(
                    select(Category.id, Category.parent_id)
                    .where(Category.updated_at <= snapshot_at)
                )
            ).all()
        )
        parent_map = {int(row.id): (int(row.parent_id) if row.parent_id is not None else None) for row in categories}
        for category_id, parent_id in parent_map.items():
            seen: set[int] = set()
            current = parent_id
            while current is not None:
                if current == category_id:
                    issues.append(
                        {
                            "issue_id": f"category_cycle_{category_id}",
                            "issue_type": "category_cycle_candidate",
                            "severity": "high",
                            "ref_ids": [f"category:{category_id}"],
                        }
                    )
                    break
                if current in seen:
                    break
                seen.add(current)
                current = parent_map.get(current)

        parent_category = aliased(Category)
        missing_parent_rows = (
            await self.session.execute(
                select(Category.id, Category.parent_id)
                .select_from(Category)
                .outerjoin(parent_category, Category.parent_id == parent_category.id)
                .where(Category.parent_id.is_not(None), parent_category.id.is_(None))
            )
        ).all()
        for row in missing_parent_rows:
            if row.parent_id is None:
                continue
            if int(row.parent_id) not in parent_map:
                issues.append(
                    {
                        "issue_id": f"missing_parent_{int(row.id)}",
                        "issue_type": "missing_parent_reference",
                        "severity": "high",
                        "ref_ids": [f"category:{int(row.id)}", f"category:{int(row.parent_id)}"],
                    }
                )

        return issues[offset:offset + limit]

    async def get_operation_for_update(self, operation_id: UUID) -> Operation | None:
        stmt = (
            select(Operation)
            .where(Operation.id == operation_id)
            .options(selectinload(Operation.lines))
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_units_by_codes(self, codes: list[str]) -> list[Unit]:
        if not codes:
            return []
        result = await self.session.execute(
            select(Unit).where(or_(Unit.code.in_(codes), Unit.symbol.in_(codes)))
        )
        return list(result.scalars().all())

    async def _build_category_path_map(
        self,
        category_ids: list[int],
        *,
        snapshot_at: datetime,
    ) -> dict[int, str]:
        if not category_ids:
            return {}

        categories = await self._load_categories_with_ancestors(category_ids, snapshot_at=snapshot_at)
        categories_by_id = {category.id: category for category in categories}
        path_map: dict[int, str] = {}
        for category_id in category_ids:
            current_id = category_id
            seen: set[int] = set()
            names: list[str] = []
            while current_id is not None and current_id not in seen:
                seen.add(current_id)
                category = categories_by_id.get(current_id)
                if category is None:
                    break
                names.append(category.name)
                current_id = category.parent_id
            names.reverse()
            path_map[category_id] = " / ".join(names) if names else ""
        return path_map

    async def _load_categories_with_ancestors(
        self,
        category_ids: list[int],
        *,
        snapshot_at: datetime,
    ) -> list[Category]:
        pending_ids = set(category_ids)
        loaded: dict[int, Category] = {}
        while pending_ids:
            stmt = (
                select(Category)
                .where(Category.id.in_(pending_ids), Category.updated_at <= snapshot_at)
            )
            batch = list((await self.session.execute(stmt)).scalars().all())
            if not batch:
                break
            for category in batch:
                loaded[category.id] = category
            pending_ids = {
                category.parent_id
                for category in batch
                if category.parent_id is not None and category.parent_id not in loaded
            }
        return list(loaded.values())

    def _operation_to_record(self, operation: Operation) -> dict:
        return {
            "id": str(operation.id),
            "status": operation.status,
            "operation_type": operation.operation_type,
            "site_id": operation.site_id,
            "source_site_id": operation.source_site_id,
            "destination_site_id": operation.destination_site_id,
            "created_at": operation.created_at,
            "effective_at": operation.effective_at,
            "applied_at": operation.submitted_at,
            "updated_at": operation.updated_at,
            "created_by": str(operation.created_by_user_id),
            "line_count": len(operation.lines),
            "notes": operation.notes,
            "version": operation.version,
            "lines": [
                {
                    "line_number": line.line_number,
                    "item_id": line.item_id,
                    "qty": line.qty,
                    "comment": line.comment,
                }
                for line in sorted(operation.lines, key=lambda x: x.line_number)
            ],
        }
