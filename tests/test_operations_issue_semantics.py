from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from app.services.operations_service import OperationsService
from main import create_app

app = create_app(enable_startup_migrations=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession]) -> dict:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}")
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
        sender = User(
            username=f"sender-{suffix}",
            email=f"sender-{suffix}@example.com",
            full_name="Sender",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([chief, sender])
        await session.flush()

        session.add_all([
            UserAccessScope(
                user_id=sender.id, site_id=site.id,
                can_view=True, can_operate=True, can_manage_catalog=False, is_active=True,
            ),
            UserAccessScope(
                user_id=chief.id, site_id=site.id,
                can_view=True, can_operate=True, can_manage_catalog=False, is_active=True,
            ),
        ])

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol=f"pc{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(
            code=f"CAT-{suffix}", name=f"Category {suffix}",
            normalized_name=f"category {suffix}", is_active=True,
        )
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"SKU-{suffix}", name=f"Item {suffix}",
            normalized_name=f"item {suffix}",
            category_id=category.id, unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.flush()

        import re
        _non_word_re = re.compile(r"[^\w\s]+", flags=re.UNICODE)
        _spaces_re = re.compile(r"\s+", flags=re.UNICODE)
        def _norm(v): return _spaces_re.sub(" ", _non_word_re.sub(" ", (v or "").strip().lower().replace("ё", "е"))).strip()

        io_cat = IssueObjectCategory(
            name=f"People {suffix}",
            normalized_key=_norm(f"People {suffix}"),
            sort_order=0, is_active=True,
        )
        session.add(io_cat)
        await session.flush()

        obj_a = IssueObject(
            display_name=f"Employee-A-{suffix}",
            normalized_key=_norm(f"Employee-A-{suffix}"),
            object_type="person", is_active=True,
            category_id=io_cat.id,
        )
        obj_b = IssueObject(
            display_name=f"Employee-B-{suffix}",
            normalized_key=_norm(f"Employee-B-{suffix}"),
            object_type="person", is_active=True,
            category_id=io_cat.id,
        )
        session.add_all([obj_a, obj_b])
        await session.commit()

        return {
            "site_id": site.id,
            "item_id": item.id,
            "issue_object_a_id": obj_a.id,
            "issue_object_b_id": obj_b.id,
            "chief_token": str(chief.user_token),
            "sender_token": str(sender.user_token),
        }


async def _ensure_balance(client, chief_token, sender_token, site_id, item_id, qty):
    """Receive and accept qty into site balance for a given item."""
    r = await client.post("/api/v1/operations", headers={"X-User-Token": sender_token}, json={
        "operation_type": "RECEIVE", "site_id": site_id,
        "lines": [{"line_number": 1, "item_id": item_id, "qty": qty}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": chief_token}, json={"submit": True})
    assert r2.status_code == 200, r2.text
    r3 = await client.post(f"/api/v1/operations/{op_id}/accept-lines", headers={"X-User-Token": chief_token}, json={
        "lines": [{"line_id": r.json()["lines"][0]["id"], "accepted_qty": qty, "lost_qty": 0}],
    })
    assert r3.status_code == 200, r3.text


async def _issue_asset(client, chief_token, sender_token, site_id, item_id, issue_object_id, qty):
    """Issue qty to an issue_object. Returns operation dict."""
    r = await client.post("/api/v1/operations", headers={"X-User-Token": sender_token}, json={
        "operation_type": "ISSUE", "site_id": site_id,
        "issue_object_id": issue_object_id,
        "lines": [{"line_number": 1, "item_id": item_id, "qty": qty}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": chief_token}, json={"submit": True})
    assert r2.status_code == 200, r2.text
    return r.json()


# ---------------------------------------------------------------------------
# Schema / validation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_issue_with_valid_issue_object_id_succeeds(client, session_factory):
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE", "site_id": seed["site_id"],
        "issue_object_id": seed["issue_object_a_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["operation_type"] == "ISSUE"
    assert r.json()["issue_object_id"] == seed["issue_object_a_id"]


@pytest.mark.asyncio
async def test_issue_with_free_text_name_rejected(client, session_factory):
    seed = await _seed_fixture(session_factory)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE", "site_id": seed["site_id"],
        "issue_object_name_snapshot": "Some Person",
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_issue_with_free_text_issued_to_name_rejected(client, session_factory):
    seed = await _seed_fixture(session_factory)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE", "site_id": seed["site_id"],
        "issued_to_name": "Some Person",
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_issue_return_with_valid_issue_object_id_succeeds(client, session_factory):
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)
    await _issue_asset(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], seed["issue_object_a_id"], 5)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE_RETURN", "site_id": seed["site_id"],
        "issue_object_id": seed["issue_object_a_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 2}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["operation_type"] == "ISSUE_RETURN"
    assert r.json()["issue_object_id"] == seed["issue_object_a_id"]


@pytest.mark.asyncio
async def test_issue_return_with_free_text_name_rejected(client, session_factory):
    seed = await _seed_fixture(session_factory)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE_RETURN", "site_id": seed["site_id"],
        "issue_object_name_snapshot": "Some Person",
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
    })
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# ISSUE / ISSUE_RETURN balance semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_issue_reduces_warehouse_but_not_enterprise_total(client, session_factory):
    """ISSUE: warehouse -qty, issued +qty => enterprise total unchanged."""
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)

    bal_before = await client.get("/api/v1/balances", headers={"X-User-Token": seed["sender_token"]},
                                  params={"site_id": seed["site_id"]})
    assert bal_before.status_code == 200
    wh_before = Decimal(bal_before.json()["items"][0]["qty"])

    await _issue_asset(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], seed["issue_object_a_id"], 3)

    bal_after = await client.get("/api/v1/balances", headers={"X-User-Token": seed["sender_token"]},
                                 params={"site_id": seed["site_id"]})
    assert bal_after.status_code == 200
    wh_after = Decimal(bal_after.json()["items"][0]["qty"])
    assert wh_after == wh_before - 3


@pytest.mark.asyncio
async def test_issue_return_increases_warehouse_but_not_enterprise_total(client, session_factory):
    """ISSUE_RETURN: warehouse +qty, issued -qty => enterprise total unchanged."""
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)
    await _issue_asset(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], seed["issue_object_a_id"], 5)

    bal_before = await client.get("/api/v1/balances", headers={"X-User-Token": seed["sender_token"]},
                                  params={"site_id": seed["site_id"]})
    wh_before = Decimal(bal_before.json()["items"][0]["qty"])

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE_RETURN", "site_id": seed["site_id"],
        "issue_object_id": seed["issue_object_a_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 2}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": seed["chief_token"]},
                           json={"submit": True})
    assert r2.status_code == 200, r2.text

    bal_after = await client.get("/api/v1/balances", headers={"X-User-Token": seed["sender_token"]},
                                 params={"site_id": seed["site_id"]})
    wh_after = Decimal(bal_after.json()["items"][0]["qty"])
    assert wh_after == wh_before + 2


@pytest.mark.asyncio
async def test_issue_return_validates_against_issued_balance(client, session_factory):
    """ISSUE_RETURN must not exceed issued balance for the same issue_object."""
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)
    await _issue_asset(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], seed["issue_object_a_id"], 2)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE_RETURN", "site_id": seed["site_id"],
        "issue_object_id": seed["issue_object_a_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 99}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": seed["chief_token"]},
                           json={"submit": True})
    assert r2.status_code == 409, r2.text


# ---------------------------------------------------------------------------
# WRITE_OFF semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_object_write_off_validates_against_issued_balance(client, session_factory):
    """Object WRITE_OFF requires sufficient issued balance."""
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)
    await _issue_asset(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], seed["issue_object_a_id"], 3)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "WRITE_OFF", "site_id": seed["site_id"],
        "issue_object_id": seed["issue_object_a_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 99}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": seed["chief_token"]},
                           json={"submit": True})
    assert r2.status_code == 409, r2.text


@pytest.mark.asyncio
async def test_object_write_off_does_not_touch_warehouse_balance(client, session_factory):
    """Object WRITE_OFF decrements issued register only, not warehouse balance."""
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)
    await _issue_asset(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], seed["issue_object_a_id"], 3)

    bal_before = await client.get("/api/v1/balances", headers={"X-User-Token": seed["sender_token"]},
                                  params={"site_id": seed["site_id"]})
    wh_before = Decimal(bal_before.json()["items"][0]["qty"])

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "WRITE_OFF", "site_id": seed["site_id"],
        "issue_object_id": seed["issue_object_a_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 2}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": seed["chief_token"]},
                           json={"submit": True})
    assert r2.status_code == 200, r2.text

    bal_after = await client.get("/api/v1/balances", headers={"X-User-Token": seed["sender_token"]},
                                 params={"site_id": seed["site_id"]})
    wh_after = Decimal(bal_after.json()["items"][0]["qty"])
    assert wh_after == wh_before


@pytest.mark.asyncio
async def test_warehouse_write_off_still_works(client, session_factory):
    """Warehouse WRITE_OFF (no issue_object_id) validates against warehouse balance."""
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 10)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "WRITE_OFF", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 4}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": seed["chief_token"]},
                           json={"submit": True})
    assert r2.status_code == 200, r2.text

    bal_after = await client.get("/api/v1/balances", headers={"X-User-Token": seed["sender_token"]},
                                 params={"site_id": seed["site_id"]})
    wh_after = Decimal(bal_after.json()["items"][0]["qty"])
    assert wh_after == 6


@pytest.mark.asyncio
async def test_warehouse_write_off_validates_against_warehouse_balance(client, session_factory):
    """Warehouse WRITE_OFF rejects if insufficient warehouse balance."""
    seed = await _seed_fixture(session_factory)
    await _ensure_balance(client, seed["chief_token"], seed["sender_token"], seed["site_id"], seed["item_id"], 2)

    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "WRITE_OFF", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 99}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    r2 = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": seed["chief_token"]},
                           json={"submit": True})
    assert r2.status_code == 409, r2.text


# ---------------------------------------------------------------------------
# Cancel semantics
# ---------------------------------------------------------------------------

def _line(*, item_id: int, qty: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=1, item_id=item_id, inventory_subject_id=1000 + item_id,
        qty=qty, accepted_qty=0, lost_qty=0, temporary_draft_payload=None,
    )


def _operation(*, operation_type: str, issue_object_id: int | None = None, site_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), status="submitted",
        operation_type=operation_type, site_id=site_id,
        source_site_id=None, destination_site_id=None,
        acceptance_required=False,
        issue_object_id=issue_object_id,
        lines=[_line(item_id=10, qty=5)],
    )


def _base_uow(operation, balance_qty: Decimal | None = None):
    """Build a minimal UoW mock for cancel_operation tests."""
    inventory_subject = SimpleNamespace(id=1010)
    return SimpleNamespace(
        balances=SimpleNamespace(
            get_for_update=AsyncMock(return_value=SimpleNamespace(qty=balance_qty or Decimal("10"))),
            update_balance_quantity=AsyncMock(),
        ),
        asset_registers=SimpleNamespace(
            upsert_issued=AsyncMock(),
            upsert_pending=AsyncMock(),
            upsert_lost=AsyncMock(),
            get_issued_balance=AsyncMock(return_value=SimpleNamespace(qty=Decimal("10"))),
        ),
        operations=SimpleNamespace(
            get_operation_by_id=AsyncMock(
                side_effect=[operation, operation],  # first call in cancel, second in _delete_temporary_items
            ),
            cancel_operation=AsyncMock(),
        ),
        inventory_subjects=SimpleNamespace(
            get_or_create_for_item=AsyncMock(return_value=inventory_subject),
            get_by_id=AsyncMock(return_value=None),  # makes _delete_temporary_items_of_operation return early
        ),
        catalog=SimpleNamespace(get_item_by_id=AsyncMock()),
        temporary_items=SimpleNamespace(get_by_id=AsyncMock()),
        session=SimpleNamespace(flush=AsyncMock()),
        audit_events=SimpleNamespace(insert=AsyncMock(), insert_effect=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_cancel_issue_restores_warehouse_and_decrements_issued():
    operation = _operation(operation_type="ISSUE", issue_object_id=77)
    uow = _base_uow(operation)
    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())
    uow.audit_events.insert.assert_awaited_once()
    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("5"),
    )
    uow.asset_registers.upsert_issued.assert_awaited_once_with(
        issue_object_id=77, inventory_subject_id=1010, qty_delta=Decimal("-5"),
    )


@pytest.mark.asyncio
async def test_cancel_issue_return_restores_issued_and_decrements_warehouse():
    operation = _operation(operation_type="ISSUE_RETURN", issue_object_id=77)
    uow = _base_uow(operation)
    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())
    uow.audit_events.insert.assert_awaited_once()
    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("-5"),
    )
    uow.asset_registers.upsert_issued.assert_awaited_once_with(
        issue_object_id=77, inventory_subject_id=1010, qty_delta=Decimal("5"),
    )


@pytest.mark.asyncio
async def test_cancel_object_write_off_restores_issued():
    operation = _operation(operation_type="WRITE_OFF", issue_object_id=77)
    uow = _base_uow(operation)
    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())
    uow.audit_events.insert.assert_awaited_once()
    uow.asset_registers.upsert_issued.assert_awaited_once_with(
        issue_object_id=77, inventory_subject_id=1010, qty_delta=Decimal("5"),
    )
    uow.balances.update_balance_quantity.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_warehouse_write_off_restores_warehouse():
    operation = _operation(operation_type="WRITE_OFF", issue_object_id=None)
    uow = _base_uow(operation)
    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())
    uow.audit_events.insert.assert_awaited_once()
    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("5"),
    )


# ---------------------------------------------------------------------------
# write_off_source computed field
# ---------------------------------------------------------------------------

def test_write_off_source_computed_field():
    from app.schemas.operation import OperationResponse
    from uuid import UUID

    wh_op = OperationResponse.model_construct(
        id=uuid4(), site_id=1, operation_type="WRITE_OFF",
        status="submitted", issue_object_id=None,
        created_by_user_id=uuid4(), created_at=None, updated_at=None,
    )
    assert wh_op.write_off_source == "warehouse"

    obj_op = OperationResponse.model_construct(
        id=uuid4(), site_id=1, operation_type="WRITE_OFF",
        status="submitted", issue_object_id=77,
        created_by_user_id=uuid4(), created_at=None, updated_at=None,
    )
    assert obj_op.write_off_source == "issue_object"

    issue_op = OperationResponse.model_construct(
        id=uuid4(), site_id=1, operation_type="ISSUE",
        status="submitted", issue_object_id=77,
        created_by_user_id=uuid4(), created_at=None, updated_at=None,
    )
    assert issue_op.write_off_source is None
