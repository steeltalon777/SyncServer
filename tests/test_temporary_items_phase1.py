from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.balance import Balance
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.temporary_item import TemporaryItem
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from main import create_app

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
            email=f"chief-{suffix}@example.com",
            full_name="Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        storekeeper = User(
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        observer = User(
            username=f"observer-{suffix}",
            email=f"observer-{suffix}@example.com",
            full_name="Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site.id,
        )
        session.add_all([chief, storekeeper, observer])
        await session.flush()

        session.add_all(
            [
                UserAccessScope(
                    user_id=chief.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=True,
                    is_active=True,
                ),
                UserAccessScope(
                    user_id=storekeeper.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=False,
                    is_active=True,
                ),
                UserAccessScope(
                    user_id=observer.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=False,
                    can_manage_catalog=False,
                    is_active=True,
                ),
            ]
        )

        unit = Unit(code=f"U-{suffix}", name=f"Unit {suffix}", symbol=f"u{suffix[:2]}", is_active=True)
        category = Category(code=f"C-{suffix}", name=f"Category {suffix}", normalized_name=f"category {suffix}", is_active=True)
        session.add_all([unit, category])
        await session.flush()

        catalog_item = Item(
            sku=f"SKU-{suffix}",
            name=f"Catalog Item {suffix}",
            normalized_name=f"catalog item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(catalog_item)
        await session.commit()
        return {
            "site_id": site.id,
            "chief_token": str(chief.user_token),
            "storekeeper_token": str(storekeeper.user_token),
            "observer_token": str(observer.user_token),
            "category_id": category.id,
            "unit_id": unit.id,
            "catalog_item_id": catalog_item.id,
        }


# =============================================================================
# 1. CREATE draft — temporary entities are NOT materialized yet
# =============================================================================


@pytest.mark.asyncio
async def test_create_draft_with_temporary_line_does_not_materialize(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """При создании draft с временной строкой temporary сущности ещё не созданы,
    но snapshots и is_draft_temporary проставлены."""
    seed = await _seed(session_factory)

    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "deferred-create-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Временный кабель",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                        "description": "deferred create",
                        "hashtags": ["кабель"],
                    },
                },
                {
                    "line_number": 2,
                    "qty": 1,
                    "item_id": seed["catalog_item_id"],
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    # Temporary line: item_id и inventory_subject_id должны быть None
    assert body["lines"][0]["item_id"] is None
    assert body["lines"][0]["inventory_subject_id"] is None
    assert body["lines"][0]["temporary_item_id"] is None
    assert body["lines"][0]["is_draft_temporary"] is True
    # Snapshots должны быть заполнены
    assert body["lines"][0]["item_name_snapshot"] == "Временный кабель"
    assert body["lines"][0]["category_name_snapshot"] is not None
    # Catalog line: всё как обычно
    assert body["lines"][1]["item_id"] == seed["catalog_item_id"]
    assert body["lines"][1]["inventory_subject_id"] is not None
    assert body["lines"][1]["is_draft_temporary"] is False

    # Проверяем в БД: temporary сущности НЕ созданы
    async with session_factory() as session:
        temporary_items = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(temporary_items) == 0

        # Проверяем draft payload в строке
        lines = list((await session.execute(select(OperationLine).order_by(OperationLine.line_number))).scalars().all())
        assert len(lines) == 2
        assert lines[0].temporary_draft_payload is not None
        assert lines[0].temporary_draft_payload["client_key"] == "tmp-1"
        assert lines[0].temporary_draft_payload["name"] == "Временный кабель"
        assert lines[0].item_id is None
        assert lines[0].inventory_subject_id is None
        assert lines[1].temporary_draft_payload is None
        assert lines[1].item_id == seed["catalog_item_id"]
        assert lines[1].inventory_subject_id is not None


# =============================================================================
# 2. SUBMIT — materialization происходит при submit
# =============================================================================


@pytest.mark.asyncio
async def test_submit_materializes_deferred_temporary_lines(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """При submit deferred temporary lines материализуются:
    создаются backing item, temporary item, inventory subject,
    строки получают ссылки, balance/register workflow отрабатывает."""
    from app.models.asset_register import PendingAcceptanceBalance

    seed = await _seed(session_factory)

    # Создаём draft
    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "deferred-submit-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Временный кабель",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
                {
                    "line_number": 2,
                    "qty": 1,
                    "item_id": seed["catalog_item_id"],
                },
            ],
        },
    )
    assert create_response.status_code == 200
    operation = create_response.json()

    # До submit — temporary сущностей нет
    async with session_factory() as session:
        pre_temp = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(pre_temp) == 0

    # Submit
    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    # После submit — проверяем materialization
    async with session_factory() as session:
        # Temporary item создан
        temporary_items = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(temporary_items) == 1
        assert temporary_items[0].name == "Временный кабель"

        # Backing item создан
        backing_item = await session.get(Item, temporary_items[0].item_id)
        assert backing_item is not None
        assert backing_item.is_active is False

        # Inventory subject создан
        subjects = list((await session.execute(select(InventorySubject))).scalars().all())
        # Должно быть 2 subject: один для temporary, один для catalog
        assert len(subjects) == 2

        # Строки получили ссылки
        lines = list((await session.execute(select(OperationLine).order_by(OperationLine.line_number))).scalars().all())
        assert len(lines) == 2
        assert lines[0].item_id is not None
        assert lines[0].inventory_subject_id is not None
        assert lines[0].temporary_draft_payload is None  # payload очищен
        assert lines[1].item_id == seed["catalog_item_id"]
        assert lines[1].inventory_subject_id is not None

        # RECEIVE с acceptance_required создаёт pending registers, а не балансы
        pending_rows = list(
            (await session.execute(
                select(PendingAcceptanceBalance).where(
                    PendingAcceptanceBalance.destination_site_id == seed["site_id"]
                )
            )).scalars().all()
        )
        assert len(pending_rows) == 2


# =============================================================================
# 3. CANCEL draft — не пытается удалять несуществующие temporary items
# =============================================================================


@pytest.mark.asyncio
async def test_cancel_draft_with_temporary_line_does_not_fail(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Отмена draft с deferred temporary строкой не должна пытаться
    удалять несуществующие temporary items."""
    seed = await _seed(session_factory)

    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "deferred-cancel-draft-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Отменяемый",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_response.status_code == 200
    operation = create_response.json()

    # Cancel draft
    cancel_response = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["chief_token"]},
        json={"cancel": True, "reason": "test cancel draft"},
    )
    assert cancel_response.status_code == 200

    # Проверяем, что temporary items не создавались
    async with session_factory() as session:
        temporary_items = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(temporary_items) == 0

        # Операция отменена
        op = await session.get(Operation, operation["id"])
        assert op is not None
        assert op.status == "cancelled"


# =============================================================================
# 4. CANCEL submitted — materialized temporary items удаляются
# =============================================================================


@pytest.mark.asyncio
async def test_cancel_submitted_operation_deletes_materialized_temporary_items(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Отмена submitted операции корректно удаляет materialized temporary items."""
    seed = await _seed(session_factory)

    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "deferred-cancel-submitted-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Удаляемый",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_response.status_code == 200
    operation = create_response.json()

    # Submit
    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    # Проверяем, что temporary item создан
    async with session_factory() as session:
        pre_temp = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(pre_temp) == 1
        assert pre_temp[0].status == "active"

    # Cancel submitted
    cancel_response = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["chief_token"]},
        json={"cancel": True, "reason": "test cancel submitted"},
    )
    assert cancel_response.status_code == 200

    # Проверяем, что temporary item мягко удалён
    async with session_factory() as session:
        temp_items = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(temp_items) == 1
        assert temp_items[0].status == "deleted"
        assert "Auto-deleted on cancel" in (temp_items[0].resolution_note or "")


# =============================================================================
# 5. Mixed scenario — catalog + temporary lines в одной операции
# =============================================================================


@pytest.mark.asyncio
async def test_mixed_catalog_and_temporary_lines_work_together(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Каталожные и временные строки в одной операции работают вместе."""
    from app.models.asset_register import PendingAcceptanceBalance

    seed = await _seed(session_factory)

    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "deferred-mixed-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 3,
                    "temporary_item": {
                        "client_key": "tmp-a",
                        "name": "Временный А",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
                {
                    "line_number": 2,
                    "qty": 5,
                    "item_id": seed["catalog_item_id"],
                },
                {
                    "line_number": 3,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-b",
                        "name": "Временный Б",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_response.status_code == 200
    operation = create_response.json()

    # Draft: temporary lines без materialization
    assert operation["lines"][0]["is_draft_temporary"] is True
    assert operation["lines"][0]["item_id"] is None
    assert operation["lines"][2]["is_draft_temporary"] is True
    assert operation["lines"][2]["item_id"] is None
    assert operation["lines"][1]["is_draft_temporary"] is False
    assert operation["lines"][1]["item_id"] == seed["catalog_item_id"]

    # Submit
    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    # После submit: все строки материализованы
    async with session_factory() as session:
        lines = list((await session.execute(select(OperationLine).order_by(OperationLine.line_number))).scalars().all())
        assert len(lines) == 3
        for line in lines:
            assert line.item_id is not None
            assert line.inventory_subject_id is not None
            assert line.temporary_draft_payload is None

        # Должно быть 3 inventory subject (2 temporary + 1 catalog)
        subjects = list((await session.execute(select(InventorySubject))).scalars().all())
        assert len(subjects) == 3

        # Должно быть 2 temporary item
        temp_items = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(temp_items) == 2

        # RECEIVE с acceptance_required создаёт pending registers
        pending_rows = list(
            (await session.execute(
                select(PendingAcceptanceBalance).where(
                    PendingAcceptanceBalance.destination_site_id == seed["site_id"]
                )
            )).scalars().all()
        )
        assert len(pending_rows) == 3


# =============================================================================
# 6. Response contract — is_draft_temporary отображается корректно
# =============================================================================


@pytest.mark.asyncio
async def test_draft_temporary_line_response_contract(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Draft temporary line отображается как временная до submit."""
    seed = await _seed(session_factory)

    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "contract-test-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Тест контракта",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
                {
                    "line_number": 2,
                    "qty": 1,
                    "item_id": seed["catalog_item_id"],
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()

    # Temporary line
    temp_line = body["lines"][0]
    assert temp_line["is_draft_temporary"] is True
    assert temp_line["temporary_item_id"] is None
    assert temp_line["item_id"] is None
    assert temp_line["inventory_subject_id"] is None
    assert temp_line["item_name_snapshot"] == "Тест контракта"
    assert temp_line["category_name_snapshot"] is not None

    # Catalog line
    cat_line = body["lines"][1]
    assert cat_line["is_draft_temporary"] is False
    assert cat_line["item_id"] == seed["catalog_item_id"]
    assert cat_line["inventory_subject_id"] is not None

    # После submit — is_draft_temporary должен стать False
    submit_response = await client.post(
        f"/api/v1/operations/{body['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200
    submitted = submit_response.json()
    assert submitted["lines"][0]["is_draft_temporary"] is False
    assert submitted["lines"][0]["item_id"] is not None
    assert submitted["lines"][0]["inventory_subject_id"] is not None


# =============================================================================
# 7. Existing tests adapted to deferred model
# =============================================================================


@pytest.mark.asyncio
async def test_inline_temporary_item_requires_client_request_id_and_blocks_observer(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    no_request_id = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Без request id",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                }
            ],
        },
    )
    assert no_request_id.status_code == 422

    forbidden = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["observer_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "observer-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Нельзя observer",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                }
            ],
        },
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_inline_temporary_item_without_category_uses_uncategorized(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """При category_id=None сервер подставляет системную категорию 'Без категории'.
    При deferred создании категория нормализуется сразу, но сущности не создаются."""
    from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE

    seed = await _seed(session_factory)

    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "no-category-deferred-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-no-cat",
                        "name": "Без категории",
                        "unit_id": seed["unit_id"],
                        "category_id": None,
                    },
                }
            ],
        },
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    operation = response.json()
    assert len(operation["lines"]) == 1
    # В ответе должно быть указано имя категории "Без категории"
    assert operation["lines"][0]["category_name_snapshot"] == "Без категории"

    # Проверяем, что temporary сущности НЕ созданы (deferred)
    async with session_factory() as session:
        uncategorized = (
            await session.execute(select(Category).where(Category.code == UNCATEGORIZED_CATEGORY_CODE))
        ).scalar_one_or_none()
        assert uncategorized is not None, "Системная категория 'Без категории' должна существовать"

        # Backing item НЕ создан
        backing_item = (
            await session.execute(
                select(Item).where(Item.source_system == "temporary_item", Item.source_ref == "tmp-no-cat")
            )
        ).scalar_one_or_none()
        assert backing_item is None, "Backing item не должен создаваться на create"

        # Но в draft payload категория уже нормализована
        line = (await session.execute(
            select(OperationLine).where(OperationLine.operation_id == operation["id"])
        )).scalar_one()
        assert line.temporary_draft_payload is not None
        assert line.temporary_draft_payload["category_id"] == uncategorized.id


@pytest.mark.asyncio
async def test_temporary_items_review_endpoints_require_submit_first(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Temporary items создаются только после submit, поэтому review эндпоинты
    должны работать с submit-нутыми операциями."""
    seed = await _seed(session_factory)

    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "review-deferred-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "На разбор",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                }
            ],
        },
    )
    assert create_response.status_code == 200
    operation = create_response.json()

    # До submit — temporary items пусто
    list_before = await client.get(
        "/api/v1/temporary-items",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert list_before.status_code == 200
    assert list_before.json()["total_count"] == 0

    # Submit — materialization
    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    # После submit — temporary item доступен
    list_after = await client.get(
        "/api/v1/temporary-items",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert list_after.status_code == 200
    assert list_after.json()["total_count"] == 1

    temporary_item_id = list_after.json()["items"][0]["id"]

    detail_response = await client.get(
        f"/api/v1/temporary-items/{temporary_item_id}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "active"

    # RECEIVE с acceptance_required создаёт pending registers.
    # Нужно сначала принять строки, чтобы разрешить pending, затем approve.
    accept_response = await client.post(
        f"/api/v1/operations/{operation['id']}/accept-lines",
        headers={"X-User-Token": seed["chief_token"]},
        json={
            "lines": [
                {
                    "line_id": submit_response.json()["lines"][0]["id"],
                    "accepted_qty": 1,
                    "lost_qty": 0,
                }
            ]
        },
    )
    assert accept_response.status_code == 200

    approve_response = await client.post(
        f"/api/v1/temporary-items/{temporary_item_id}/approve-as-item",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved_as_item"
    assert approve_response.json()["resolved_item_id"] is not None
    assert approve_response.json()["resolution_type"] == "approve_as_item"


# =============================================================================
# 8. Idempotency — повторный create с тем же client_request_id
# =============================================================================


@pytest.mark.asyncio
async def test_idempotent_create_with_temporary_lines(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Повторный POST с тем же client_request_id возвращает ту же операцию."""
    seed = await _seed(session_factory)

    payload = {
        "operation_type": "RECEIVE",
        "site_id": seed["site_id"],
        "client_request_id": "idempotent-deferred-1",
        "lines": [
            {
                "line_number": 1,
                "qty": 2,
                "temporary_item": {
                    "client_key": "tmp-1",
                    "name": "Idempotent",
                    "unit_id": seed["unit_id"],
                    "category_id": seed["category_id"],
                },
            },
        ],
    }

    first = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload,
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload,
    )
    assert second.status_code == 200
    assert second.json()["id"] == first_id
