from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.balance import Balance
from app.models.category import Category
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from main import create_app

app = create_app(enable_startup_migrations=False)


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


async def _seed_reports_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, int | str]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site_main = Site(code=f"R-S1-{suffix}", name=f"Main Site {suffix}")
        site_reserve = Site(code=f"R-S2-{suffix}", name=f"Reserve Site {suffix}")
        session.add_all([site_main, site_reserve])
        await session.flush()

        chief = User(
            username=f"chief-reports-{suffix}",
            email=f"chief-reports-{suffix}@example.com",
            full_name="Chief Reports",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site_main.id,
        )
        observer = User(
            username=f"observer-reports-{suffix}",
            email=f"observer-reports-{suffix}@example.com",
            full_name="Observer Reports",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site_main.id,
        )
        session.add_all([chief, observer])
        await session.flush()

        session.add(
            UserAccessScope(
                user_id=observer.id,
                site_id=site_main.id,
                can_view=True,
                can_operate=False,
                can_manage_catalog=False,
                is_active=True,
            )
        )

        unit = Unit(name=f"Piece Reports {suffix}", symbol=f"rp{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(name=f"Warehouse Goods {suffix}", code=f"WG-{suffix}", is_active=True)
        session.add(category)
        await session.flush()

        tracked_item = Item(
            sku=f"TRACK-{suffix}",
            name=f"Tracked Item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        helper_item = Item(
            sku=f"HELP-{suffix}",
            name=f"Helper Item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        reserve_item = Item(
            sku=f"RSV-{suffix}",
            name=f"Reserve Item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add_all([tracked_item, helper_item, reserve_item])
        await session.flush()

        jan10 = datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc)
        jan11 = datetime(2026, 1, 11, 9, 0, tzinfo=timezone.utc)
        jan12 = datetime(2026, 1, 12, 9, 0, tzinfo=timezone.utc)
        jan13 = datetime(2026, 1, 13, 9, 0, tzinfo=timezone.utc)
        jan14 = datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)

        receive = Operation(
            site_id=site_main.id,
            operation_type="RECEIVE",
            status="submitted",
            effective_at=jan10,
            created_by_user_id=chief.id,
            created_at=jan10,
            updated_at=jan10,
            submitted_at=jan10,
            submitted_by_user_id=chief.id,
        )
        expense = Operation(
            site_id=site_main.id,
            operation_type="EXPENSE",
            status="submitted",
            effective_at=jan11,
            created_by_user_id=chief.id,
            created_at=jan11,
            updated_at=jan11,
            submitted_at=jan11,
            submitted_by_user_id=chief.id,
        )
        adjustment = Operation(
            site_id=site_main.id,
            operation_type="ADJUSTMENT",
            status="submitted",
            effective_at=jan12,
            created_by_user_id=chief.id,
            created_at=jan12,
            updated_at=jan12,
            submitted_at=jan12,
            submitted_by_user_id=chief.id,
        )
        move = Operation(
            site_id=site_main.id,
            operation_type="MOVE",
            status="submitted",
            effective_at=jan13,
            source_site_id=site_main.id,
            destination_site_id=site_reserve.id,
            created_by_user_id=chief.id,
            created_at=jan13,
            updated_at=jan13,
            submitted_at=jan13,
            submitted_by_user_id=chief.id,
        )
        cancelled = Operation(
            site_id=site_main.id,
            operation_type="RECEIVE",
            status="cancelled",
            effective_at=jan14,
            created_by_user_id=chief.id,
            created_at=jan14,
            updated_at=jan14,
        )
        session.add_all([receive, expense, adjustment, move, cancelled])
        await session.flush()

        session.add_all(
            [
                OperationLine(operation_id=receive.id, line_number=1, item_id=tracked_item.id, qty=Decimal("10")),
                OperationLine(operation_id=expense.id, line_number=1, item_id=tracked_item.id, qty=Decimal("3")),
                OperationLine(operation_id=adjustment.id, line_number=1, item_id=tracked_item.id, qty=Decimal("-1")),
                OperationLine(operation_id=move.id, line_number=1, item_id=tracked_item.id, qty=Decimal("2")),
                OperationLine(operation_id=cancelled.id, line_number=1, item_id=tracked_item.id, qty=Decimal("99")),
            ]
        )

        session.add_all(
            [
                Balance(site_id=site_main.id, item_id=tracked_item.id, qty=Decimal("4")),
                Balance(site_id=site_main.id, item_id=helper_item.id, qty=Decimal("1")),
                Balance(site_id=site_reserve.id, item_id=reserve_item.id, qty=Decimal("8")),
            ]
        )

        await session.commit()

        return {
            "chief_token": str(chief.user_token),
            "observer_token": str(observer.user_token),
            "site_main_id": site_main.id,
            "tracked_item_id": tracked_item.id,
            "site_main_name": site_main.name,
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_item_movement_report_aggregates_submitted_operations_for_period(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_reports_fixture(session_factory)

    response = await client.get(
        "/api/v1/reports/item-movement",
        headers={"X-User-Token": seed["chief_token"]},
        params={
            "site_id": seed["site_main_id"],
            "item_id": seed["tracked_item_id"],
            "date_from": "2026-01-01T00:00:00+00:00",
            "date_to": "2026-01-31T23:59:59+00:00",
            "page": 1,
            "page_size": 20,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1

    row = body["items"][0]
    assert row["site_name"] == seed["site_main_name"]
    assert Decimal(row["incoming_qty"]) == Decimal("10")
    assert Decimal(row["outgoing_qty"]) == Decimal("6")
    assert Decimal(row["net_qty"]) == Decimal("4")
    assert row["last_operation_at"].startswith("2026-01-13T09:00:00")


@pytest.mark.asyncio(loop_scope="session")
async def test_stock_summary_report_respects_visible_sites_scope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_reports_fixture(session_factory)

    response = await client.get(
        "/api/v1/reports/stock-summary",
        headers={"X-User-Token": seed["observer_token"]},
        params={"page": 1, "page_size": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1

    row = body["items"][0]
    assert row["site_name"] == seed["site_main_name"]
    assert row["items_count"] == 2
    assert row["positive_items_count"] == 2
    assert Decimal(row["total_quantity"]) == Decimal("5")
