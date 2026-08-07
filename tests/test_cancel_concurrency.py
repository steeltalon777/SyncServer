"""Concurrency tests for the cancel-flow envelope (TZ §10.5).

Each test proves the race with a real two-party barrier/hook installed on the
critical row-lock call, mirroring `test_submit_concurrency.py`:

1. `test_concurrent_cancel_and_submit` — a cancel that reaches the operation
   row lock first commits `cancelled`; the queued submit then reads the
   committed state and gets 409 `operation_in_wrong_state` (current_state
   "cancelled"), never a double transition.
2. `test_concurrent_two_cancels` — two cancels of one submitted RECEIVE race
   at the balance pre-check row lock; exactly one wins (200), the loser reads
   the post-rollback balance inside its lock and gets 409 `insufficient_stock`.
   Exactly one `operation.cancel` audit event is written and the balance never
   goes negative (no double rollback).
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.audit_event import AuditEvent
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.repos.balances_repo import BalancesRepo
from app.repos.operations_repo import OperationsRepo
from main import create_app

app = create_app(enable_startup_migrations=False)

TIMEOUT = 15


class _ArrivalBarrier:
    """Two-party arrival barrier used to prove the race.

    The first caller sets ``first``; when ``parties`` callers have arrived,
    ``all`` is set. Every caller then waits on ``release``. A caller that
    reaches the barrier again passes straight through once ``release`` is set.
    """

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._count = 0
        self.first = asyncio.Event()
        self.all = asyncio.Event()
        self.release = asyncio.Event()

    async def wait(self) -> None:
        self._count += 1
        if self._count == 1:
            self.first.set()
        if self._count >= self._parties:
            self.all.set()
        await self.release.wait()


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    """Per-request sessions so two concurrent requests use two transactions."""
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


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict:
    """One site, one root user, one item with a zero-remaining balance row."""
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
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

        item = Item(
            sku=f"SKU-{suffix}",
            name=f"Item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.flush()

        subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
        session.add(subject)
        await session.flush()

        session.add(
            Balance(
                site_id=site.id,
                inventory_subject_id=subject.id,
                item_id=item.id,
                qty=Decimal("0.000"),
            )
        )
        await session.commit()

        return {
            "site_id": site.id,
            "root_token": str(root.user_token),
            "item_id": item.id,
            "subject_id": subject.id,
        }


async def _create_receive(client: AsyncClient, seed: dict, qty: int = 10) -> str:
    resp = await client.post(
        "/api/v1/operations",
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "acceptance_required": False,
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": qty}],
        },
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, f"create failed: {resp.text}"
    return resp.json()["id"]


async def _submit(client: AsyncClient, token: str, op_id: str):
    return await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": token},
    )


async def _cancel(client: AsyncClient, token: str, op_id: str):
    return await client.post(
        f"/api/v1/operations/{op_id}/cancel",
        json={"cancel": True},
        headers={"X-User-Token": token},
    )


async def _balance_qty(session_factory: async_sessionmaker[AsyncSession], site_id: int, subject_id: int) -> Decimal:
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


async def _operation_status(session_factory: async_sessionmaker[AsyncSession], op_id: str) -> str:
    async with session_factory() as session:
        row = (
            await session.execute(select(Operation).where(Operation.id == op_id))
        ).scalar_one_or_none()
        return row.status if row is not None else "missing"


async def _event_count(session_factory: async_sessionmaker[AsyncSession], op_id: str, event_type: str) -> int:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == event_type,
                    AuditEvent.entity_id == str(op_id),
                )
            )
        ).scalars().all()
        return len(rows)


async def _run(scenario_coro):
    """Run the concurrency orchestration under a hard timeout."""
    return await asyncio.wait_for(scenario_coro, timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_concurrent_cancel_and_submit(client, session_factory, monkeypatch):
    """TZ §10.5: cancel that reaches the row lock first wins; the queued submit
    reads the committed 'cancelled' state and gets 409 operation_in_wrong_state."""
    seed = await _seed(session_factory)
    op_id = await _create_receive(client, seed)

    original = OperationsRepo.get_operation_by_id_for_update
    cancel_locked = asyncio.Event()
    submit_at_lock = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def ordered_hook(self, operation_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            # First caller is the cancel: take the row lock, then hold it
            # until the submit is queued behind the same lock.
            result = await original(self, operation_id)
            cancel_locked.set()
            await asyncio.wait_for(release.wait(), TIMEOUT)
            return result
        # Second caller is the submit: signal that it reached the lock step,
        # then block on the real lock until the cancel commits.
        submit_at_lock.set()
        return await original(self, operation_id)

    monkeypatch.setattr(OperationsRepo, "get_operation_by_id_for_update", ordered_hook)

    async def cancel_task():
        return await _cancel(client, seed["root_token"], op_id)

    async def submit_task():
        return await _submit(client, seed["root_token"], op_id)

    async def scenario():
        t1 = asyncio.create_task(cancel_task())
        await asyncio.wait_for(cancel_locked.wait(), TIMEOUT)
        t2 = asyncio.create_task(submit_task())
        await asyncio.wait_for(submit_at_lock.wait(), TIMEOUT)
        release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r_cancel, r_submit = await _run(scenario())

    assert r_cancel.status_code == 200, r_cancel.text
    assert r_cancel.json()["status"] == "cancelled"

    assert r_submit.status_code == 409, r_submit.text
    data = r_submit.json()
    assert data["status"] == 409
    assert data["code"] == "operation_submit_rejected"
    errors = data["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "operation_in_wrong_state"
    assert errors[0]["scope"] == "operation"
    assert errors[0]["current_state"] == "cancelled"

    # The draft was cancelled before any submit side effect: no balance change
    # (RECEIVE was never submitted), no submit audit, exactly one cancel event.
    assert await _operation_status(session_factory, op_id) == "cancelled"
    assert await _balance_qty(session_factory, seed["site_id"], seed["subject_id"]) == Decimal("0.000")
    assert await _event_count(session_factory, op_id, "operation.submit") == 0
    assert await _event_count(session_factory, op_id, "operation.cancel") == 1


@pytest.mark.asyncio
async def test_concurrent_two_cancels(client, session_factory, monkeypatch):
    """TZ §10.5: two cancels of one submitted RECEIVE — exactly one wins, the
    loser reads the depleted balance inside the pre-check row lock and gets
    409; no double rollback, exactly one cancel audit event."""
    seed = await _seed(session_factory)
    op_id = await _create_receive(client, seed)

    submitted = await _submit(client, seed["root_token"], op_id)
    assert submitted.status_code == 200, submitted.text
    assert await _balance_qty(session_factory, seed["site_id"], seed["subject_id"]) == Decimal("10.000")

    barrier = _ArrivalBarrier(parties=2)
    original = BalancesRepo.get_for_update

    async def balance_hook(self, site_id, inventory_subject_id):
        await barrier.wait()
        return await original(self, site_id, inventory_subject_id)

    monkeypatch.setattr(BalancesRepo, "get_for_update", balance_hook)

    async def cancel_task():
        return await _cancel(client, seed["root_token"], op_id)

    async def scenario():
        t1 = asyncio.create_task(cancel_task())
        await asyncio.wait_for(barrier.first.wait(), TIMEOUT)
        t2 = asyncio.create_task(cancel_task())
        await asyncio.wait_for(barrier.all.wait(), TIMEOUT)
        barrier.release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r1, r2 = await _run(scenario())
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    ok = r1 if r1.status_code == 200 else r2
    conflict = r1 if r1.status_code == 409 else r2

    assert ok.json()["status"] == "cancelled"
    data = conflict.json()
    assert data["status"] == 409
    assert data["code"] == "operation_cancel_rejected"
    errors = data["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "insufficient_stock"
    assert errors[0]["scope"] == "line_group"
    assert errors[0]["required_qty"] == "10.000"
    assert errors[0]["available_qty"] == "0.000"

    # The rollback applied exactly once: balance back to zero, never negative,
    # and only the winner wrote an audit event.
    assert await _operation_status(session_factory, op_id) == "cancelled"
    assert await _balance_qty(session_factory, seed["site_id"], seed["subject_id"]) == Decimal("0.000")
    assert await _event_count(session_factory, op_id, "operation.cancel") == 1
