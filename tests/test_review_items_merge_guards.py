"""D3 merge integrity guard regression tests.

Covers the backend guard that blocks ``ReviewItemsService.merge_review_item``
while the source inventory subject still has active pending/lost/issued
registers. See ``docs/reviews/architecture-review-review-item-backend-hardening.md``
section D3 and ``docs/reviews/D3-merge-guard-checkpoint.md``.

Before the fix the merge flow silently archived the source subject and
dropped later-accepted quantities into an archived subject (data loss).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.asset_register import (
    IssuedAssetBalance,
    LostAssetBalance,
    PendingAcceptanceBalance,
)
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


def _norm(value: str) -> str:
    import re

    non_word = re.compile(r"[^\w\s]+", flags=re.UNICODE)
    spaces = re.compile(r"\s+", flags=re.UNICODE)
    return spaces.sub(" ", non_word.sub(" ", (value or "").strip().lower().replace("ё", "е"))).strip()


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"MG-{suffix}", name=f"Merge Guard {suffix}", is_active=True)
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
            username=f"sk-{suffix}",
            email=f"sk-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([chief, storekeeper])
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
            ]
        )

        unit = Unit(code=f"U-{suffix}", name=f"Unit {suffix}", symbol=f"u{suffix[:2]}", is_active=True)
        category = Category(
            code=f"C-{suffix}",
            name=f"Category {suffix}",
            normalized_name=f"category {suffix}",
            is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        target_item = Item(
            sku=f"TGT-{suffix}",
            name=f"Target Item {suffix}",
            normalized_name=f"target item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(target_item)
        await session.flush()

        issue_object_category = IssueObjectCategory(
            name=f"People {suffix}",
            normalized_key=_norm(f"People {suffix}"),
            sort_order=0,
            is_active=True,
        )
        session.add(issue_object_category)
        await session.flush()

        issue_object = IssueObject(
            display_name=f"Employee-{suffix}",
            normalized_key=_norm(f"Employee-{suffix}"),
            object_type="person",
            is_active=True,
            category_id=issue_object_category.id,
        )
        session.add(issue_object)
        await session.commit()

        return {
            "site_id": site.id,
            "chief_user_id": chief.id,
            "chief_token": str(chief.user_token),
            "storekeeper_token": str(storekeeper.user_token),
            "unit_id": unit.id,
            "category_id": category.id,
            "target_item_id": target_item.id,
            "issue_object_id": issue_object.id,
        }


async def _receive_review_item(
    client: AsyncClient,
    seed: dict[str, object],
    *,
    qty: int,
    client_key: str,
) -> tuple[dict, int]:
    """RECEIVE an inline temporary item, submit it, return (operation, review_item_id)."""
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": client_key,
            "lines": [
                {
                    "line_number": 1,
                    "qty": qty,
                    "temporary_item": {
                        "client_key": client_key,
                        "name": f"Merge Guard Temp {client_key}",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    op = create_resp.json()

    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200, submit_resp.text
    review_item_id = submit_resp.json()["lines"][0]["item_id"]
    assert review_item_id is not None
    return op, int(review_item_id)


async def _accept(
    client: AsyncClient,
    seed: dict[str, object],
    op: dict,
    *,
    accepted: int,
    lost: int = 0,
) -> None:
    resp = await client.post(
        f"/api/v1/operations/{op['id']}/accept-lines",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {"line_id": op["lines"][0]["id"], "accepted_qty": accepted, "lost_qty": lost},
            ]
        },
    )
    assert resp.status_code == 200, resp.text


async def _issue(
    client: AsyncClient,
    seed: dict[str, object],
    review_item_id: int,
    *,
    qty: int,
) -> None:
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "ISSUE",
            "site_id": seed["site_id"],
            "issue_object_id": seed["issue_object_id"],
            "lines": [{"line_number": 1, "item_id": review_item_id, "qty": qty}],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    op = create_resp.json()
    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200, submit_resp.text


async def _merge(client: AsyncClient, seed: dict[str, object], review_item_id: int):
    return await client.post(
        f"/api/v1/review-items/{review_item_id}/merge",
        headers={"X-User-Token": seed["chief_token"]},
        json={"target_item_id": seed["target_item_id"]},
    )


async def _register_qtys(session: AsyncSession, model, subject_id: int | None) -> list[str]:
    if subject_id is None:
        return []
    stmt = select(model.qty).where(model.inventory_subject_id == subject_id).order_by(model.qty)
    return [str(qty) for qty in (await session.execute(stmt)).scalars().all()]


async def _snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    source_item_id: int,
    target_item_id: int,
) -> dict[str, object]:
    """Full domain snapshot used to prove a blocked merge changed nothing."""
    async with session_factory() as session:
        source_item = (
            await session.execute(select(Item).where(Item.id == source_item_id))
        ).scalar_one()
        target_item = (
            await session.execute(select(Item).where(Item.id == target_item_id))
        ).scalar_one()
        source_subject = (
            await session.execute(
                select(InventorySubject).where(InventorySubject.item_id == source_item_id)
            )
        ).scalar_one_or_none()
        target_subject = (
            await session.execute(
                select(InventorySubject).where(InventorySubject.item_id == target_item_id)
            )
        ).scalar_one_or_none()

        source_subject_id = int(source_subject.id) if source_subject is not None else None
        target_subject_id = int(target_subject.id) if target_subject is not None else None

        async def _balances(subject_id: int | None) -> list[list[object]]:
            if subject_id is None:
                return []
            stmt = select(Balance.site_id, Balance.qty).where(
                Balance.inventory_subject_id == subject_id
            )
            rows = (await session.execute(stmt)).all()
            return sorted([[int(site_id), str(qty)] for site_id, qty in rows])

        review_merge_ops = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Operation)
                    .where(Operation.system_reason == "review_merge")
                )
            ).scalar_one()
            or 0
        )

        return {
            "source_item": {
                "is_active": source_item.is_active,
                "requires_review": source_item.requires_review,
                "review_status": source_item.review_status,
                "deleted_at": source_item.deleted_at,
            },
            "target_item_is_active": target_item.is_active,
            "source_subject": {
                "exists": source_subject is not None,
                "archived_at": source_subject.archived_at if source_subject is not None else None,
            },
            "target_subject": {
                "exists": target_subject is not None,
                "archived_at": target_subject.archived_at if target_subject is not None else None,
            },
            "source_balances": await _balances(source_subject_id),
            "target_balances": await _balances(target_subject_id),
            "pending": await _register_qtys(session, PendingAcceptanceBalance, source_subject_id),
            "lost": await _register_qtys(session, LostAssetBalance, source_subject_id),
            "issued": await _register_qtys(session, IssuedAssetBalance, source_subject_id),
            "review_merge_ops": review_merge_ops,
        }


@pytest.mark.asyncio
async def test_merge_blocked_by_pending_acceptance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3: pending acceptance blocks merge with 409 and zero state changes."""
    seed = await _seed(session_factory)
    _, review_item_id = await _receive_review_item(client, seed, qty=5, client_key="mg-pending-1")

    before = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )

    resp = await _merge(client, seed, review_item_id)
    assert resp.status_code == 409, resp.text
    assert "active pending/lost/issued registers" in resp.json()["detail"]

    after = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert after == before
    assert after["target_subject"]["exists"] is False
    assert after["review_merge_ops"] == 0
    assert after["pending"] == ["5.000"]


@pytest.mark.asyncio
async def test_merge_blocked_by_lost_register(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3: an unresolved lost register blocks merge with 409 and zero state changes."""
    seed = await _seed(session_factory)
    op, review_item_id = await _receive_review_item(client, seed, qty=5, client_key="mg-lost-1")
    await _accept(client, seed, op, accepted=3, lost=2)

    before = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert before["lost"] == ["2.000"]
    assert before["pending"] == []

    resp = await _merge(client, seed, review_item_id)
    assert resp.status_code == 409, resp.text
    assert "active pending/lost/issued registers" in resp.json()["detail"]

    after = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert after == before
    assert after["source_item"]["review_status"] == "needs_review"


@pytest.mark.asyncio
async def test_merge_blocked_by_issued_register(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3: an issued balance > 0 blocks merge with 409 and zero state changes."""
    seed = await _seed(session_factory)
    op, review_item_id = await _receive_review_item(client, seed, qty=5, client_key="mg-issued-1")
    await _accept(client, seed, op, accepted=5, lost=0)
    await _issue(client, seed, review_item_id, qty=5)

    before = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert before["issued"] == ["5.000"]
    assert before["pending"] == []

    resp = await _merge(client, seed, review_item_id)
    assert resp.status_code == 409, resp.text
    assert "active pending/lost/issued registers" in resp.json()["detail"]

    after = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert after == before


@pytest.mark.asyncio
async def test_merge_integration_pending_409_then_accept_then_merge_200(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3 integration scenario: RECEIVE -> submit -> pending -> merge 409 -> accept -> merge 200."""
    seed = await _seed(session_factory)
    op, review_item_id = await _receive_review_item(
        client, seed, qty=5, client_key="mg-integration-1"
    )

    blocked = await _merge(client, seed, review_item_id)
    assert blocked.status_code == 409, blocked.text
    assert "active pending/lost/issued registers" in blocked.json()["detail"]

    await _accept(client, seed, op, accepted=5, lost=0)

    merged = await _merge(client, seed, review_item_id)
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["review_status"] == "merged"
    assert body["is_active"] is False

    after = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )

    # Balance is on the canonical target; the source is drained.
    assert after["target_balances"] == [[seed["site_id"], "5.000"]]
    assert after["source_balances"] in ([], [[seed["site_id"], "0.000"]])
    # Pending register is gone and the source subject/item are resolved.
    assert after["pending"] == []
    assert after["source_subject"]["archived_at"] is not None
    assert after["source_item"]["review_status"] == "merged"
    assert after["source_item"]["requires_review"] is False
    assert after["source_item"]["is_active"] is False
    # Exactly one write-off + one receipt ADJUSTMENT were generated.
    assert after["review_merge_ops"] == 2

    # History is intact: the original operation still carries the source item.
    op_resp = await client.get(
        f"/api/v1/operations/{op['id']}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert op_resp.status_code == 200, op_resp.text
    line = op_resp.json()["lines"][0]
    assert line["item_id"] == review_item_id
    assert line["item_name_snapshot"] == "Merge Guard Temp mg-integration-1"


@pytest.mark.asyncio
async def test_merge_succeeds_without_registers(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3: normal no-register merge still succeeds and transfers balances."""
    seed = await _seed(session_factory)
    op, review_item_id = await _receive_review_item(client, seed, qty=5, client_key="mg-clean-1")
    await _accept(client, seed, op, accepted=5, lost=0)

    before = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert before["pending"] == []
    assert before["lost"] == []
    assert before["issued"] == []

    resp = await _merge(client, seed, review_item_id)
    assert resp.status_code == 200, resp.text

    after = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert after["target_balances"] == [[seed["site_id"], "5.000"]]
    assert after["source_balances"] in ([], [[seed["site_id"], "0.000"]])
    assert after["source_item"]["review_status"] == "merged"
    assert after["source_item"]["is_active"] is False
    assert after["review_merge_ops"] == 2


@pytest.mark.asyncio
async def test_repeated_merge_returns_existing_conflict(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3: repeating a merge hits the pre-existing resolved-status conflict."""
    seed = await _seed(session_factory)
    op, review_item_id = await _receive_review_item(client, seed, qty=5, client_key="mg-repeat-1")
    await _accept(client, seed, op, accepted=5, lost=0)

    first = await _merge(client, seed, review_item_id)
    assert first.status_code == 200, first.text

    before = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )

    second = await _merge(client, seed, review_item_id)
    assert second.status_code == 409, second.text
    # Pre-existing conflict path: after the first merge requires_review=False,
    # so the service short-circuits before the review_status check.
    assert second.json()["detail"] == "item does not require review"

    after = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert after == before


@pytest.mark.asyncio
async def test_merge_after_confirm_returns_existing_conflict(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3: merge after confirm keeps the pre-existing resolved-status conflict."""
    seed = await _seed(session_factory)
    op, review_item_id = await _receive_review_item(client, seed, qty=5, client_key="mg-confirmed-1")
    await _accept(client, seed, op, accepted=5, lost=0)

    confirm = await client.post(
        f"/api/v1/review-items/{review_item_id}/confirm",
        headers={"X-User-Token": seed["chief_token"]},
        json={},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["review_status"] == "confirmed"

    before = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )

    resp = await _merge(client, seed, review_item_id)
    assert resp.status_code == 409, resp.text
    # Pre-existing conflict path: confirm clears requires_review, so merge
    # short-circuits before the review_status check.
    assert resp.json()["detail"] == "item does not require review"

    after = await _snapshot(
        session_factory, source_item_id=review_item_id, target_item_id=seed["target_item_id"]
    )
    assert after == before


@pytest.mark.asyncio
async def test_confirm_not_blocked_by_pending_acceptance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """D3: confirm intentionally stays possible during pending acceptance (asymmetry)."""
    seed = await _seed(session_factory)
    _, review_item_id = await _receive_review_item(
        client, seed, qty=5, client_key="mg-confirm-pending-1"
    )

    resp = await client.post(
        f"/api/v1/review-items/{review_item_id}/confirm",
        headers={"X-User-Token": seed["chief_token"]},
        json={},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["review_status"] == "confirmed"
