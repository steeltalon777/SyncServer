from __future__ import annotations

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
from main import app


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


async def _seed_machine_fixture(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    role: str = "chief_storekeeper",
    with_manage_scope: bool = True,
) -> dict:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"MS-{suffix}", name=f"Machine Site {suffix}")
        session.add(site)
        await session.flush()

        user = User(
            username=f"machine-{role}-{suffix}",
            email=f"machine-{role}-{suffix}@example.com",
            full_name=f"Machine {role}",
            is_active=True,
            is_root=False,
            role=role,
            default_site_id=site.id,
        )
        session.add(user)
        await session.flush()

        if role in {"storekeeper", "observer"}:
            scope = UserAccessScope(
                user_id=user.id,
                site_id=site.id,
                can_view=True,
                can_operate=with_manage_scope,
                can_manage_catalog=with_manage_scope,
                is_active=True,
            )
            session.add(scope)

        unit = Unit(code=f"PCS{suffix}", name=f"Piece {suffix}", symbol=f"PCS{suffix}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(
            code=f"TOOLS-{suffix}",
            name=f"Tools {suffix}",
            normalized_name=f"tools {suffix}",
            is_active=True,
        )
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"HAMMER-{suffix}",
            name=f"Hammer {suffix}",
            normalized_name=f"hammer {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "token": str(user.user_token),
            "site_id": site.id,
            "unit_code": unit.code,
            "item_id": item.id,
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_machine_snapshot_and_read_items(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_machine_fixture(session_factory)
    headers = {"X-User-Token": seed["token"]}

    snapshot_response = await client.get("/api/v1/machine/snapshots/latest", headers=headers)
    assert snapshot_response.status_code == 200
    snapshot_body = snapshot_response.json()
    assert "snapshot_id" in snapshot_body
    assert snapshot_body["schema_version"] == "2026-04-07"

    read_response = await client.get(
        "/api/v1/machine/read/catalog/items",
        headers=headers,
        params={"snapshot_id": snapshot_body["snapshot_id"], "limit": 10},
    )
    assert read_response.status_code == 200
    read_body = read_response.json()
    assert read_body["snapshot_id"] == snapshot_body["snapshot_id"]
    assert read_body["schema_version"] == "2026-04-07"
    assert any(item["id"] == seed["item_id"] for item in read_body["items"])


@pytest.mark.asyncio(loop_scope="session")
async def test_machine_reports_create_and_fetch(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_machine_fixture(session_factory)
    headers = {"X-User-Token": seed["token"]}

    snapshot_response = await client.get("/api/v1/machine/snapshots/latest", headers=headers)
    snapshot_id = snapshot_response.json()["snapshot_id"]

    create_response = await client.post(
        "/api/v1/machine/reports",
        headers=headers,
        json={
            "report_type": "catalog_duplicate_review",
            "snapshot_id": snapshot_id,
            "summary": "Potential duplicate groups detected.",
            "findings": [
                {
                    "kind": "duplicate_candidate_group",
                    "ref_id": "dup_items_001",
                    "severity": "medium",
                }
            ],
            "references": ["dup_items_001"],
        },
    )
    assert create_response.status_code == 200
    report = create_response.json()
    assert report["snapshot_id"] == snapshot_id
    assert report["report_type"] == "catalog_duplicate_review"

    fetch_response = await client.get(f"/api/v1/machine/reports/{report['report_id']}", headers=headers)
    assert fetch_response.status_code == 200
    result_response = await client.get(f"/api/v1/machine/reports/{report['report_id']}/result", headers=headers)
    assert result_response.status_code == 200
    assert len(result_response.json()["items"]) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_machine_catalog_batch_preview_and_apply(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_machine_fixture(session_factory)
    headers = {"X-User-Token": seed["token"]}
    suffix = uuid4().hex[:6]

    preview_response = await client.post(
        "/api/v1/machine/batches/catalog/preview",
        headers=headers,
        json={
            "domain": "catalog",
            "payload_format": "catalog_package_v1",
            "mode": "atomic",
            "idempotency_key": str(uuid4()),
            "payload": {
                "meta": {"source": "test_suite"},
                "categories": [
                    {
                        "ref": f"cat-{suffix}",
                        "code": f"CAT-{suffix}",
                        "name": f"Category {suffix}",
                    }
                ],
                "items": [
                    {
                        "ref": f"item-{suffix}",
                        "sku": f"SKU-{suffix}",
                        "name": f"Item {suffix}",
                        "category_ref": f"cat-{suffix}",
                        "unit_code": seed["unit_code"],
                        "is_active": True,
                    }
                ],
            },
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["status"] == "preview_ready"
    assert preview["summary"]["create"] >= 2

    apply_response = await client.post(
        "/api/v1/machine/batches/catalog/apply",
        headers=headers,
        json={"batch_id": preview["batch_id"], "plan_id": preview["plan_id"]},
    )
    assert apply_response.status_code == 200
    applied = apply_response.json()
    assert applied["status"] == "applied"
    assert applied["result"] is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_machine_operations_batch_preview_and_apply(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_machine_fixture(session_factory)
    headers = {"X-User-Token": seed["token"]}

    preview_response = await client.post(
        "/api/v1/machine/batches/operations/preview",
        headers=headers,
        json={
            "domain": "operations",
            "payload_format": "operation_actions_v1",
            "mode": "atomic",
            "idempotency_key": str(uuid4()),
            "payload": {
                "actions": [
                    {
                        "action": "operation.create_draft",
                        "data": {
                            "operation_type": "RECEIVE",
                            "site_id": seed["site_id"],
                            "lines": [
                                {
                                    "line_number": 1,
                                    "item_id": seed["item_id"],
                                    "qty": 5,
                                }
                            ],
                        },
                    }
                ]
            },
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["status"] == "preview_ready"
    assert preview["summary"]["create"] == 1

    apply_response = await client.post(
        "/api/v1/machine/batches/operations/apply",
        headers=headers,
        json={"batch_id": preview["batch_id"], "plan_id": preview["plan_id"]},
    )
    assert apply_response.status_code == 200
    applied = apply_response.json()
    assert applied["status"] == "applied"
    assert applied["result"]["summary"]["create"] == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_machine_observer_cannot_apply_catalog_batch(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_machine_fixture(
        session_factory,
        role="observer",
        with_manage_scope=False,
    )
    headers = {"X-User-Token": seed["token"]}

    preview_response = await client.post(
        "/api/v1/machine/batches/catalog/preview",
        headers=headers,
        json={
            "domain": "catalog",
            "payload_format": "catalog_package_v1",
            "mode": "atomic",
            "idempotency_key": str(uuid4()),
            "payload": {"categories": [], "items": []},
        },
    )
    assert preview_response.status_code == 403
