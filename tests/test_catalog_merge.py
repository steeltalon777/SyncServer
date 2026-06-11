"""
Тесты для слияния (merge) ТМЦ и категорий в CatalogAdminService.
"""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.models import Balance, Category, InventorySubject, Item, Operation, OperationLine, Unit
from app.schemas.catalog import (
    CategoryCreateRequest,
    ItemCreateRequest,
    UnitCreateRequest,
)
from app.services.catalog_admin_service import CatalogAdminService
from fastapi import HTTPException


class TestMergeItems:
    """Тесты для merge_items."""

    @pytest.mark.asyncio
    async def test_merge_items_success(self, uow, admin_user, site):
        """Успешный merge: balance перенесён, operation lines обновлены, source деактивирован."""
        service = CatalogAdminService()

        # Создаём unit
        unit = await service.create_unit(
            uow, UnitCreateRequest(name="Merge Unit", symbol="MU"),
        )
        # Создаём две категории
        cat1 = await service.create_category(
            uow, CategoryCreateRequest(name="Cat 1"),
        )
        # Создаём source и target items
        source = await service.create_item(
            uow, ItemCreateRequest(name="Source Item", unit_id=unit.id, category_id=cat1.id),
        )
        target = await service.create_item(
            uow, ItemCreateRequest(name="Target Item", unit_id=unit.id, category_id=cat1.id),
        )

        # Создаём inventory subjects и balance для source
        source_subject = InventorySubject(subject_type="catalog_item", item_id=source.id)
        uow.session.add(source_subject)
        await uow.session.flush()

        target_subject = InventorySubject(subject_type="catalog_item", item_id=target.id)
        uow.session.add(target_subject)
        await uow.session.flush()

        balance = Balance(
            site_id=site.id,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("10.000"),
        )
        uow.session.add(balance)
        await uow.session.flush()

        # Создаём operation line для source
        op = Operation(
            site_id=site.id,
            operation_type="ADJUSTMENT",
            status="submitted",
            created_by_user_id=admin_user.id,
            effective_at=datetime.now(UTC),
        )
        uow.session.add(op)
        await uow.session.flush()

        op_line = OperationLine(
            operation_id=op.id,
            line_number=1,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("10.000"),
        )
        uow.session.add(op_line)
        await uow.session.flush()

        # Сохраняем ID для проверки после merge
        op_line_id = op_line.id

        # Выполняем merge
        result = await service.merge_items(
            uow,
            source_item_id=source.id,
            target_item_id=target.id,
            comment="testing merge",
            resolved_by_user_id=admin_user.id,
        )

        # Проверки
        assert result.id == target.id

        # Source деактивирован
        source_after = await uow.catalog.get_item_by_id(source.id)
        assert source_after is not None
        assert source_after.is_active is False
        assert source_after.merged_into_id == target.id
        assert source_after.merge_comment == "testing merge"

        # Обновляем созданные объекты после Core UPDATE
        await uow.session.refresh(op_line)
        assert op_line.item_id == target.id

        # Source inventory subject заархивирован
        await uow.session.refresh(source_subject)
        assert source_subject.archived_at is not None

        # Баланс перенесён через ADJUSTMENT операции (проверяем, что операции созданы)
        from sqlalchemy import select as sa_select

        ops_stmt = await uow.session.execute(
            sa_select(Operation).where(
                Operation.notes.contains("[catalog merge]")
            )
        )
        merge_ops = list(ops_stmt.scalars().all())
        assert len(merge_ops) >= 2  # write-off + receipt

    @pytest.mark.asyncio
    async def test_merge_items_self_merge_422(self, uow, admin_user, site):
        """Self-merge должен вернуть 422."""
        service = CatalogAdminService()
        unit = await service.create_unit(uow, UnitCreateRequest(name="Unit", symbol="U"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Cat"))
        item = await service.create_item(
            uow, ItemCreateRequest(name="Item", unit_id=unit.id, category_id=cat.id),
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.merge_items(
                uow,
                source_item_id=item.id,
                target_item_id=item.id,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_merge_items_source_not_found_404(self, uow, admin_user, site):
        """Несуществующий source → 404."""
        service = CatalogAdminService()
        unit = await service.create_unit(uow, UnitCreateRequest(name="Unit", symbol="U"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Cat"))
        target = await service.create_item(
            uow, ItemCreateRequest(name="Target", unit_id=unit.id, category_id=cat.id),
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.merge_items(
                uow,
                source_item_id=99999,
                target_item_id=target.id,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_merge_items_target_not_found_404(self, uow, admin_user, site):
        """Несуществующий target → 404."""
        service = CatalogAdminService()
        unit = await service.create_unit(uow, UnitCreateRequest(name="Unit", symbol="U"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Cat"))
        source = await service.create_item(
            uow, ItemCreateRequest(name="Source", unit_id=unit.id, category_id=cat.id),
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.merge_items(
                uow,
                source_item_id=source.id,
                target_item_id=99999,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_merge_items_frozen_409(self, uow, admin_user, site):
        """Замороженная ТМЦ (lost assets) не должна сливаться."""
        service = CatalogAdminService()
        unit = await service.create_unit(uow, UnitCreateRequest(name="Unit", symbol="U"))
        cat = await service.create_category(uow, CategoryCreateRequest(name="Cat"))
        source = await service.create_item(
            uow, ItemCreateRequest(name="Source", unit_id=unit.id, category_id=cat.id),
        )
        target = await service.create_item(
            uow, ItemCreateRequest(name="Target", unit_id=unit.id, category_id=cat.id),
        )

        # Симулируем frozen state через lost asset
        source_subject = InventorySubject(subject_type="catalog_item", item_id=source.id)
        uow.session.add(source_subject)
        await uow.session.flush()

        from app.models.asset_register import LostAssetBalance
        from app.models.operation import Operation as OpModel, OperationLine as OpLineModel

        # Создаём operation + operation_line для LostAssetBalance (требуется FK)
        op = Operation(
            site_id=site.id,
            operation_type="ADJUSTMENT",
            status="submitted",
            created_by_user_id=admin_user.id,
            effective_at=datetime.now(UTC),
        )
        uow.session.add(op)
        await uow.session.flush()

        op_line = OperationLine(
            operation_id=op.id,
            line_number=1,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("5.000"),
        )
        uow.session.add(op_line)
        await uow.session.flush()

        lost = LostAssetBalance(
            operation_id=op.id,
            operation_line_id=op_line.id,
            site_id=site.id,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("5.000"),
        )
        uow.session.add(lost)
        await uow.session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await service.merge_items(
                uow,
                source_item_id=source.id,
                target_item_id=target.id,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 409
        assert "frozen" in str(exc_info.value.detail)


class TestMergeCategories:
    """Тесты для merge_categories."""

    @pytest.mark.asyncio
    async def test_merge_categories_success(self, uow, admin_user, site):
        """Успешный merge категорий: ТМЦ перенесены, subcategories перенесены, source деактивирован."""
        service = CatalogAdminService()
        unit = await service.create_unit(uow, UnitCreateRequest(name="Unit", symbol="U"))

        source_cat = await service.create_category(
            uow, CategoryCreateRequest(name="Source Category"),
        )
        target_cat = await service.create_category(
            uow, CategoryCreateRequest(name="Target Category"),
        )

        # Создаём ТМЦ в source категории
        item1 = await service.create_item(
            uow, ItemCreateRequest(name="Item in Source", unit_id=unit.id, category_id=source_cat.id),
        )

        # Создаём подкатегорию в source
        sub_cat = await service.create_category(
            uow, CategoryCreateRequest(name="Subcategory", parent_id=source_cat.id),
        )

        # Выполняем merge
        result = await service.merge_categories(
            uow,
            source_category_id=source_cat.id,
            target_category_id=target_cat.id,
            comment="merging categories",
            resolved_by_user_id=admin_user.id,
        )
        assert result.id == target_cat.id

        # Source деактивирован
        source_after = await uow.catalog.get_category_by_id(source_cat.id)
        assert source_after is not None
        assert source_after.is_active is False
        assert source_after.merged_into_id == target_cat.id
        assert source_after.merge_comment == "merging categories"

        # ТМЦ перенесён в target категорию (force populate from DB to bypass identity map)
        from sqlalchemy import select as sa_select

        fresh_item_stmt = await uow.session.execute(
            sa_select(Item).where(Item.id == item1.id).execution_options(populate_existing=True)
        )
        item1_fresh = fresh_item_stmt.scalar_one()
        assert item1_fresh.category_id == target_cat.id

        # Подкатегория перенесена
        fresh_cat_stmt = await uow.session.execute(
            sa_select(Category).where(Category.id == sub_cat.id).execution_options(populate_existing=True)
        )
        sub_cat_fresh = fresh_cat_stmt.scalar_one()
        assert sub_cat_fresh.parent_id == target_cat.id

    @pytest.mark.asyncio
    async def test_merge_categories_self_merge_422(self, uow, admin_user, site):
        """Self-merge категории → 422."""
        service = CatalogAdminService()
        cat = await service.create_category(
            uow, CategoryCreateRequest(name="Category"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.merge_categories(
                uow,
                source_category_id=cat.id,
                target_category_id=cat.id,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_merge_categories_cycle_check(self, uow, admin_user, site):
        """Если target — потомок source, должно быть 422."""
        service = CatalogAdminService()

        parent = await service.create_category(
            uow, CategoryCreateRequest(name="Parent"),
        )
        child = await service.create_category(
            uow, CategoryCreateRequest(name="Child", parent_id=parent.id),
        )
        grandchild = await service.create_category(
            uow, CategoryCreateRequest(name="Grandchild", parent_id=child.id),
        )

        # Попытка слить parent → grandchild (grandchild — потомок parent)
        with pytest.raises(HTTPException) as exc_info:
            await service.merge_categories(
                uow,
                source_category_id=parent.id,
                target_category_id=grandchild.id,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_merge_categories_subcategories_transferred(self, uow, admin_user, site):
        """Подкатегории source переносятся в target."""
        service = CatalogAdminService()

        source = await service.create_category(
            uow, CategoryCreateRequest(name="Source"),
        )
        target = await service.create_category(
            uow, CategoryCreateRequest(name="Target"),
        )
        sub1 = await service.create_category(
            uow, CategoryCreateRequest(name="Sub 1", parent_id=source.id),
        )
        sub2 = await service.create_category(
            uow, CategoryCreateRequest(name="Sub 2", parent_id=source.id),
        )

        await service.merge_categories(
            uow,
            source_category_id=source.id,
            target_category_id=target.id,
            resolved_by_user_id=admin_user.id,
        )

        # Fresh queries with populate_existing to bypass identity map
        from sqlalchemy import select as sa_select

        stmt1 = await uow.session.execute(
            sa_select(Category).where(Category.id == sub1.id).execution_options(populate_existing=True)
        )
        sub1_fresh = stmt1.scalar_one()
        assert sub1_fresh.parent_id == target.id

        stmt2 = await uow.session.execute(
            sa_select(Category).where(Category.id == sub2.id).execution_options(populate_existing=True)
        )
        sub2_fresh = stmt2.scalar_one()
        assert sub2_fresh.parent_id == target.id

    @pytest.mark.asyncio
    async def test_merge_categories_source_not_found_404(self, uow, admin_user, site):
        """Несуществующий source → 404."""
        service = CatalogAdminService()
        target = await service.create_category(
            uow, CategoryCreateRequest(name="Target"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.merge_categories(
                uow,
                source_category_id=99999,
                target_category_id=target.id,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_merge_categories_target_not_found_404(self, uow, admin_user, site):
        """Несуществующий target → 404."""
        service = CatalogAdminService()
        source = await service.create_category(
            uow, CategoryCreateRequest(name="Source"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.merge_categories(
                uow,
                source_category_id=source.id,
                target_category_id=99999,
                resolved_by_user_id=admin_user.id,
            )
        assert exc_info.value.status_code == 404
