from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.identity import Identity
from app.models import Balance, Category, InventorySubject, Item, Operation, OperationLine, Unit
from app.schemas.catalog import (
    BatchChangeCategoryPayload,
    BatchChangeCreate,
    BatchChangeDelete,
    BatchChangeItemPayload,
    BatchChangeMerge,
    BatchChangeMergePayload,
    BatchChangeUnitPayload,
    BatchChangeUpdate,
    BatchChangeUpdatePayload,
    CatalogBatchRequest,
    CategoryCreateRequest,
    ItemCreateRequest,
    UnitCreateRequest,
    UnitUpdateRequest,
)
from app.services.catalog_admin_service import CatalogAdminService
from app.services.uow import UnitOfWork


class TestBatchMerge:

    @pytest.mark.asyncio
    async def test_merge_item_through_batch(self, uow: UnitOfWork, admin_user, site):
        """Item merge through batch: balance transfer, source deactivated."""
        service = CatalogAdminService()

        unit = await service.create_unit(uow, UnitCreateRequest(name="Merge Item Unit", symbol="MIU"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Merge Item Cat"))
        source = await service.create_item(
            uow, ItemCreateRequest(name="Source Item", unit_id=unit.id, category_id=cat.id),
        )
        target = await service.create_item(
            uow, ItemCreateRequest(name="Target Item", unit_id=unit.id, category_id=cat.id),
        )

        source_subject = InventorySubject(subject_type="catalog_item", item_id=source.id)
        uow.session.add(source_subject)
        await uow.session.flush()

        balance = Balance(
            site_id=site.id,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("10.000"),
        )
        uow.session.add(balance)
        await uow.session.flush()

        identity = Identity(user=admin_user, device=None, scopes=[])

        batch = CatalogBatchRequest(
            client_batch_id=f"merge-item-{uuid4().hex[:8]}",
            mode="atomic",
            changes=[
                BatchChangeMerge(
                    local_id="m1",
                    entity_type="item",
                    entity_id=source.id,
                    payload=BatchChangeMergePayload(
                        target_entity_id=target.id,
                        comment="merge through batch",
                    ),
                ),
            ],
        )

        results, summary = await service.apply_batch(uow, batch, identity)

        assert len(results) == 1
        assert results[0].status == "applied"
        assert results[0].action == "merge"
        assert summary["merge"] == 1
        assert summary["error"] == 0

        # Source deactivated
        source_after = await uow.catalog.get_item_by_id(source.id)
        assert source_after is not None
        assert source_after.is_active is False
        assert source_after.merged_into_id == target.id
        assert source_after.merge_comment == "merge through batch"

    @pytest.mark.asyncio
    async def test_merge_category_through_batch(self, uow: UnitOfWork, admin_user, site):
        """Category merge through batch: items moved, source deactivated."""
        service = CatalogAdminService()

        unit = await service.create_unit(uow, UnitCreateRequest(name="Merge Cat Unit", symbol="MCU"))
        source_cat = await service.create_category(
            uow, CategoryCreateRequest(name="Source Category"),
        )
        target_cat = await service.create_category(
            uow, CategoryCreateRequest(name="Target Category"),
        )
        item_in_source = await service.create_item(
            uow, ItemCreateRequest(
                name="Item in Source", unit_id=unit.id, category_id=source_cat.id,
            ),
        )

        identity = Identity(user=admin_user, device=None, scopes=[])

        batch = CatalogBatchRequest(
            client_batch_id=f"merge-cat-{uuid4().hex[:8]}",
            mode="atomic",
            changes=[
                BatchChangeMerge(
                    local_id="m1",
                    entity_type="category",
                    entity_id=source_cat.id,
                    payload=BatchChangeMergePayload(
                        target_entity_id=target_cat.id,
                        comment="category merge through batch",
                    ),
                ),
            ],
        )

        results, summary = await service.apply_batch(uow, batch, identity)

        assert len(results) == 1
        assert results[0].status == "applied"
        assert results[0].action == "merge"
        assert summary["merge"] == 1
        assert summary["error"] == 0

        # Source deactivated
        source_after = await uow.catalog.get_category_by_id(source_cat.id)
        assert source_after is not None
        assert source_after.is_active is False
        assert source_after.merged_into_id == target_cat.id

        # Item moved to target category
        from sqlalchemy import select as sa_select

        stmt = await uow.session.execute(
            sa_select(Item).where(Item.id == item_in_source.id).execution_options(populate_existing=True)
        )
        item_fresh = stmt.scalar_one()
        assert item_fresh.category_id == target_cat.id

    @pytest.mark.asyncio
    async def test_merge_in_batch_with_create(self, uow: UnitOfWork, admin_user, site):
        """Create new items in batch and merge existing items — both succeed."""
        service = CatalogAdminService()

        unit = await service.create_unit(uow, UnitCreateRequest(name="Combine Unit", symbol="CBU"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Combine Cat"))

        source = await service.create_item(
            uow, ItemCreateRequest(name="Source Item", unit_id=unit.id, category_id=cat.id),
        )
        target = await service.create_item(
            uow, ItemCreateRequest(name="Target Item", unit_id=unit.id, category_id=cat.id),
        )

        identity = Identity(user=admin_user, device=None, scopes=[])

        batch = CatalogBatchRequest(
            client_batch_id=f"combine-{uuid4().hex[:8]}",
            mode="atomic",
            changes=[
                BatchChangeCreate(
                    local_id="u1",
                    entity_type="unit",
                    payload=BatchChangeUnitPayload(name="New Unit", symbol="NU"),
                ),
                BatchChangeCreate(
                    local_id="c1",
                    entity_type="category",
                    payload=BatchChangeCategoryPayload(
                        name="New Category",
                    ),
                ),
                BatchChangeMerge(
                    local_id="m1",
                    entity_type="item",
                    entity_id=source.id,
                    payload=BatchChangeMergePayload(
                        target_entity_id=target.id,
                        comment="merge in batch with create",
                    ),
                ),
            ],
        )

        results, summary = await service.apply_batch(uow, batch, identity)

        assert summary["create"] == 2
        assert summary["merge"] == 1
        assert summary["error"] == 0

        merge_records = [r for r in results if r.action == "merge"]
        assert len(merge_records) == 1
        assert merge_records[0].status == "applied"
        assert merge_records[0].entity_id == source.id

    @pytest.mark.asyncio
    async def test_merge_invalid_target_returns_error(self, uow: UnitOfWork, admin_user, site):
        """Merge into non-existent target returns error; batch does not crash."""
        service = CatalogAdminService()

        unit = await service.create_unit(uow, UnitCreateRequest(name="Error Unit", symbol="ERU"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Error Cat"))
        source = await service.create_item(
            uow, ItemCreateRequest(name="Source Item", unit_id=unit.id, category_id=cat.id),
        )

        identity = Identity(user=admin_user, device=None, scopes=[])

        batch = CatalogBatchRequest(
            client_batch_id=f"err-target-{uuid4().hex[:8]}",
            mode="atomic",
            changes=[
                BatchChangeMerge(
                    local_id="m1",
                    entity_type="item",
                    entity_id=source.id,
                    payload=BatchChangeMergePayload(target_entity_id=99999),
                ),
            ],
        )

        results, summary = await service.apply_batch(uow, batch, identity)

        assert summary["merge"] == 0
        assert summary["error"] == 1
        assert len(results) == 1
        assert results[0].status == "error"
        assert results[0].error_code == "404"

    @pytest.mark.asyncio
    async def test_merge_does_not_break_regular_actions(self, uow: UnitOfWork, admin_user, site):
        """Batch with create + update + merge + delete — all actions executed."""
        service = CatalogAdminService()

        unit = await service.create_unit(uow, UnitCreateRequest(name="Mixed Unit", symbol="MXU"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Mixed Cat"))
        source = await service.create_item(
            uow, ItemCreateRequest(name="Source Item", unit_id=unit.id, category_id=cat.id),
        )
        target = await service.create_item(
            uow, ItemCreateRequest(name="Target Item", unit_id=unit.id, category_id=cat.id),
        )
        item_to_update = await service.create_item(
            uow, ItemCreateRequest(name="Item To Update", unit_id=unit.id, category_id=cat.id),
        )
        unit_to_delete = await service.create_unit(
            uow, UnitCreateRequest(name="To Delete", symbol="TDL"),
        )
        await service.update_unit(
            uow, unit_to_delete.id, UnitUpdateRequest(is_active=False),
            updated_by_user_id=admin_user.id,
        )

        identity = Identity(user=admin_user, device=None, scopes=[])

        batch = CatalogBatchRequest(
            client_batch_id=f"mixed-{uuid4().hex[:8]}",
            mode="atomic",
            changes=[
                BatchChangeCreate(
                    local_id="u1",
                    entity_type="unit",
                    payload=BatchChangeUnitPayload(name="Fresh Unit", symbol="FRU"),
                ),
                BatchChangeUpdate(
                    local_id="upd1",
                    entity_type="item",
                    entity_id=item_to_update.id,
                    payload=BatchChangeUpdatePayload(name="Updated Item"),
                ),
                BatchChangeMerge(
                    local_id="m1",
                    entity_type="item",
                    entity_id=source.id,
                    payload=BatchChangeMergePayload(
                        target_entity_id=target.id,
                        comment="mixed batch merge",
                    ),
                ),
                BatchChangeDelete(
                    local_id="d1",
                    entity_type="unit",
                    entity_id=unit_to_delete.id,
                ),
            ],
        )

        results, summary = await service.apply_batch(uow, batch, identity)

        assert summary["create"] == 1
        assert summary["update"] == 1
        assert summary["merge"] == 1
        assert summary["delete"] == 1
        assert summary["error"] == 0
        assert len(results) == 4

        # Verify merge
        source_after = await uow.catalog.get_item_by_id(source.id)
        assert source_after is not None
        assert source_after.is_active is False
        assert source_after.merged_into_id == target.id

        # Verify update
        updated = await uow.catalog.get_item_by_id(item_to_update.id)
        assert updated is not None
        assert updated.name == "Updated Item"

        # Verify delete
        unit_after = await uow.catalog.get_unit_by_id(unit_to_delete.id)
        assert unit_after is not None
        assert unit_after.deleted_at is not None
