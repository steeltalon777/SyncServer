"""
Тесты для аудит-полей created_by_user_id и updated_by_user_id на сущностях каталога.
"""

import pytest

from app.schemas.catalog import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemUpdateRequest,
    UnitCreateRequest,
    UnitUpdateRequest,
)
from app.services.catalog_admin_service import CatalogAdminService


class TestCatalogAdminAudit:
    """Тесты для аудит-полей created_by_user_id, updated_by_user_id и review_created_by_user_id."""

    @pytest.mark.asyncio
    async def test_create_unit_sets_created_by(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Audit Unit", symbol="AU"),
            created_by_user_id=admin_user.id,
        )

        assert unit.created_by_user_id == admin_user.id
        assert unit.updated_by_user_id is None

    @pytest.mark.asyncio
    async def test_update_unit_sets_updated_by(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Audit Unit 2", symbol="AU2"),
        )

        unit = await service.update_unit(
            uow,
            unit.id,
            UnitUpdateRequest(name="Audit Unit 2 Updated"),
            updated_by_user_id=admin_user.id,
        )

        assert unit.updated_by_user_id == admin_user.id
        assert unit.created_by_user_id is None

    @pytest.mark.asyncio
    async def test_create_category_sets_created_by(self, uow, admin_user):
        service = CatalogAdminService()

        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Audit Category"),
            created_by_user_id=admin_user.id,
        )

        assert category.created_by_user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_update_category_sets_updated_by(self, uow, admin_user):
        service = CatalogAdminService()

        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Audit Category 2"),
        )

        category = await service.update_category(
            uow,
            category.id,
            CategoryUpdateRequest(name="Audit Category 2 Updated"),
            updated_by_user_id=admin_user.id,
        )

        assert category.updated_by_user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_create_item_sets_created_by(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Item Unit", symbol="ITU"),
        )
        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Item Category"),
        )

        item = await service.create_item(
            uow,
            ItemCreateRequest(
                name="Audit Item",
                unit_id=unit.id,
                category_id=category.id,
            ),
            created_by_user_id=admin_user.id,
        )

        assert item.created_by_user_id == admin_user.id
        assert item.review_created_by_user_id is None

    @pytest.mark.asyncio
    async def test_create_item_sets_both_audit_and_review(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Review Unit", symbol="RVU"),
        )
        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Review Category"),
        )

        item = await service.create_item(
            uow,
            ItemCreateRequest(
                name="Review Item",
                unit_id=unit.id,
                category_id=category.id,
                requires_review=True,
            ),
            created_by_user_id=admin_user.id,
        )

        assert item.created_by_user_id == admin_user.id
        assert item.review_created_by_user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_update_item_sets_updated_by(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Update Item Unit", symbol="UPU"),
        )
        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Update Item Category"),
        )
        item = await service.create_item(
            uow,
            ItemCreateRequest(
                name="Update Item",
                unit_id=unit.id,
                category_id=category.id,
            ),
        )

        item = await service.update_item(
            uow,
            item.id,
            ItemUpdateRequest(name="Update Item Updated"),
            updated_by_user_id=admin_user.id,
        )

        assert item.updated_by_user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_no_user_id_leaves_fields_null(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="No Audit Unit", symbol="NAU"),
        )
        assert unit.created_by_user_id is None

        unit = await service.update_unit(
            uow,
            unit.id,
            UnitUpdateRequest(name="No Audit Unit Updated"),
        )
        assert unit.updated_by_user_id is None

        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="No Audit Category"),
        )
        assert category.created_by_user_id is None

        category = await service.update_category(
            uow,
            category.id,
            CategoryUpdateRequest(name="No Audit Category Updated"),
        )
        assert category.updated_by_user_id is None

        unit_for_item = await service.create_unit(
            uow,
            UnitCreateRequest(name="No Audit Item Unit", symbol="NAIU"),
        )
        cat_for_item = await service.create_category(
            uow,
            CategoryCreateRequest(name="No Audit Item Category"),
        )
        item = await service.create_item(
            uow,
            ItemCreateRequest(
                name="No Audit Item",
                unit_id=unit_for_item.id,
                category_id=cat_for_item.id,
            ),
        )
        assert item.created_by_user_id is None

        item = await service.update_item(
            uow,
            item.id,
            ItemUpdateRequest(name="No Audit Item Updated"),
        )
        assert item.updated_by_user_id is None

    @pytest.mark.asyncio
    async def test_created_by_persisted_in_db(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Persist Unit", symbol="PRU"),
            created_by_user_id=admin_user.id,
        )

        fetched = await uow.catalog.get_unit_by_id(unit.id)
        assert fetched.created_by_user_id == admin_user.id

    @pytest.mark.asyncio
    async def test_updated_by_persisted_in_db(self, uow, admin_user):
        service = CatalogAdminService()

        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Persist Update Unit", symbol="PRU2"),
        )

        unit = await service.update_unit(
            uow,
            unit.id,
            UnitUpdateRequest(name="Persist Update Unit Updated"),
            updated_by_user_id=admin_user.id,
        )

        fetched = await uow.catalog.get_unit_by_id(unit.id)
        assert fetched.updated_by_user_id == admin_user.id
