from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.item import Item
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


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        source_site = Site(code=f"SRC-{suffix}", name=f"Source {suffix}")
        destination_site = Site(code=f"DST-{suffix}", name=f"Destination {suffix}")
        session.add_all([source_site, destination_site])
        await session.flush()

        chief = User(
            username=f"chief-{suffix}",
            email=f"chief-{suffix}@example.com",
            full_name="Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=source_site.id,
        )
        sender = User(
            username=f"sender-{suffix}",
            email=f"sender-{suffix}@example.com",
            full_name="Sender",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=source_site.id,
        )
        receiver = User(
            username=f"receiver-{suffix}",
            email=f"receiver-{suffix}@example.com",
            full_name="Receiver",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=destination_site.id,
        )
        root = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root",
            is_active=True,
            is_root=True,
            role="storekeeper",
            default_site_id=None,
        )
        observer = User(
            username=f"observer-{suffix}",
            email=f"observer-{suffix}@example.com",
            full_name="Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=destination_site.id,
        )
        session.add_all([chief, sender, receiver, root, observer])
        await session.flush()

        session.add_all(
            [
                UserAccessScope(
                    user_id=sender.id,
                    site_id=source_site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=False,
                    is_active=True,
                ),
                UserAccessScope(
                    user_id=receiver.id,
                    site_id=destination_site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=False,
                    is_active=True,
                ),
                UserAccessScope(
                    user_id=observer.id,
                    site_id=destination_site.id,
                    can_view=True,
                    can_operate=False,
                    can_manage_catalog=False,
                    is_active=True,
                ),
            ]
        )

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol=f"pc{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(
            code=f"CAT-{suffix}",
            name=f"Category {suffix}",
            normalized_name=f"category {suffix}",
            is_active=True,
        )
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"SKU-{suffix}",
            name=f"Item {suffix}",
            normalized_name=f"item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "source_site_id": source_site.id,
            "destination_site_id": destination_site.id,
            "item_id": item.id,
            "chief_token": str(chief.user_token),
            "sender_token": str(sender.user_token),
            "receiver_token": str(receiver.user_token),
            "root_token": str(root.user_token),
            "observer_token": str(observer.user_token),
        }


@pytest.mark.asyncio
async def test_move_submit_creates_pending_and_accept_resolves_to_destination_balance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)

    receive_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["source_site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 10}],
        },
    )
    assert receive_response.status_code == 200

    submit_receive = await client.post(
        f"/api/v1/operations/{receive_response.json()['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_receive.status_code == 200

    accept_receive = await client.post(
        f"/api/v1/operations/{receive_response.json()['id']}/accept-lines",
        headers={"X-User-Token": seed["sender_token"]},
        json={"lines": [{"line_id": receive_response.json()["lines"][0]["id"], "accepted_qty": 10, "lost_qty": 0}]},
    )
    assert accept_receive.status_code == 200

    move_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "MOVE",
            "site_id": seed["source_site_id"],
            "source_site_id": seed["source_site_id"],
            "destination_site_id": seed["destination_site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
        },
    )
    assert move_response.status_code == 200
    move_id = move_response.json()["id"]
    line_id = move_response.json()["lines"][0]["id"]

    submit_move = await client.post(
        f"/api/v1/operations/{move_id}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_move.status_code == 200
    assert submit_move.json()["acceptance_state"] == "pending"

    pending_before = await client.get(
        "/api/v1/pending-acceptance",
        headers={"X-User-Token": seed["receiver_token"]},
    )
    assert pending_before.status_code == 200
    assert pending_before.json()["total_count"] == 1
    assert Decimal(pending_before.json()["items"][0]["qty"]) == Decimal("5")

    balances_before = await client.get(
        "/api/v1/balances",
        headers={"X-User-Token": seed["receiver_token"]},
        params={"site_id": seed["destination_site_id"]},
    )
    assert balances_before.status_code == 200
    assert balances_before.json()["total_count"] == 0

    accept_move = await client.post(
        f"/api/v1/operations/{move_id}/accept-lines",
        headers={"X-User-Token": seed["receiver_token"]},
        json={"lines": [{"line_id": line_id, "accepted_qty": 3, "lost_qty": 2}]},
    )
    assert accept_move.status_code == 200
    assert accept_move.json()["acceptance_state"] == "resolved"

    pending_after = await client.get(
        "/api/v1/pending-acceptance",
        headers={"X-User-Token": seed["receiver_token"]},
    )
    assert pending_after.status_code == 200
    assert pending_after.json()["total_count"] == 0

    lost_after = await client.get(
        "/api/v1/lost-assets",
        headers={"X-User-Token": seed["receiver_token"]},
    )
    assert lost_after.status_code == 200
    assert lost_after.json()["total_count"] == 1
    assert Decimal(lost_after.json()["items"][0]["qty"]) == Decimal("2")

    balances_after = await client.get(
        "/api/v1/balances",
        headers={"X-User-Token": seed["receiver_token"]},
        params={"site_id": seed["destination_site_id"]},
    )
    assert balances_after.status_code == 200
    assert balances_after.json()["total_count"] == 1
    assert Decimal(balances_after.json()["items"][0]["qty"]) == Decimal("3")

    resolve_lost = await client.post(
        f"/api/v1/lost-assets/{line_id}/resolve",
        headers={"X-User-Token": seed["chief_token"]},
        json={"action": "found_to_destination", "qty": 1},
    )
    assert resolve_lost.status_code == 200

    lost_after_resolve = await client.get(
        "/api/v1/lost-assets",
        headers={"X-User-Token": seed["receiver_token"]},
    )
    assert lost_after_resolve.status_code == 200
    assert lost_after_resolve.json()["total_count"] == 1
    assert Decimal(lost_after_resolve.json()["items"][0]["qty"]) == Decimal("1")

    balances_after_resolve = await client.get(
        "/api/v1/balances",
        headers={"X-User-Token": seed["receiver_token"]},
        params={"site_id": seed["destination_site_id"]},
    )
    assert balances_after_resolve.status_code == 200
    assert balances_after_resolve.json()["total_count"] == 1
    assert Decimal(balances_after_resolve.json()["items"][0]["qty"]) == Decimal("4")


@pytest.mark.asyncio
async def test_move_acceptance_allows_only_target_storekeeper_chief_or_root(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)

    receive_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["source_site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 8}],
        },
    )
    assert receive_response.status_code == 200

    submit_receive = await client.post(
        f"/api/v1/operations/{receive_response.json()['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_receive.status_code == 200

    accept_receive = await client.post(
        f"/api/v1/operations/{receive_response.json()['id']}/accept-lines",
        headers={"X-User-Token": seed["sender_token"]},
        json={"lines": [{"line_id": receive_response.json()["lines"][0]["id"], "accepted_qty": 8, "lost_qty": 0}]},
    )
    assert accept_receive.status_code == 200

    move_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "MOVE",
            "site_id": seed["source_site_id"],
            "source_site_id": seed["source_site_id"],
            "destination_site_id": seed["destination_site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
        },
    )
    assert move_response.status_code == 200
    move_id = move_response.json()["id"]
    line_id = move_response.json()["lines"][0]["id"]

    submit_move = await client.post(
        f"/api/v1/operations/{move_id}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_move.status_code == 200

    sender_accept = await client.post(
        f"/api/v1/operations/{move_id}/accept-lines",
        headers={"X-User-Token": seed["sender_token"]},
        json={"lines": [{"line_id": line_id, "accepted_qty": 1, "lost_qty": 0}]},
    )
    assert sender_accept.status_code == 403
    assert sender_accept.json()["detail"] == "acceptance permission required for destination site"

    observer_accept = await client.post(
        f"/api/v1/operations/{move_id}/accept-lines",
        headers={"X-User-Token": seed["observer_token"]},
        json={"lines": [{"line_id": line_id, "accepted_qty": 1, "lost_qty": 0}]},
    )
    assert observer_accept.status_code == 403
    assert observer_accept.json()["detail"] == "acceptance permission required for destination site"

    chief_accept = await client.post(
        f"/api/v1/operations/{move_id}/accept-lines",
        headers={"X-User-Token": seed["chief_token"]},
        json={"lines": [{"line_id": line_id, "accepted_qty": 2, "lost_qty": 0}]},
    )
    assert chief_accept.status_code == 200
    assert chief_accept.json()["acceptance_state"] == "in_progress"

    root_accept = await client.post(
        f"/api/v1/operations/{move_id}/accept-lines",
        headers={"X-User-Token": seed["root_token"]},
        json={"lines": [{"line_id": line_id, "accepted_qty": 3, "lost_qty": 0}]},
    )
    assert root_accept.status_code == 200
    assert root_accept.json()["acceptance_state"] == "resolved"


@pytest.mark.asyncio
async def test_issue_and_return_moves_stock_to_recipient_register(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)

    receive_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["source_site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 4}],
        },
    )
    assert receive_response.status_code == 200
    submit_receive = await client.post(
        f"/api/v1/operations/{receive_response.json()['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_receive.status_code == 200
    accept_receive = await client.post(
        f"/api/v1/operations/{receive_response.json()['id']}/accept-lines",
        headers={"X-User-Token": seed["sender_token"]},
        json={"lines": [{"line_id": receive_response.json()["lines"][0]["id"], "accepted_qty": 4, "lost_qty": 0}]},
    )
    assert accept_receive.status_code == 200

    issue_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "ISSUE",
            "site_id": seed["source_site_id"],
            "recipient_name": "Employee A",
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
        },
    )
    assert issue_response.status_code == 200
    issue_id = issue_response.json()["id"]
    recipient_id = issue_response.json()["recipient_id"]

    submit_issue = await client.post(
        f"/api/v1/operations/{issue_id}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_issue.status_code == 200

    issued_rows = await client.get(
        "/api/v1/issued-assets",
        headers={"X-User-Token": seed["sender_token"]},
        params={"recipient_id": recipient_id},
    )
    assert issued_rows.status_code == 200
    assert issued_rows.json()["total_count"] == 1
    assert Decimal(issued_rows.json()["items"][0]["qty"]) == Decimal("3")

    issue_return_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "ISSUE_RETURN",
            "site_id": seed["source_site_id"],
            "recipient_id": recipient_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 1}],
        },
    )
    assert issue_return_response.status_code == 200

    submit_return = await client.post(
        f"/api/v1/operations/{issue_return_response.json()['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_return.status_code == 200

    issued_after_return = await client.get(
        "/api/v1/issued-assets",
        headers={"X-User-Token": seed["sender_token"]},
        params={"recipient_id": recipient_id},
    )
    assert issued_after_return.status_code == 200
    assert issued_after_return.json()["total_count"] == 1
    assert Decimal(issued_after_return.json()["items"][0]["qty"]) == Decimal("2")
