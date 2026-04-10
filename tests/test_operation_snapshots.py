"""
Тесты для исторических снапшотов в операциях.
"""
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import Operation, OperationLine
from app.schemas.operation import OperationCreate, OperationLineCreate
from app.services.operations_service import OperationsService


class TestOperationSnapshots:
    """Тесты для snapshot полей в операциях."""

    @pytest.mark.asyncio
    async def test_create_operation_with_snapshots(self, uow, site, user):
        """Тест создания операции с заполнением snapshot полей."""
        # Создаем тестовые данные каталога
        unit = await uow.catalog.create_unit(
            name="Test Unit",
            symbol="TU",
            is_active=True
        )

        category = await uow.catalog.create_category(
            name="Test Category",
            is_active=True
        )

        item = await uow.catalog.create_item(
            name="Test Item",
            sku="TEST-001",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True
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

        operation_dict = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )

        # Проверяем, что операция создана
        assert operation_dict is not None
        assert "id" in operation_dict

        # Получаем операцию из БД для проверки
        operation = await uow.operations.get_operation_by_id(operation_dict["id"])
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
        unit = await uow.catalog.create_unit(
            name="Original Unit",
            symbol="OU",
            is_active=True
        )

        category = await uow.catalog.create_category(
            name="Original Category",
            is_active=True
        )

        item = await uow.catalog.create_item(
            name="Original Item",
            sku="ORIG-001",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True
        )

        # Создаем операцию
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(
                    item_id=item.id,
                    qty=Decimal("5.0")
                )
            ]
        )

        operation = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )

        line = operation.lines[0]
        original_snapshots = {
            "item_name": line.item_name_snapshot,
            "item_sku": line.item_sku_snapshot,
            "unit_name": line.unit_name_snapshot,
            "unit_symbol": line.unit_symbol_snapshot,
            "category_name": line.category_name_snapshot
        }

        # Изменяем данные в каталоге
        await uow.catalog.update_item(item.id, name="Updated Item", sku="UPD-001")
        await uow.catalog.update_unit(unit.id, name="Updated Unit", symbol="UU")
        await uow.catalog.update_category(category.id, name="Updated Category")

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
        """Тест: snapshot поля заполняются даже для неактивных элементов каталога."""
        unit = await uow.catalog.create_unit(
            name="Inactive Unit",
            symbol="IU",
            is_active=False  # Неактивный unit
        )

        category = await uow.catalog.create_category(
            name="Inactive Category",
            is_active=False  # Неактивная категория
        )

        item = await uow.catalog.create_item(
            name="Inactive Item",
            sku="INACT-001",
            category_id=category.id,
            unit_id=unit.id,
            is_active=False  # Неактивный item
        )

        # Создаем операцию
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(
                    item_id=item.id,
                    qty=Decimal("3.0")
                )
            ]
        )

        operation = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )

        line = operation.lines[0]

        # Проверяем, что snapshot поля все равно заполнены
        assert line.item_name_snapshot == "Inactive Item"
        assert line.item_sku_snapshot == "INACT-001"
        assert line.unit_name_snapshot == "Inactive Unit"
        assert line.unit_symbol_snapshot == "IU"
        assert line.category_name_snapshot == "Inactive Category"

    @pytest.mark.asyncio
    async def test_snapshots_for_deleted_catalog_items(self, uow, site, user, admin_user):
        """Тест: snapshot поля сохраняются даже после удаления элементов каталога."""
        unit = await uow.catalog.create_unit(
            name="To Be Deleted Unit",
            symbol="TBDU",
            is_active=True
        )

        category = await uow.catalog.create_category(
            name="To Be Deleted Category",
            is_active=True
        )

        item = await uow.catalog.create_item(
            name="To Be Deleted Item",
            sku="TBD-001",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True
        )

        # Создаем операцию
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(
                    item_id=item.id,
                    qty=Decimal("7.5")
                )
            ]
        )

        operation = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )

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
        await uow.catalog.update_item(item.id, is_active=False)
        await uow.catalog.update_unit(unit.id, is_active=False)
        await uow.catalog.update_category(category.id, is_active=False)

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
        unit1 = await uow.catalog.create_unit(name="Unit 1", symbol="U1", is_active=True)
        unit2 = await uow.catalog.create_unit(name="Unit 2", symbol="U2", is_active=True)

        category1 = await uow.catalog.create_category(name="Category 1", is_active=True)
        category2 = await uow.catalog.create_category(name="Category 2", is_active=True)

        item1 = await uow.catalog.create_item(
            name="Item 1",
            sku="ITEM-001",
            category_id=category1.id,
            unit_id=unit1.id,
            is_active=True
        )

        item2 = await uow.catalog.create_item(
            name="Item 2",
            sku="ITEM-002",
            category_id=category2.id,
            unit_id=unit2.id,
            is_active=True
        )

        # Создаем операцию с двумя строками
        operation_data = OperationCreate(
            site_id=site.id,
            operation_type="RECEIVE",
            lines=[
                OperationLineCreate(item_id=item1.id, qty=Decimal("10.0")),
                OperationLineCreate(item_id=item2.id, qty=Decimal("20.0"))
            ]
        )

        operation = await OperationsService.create_operation(
            uow,
            operation_data,
            user.id
        )

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
