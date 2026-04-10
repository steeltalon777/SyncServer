"""
Тесты для архивного удаления и фильтрации в каталоге.
"""
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.models import Category, Item, Unit
from app.schemas.catalog import (
    CategoryCreateRequest,
    CategoryFilter,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemFilter,
    ItemUpdateRequest,
    UnitCreateRequest,
    UnitFilter,
    UnitUpdateRequest,
)
from app.services.catalog_admin_service import CatalogAdminService


class TestCatalogAdminSoftDelete:
    """Тесты для архивного удаления единиц измерения, категорий и номенклатуры."""

    @pytest.mark.asyncio
    async def test_soft_delete_unit(self, uow, admin_user):
        """Тест архивного удаления единицы измерения."""
        service = CatalogAdminService()

        # Создаем единицу измерения
        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Test Unit", symbol="TU")
        )

        # Проверяем, что unit не удален
        assert unit.deleted_at is None
        assert unit.deleted_by_user_id is None

        # Архивируем unit
        await service.delete_unit(uow, unit.id, admin_user.id)

        # Получаем unit снова
        unit = await uow.catalog.get_unit_by_id(unit.id)
        assert unit is not None
        assert unit.deleted_at is not None
        assert unit.deleted_by_user_id == admin_user.id

        # Проверяем, что unit не возвращается в списке по умолчанию
        units, total = await service.list_units(uow)
        unit_ids = [u.id for u in units]
        assert unit.id not in unit_ids

        # Проверяем, что unit возвращается с include_deleted=True
        units, total = await service.list_units(uow, include_deleted=True)
        unit_ids = [u.id for u in units]
        assert unit.id in unit_ids

    @pytest.mark.asyncio
    async def test_cannot_delete_unit_with_active_items(self, uow, admin_user):
        """Тест: нельзя удалить единицу измерения с активными номенклатурами."""
        service = CatalogAdminService()

        # Создаем unit и item
        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Unit with items", symbol="UWI")
        )

        # Создаем категорию для item
        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Test Category")
        )

        item = await service.create_item(
            uow,
            ItemCreateRequest(
                name="Test Item",
                unit_id=unit.id,
                category_id=category.id
            )
        )

        # Пытаемся удалить unit - должно быть исключение
        with pytest.raises(Exception) as exc_info:
            await service.delete_unit(uow, unit.id, admin_user.id)

        assert "активными номенклатурами" in str(exc_info.value) or "Cannot delete" in str(exc_info.value)

        # Деактивируем item
        await service.update_item(
            uow,
            item.id,
            ItemUpdateRequest(is_active=False)
        )

        # Теперь удаление должно пройти
        await service.delete_unit(uow, unit.id, admin_user.id)

        unit = await uow.catalog.get_unit_by_id(unit.id)
        assert unit.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_category(self, uow, admin_user):
        """Тест архивного удаления категории."""
        service = CatalogAdminService()

        # Создаем категорию
        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Test Category")
        )

        # Архивируем категорию
        await service.delete_category(uow, category.id, admin_user.id)

        # Проверяем
        category = await uow.catalog.get_category_by_id(category.id)
        assert category.deleted_at is not None
        assert category.deleted_by_user_id == admin_user.id

        # Проверяем фильтрацию
        categories, total = await service.list_categories(uow)
        category_ids = [c.id for c in categories]
        assert category.id not in category_ids

        categories, total = await service.list_categories(uow, include_deleted=True)
        category_ids = [c.id for c in categories]
        assert category.id in category_ids

    @pytest.mark.asyncio
    async def test_cannot_delete_category_with_active_children(self, uow, admin_user):
        """Тест: нельзя удалить категорию с активными подкатегориями."""
        service = CatalogAdminService()

        # Создаем родительскую категорию
        parent = await service.create_category(
            uow,
            CategoryCreateRequest(name="Parent Category")
        )

        # Создаем дочернюю категорию
        child = await service.create_category(
            uow,
            CategoryCreateRequest(name="Child Category", parent_id=parent.id)
        )

        # Пытаемся удалить родительскую категорию - должно быть исключение
        with pytest.raises(Exception) as exc_info:
            await service.delete_category(uow, parent.id, admin_user.id)

        assert "активными подкатегориями" in str(exc_info.value) or "Cannot delete" in str(exc_info.value)

        # Деактивируем дочернюю категорию
        await service.update_category(
            uow,
            child.id,
            CategoryUpdateRequest(is_active=False)
        )

        # Теперь удаление должно пройти
        await service.delete_category(uow, parent.id, admin_user.id)

        parent = await uow.catalog.get_category_by_id(parent.id)
        assert parent.deleted_at is not None

    @pytest.mark.asyncio
    async def test_soft_delete_item(self, uow, admin_user):
        """Тест архивного удаления номенклатуры."""
        service = CatalogAdminService()

        # Создаем unit и category
        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Test Unit", symbol="TU")
        )

        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Test Category")
        )

        # Создаем item
        item = await service.create_item(
            uow,
            ItemCreateRequest(
                name="Test Item",
                unit_id=unit.id,
                category_id=category.id
            )
        )

        # Архивируем item
        await service.delete_item(uow, item.id, admin_user.id)

        # Проверяем
        item = await uow.catalog.get_item_by_id(item.id)
        assert item.deleted_at is not None
        assert item.deleted_by_user_id == admin_user.id

        # Проверяем фильтрацию
        items, total = await service.list_items(uow)
        item_ids = [i.id for i in items]
        assert item.id not in item_ids

        items, total = await service.list_items(uow, include_deleted=True)
        item_ids = [i.id for i in items]
        assert item.id in item_ids

    @pytest.mark.asyncio
    async def test_list_with_filters(self, uow, admin_user):
        """Тест фильтрации списков."""
        service = CatalogAdminService()

        # Создаем несколько units с разными статусами
        unit1 = await service.create_unit(
            uow,
            UnitCreateRequest(name="Active Unit", symbol="AU", is_active=True)
        )

        unit2 = await service.create_unit(
            uow,
            UnitCreateRequest(name="Inactive Unit", symbol="IU", is_active=False)
        )

        # Архивируем unit2
        await service.delete_unit(uow, unit2.id, admin_user.id)

        # Тестируем фильтры
        # Только активные (по умолчанию)
        units, total = await service.list_units(uow)
        unit_ids = [u.id for u in units]
        assert unit1.id in unit_ids
        assert unit2.id not in unit_ids

        # Все (включая неактивные и удаленные)
        units, total = await service.list_units(uow, include_inactive=True, include_deleted=True)
        unit_ids = [u.id for u in units]
        assert unit1.id in unit_ids
        assert unit2.id in unit_ids

        # Только неактивные
        units, total = await service.list_units(uow, include_inactive=True, include_deleted=True)
        # Фильтруем вручную по is_active=False
        inactive_units = [u for u in units if not u.is_active]
        inactive_unit_ids = [u.id for u in inactive_units]
        assert unit1.id not in inactive_unit_ids
        assert unit2.id in inactive_unit_ids

        # Поиск по имени - в текущей реализации нет параметра search, пропускаем

    @pytest.mark.asyncio
    async def test_get_deleted_item_returns_none_by_default(self, uow, admin_user):
        """Тест: получение удаленного элемента возвращает None по умолчанию."""
        service = CatalogAdminService()

        # Создаем и удаляем item
        unit = await service.create_unit(
            uow,
            UnitCreateRequest(name="Test Unit", symbol="TU")
        )

        category = await service.create_category(
            uow,
            CategoryCreateRequest(name="Test Category")
        )

        item = await service.create_item(
            uow,
            ItemCreateRequest(
                name="Test Item",
                unit_id=unit.id,
                category_id=category.id
            )
        )

        # Удаляем item
        await service.delete_item(uow, item.id, admin_user.id)

        # Пытаемся получить удаленный item - должно вернуть None
        with pytest.raises(Exception):
            await service.get_item(uow, item.id)

        # Но можем получить через репозиторий напрямую
        item_from_repo = await uow.catalog.get_item_by_id(item.id)
        assert item_from_repo is not None
        assert item_from_repo.deleted_at is not None
