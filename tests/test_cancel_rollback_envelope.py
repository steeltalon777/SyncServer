"""DB-backed integration tests for the cancel-flow ProblemEnvelope (TZ §10.4).

Every rollback deficit of a submitted operation must surface as HTTP 409 with
the same envelope contract as submit (ADR-0027):

- type: urn:warehouse:problem:operation-cancel-rejected
- top-level code: operation_cancel_rejected
- errors[].code: insufficient_stock | insufficient_issued_balance |
  operation_in_wrong_state | role_not_permitted | operation_not_found
- errors[].operation_line_ids[], item.name, stock_site.name, required_qty /
  available_qty as strings.

Two TZ §10.4 cases are impossible against the implemented pre-check and are
replaced by their observable behaviour:

- EXPENSE rollback INCREASES the warehouse balance, so cancel can never be
  balance-blocked; the test proves cancel succeeds even at zero balance
  (test_cancel_expense_with_zero_balance_still_succeeds).
- WRITE_OFF with issue_object rollback RESTORES the issued register, so a
  deficit is impossible; the happy path is covered by
  test_cancel_write_off_with_issue_object_restores_issued.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.asset_register import IssuedAssetBalance
from app.models.audit_event import AuditEvent
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory
from app.models.item import Item
from app.models.operation import Operation
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from main import create_app

app = create_app(enable_startup_migrations=False)


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    item_qty: str = "10.000",
    second_site: bool = False,
    with_issue_object: bool = False,
    item_count: int = 1,
) -> dict:
    """Create sites, root user, catalog items, subjects, balances (and
    optionally a destination site / issue object)."""
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        dest = None
        if second_site:
            dest = Site(code=f"DST-{suffix}", name=f"Dest {suffix}", is_active=True)
            session.add(dest)
            await session.flush()

        root = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root Test",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        session.add(root)
        await session.flush()

        unit = Unit(name=f"pcs-{suffix}", symbol=f"p{suffix[:3]}", is_active=True)
        category = Category(name=f"cat-{suffix}", is_active=True)
        session.add_all([unit, category])
        await session.flush()

        items: list[dict] = []
        for idx in range(item_count):
            item = Item(
                sku=f"SKU-{suffix}-{idx}",
                name=f"Item {idx} {suffix}",
                category_id=category.id,
                unit_id=unit.id,
                is_active=True,
            )
            session.add(item)
            await session.flush()
            subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
            session.add(subject)
            await session.flush()
            items.append(
                {
                    "item_id": item.id,
                    "item_name": item.name,
                    "subject_id": subject.id,
                }
            )

        for item in items:
            session.add(
                Balance(
                    site_id=site.id,
                    inventory_subject_id=item["subject_id"],
                    item_id=item["item_id"],
                    qty=Decimal(item_qty),
                )
            )

        issue_object_id = None
        issue_object_name = None
        if with_issue_object:
            io_cat = IssueObjectCategory(
                name=f"People {suffix}",
                normalized_key=f"people {suffix}",
                sort_order=0,
                is_active=True,
            )
            session.add(io_cat)
            await session.flush()
            issue_object = IssueObject(
                display_name=f"Employee-{suffix}",
                normalized_key=f"employee {suffix}",
                object_type="person",
                is_active=True,
                category_id=io_cat.id,
            )
            session.add(issue_object)
            await session.flush()
            issue_object_id = issue_object.id
            issue_object_name = issue_object.display_name

        await session.commit()

        result = {
            "site_id": site.id,
            "site_name": site.name,
            "root_token": str(root.user_token),
            "items": items,
            "item_id": items[0]["item_id"],
            "item_name": items[0]["item_name"],
            "subject_id": items[0]["subject_id"],
        }
        if dest is not None:
            result["dest_site_id"] = dest.id
            result["dest_site_name"] = dest.name
        if issue_object_id is not None:
            result["issue_object_id"] = issue_object_id
            result["issue_object_name"] = issue_object_name
        return result


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    """Per-request sessions so concurrent requests use two transactions."""
    from httpx import ASGITransport, AsyncClient

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


async def _create_operation(client: AsyncClient, token: str, payload: dict) -> dict:
    resp = await client.post(
        "/api/v1/operations",
        json=payload,
        headers={"X-User-Token": token},
    )
    assert resp.status_code == 200, f"create failed: {resp.text}"
    return resp.json()


async def _submit(client: AsyncClient, token: str, op_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": token},
    )
    assert resp.status_code == 200, f"submit failed: {resp.text}"
    return resp.json()


async def _cancel(client: AsyncClient, token: str, op_id: str):
    return await client.post(
        f"/api/v1/operations/{op_id}/cancel",
        json={"cancel": True},
        headers={"X-User-Token": token},
    )


async def _set_balance(
    session_factory: async_sessionmaker[AsyncSession],
    site_id: int,
    subject_id: int,
    qty: str,
) -> None:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Balance).where(
                    Balance.site_id == site_id,
                    Balance.inventory_subject_id == subject_id,
                )
            )
        ).scalar_one()
        row.qty = Decimal(qty)
        await session.commit()


async def _set_issued(
    session_factory: async_sessionmaker[AsyncSession],
    issue_object_id: int,
    subject_id: int,
    qty: str,
) -> None:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(IssuedAssetBalance).where(
                    IssuedAssetBalance.issue_object_id == issue_object_id,
                    IssuedAssetBalance.inventory_subject_id == subject_id,
                )
            )
        ).scalar_one()
        row.qty = Decimal(qty)
        await session.commit()


async def _balance_qty(
    session_factory: async_sessionmaker[AsyncSession],
    site_id: int,
    subject_id: int,
) -> Decimal:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Balance).where(
                    Balance.site_id == site_id,
                    Balance.inventory_subject_id == subject_id,
                )
            )
        ).scalar_one_or_none()
        return Decimal(row.qty) if row is not None else Decimal("0")


async def _issued_qty(
    session_factory: async_sessionmaker[AsyncSession],
    issue_object_id: int,
    subject_id: int,
) -> Decimal:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(IssuedAssetBalance).where(
                    IssuedAssetBalance.issue_object_id == issue_object_id,
                    IssuedAssetBalance.inventory_subject_id == subject_id,
                )
            )
        ).scalar_one_or_none()
        return Decimal(row.qty) if row is not None else Decimal("0")


async def _operation_status(session_factory: async_sessionmaker[AsyncSession], op_id: str) -> str:
    async with session_factory() as session:
        row = (await session.execute(select(Operation).where(Operation.id == op_id))).scalar_one_or_none()
        return row.status if row is not None else "missing"


async def _cancel_event_count(session_factory: async_sessionmaker[AsyncSession], op_id: str) -> int:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "operation.cancel",
                    AuditEvent.entity_id == str(op_id),
                )
            )
        ).scalars().all()
        return len(rows)


def _assert_cancel_rejected(data: dict) -> None:
    assert data["type"] == "urn:warehouse:problem:operation-cancel-rejected"
    assert data["code"] == "operation_cancel_rejected"
    assert data["status"] == 409
    assert isinstance(data["detail"], str)
    errors = data.get("errors") or []
    assert errors and isinstance(errors, list)


@pytest.mark.asyncio
async def test_cancel_move_rollback_insufficient_stock_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submitted MOVE without acceptance over an empty destination → 409 envelope."""
    seed = await _seed(session_factory, item_qty="10.000", second_site=True)
    token = seed["root_token"]
    src, dst = seed["site_id"], seed["dest_site_id"]
    item_id, subject_id = seed["item_id"], seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "MOVE",
            "site_id": src,
            "source_site_id": src,
            "destination_site_id": dst,
            "acceptance_required": False,
            "lines": [{"line_number": 1, "item_id": item_id, "qty": 5}],
        },
    )
    await _submit(client, token, op["id"])
    assert await _balance_qty(session_factory, dst, subject_id) == Decimal("5.000")

    await _set_balance(session_factory, dst, subject_id, "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)
    assert "Недостаточно товара" in data["detail"]
    assert seed["item_name"] in data["detail"]

    first = data["errors"][0]
    assert first["code"] == "insufficient_stock"
    assert first["scope"] == "line_group"
    assert first["operation_line_ids"] == [op["lines"][0]["id"]]
    assert first["item"]["id"] == item_id
    assert first["item"]["name"] == seed["item_name"]
    assert first["stock_site"]["id"] == dst
    assert first["stock_site"]["name"] == seed["dest_site_name"]
    assert first["required_qty"] == "5.000"
    assert first["available_qty"] == "0.000"
    assert isinstance(first["required_qty"], str)
    assert isinstance(first["available_qty"], str)


@pytest.mark.asyncio
async def test_cancel_receive_rollback_insufficient_stock_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submitted RECEIVE whose rollback exceeds the current balance → 409 envelope."""
    # RECEIVE submit ADDS qty to the warehouse; a zero seed keeps the
    # post-submit balance exactly at the received quantity.
    seed = await _seed(session_factory, item_qty="0.000")
    token = seed["root_token"]
    site_id, subject_id = seed["site_id"], seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "acceptance_required": False,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 10}],
        },
    )
    await _submit(client, token, op["id"])
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("10.000")

    await _set_balance(session_factory, site_id, subject_id, "2.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)

    first = data["errors"][0]
    assert first["code"] == "insufficient_stock"
    assert first["scope"] == "line_group"
    assert first["item"]["name"] == seed["item_name"]
    assert first["stock_site"]["id"] == site_id
    assert first["operation_line_ids"] == [op["lines"][0]["id"]]
    assert first["required_qty"] == "10.000"
    assert first["available_qty"] == "2.000"


@pytest.mark.asyncio
async def test_cancel_expense_with_zero_balance_still_succeeds(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """EXPENSE rollback increases the warehouse, so a deficit is impossible.

    Replaces the TZ §10.4 case test_cancel_expense_rollback_insufficient_stock_envelope
    (submitted EXPENSE, остаток=0 → 409), which cannot exist against the
    implemented pre-check: EXPENSE/WRITE_OFF (без issue_object) НЕ требует
    остатка при отмене (TZ §5.1 / ADR-0027 §3, DECREMENT_OPERATION_TYPES skip).
    """
    seed = await _seed(session_factory, item_qty="10.000")
    token = seed["root_token"]
    site_id, subject_id = seed["site_id"], seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "EXPENSE",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
        },
    )
    await _submit(client, token, op["id"])
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("7.000")

    await _set_balance(session_factory, site_id, subject_id, "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("3.000")
    assert await _operation_status(session_factory, op["id"]) == "cancelled"


@pytest.mark.asyncio
async def test_cancel_adjustment_rollback_insufficient_stock_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submitted positive ADJUSTMENT whose rollback exceeds the current balance → 409."""
    seed = await _seed(session_factory, item_qty="0.000")
    token = seed["root_token"]
    site_id, subject_id = seed["site_id"], seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "ADJUSTMENT",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
        },
    )
    await _submit(client, token, op["id"])
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("5.000")

    await _set_balance(session_factory, site_id, subject_id, "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)

    first = data["errors"][0]
    assert first["code"] == "insufficient_stock"
    assert first["scope"] == "line_group"
    assert first["stock_site"]["id"] == site_id
    assert first["operation_line_ids"] == [op["lines"][0]["id"]]
    assert first["required_qty"] == "5.000"
    assert first["available_qty"] == "0.000"


@pytest.mark.asyncio
async def test_cancel_issue_rollback_insufficient_issued_balance_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submitted ISSUE whose rollback exceeds the issued register → 409 envelope."""
    seed = await _seed(session_factory, item_qty="10.000", with_issue_object=True)
    token = seed["root_token"]
    site_id = seed["site_id"]
    issue_object_id = seed["issue_object_id"]
    subject_id = seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "ISSUE",
            "site_id": site_id,
            "issue_object_id": issue_object_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
        },
    )
    await _submit(client, token, op["id"])
    assert await _issued_qty(session_factory, issue_object_id, subject_id) == Decimal("3.000")

    await _set_issued(session_factory, issue_object_id, subject_id, "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)

    first = data["errors"][0]
    assert first["code"] == "insufficient_issued_balance"
    assert first["scope"] == "line_group"
    assert first["issue_object"]["id"] == issue_object_id
    assert first["issue_object"]["name"] == seed["issue_object_name"]
    assert first["item"]["name"] == seed["item_name"]
    assert first["operation_line_ids"] == [op["lines"][0]["id"]]
    assert first["required_qty"] == "3.000"
    assert first["available_qty"] == "0.000"


@pytest.mark.asyncio
async def test_cancel_issue_return_rollback_insufficient_stock_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submitted ISSUE_RETURN whose rollback exceeds the warehouse balance → 409."""
    seed = await _seed(session_factory, item_qty="10.000", with_issue_object=True)
    token = seed["root_token"]
    site_id = seed["site_id"]
    issue_object_id = seed["issue_object_id"]
    subject_id = seed["subject_id"]

    issue = await _create_operation(
        client,
        token,
        {
            "operation_type": "ISSUE",
            "site_id": site_id,
            "issue_object_id": issue_object_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
        },
    )
    await _submit(client, token, issue["id"])

    ret = await _create_operation(
        client,
        token,
        {
            "operation_type": "ISSUE_RETURN",
            "site_id": site_id,
            "issue_object_id": issue_object_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 2}],
        },
    )
    await _submit(client, token, ret["id"])
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("9.000")

    await _set_balance(session_factory, site_id, subject_id, "0.000")

    resp = await _cancel(client, token, ret["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)

    first = data["errors"][0]
    assert first["code"] == "insufficient_stock"
    assert first["scope"] == "line_group"
    assert first["stock_site"]["id"] == site_id
    assert first["operation_line_ids"] == [ret["lines"][0]["id"]]
    assert first["required_qty"] == "2.000"
    assert first["available_qty"] == "0.000"


@pytest.mark.asyncio
async def test_cancel_write_off_with_issue_object_restores_issued(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """WRITE_OFF with issue_object rollback restores the issued register.

    Replaces the TZ §10.4 case test_cancel_write_off_with_issue_object_rollback_insufficient_issued_balance_envelope
    (submitted WRITE_OFF with issue_object, issued=0 → 409), which is impossible:
    cancel of such a WRITE_OFF INCREASES issued, so a deficit can never occur
    (ADR-0027 §3, WRITE_OFF + issue_object skips the pre-check entirely).
    """
    seed = await _seed(session_factory, item_qty="10.000", with_issue_object=True)
    token = seed["root_token"]
    site_id = seed["site_id"]
    issue_object_id = seed["issue_object_id"]
    subject_id = seed["subject_id"]

    issue = await _create_operation(
        client,
        token,
        {
            "operation_type": "ISSUE",
            "site_id": site_id,
            "issue_object_id": issue_object_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
        },
    )
    await _submit(client, token, issue["id"])
    assert await _issued_qty(session_factory, issue_object_id, subject_id) == Decimal("3.000")

    write_off = await _create_operation(
        client,
        token,
        {
            "operation_type": "WRITE_OFF",
            "site_id": site_id,
            "issue_object_id": issue_object_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 2}],
        },
    )
    await _submit(client, token, write_off["id"])
    assert await _issued_qty(session_factory, issue_object_id, subject_id) == Decimal("1.000")

    resp = await _cancel(client, token, write_off["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"
    assert await _issued_qty(session_factory, issue_object_id, subject_id) == Decimal("3.000")
    assert await _operation_status(session_factory, write_off["id"]) == "cancelled"


@pytest.mark.asyncio
async def test_cancel_move_with_acceptance_required_rollback_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submitted MOVE with acceptance: accepted_qty rollback deficit → 409 envelope."""
    seed = await _seed(session_factory, item_qty="10.000", second_site=True)
    token = seed["root_token"]
    src, dst = seed["site_id"], seed["dest_site_id"]
    item_id, subject_id = seed["item_id"], seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "MOVE",
            "site_id": src,
            "source_site_id": src,
            "destination_site_id": dst,
            "acceptance_required": True,
            "lines": [{"line_number": 1, "item_id": item_id, "qty": 5}],
        },
    )
    await _submit(client, token, op["id"])
    line_id = op["lines"][0]["id"]
    accept = await client.post(
        f"/api/v1/operations/{op['id']}/accept-lines",
        json={"lines": [{"line_id": line_id, "accepted_qty": 3, "lost_qty": 0}]},
        headers={"X-User-Token": token},
    )
    assert accept.status_code == 200, f"accept failed: {accept.text}"
    assert await _balance_qty(session_factory, dst, subject_id) == Decimal("3.000")

    await _set_balance(session_factory, dst, subject_id, "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)

    first = data["errors"][0]
    assert first["code"] == "insufficient_stock"
    assert first["scope"] == "line_group"
    assert first["stock_site"]["id"] == dst
    assert first["operation_line_ids"] == [line_id]
    assert first["required_qty"] == "3.000"
    assert first["available_qty"] == "0.000"


@pytest.mark.asyncio
async def test_cancel_operation_in_wrong_state_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Cancelling an already-cancelled operation → 409 envelope."""
    seed = await _seed(session_factory, item_qty="10.000")
    token = seed["root_token"]
    site_id = seed["site_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "EXPENSE",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
        },
    )
    await _submit(client, token, op["id"])

    first = await _cancel(client, token, op["id"])
    assert first.status_code == 200, first.text

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["type"] == "urn:warehouse:problem:operation-cancel-rejected"
    assert data["code"] == "operation_cancel_rejected"
    assert data["status"] == 409
    assert isinstance(data["detail"], str)
    assert len(data["errors"]) == 1
    first_error = data["errors"][0]
    assert first_error["code"] == "operation_in_wrong_state"
    assert first_error["scope"] == "operation"
    assert first_error["current_state"] == "cancelled"
    assert first_error["allowed_states"] == ["draft", "submitted"]


@pytest.mark.asyncio
async def test_cancel_operation_not_found_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Cancelling a non-existent operation → 404 envelope."""
    seed = await _seed(session_factory, item_qty="10.000")

    resp = await _cancel(client, seed["root_token"], str(uuid4()))
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data["type"] == "urn:warehouse:problem:operation-not-found"
    assert data["code"] == "operation_not_found"
    assert data["status"] == 404
    assert isinstance(data["detail"], str)
    assert len(data["errors"]) == 1
    first = data["errors"][0]
    assert first["code"] == "operation_not_found"
    assert first["scope"] == "operation"


@pytest.mark.asyncio
async def test_cancel_role_not_permitted_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Storekeeper without access to the operation site → 403 envelope."""
    seed = await _seed(session_factory, item_qty="10.000", second_site=True)
    site_id = seed["site_id"]

    op = await _create_operation(
        client,
        seed["root_token"],
        {
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "acceptance_required": False,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 1}],
        },
    )

    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        storekeeper = User(
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper Test",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=seed["dest_site_id"],
        )
        session.add(storekeeper)
        await session.flush()
        session.add(
            UserAccessScope(
                user_id=storekeeper.id,
                site_id=seed["dest_site_id"],
                can_view=True,
                can_operate=True,
                can_manage_catalog=False,
                is_active=True,
            )
        )
        await session.commit()
        storekeeper_token = str(storekeeper.user_token)

    resp = await _cancel(client, storekeeper_token, op["id"])
    assert resp.status_code == 403, resp.text
    data = resp.json()
    assert data["type"] == "urn:warehouse:problem:operation-cancel-rejected"
    assert data["code"] == "operation_cancel_rejected"
    assert data["status"] == 403
    assert isinstance(data["detail"], str)
    assert len(data["errors"]) == 1
    first = data["errors"][0]
    assert first["code"] == "role_not_permitted"
    assert first["scope"] == "operation"
    assert set(first.keys()) == {"code", "scope"}


@pytest.mark.asyncio
async def test_cancel_aggregate_deficits_multiple_lines(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two lines of different items with insufficient balance are reported separately."""
    seed = await _seed(session_factory, item_qty="10.000", second_site=True, item_count=2)
    token = seed["root_token"]
    src, dst = seed["site_id"], seed["dest_site_id"]
    item_a = seed["items"][0]
    item_b = seed["items"][1]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "MOVE",
            "site_id": src,
            "source_site_id": src,
            "destination_site_id": dst,
            "acceptance_required": False,
            "lines": [
                {"line_number": 1, "item_id": item_a["item_id"], "qty": 2},
                {"line_number": 2, "item_id": item_b["item_id"], "qty": 3},
            ],
        },
    )
    await _submit(client, token, op["id"])

    # Zero out both balances at destination
    await _set_balance(session_factory, dst, item_a["subject_id"], "0.000")
    await _set_balance(session_factory, dst, item_b["subject_id"], "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)
    assert len(data["errors"]) == 2


@pytest.mark.asyncio
async def test_cancel_determinism_deficit_order(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """errors[] is ordered by the line_number of each deficit group's first line."""
    seed = await _seed(session_factory, item_qty="5.000", second_site=True, item_count=3)
    token = seed["root_token"]
    src, dst = seed["site_id"], seed["dest_site_id"]
    items = seed["items"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "MOVE",
            "site_id": src,
            "source_site_id": src,
            "destination_site_id": dst,
            "acceptance_required": False,
            "lines": [
                {"line_number": 1, "item_id": items[0]["item_id"], "qty": 1},
                {"line_number": 2, "item_id": items[1]["item_id"], "qty": 1},
                {"line_number": 3, "item_id": items[2]["item_id"], "qty": 1},
            ],
        },
    )
    await _submit(client, token, op["id"])

    # Deficit on lines 1 and 3; line 2 stays sufficient.
    await _set_balance(session_factory, dst, items[0]["subject_id"], "0.000")
    await _set_balance(session_factory, dst, items[1]["subject_id"], "1.000")
    await _set_balance(session_factory, dst, items[2]["subject_id"], "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    data = resp.json()
    _assert_cancel_rejected(data)
    assert len(data["errors"]) == 2

    first, second = data["errors"]
    assert first["code"] == "insufficient_stock"
    assert second["code"] == "insufficient_stock"
    assert first["item"]["id"] == items[0]["item_id"]
    assert first["operation_line_ids"] == [op["lines"][0]["id"]]
    assert first["required_qty"] == "1.000"
    assert second["item"]["id"] == items[2]["item_id"]
    assert second["operation_line_ids"] == [op["lines"][2]["id"]]


@pytest.mark.asyncio
async def test_cancel_happy_path_no_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sufficient balance → 200, operation cancelled, balances restored, audit recorded."""
    seed = await _seed(session_factory, item_qty="10.000")
    token = seed["root_token"]
    site_id, subject_id = seed["site_id"], seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "EXPENSE",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
        },
    )
    await _submit(client, token, op["id"])
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("7.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "cancelled"
    assert data["id"] == op["id"]

    assert await _operation_status(session_factory, op["id"]) == "cancelled"
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("10.000")
    assert await _cancel_event_count(session_factory, op["id"]) == 1


@pytest.mark.asyncio
async def test_cancel_partial_rollback_failure_leaves_balance_unchanged(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Failed cancel leaves balances untouched, keeps the operation submitted and writes no audit.

    Uses RECEIVE instead of the EXPENSE case from TZ §10.4: EXPENSE rollback
    increases the warehouse, so it can never be balance-blocked; RECEIVE is
    the minimal operation whose cancel pre-check can fail.
    """
    seed = await _seed(session_factory, item_qty="0.000")
    token = seed["root_token"]
    site_id, subject_id = seed["site_id"], seed["subject_id"]

    op = await _create_operation(
        client,
        token,
        {
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "acceptance_required": False,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 10}],
        },
    )
    await _submit(client, token, op["id"])
    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("10.000")

    await _set_balance(session_factory, site_id, subject_id, "0.000")

    resp = await _cancel(client, token, op["id"])
    assert resp.status_code == 409, resp.text
    _assert_cancel_rejected(resp.json())

    assert await _balance_qty(session_factory, site_id, subject_id) == Decimal("0.000")
    assert await _operation_status(session_factory, op["id"]) == "submitted"
    assert await _cancel_event_count(session_factory, op["id"]) == 0
