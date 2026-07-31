"""Concurrency tests for operation submit (TZ §13).

Each test proves the race with a real two-party barrier: a hook installed on
the critical row-lock call (`BalancesRepo.get_for_update` or
`OperationsRepo.get_operation_by_id_for_update`) holds both transactions at
the same point until both have arrived, then releases them together. Every
scenario is wrapped in `asyncio.wait_for` so a deadlock surfaces as a
`TimeoutError` instead of a hanging test.

Covered scenarios (TZ §13.2):

1. two submits of one operation -> one wins, the other gets
   `operation_in_wrong_state` (state-before-version, never `stale_version`);
2. a PATCH bumping the version races a submit with an old `expected_version`
   -> `stale_version`;
3. two MOVE operations from one site -> first consumes the balance, second
   gets `insufficient_stock`;
4. reversed line order over the same two balance groups -> global key
   sorting prevents the deadlock, both pass;
5. different sites share no balance key -> neither blocks the other;
6. a failed concurrent submit leaves no partial audit records.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.audit_event import AuditEvent
from app.models.audit_item_effect import AuditItemEffect
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

TIMEOUT = 10


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    """Per-request sessions so two concurrent requests use two transactions."""
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


class _ArrivalBarrier:
    """Two-party arrival barrier used to prove the race.

    The first caller sets ``first``; when ``parties`` callers have arrived,
    ``all`` is set. Every caller then waits on ``release``. A caller that
    reaches the barrier twice (e.g. the second lock of a winning submit)
    passes straight through once ``release`` is already set.
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


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    site_names: list[str],
    item_balances: dict[tuple[int, int], str],
) -> dict:
    """Seed sites, a root user, catalog items and per-site balances.

    ``item_balances`` maps ``(site_index, item_index) -> qty``. Items are
    created once for the maximum used index and shared across sites.
    """
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site_ids: list[int] = []
        for idx, name in enumerate(site_names):
            site = Site(code=f"SITE-{suffix}-{idx}", name=f"{name} {suffix}", is_active=True)
            session.add(site)
            await session.flush()
            site_ids.append(site.id)

        root = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root Test",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site_ids[0],
        )
        session.add(root)
        await session.flush()

        unit = Unit(
            code=f"PC-{suffix}",
            name=f"Piece {suffix}",
            symbol=f"pc{suffix[:3]}",
            is_active=True,
        )
        category = Category(
            code=f"CAT-{suffix}",
            name=f"Category {suffix}",
            normalized_name=f"category {suffix}",
            is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        item_count = max((k[1] for k in item_balances), default=-1) + 1
        items: list[dict] = []
        for idx in range(item_count):
            item = Item(
                sku=f"SKU-{suffix}-{idx}",
                name=f"Item {idx} {suffix}",
                normalized_name=f"item {idx} {suffix}",
                category_id=category.id,
                unit_id=unit.id,
                is_active=True,
            )
            session.add(item)
            await session.flush()
            subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
            session.add(subject)
            await session.flush()
            items.append({"item_id": item.id, "subject_id": subject.id})

        subjects = [it["subject_id"] for it in items]
        for (site_idx, item_idx), qty in item_balances.items():
            balance = Balance(
                site_id=site_ids[site_idx],
                inventory_subject_id=subjects[item_idx],
                item_id=items[item_idx]["item_id"],
                qty=Decimal(qty),
            )
            session.add(balance)

        await session.commit()

        return {
            "site_ids": site_ids,
            "root_token": str(root.user_token),
            "items": items,
            "subjects": subjects,
        }


def _line(item_id: int, qty: str | int, line_number: int) -> dict:
    return {"line_number": line_number, "item_id": item_id, "qty": qty}


async def _create_operation(
    client: AsyncClient,
    seed: dict,
    *,
    op_type: str,
    site_idx: int,
    lines: list[dict],
    source_site_idx: int | None = None,
    destination_site_idx: int | None = None,
) -> str:
    payload: dict = {"operation_type": op_type, "site_id": seed["site_ids"][site_idx], "lines": lines}
    if source_site_idx is not None:
        payload["source_site_id"] = seed["site_ids"][source_site_idx]
    if destination_site_idx is not None:
        payload["destination_site_id"] = seed["site_ids"][destination_site_idx]
    resp = await client.post(
        "/api/v1/operations",
        json=payload,
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, f"create failed: {resp.text}"
    return resp.json()["id"]


async def _submit(client: AsyncClient, token: str, op_id: str, *, expected_version: int | None = None):
    body: dict = {"submit": True}
    if expected_version is not None:
        body["expected_version"] = expected_version
    return await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json=body,
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


async def _operation_version(session_factory: async_sessionmaker[AsyncSession], op_id: str) -> int:
    async with session_factory() as session:
        row = (
            await session.execute(select(Operation).where(Operation.id == op_id))
        ).scalar_one_or_none()
        return int(row.version) if row is not None else -1


async def _submit_event_count(session_factory: async_sessionmaker[AsyncSession], op_id: str) -> int:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "operation.submit",
                    AuditEvent.entity_id == op_id,
                )
            )
        ).scalars().all()
        return len(rows)


async def _effects_for_operation(session_factory: async_sessionmaker[AsyncSession], op_id: str) -> list[AuditItemEffect]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditItemEffect).where(AuditItemEffect.operation_id == op_id)
            )
        ).scalars().all()
        return list(rows)


async def _run_pair(scenario_coro):
    """Run the concurrency orchestration under a hard timeout."""
    return await asyncio.wait_for(scenario_coro, timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_concurrent_submit_one_wins_one_gets_in_wrong_state(client, session_factory, monkeypatch):
    """TZ §13.2 scenario 1: state-before-version beats stale_version."""
    seed = await _seed(session_factory, site_names=["s1"], item_balances={(0, 0): "200.000"})
    op_id = await _create_operation(
        client, seed, op_type="EXPENSE", site_idx=0,
        lines=[_line(seed["items"][0]["item_id"], 10, 1)],
    )

    barrier = _ArrivalBarrier(parties=2)
    original = OperationsRepo.get_operation_by_id_for_update

    async def locked_hook(self, operation_id):
        await barrier.wait()
        return await original(self, operation_id)

    monkeypatch.setattr(OperationsRepo, "get_operation_by_id_for_update", locked_hook)

    async def submit_task():
        return await _submit(client, seed["root_token"], op_id, expected_version=1)

    async def scenario():
        t1 = asyncio.create_task(submit_task())
        await asyncio.wait_for(barrier.first.wait(), TIMEOUT)
        t2 = asyncio.create_task(submit_task())
        await asyncio.wait_for(barrier.all.wait(), TIMEOUT)
        barrier.release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r1, r2 = await _run_pair(scenario())
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    ok = r1 if r1.status_code == 200 else r2
    conflict = r1 if r1.status_code == 409 else r2

    data = conflict.json()
    assert data["status"] == 409
    assert data["code"] == "operation_submit_rejected"
    errors = data["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "operation_in_wrong_state"
    assert errors[0]["scope"] == "operation"
    assert errors[0]["current_state"] == "submitted"

    assert ok.json()["status"] == "submitted"
    assert await _operation_status(session_factory, op_id) == "submitted"

    # The second transaction rolled back: the balance reflects only the winner.
    assert await _balance_qty(session_factory, seed["site_ids"][0], seed["subjects"][0]) == Decimal("190.000")
    assert await _submit_event_count(session_factory, op_id) == 1
    assert len(await _effects_for_operation(session_factory, op_id)) == 1


@pytest.mark.asyncio
async def test_concurrent_submit_one_wins_one_gets_stale_version_when_version_changes(client, session_factory, monkeypatch):
    """TZ §13.2 scenario 2: a version bump racing a submit -> stale_version."""
    seed = await _seed(session_factory, site_names=["s1"], item_balances={(0, 0): "200.000"})
    op_id = await _create_operation(
        client, seed, op_type="EXPENSE", site_idx=0,
        lines=[_line(seed["items"][0]["item_id"], 10, 1)],
    )

    original = OperationsRepo.get_operation_by_id_for_update
    patch_locked = asyncio.Event()
    submit_at_lock = asyncio.Event()
    release_patch = asyncio.Event()
    calls = 0

    async def ordered_hook(self, operation_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            # First caller is the PATCH: take the row lock, then hold it until
            # the submit is queued behind the same lock.
            result = await original(self, operation_id)
            patch_locked.set()
            await asyncio.wait_for(release_patch.wait(), TIMEOUT)
            return result
        # Second caller is the submit: signal that it reached the lock step,
        # then block on the real lock until the PATCH commits.
        submit_at_lock.set()
        return await original(self, operation_id)

    monkeypatch.setattr(OperationsRepo, "get_operation_by_id_for_update", ordered_hook)

    async def patch_task():
        return await client.patch(
            f"/api/v1/operations/{op_id}",
            json={"notes": "version bump"},
            headers={"X-User-Token": seed["root_token"]},
        )

    async def submit_task():
        return await _submit(client, seed["root_token"], op_id, expected_version=1)

    async def scenario():
        t1 = asyncio.create_task(patch_task())
        await asyncio.wait_for(patch_locked.wait(), TIMEOUT)
        t2 = asyncio.create_task(submit_task())
        await asyncio.wait_for(submit_at_lock.wait(), TIMEOUT)
        release_patch.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r_patch, r_submit = await _run_pair(scenario())
    assert r_patch.status_code == 200, r_patch.text
    assert r_submit.status_code == 409, r_submit.text

    data = r_submit.json()
    assert data["status"] == 409
    assert data["code"] == "operation_submit_rejected"
    errors = data["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "stale_version"
    assert errors[0]["scope"] == "operation"
    assert errors[0]["expected_version"] == 1
    assert errors[0]["actual_version"] == 2

    # No state conflict: the operation stays DRAFT, only the version moved.
    assert await _operation_status(session_factory, op_id) == "draft"
    assert await _operation_version(session_factory, op_id) == 2
    assert await _balance_qty(session_factory, seed["site_ids"][0], seed["subjects"][0]) == Decimal("200.000")
    assert await _submit_event_count(session_factory, op_id) == 0


@pytest.mark.asyncio
async def test_concurrent_submit_one_consumes_balance_other_gets_insufficient_stock(client, session_factory, monkeypatch):
    """TZ §13.2 scenario 3: the loser reads the depleted balance inside the lock."""
    seed = await _seed(
        session_factory,
        site_names=["src", "dst"],
        item_balances={(0, 0): "1.000"},
    )
    src = seed["site_ids"][0]
    item_id = seed["items"][0]["item_id"]

    op_a = await _create_operation(
        client, seed, op_type="MOVE", site_idx=0,
        source_site_idx=0, destination_site_idx=1,
        lines=[_line(item_id, 1, 1)],
    )
    op_b = await _create_operation(
        client, seed, op_type="MOVE", site_idx=0,
        source_site_idx=0, destination_site_idx=1,
        lines=[_line(item_id, 1, 1)],
    )

    barrier = _ArrivalBarrier(parties=2)
    original = BalancesRepo.get_for_update

    async def balance_hook(self, site_id, inventory_subject_id):
        await barrier.wait()
        return await original(self, site_id, inventory_subject_id)

    monkeypatch.setattr(BalancesRepo, "get_for_update", balance_hook)

    async def submit_task(op_id):
        return await _submit(client, seed["root_token"], op_id)

    async def scenario():
        t1 = asyncio.create_task(submit_task(op_a))
        await asyncio.wait_for(barrier.first.wait(), TIMEOUT)
        t2 = asyncio.create_task(submit_task(op_b))
        await asyncio.wait_for(barrier.all.wait(), TIMEOUT)
        barrier.release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r1, r2 = await _run_pair(scenario())
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    ok = r1 if r1.status_code == 200 else r2
    conflict = r1 if r1.status_code == 409 else r2

    data = conflict.json()
    assert data["status"] == 409
    errors = data["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "insufficient_stock"
    assert errors[0]["scope"] == "line_group"
    assert errors[0]["required_qty"] == "1.000"
    assert errors[0]["available_qty"] == "0.000"

    final_balance = await _balance_qty(session_factory, src, seed["subjects"][0])
    assert final_balance == Decimal("0.000")
    assert final_balance >= 0

    ok_op_id = ok.json()["id"]
    failed_op_id = op_a if ok_op_id == op_b else op_b
    statuses = sorted(
        [await _operation_status(session_factory, op_a), await _operation_status(session_factory, op_b)]
    )
    assert statuses == ["draft", "submitted"]

    # MOVE defaults to acceptance_required=True (OperationsService.create_operation),
    # so only the move_out side is captured as an audit_item_effect; the failed one
    # left nothing at all.
    ok_effects = await _effects_for_operation(session_factory, ok_op_id)
    assert len(ok_effects) == 1
    assert len(await _effects_for_operation(session_factory, failed_op_id)) == 0
    total_events = await _submit_event_count(session_factory, op_a) + await _submit_event_count(session_factory, op_b)
    assert total_events == 1


@pytest.mark.asyncio
async def test_concurrent_submit_no_deadlock_with_reversed_line_order(client, session_factory, monkeypatch):
    """TZ §13.2 scenario 4: global key sorting prevents the classic deadlock."""
    seed = await _seed(
        session_factory,
        site_names=["src", "dst"],
        item_balances={(0, 0): "2.000", (0, 1): "2.000"},
    )
    item_x = seed["items"][0]["item_id"]
    item_y = seed["items"][1]["item_id"]

    op_a = await _create_operation(
        client, seed, op_type="MOVE", site_idx=0,
        source_site_idx=0, destination_site_idx=1,
        lines=[_line(item_x, 1, 1), _line(item_y, 1, 2)],
    )
    op_b = await _create_operation(
        client, seed, op_type="MOVE", site_idx=0,
        source_site_idx=0, destination_site_idx=1,
        lines=[_line(item_y, 1, 1), _line(item_x, 1, 2)],
    )

    barrier = _ArrivalBarrier(parties=2)
    original = BalancesRepo.get_for_update

    async def balance_hook(self, site_id, inventory_subject_id):
        await barrier.wait()
        return await original(self, site_id, inventory_subject_id)

    monkeypatch.setattr(BalancesRepo, "get_for_update", balance_hook)

    async def submit_task(op_id):
        return await _submit(client, seed["root_token"], op_id)

    async def scenario():
        t1 = asyncio.create_task(submit_task(op_a))
        await asyncio.wait_for(barrier.first.wait(), TIMEOUT)
        t2 = asyncio.create_task(submit_task(op_b))
        await asyncio.wait_for(barrier.all.wait(), TIMEOUT)
        barrier.release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r1, r2 = await _run_pair(scenario())
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    src = seed["site_ids"][0]
    assert await _balance_qty(session_factory, src, seed["subjects"][0]) == Decimal("0.000")
    assert await _balance_qty(session_factory, src, seed["subjects"][1]) == Decimal("0.000")
    assert await _operation_status(session_factory, op_a) == "submitted"
    assert await _operation_status(session_factory, op_b) == "submitted"
    assert await _submit_event_count(session_factory, op_a) == 1
    assert await _submit_event_count(session_factory, op_b) == 1


@pytest.mark.asyncio
async def test_concurrent_submit_different_operations_different_sites_dont_block(client, session_factory, monkeypatch):
    """TZ §13.2 scenario 5: disjoint balance keys never contend."""
    seed = await _seed(
        session_factory,
        site_names=["sA", "sB"],
        item_balances={(0, 0): "50.000", (1, 0): "50.000"},
    )
    item_id = seed["items"][0]["item_id"]
    op_a = await _create_operation(
        client, seed, op_type="EXPENSE", site_idx=0,
        lines=[_line(item_id, 5, 1)],
    )
    op_b = await _create_operation(
        client, seed, op_type="EXPENSE", site_idx=1,
        lines=[_line(item_id, 7, 1)],
    )

    barrier = _ArrivalBarrier(parties=2)
    original = BalancesRepo.get_for_update

    async def balance_hook(self, site_id, inventory_subject_id):
        await barrier.wait()
        return await original(self, site_id, inventory_subject_id)

    monkeypatch.setattr(BalancesRepo, "get_for_update", balance_hook)

    async def submit_task(op_id):
        return await _submit(client, seed["root_token"], op_id)

    async def scenario():
        t1 = asyncio.create_task(submit_task(op_a))
        await asyncio.wait_for(barrier.first.wait(), TIMEOUT)
        t2 = asyncio.create_task(submit_task(op_b))
        await asyncio.wait_for(barrier.all.wait(), TIMEOUT)
        barrier.release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r1, r2 = await _run_pair(scenario())
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    sA, sB = seed["site_ids"]
    subject = seed["subjects"][0]
    assert await _balance_qty(session_factory, sA, subject) == Decimal("45.000")
    assert await _balance_qty(session_factory, sB, subject) == Decimal("43.000")
    assert await _operation_status(session_factory, op_a) == "submitted"
    assert await _operation_status(session_factory, op_b) == "submitted"


@pytest.mark.asyncio
async def test_no_partial_audit_on_concurrent_failure(client, session_factory, monkeypatch):
    """TZ §13.2 scenario 6: the losing submit leaves no audit trace at all."""
    seed = await _seed(session_factory, site_names=["s1"], item_balances={(0, 0): "200.000"})
    op_id = await _create_operation(
        client, seed, op_type="EXPENSE", site_idx=0,
        lines=[_line(seed["items"][0]["item_id"], 10, 1)],
    )

    barrier = _ArrivalBarrier(parties=2)
    original = OperationsRepo.get_operation_by_id_for_update

    async def locked_hook(self, operation_id):
        await barrier.wait()
        return await original(self, operation_id)

    monkeypatch.setattr(OperationsRepo, "get_operation_by_id_for_update", locked_hook)

    async def submit_task():
        return await _submit(client, seed["root_token"], op_id, expected_version=1)

    async def scenario():
        t1 = asyncio.create_task(submit_task())
        await asyncio.wait_for(barrier.first.wait(), TIMEOUT)
        t2 = asyncio.create_task(submit_task())
        await asyncio.wait_for(barrier.all.wait(), TIMEOUT)
        barrier.release.set()
        r1, r2 = await asyncio.gather(t1, t2)
        return r1, r2

    r1, r2 = await _run_pair(scenario())
    assert sorted([r1.status_code, r2.status_code]) == [200, 409]
    ok = r1 if r1.status_code == 200 else r2
    conflict = r1 if r1.status_code == 409 else r2
    assert conflict.json()["errors"][0]["code"] == "operation_in_wrong_state"

    # Exactly one operation.submit event from the winner; no partial rows.
    assert await _submit_event_count(session_factory, op_id) == 1

    effects = await _effects_for_operation(session_factory, op_id)
    assert len(effects) == 1
    assert effects[0].quantity_delta == Decimal("-10.000")
    assert ok.json()["status"] == "submitted"
