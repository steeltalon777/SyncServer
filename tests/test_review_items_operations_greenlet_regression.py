"""D1 regression: GET /api/v1/review-items/{id}/operations must serialize lines.

Before the fix ``OperationsRepo.get_operations_by_item_id`` only eager-loaded
``Operation.lines``. During pydantic validation of ``OperationListResponse``
the ``OperationLineResponse`` projection fields triggered async lazy-load of
``inventory_subject`` / ``item.temporary_item`` / ``temporary_item.resolved_item``
outside the greenlet context, so the endpoint returned HTTP 500 MissingGreenlet
for every review item. See
``docs/reviews/architecture-review-review-item-backend-hardening.md`` section D1.

These tests exercise the real HTTP path (response_model serialization), not
the repository directly. Two real line shapes are covered:

* modern inline materialization: permanent review Item + ``catalog_item`` subject;
* legacy ``temporary_item`` subject backed by a real ``TemporaryItem`` row,
  including resolved projections (``merged_to_item`` / ``resolved_item_id``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.temporary_item import TemporaryItem
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


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"D1-{suffix}", name=f"D1 Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        chief = User(
            username=f"d1-chief-{suffix}",
            email=f"d1-chief-{suffix}@example.com",
            full_name="D1 Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        storekeeper = User(
            username=f"d1-sk-{suffix}",
            email=f"d1-sk-{suffix}@example.com",
            full_name="D1 Storekeeper",
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

        unit = Unit(
            code=f"D1U-{suffix}",
            name=f"D1 Unit {suffix}",
            symbol=f"d{suffix[:2]}",
            is_active=True,
        )
        category = Category(
            code=f"D1C-{suffix}",
            name=f"D1 Category {suffix}",
            normalized_name=f"d1 category {suffix}",
            is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        target_item = Item(
            sku=f"D1T-{suffix}",
            name=f"D1 Target {suffix}",
            normalized_name=f"d1 target {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(target_item)
        await session.commit()

        return {
            "site_id": site.id,
            "chief_user_id": chief.id,
            "chief_token": str(chief.user_token),
            "storekeeper_token": str(storekeeper.user_token),
            "unit_id": unit.id,
            "unit_name": unit.name,
            "unit_symbol": unit.symbol,
            "category_id": category.id,
            "category_name": category.name,
            "target_item_id": target_item.id,
            "target_name": target_item.name,
        }


async def _receive_review_item(
    client: AsyncClient,
    seed: dict[str, object],
    *,
    qty: int,
    client_key: str,
) -> tuple[dict, int, str]:
    """RECEIVE an inline temporary item, submit it, return (operation, review_item_id, temp_name)."""
    temp_name = f"D1 Temp {client_key}"
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
                        "name": temp_name,
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
    return op, int(review_item_id), temp_name


async def _seed_legacy_temporary_line(
    session_factory: async_sessionmaker[AsyncSession],
    seed: dict[str, object],
) -> dict[str, int]:
    """Seed a legacy temporary-item backed operation line (real TemporaryItem row).

    Legacy data shape: backing Item (inactive, source_system='temporary_item'),
    TemporaryItem record and an InventorySubject with subject_type='temporary_item'
    referenced by a real operation line.
    """
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        backing_item = Item(
            sku=f"D1LEG-{suffix}",
            name=f"Legacy Temp Item {suffix}",
            normalized_name=f"legacy temp item {suffix}",
            unit_id=seed["unit_id"],
            category_id=seed["category_id"],
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
            unit_id=seed["unit_id"],
            category_id=seed["category_id"],
            status="active",
            created_by_user_id=seed["chief_user_id"],
        )
        session.add(temporary_item)
        await session.flush()

        subject = InventorySubject(
            subject_type="temporary_item",
            temporary_item_id=temporary_item.id,
            item_id=backing_item.id,
        )
        session.add(subject)
        await session.flush()

        operation = Operation(
            site_id=seed["site_id"],
            operation_type="RECEIVE",
            status="submitted",
            created_by_user_id=seed["chief_user_id"],
            effective_at=datetime.now(UTC),
        )
        session.add(operation)
        await session.flush()

        line = OperationLine(
            operation_id=operation.id,
            line_number=1,
            qty=Decimal("7"),
            item_id=backing_item.id,
            inventory_subject_id=subject.id,
            item_name_snapshot=backing_item.name,
            unit_name_snapshot=seed["unit_name"],
        )
        session.add(line)
        await session.commit()

        return {
            "backing_item_id": backing_item.id,
            "backing_item_name": backing_item.name,
            "temporary_item_id": temporary_item.id,
            "subject_id": subject.id,
            "operation_id": operation.id,
            "line_id": line.id,
        }


@pytest.mark.asyncio
async def test_list_review_item_operations_serializes_modern_line_http(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /review-items/{id}/operations returns 200 for a modern review item.

    Before the fix this HTTP path returned 500 MissingGreenlet while
    serializing ``OperationLineResponse`` projections (lazy ``inventory_subject``).
    Modern inline materialization produces a permanent review Item with a
    ``catalog_item`` subject, so temporary/resolved projections are null.
    """
    seed = await _seed(session_factory)
    op, review_item_id, temp_name = await _receive_review_item(
        client, seed, qty=5, client_key="d1-modern"
    )

    resp = await client.get(
        f"/api/v1/review-items/{review_item_id}/operations",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_count"] >= 1
    assert body["page"] == 1
    assert body["page_size"] == 50

    receive_op = next(item for item in body["items"] if item["id"] == op["id"])
    assert len(receive_op["lines"]) == 1
    line = receive_op["lines"][0]

    assert line["subject_type"] == "catalog_item"
    assert line["temporary_item_id"] is None
    assert line["temporary_item_status"] is None
    assert line["resolved_item_id"] is None
    assert line["resolved_item_name"] is None
    assert line["item_id"] == review_item_id
    assert line["inventory_subject_id"] is not None
    assert line["line_number"] == 1
    assert float(line["qty"]) == 5.0
    assert float(line["accepted_qty"]) == 0.0
    assert float(line["lost_qty"]) == 0.0
    assert line["item_name_snapshot"] == temp_name
    assert line["unit_name_snapshot"] == seed["unit_name"]
    assert line["unit_symbol_snapshot"] == seed["unit_symbol"]
    assert line["category_name_snapshot"] == seed["category_name"]
    assert line["is_draft_temporary"] is False


@pytest.mark.asyncio
async def test_list_review_item_operations_serializes_legacy_temporary_line_http(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /review-items/{id}/operations serializes legacy temporary/resolved projections.

    Uses a real legacy row set (TemporaryItem + ``temporary_item`` subject) and
    verifies both unresolved (``active``, no resolution) and resolved
    (``merged_to_item`` + ``resolved_item_id/name``) line projections.
    """
    seed = await _seed(session_factory)
    legacy = await _seed_legacy_temporary_line(session_factory, seed)
    url = f"/api/v1/review-items/{legacy['backing_item_id']}/operations"
    headers = {"X-User-Token": seed["chief_token"]}

    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    receive_op = next(item for item in body["items"] if item["id"] == str(legacy["operation_id"]))
    line = receive_op["lines"][0]

    assert line["subject_type"] == "temporary_item"
    assert line["temporary_item_id"] == legacy["temporary_item_id"]
    assert line["temporary_item_status"] == "active"
    assert line["resolved_item_id"] is None
    assert line["resolved_item_name"] is None
    assert line["item_id"] == legacy["backing_item_id"]
    assert line["inventory_subject_id"] == legacy["subject_id"]
    assert float(line["qty"]) == 7.0
    assert line["item_name_snapshot"] == legacy["backing_item_name"]

    async with session_factory() as session:
        temporary_item = (
            await session.execute(
                select(TemporaryItem).where(TemporaryItem.id == legacy["temporary_item_id"])
            )
        ).scalar_one()
        temporary_item.status = "merged_to_item"
        temporary_item.resolved_item_id = seed["target_item_id"]
        temporary_item.resolution_type = "merge"
        temporary_item.resolved_at = datetime.now(UTC)
        await session.commit()

    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    receive_op = next(item for item in body["items"] if item["id"] == str(legacy["operation_id"]))
    line = receive_op["lines"][0]

    assert line["subject_type"] == "temporary_item"
    assert line["temporary_item_id"] == legacy["temporary_item_id"]
    assert line["temporary_item_status"] == "merged_to_item"
    assert line["resolved_item_id"] == seed["target_item_id"]
    assert line["resolved_item_name"] == seed["target_name"]
    assert line["item_id"] == legacy["backing_item_id"]
    assert line["inventory_subject_id"] == legacy["subject_id"]
