"""
Тесты для исторических снапшотов в операциях.
"""
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit
from app.models import Operation, OperationLine
from app.schemas.operation import OperationCreate, OperationLineCreate
from app.services.operations_service import OperationsService


class TestOperationSnapshots:
    """Тесты для snapshot полей в операциях."""

    @staticmethod
    async def _create_catalog_fixture(uow, *, unit_name: str, unit_symbol: str, category_name: str, item_name: str, item_sku: str, is_active: bool = True):
        unit = await uow.catalog.create_unit(
            Unit(
                name=unit_name,
                symbol=unit_symbol,
                is_active=is_active,
            )
        )

        category = await uow.catalog.create_category(
            Category(
                name=category_name,
                normalized_name=category_name.lower(),
                is_active=is_active,
            )
        )

        item = await uow.catalog.create_item(
            Item(
                name=item_name,
                normalized_name=item_name.lower(),
                sku=item_sku,
                category_id=category.id,
                unit_id=unit.id,
                is_active=is_active,
            )
        )
        return unit, category, item

    @pytest.mark.asyncio
    async def test_create_operation_with_snapshots(self, uow, site, user):
        """Тест создания операции с заполнением snapshot полей."""
        # Создаем тестовые данные каталога
        unit, category, item = await self._create_catalog_fixture(
            uow,
            unit_name="Test Unit",
            unit_symbol="TU",
            category_name="Test Category",
            item_name="Test Item",
            item_sku="TEST-001",
        )

        # Создаем операцию
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=10,  # int, не Decimal
                    batch="BATCH-001",
                    comment="Test comment"
                )
            ]
        )

        operation_result = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )

        # Проверяем, что операция создана
        assert operation_result is not None
        assert "operation" in operation_result
        assert operation_result["operation"] is not None
        operation_id = operation_result["operation"].id

        # Получаем операцию из БД для проверки
        operation = await uow.operations.get_operation_by_id(operation_id)
        assert operation is not None
        assert len(operation.lines) == 1

        line = operation.lines[0]

        # Проверяем, что snapshot поля заполнены
        assert line.item_name_snapshot == "Test Item"
        assert line.item_sku_snapshot == "TEST-001"
        assert line.unit_name_snapshot == "Test Unit"
        assert line.unit_symbol_snapshot == "TU"
        assert line.category_name_snapshot == "Test Category"

        # Проверяем связь с оригинальными объектами
        assert line.item_id == item.id
        assert line.item.name == "Test Item"

    @pytest.mark.asyncio
    async def test_snapshots_preserved_when_catalog_changes(self, uow, site, user):
        """Тест: snapshot поля сохраняются при изменении каталога."""
        # Создаем тестовые данные
        unit, category, item = await self._create_catalog_fixture(
            uow,
            unit_name="Original Unit",
            unit_symbol="OU",
            category_name="Original Category",
            item_name="Original Item",
            item_sku="ORIG-001",
        )

        # Создаем операцию
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=5
                )
            ]
        )

        operation_result = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )
        operation = operation_result["operation"]

        line = operation.lines[0]
        original_snapshots = {
            "item_name": line.item_name_snapshot,
            "item_sku": line.item_sku_snapshot,
            "unit_name": line.unit_name_snapshot,
            "unit_symbol": line.unit_symbol_snapshot,
            "category_name": line.category_name_snapshot
        }

        # Изменяем данные в каталоге
        item.name = "Updated Item"
        item.sku = "UPD-001"
        unit.name = "Updated Unit"
        unit.symbol = "UU"
        category.name = "Updated Category"
        category.normalized_name = "updated category"
        await uow.catalog.update_item(item)
        await uow.catalog.update_unit(unit)
        await uow.catalog.update_category(category)

        # Обновляем объекты в сессии
        await uow.commit()

        # Получаем операцию заново
        operation = await uow.operations.get_operation_by_id(operation.id)
        line = operation.lines[0]

        # Проверяем, что snapshot поля остались неизменными
        assert line.item_name_snapshot == original_snapshots["item_name"]
        assert line.item_sku_snapshot == original_snapshots["item_sku"]
        assert line.unit_name_snapshot == original_snapshots["unit_name"]
        assert line.unit_symbol_snapshot == original_snapshots["unit_symbol"]
        assert line.category_name_snapshot == original_snapshots["category_name"]

        # Проверяем, что текущие данные в каталоге изменились
        updated_item = await uow.catalog.get_item_by_id(item.id)
        assert updated_item.name == "Updated Item"
        assert updated_item.sku == "UPD-001"

        # Но snapshot в операции сохранил оригинальные значения
        assert line.item_name_snapshot == "Original Item"
        assert line.item_sku_snapshot == "ORIG-001"

    @pytest.mark.asyncio
    async def test_snapshots_for_inactive_catalog_items(self, uow, site, user):
        """Тест: создание операции с неактивной номенклатурой отклоняется (текущее поведение сервиса)."""
        unit, category, item = await self._create_catalog_fixture(
            uow,
            unit_name="Inactive Unit",
            unit_symbol="IU",
            category_name="Inactive Category",
            item_name="Inactive Item",
            item_sku="INACT-001",
            is_active=False,
        )

        # Создаем операцию
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=3
                )
            ]
        )

        with pytest.raises(HTTPException) as exc_info:
            await OperationsService.create_operation(
                uow,
                operation_data,
                user.id,
            )

        assert exc_info.value.status_code == 404
        assert "item with id" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_snapshots_for_deleted_catalog_items(self, uow, site, user, admin_user):
        """Тест: snapshot поля сохраняются даже после удаления элементов каталога."""
        unit, category, item = await self._create_catalog_fixture(
            uow,
            unit_name="To Be Deleted Unit",
            unit_symbol="TBDU",
            category_name="To Be Deleted Category",
            item_name="To Be Deleted Item",
            item_sku="TBD-001",
        )

        # Создаем операцию
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=8
                )
            ]
        )

        operation_result = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )
        operation = operation_result["operation"]

        line = operation.lines[0]
        original_snapshots = {
            "item_name": line.item_name_snapshot,
            "item_sku": line.item_sku_snapshot,
            "unit_name": line.unit_name_snapshot,
            "unit_symbol": line.unit_symbol_snapshot,
            "category_name": line.category_name_snapshot
        }

        # Архивируем элементы каталога
        from app.services.catalog_admin_service import CatalogAdminService
        service = CatalogAdminService()

        # Деактивируем перед удалением
        item.is_active = False
        unit.is_active = False
        category.is_active = False
        await uow.catalog.update_item(item)
        await uow.catalog.update_unit(unit)
        await uow.catalog.update_category(category)

        # Архивируем
        await service.delete_item(uow, item.id, admin_user.id)
        await service.delete_unit(uow, unit.id, admin_user.id)
        await service.delete_category(uow, category.id, admin_user.id)

        # Получаем операцию заново
        operation = await uow.operations.get_operation_by_id(operation.id)
        line = operation.lines[0]

        # Проверяем, что snapshot поля остались
        assert line.item_name_snapshot == original_snapshots["item_name"]
        assert line.item_sku_snapshot == original_snapshots["item_sku"]
        assert line.unit_name_snapshot == original_snapshots["unit_name"]
        assert line.unit_symbol_snapshot == original_snapshots["unit_symbol"]
        assert line.category_name_snapshot == original_snapshots["category_name"]

        # Проверяем, что элементы каталога действительно удалены (архивированы)
        deleted_item = await uow.catalog.get_item_by_id(item.id)
        assert deleted_item.deleted_at is not None

        # Но операция все еще ссылается на item_id
        assert line.item_id == item.id

    @pytest.mark.asyncio
    async def test_multiple_lines_with_different_items(self, uow, site, user):
        """Тест создания операции с несколькими строками и разными номенклатурами."""
        # Создаем несколько элементов каталога
        unit1, category1, item1 = await self._create_catalog_fixture(
            uow,
            unit_name="Unit 1",
            unit_symbol="U1",
            category_name="Category 1",
            item_name="Item 1",
            item_sku="ITEM-001",
        )
        unit2, category2, item2 = await self._create_catalog_fixture(
            uow,
            unit_name="Unit 2",
            unit_symbol="U2",
            category_name="Category 2",
            item_name="Item 2",
            item_sku="ITEM-002",
        )

        # Создаем операцию с двумя строками
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(line_number=1, item_id=item1.id, qty=10),
                OperationLineCreate(line_number=2, item_id=item2.id, qty=20)
            ]
        )

        operation_result = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )
        operation = operation_result["operation"]

        # Проверяем обе строки
        assert len(operation.lines) == 2

        line1 = operation.lines[0]
        line2 = operation.lines[1]

        # Проверяем snapshot для первой строки
        assert line1.item_name_snapshot == "Item 1"
        assert line1.item_sku_snapshot == "ITEM-001"
        assert line1.unit_name_snapshot == "Unit 1"
        assert line1.unit_symbol_snapshot == "U1"
        assert line1.category_name_snapshot == "Category 1"

        # Проверяем snapshot для второй строки
        assert line2.item_name_snapshot == "Item 2"
        assert line2.item_sku_snapshot == "ITEM-002"
        assert line2.unit_name_snapshot == "Unit 2"
        assert line2.unit_symbol_snapshot == "U2"
        assert line2.category_name_snapshot == "Category 2"
