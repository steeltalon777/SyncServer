from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.db import get_db
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.temporary_item import TemporaryItem
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from httpx import ASGITransport, AsyncClient
from main import create_app
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

app = create_app()


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"ST-{suffix}", name=f"Site {suffix}")
        session.add(site)
        await session.flush()

        chief = User(
            username=f"chief-{suffix}",
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        session.add(chief)
        await session.flush()

        scope = UserAccessScope(
            user_id=chief.id,
            site_id=site.id,
            can_view=True,
            can_operate=True,
            can_manage_catalog=True,
            is_active=True,
        )
        session.add(scope)

        unit = Unit(name=f"Unit {suffix}", symbol="pcs")
        session.add(unit)
        await session.flush()

        category = Category(name=f"Category {suffix}")
        session.add(category)
        await session.flush()

        # Создаём временный ТМЦ с backing item
        backing_item = Item(
            sku=f"TEMP-{suffix}",
            name=f"Temporary Item {suffix}",
            normalized_name=f"temporary item {suffix}",
            unit_id=unit.id,
            category_id=category.id,
            is_active=False,
            source_system="temporary_item",
        )
        session.add(backing_item)
        await session.flush()

        temporary_item = TemporaryItem(
            item_id=backing_item.id,
            name=backing_item.name,
            normalized_name=backing_item.normalized_name,
            sku=backing_item.sku,
            unit_id=unit.id,
            category_id=category.id,
            status="active",
            created_by_user_id=chief.id,
        )
        session.add(temporary_item)
        await session.flush()

        # Создаём inventory subject для временного ТМЦ
        subject = InventorySubject(
            subject_type="temporary_item",
            temporary_item_id=temporary_item.id,
            item_id=backing_item.id,
        )
        session.add(subject)
        await session.flush()

        await session.commit()

        return {
            "site": site,
            "chief": chief,
            "unit": unit,
            "category": category,
            "backing_item": backing_item,
            "temporary_item": temporary_item,
            "subject": subject,
        }


@pytest.mark.asyncio
async def test_delete_temporary_item_success(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
):
    """Успешное удаление временного ТМЦ без остатков и активных регистров."""
    seed = await _seed(session_factory)
    chief = seed["chief"]
    temporary_item = seed["temporary_item"]

    # Аутентификация chief
    auth_headers = {"X-User-Id": str(chief.id)}

    # DELETE запрос
    resp = await client.delete(
        f"/temporary-items/{temporary_item.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deleted"
    assert body["resolution_type"] == "deleted"
    assert body["resolved_by_user_id"] == str(chief.id)

    # Проверяем, что временный ТМЦ помечен как удалённый
    async with session_factory() as session:
        db_item = await session.get(TemporaryItem, temporary_item.id)
        assert db_item is not None
        assert db_item.status == "deleted"
        assert db_item.resolution_type == "deleted"
        assert db_item.resolved_by_user_id == chief.id

        # Backing item должен быть деактивирован
        backing_item = await session.get(Item, seed["backing_item"].id)
        assert backing_item.is_active is False

        # Inventory subject должен быть архивирован
        subject = await session.get(InventorySubject, seed["subject"].id)
        assert subject.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_temporary_item_with_non_zero_balance_fails(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
):
    """Удаление временного ТМЦ с ненулевым остатком должно завершиться ошибкой."""
    seed = await _seed(session_factory)
    chief = seed["chief"]
    temporary_item = seed["temporary_item"]
    subject = seed["subject"]
    site = seed["site"]

    # Создаём ненулевой остаток
    async with session_factory() as session:
        balance = Balance(
            site_id=site.id,
            inventory_subject_id=subject.id,
            item_id=seed["backing_item"].id,
            qty=Decimal("5.000"),
        )
        session.add(balance)
        await session.commit()

    auth_headers = {"X-User-Id": str(chief.id)}
    resp = await client.delete(
        f"/temporary-items/{temporary_item.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "non-zero balances" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_temporary_item_with_active_registers_fails(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
):
    """Удаление временного ТМЦ с активными регистрами должно завершиться ошибкой."""
    seed = await _seed(session_factory)
    chief = seed["chief"]
    temporary_item = seed["temporary_item"]
    subject = seed["subject"]
    site = seed["site"]

    # Создаём операцию с pending acceptance
    async with session_factory() as session:
        operation = Operation(
            site_id=site.id,
            operation_type="RECEIVE",
            created_by_user_id=chief.id,
            status="submitted",
        )
        session.add(operation)
        await session.flush()

        line = OperationLine(
            operation_id=operation.id,
            line_number=1,
            inventory_subject_id=subject.id,
            item_id=seed["backing_item"].id,
            qty=Decimal("10.000"),
        )
        session.add(line)
        await session.flush()

        # Создаём pending acceptance (имитируем через raw SQL или используем репозиторий)
        # Для простоты теста просто создадим запись в таблице pending_acceptance_balances
        from app.models.asset_register import PendingAcceptanceBalance
        pending = PendingAcceptanceBalance(
            operation_line_id=line.id,
            operation_id=operation.id,
            destination_site_id=site.id,
            source_site_id=None,
            inventory_subject_id=subject.id,
            qty=Decimal("10.000"),
        )
        session.add(pending)
        await session.commit()

    auth_headers = {"X-User-Id": str(chief.id)}
    resp = await client.delete(
        f"/temporary-items/{temporary_item.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "active pending/lost/issued registers" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_temporary_item_not_found(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
):
    """Попытка удалить несуществующий временный ТМЦ."""
    seed = await _seed(session_factory)
    chief = seed["chief"]
    auth_headers = {"X-User-Id": str(chief.id)}
    resp = await client.delete("/temporary-items/999999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_temporary_item_already_resolved(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
):
    """Попытка удалить уже разрешённый временный ТМЦ."""
    seed = await _seed(session_factory)
    chief = seed["chief"]
    temporary_item = seed["temporary_item"]

    # Помечаем временный ТМЦ как approved
    async with session_factory() as session:
        db_item = await session.get(TemporaryItem, temporary_item.id)
        db_item.status = "approved_as_item"
        db_item.resolved_item_id = 999
        db_item.resolution_type = "approve_as_item"
        db_item.resolved_by_user_id = chief.id
        await session.commit()

    auth_headers = {"X-User-Id": str(chief.id)}
    resp = await client.delete(
        f"/temporary-items/{temporary_item.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "already resolved" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_temporary_item_unauthorized(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
):
    """Попытка удалить без аутентификации."""
    seed = await _seed(session_factory)
    temporary_item = seed["temporary_item"]
    resp = await client.delete(f"/temporary-items/{temporary_item.id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_temporary_item_no_permission(
    session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
):
    """Попытка удалить без прав модерации."""
    seed = await _seed(session_factory)
    temporary_item = seed["temporary_item"]

    # Создаём обычного пользователя без прав
    async with session_factory() as session:
        user = User(
            username="regular",
            role="storekeeper",
            default_site_id=seed["site"].id,
        )
        session.add(user)
        await session.flush()
        # Не даём scope
        await session.commit()

    auth_headers = {"X-User-Id": str(user.id)}
    resp = await client.delete(
        f"/temporary-items/{temporary_item.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 403

