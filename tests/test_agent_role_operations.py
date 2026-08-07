"""Agent role (ADR-0030) — draft operations authorization tests.

Covers TZ-AGENT-ROLE-SYNCSERVER §6 / §10.6:
- agent reads operations globally (list/get);
- agent creates draft;
- agent PATCHes/cancels ONLY its own draft;
- agent cannot PATCH/cancel other drafts or submitted operations;
- agent cannot submit/restore/accept/delete/temporary-item;
- existing storekeeper/chief/observer flows do not regress.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.core.identity import Identity
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from app.services.operations_policy import OperationsPolicy
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
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        second_site = Site(code=f"SITE2-{suffix}", name=f"Site 2 {suffix}", is_active=True)
        session.add(second_site)
        await session.flush()

        root_user = User(
            username=f"root-{suffix}", email=f"root-{suffix}@example.com",
            full_name="Root", is_active=True, is_root=True, role="root",
            default_site_id=site.id,
        )
        chief_user = User(
            username=f"chief-{suffix}", email=f"chief-{suffix}@example.com",
            full_name="Chief Storekeeper", is_active=True, is_root=False,
            role="chief_storekeeper", default_site_id=site.id,
        )
        storekeeper_user = User(
            username=f"storekeeper-{suffix}", email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper", is_active=True, is_root=False,
            role="storekeeper", default_site_id=site.id,
        )
        observer_user = User(
            username=f"observer-{suffix}", email=f"observer-{suffix}@example.com",
            full_name="Observer", is_active=True, is_root=False,
            role="observer", default_site_id=site.id,
        )
        agent_user = User(
            username=f"agent-{suffix}", email=f"agent-{suffix}@example.com",
            full_name="Agent", is_active=True, is_root=False,
            role="agent", default_site_id=site.id,
        )
        other_agent_user = User(
            username=f"agent2-{suffix}", email=f"agent2-{suffix}@example.com",
            full_name="Agent 2", is_active=True, is_root=False,
            role="agent", default_site_id=site.id,
        )
        session.add_all([root_user, chief_user, storekeeper_user, observer_user, agent_user, other_agent_user])
        await session.flush()

        session.add(
            UserAccessScope(
                user_id=storekeeper_user.id,
                site_id=site.id,
                can_view=True,
                can_operate=True,
                can_manage_catalog=False,
                is_active=True,
            )
        )

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol="pcs", is_active=True)
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
            category_id=category.id, unit_id=unit.id, is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "site_id": site.id,
            "second_site_id": second_site.id,
            "item_id": item.id,
            "unit_id": unit.id,
            "root_token": str(root_user.user_token),
            "chief_token": str(chief_user.user_token),
            "storekeeper_token": str(storekeeper_user.user_token),
            "observer_token": str(observer_user.user_token),
            "agent_token": str(agent_user.user_token),
            "other_agent_token": str(other_agent_user.user_token),
        }


async def _create_draft(
    client: AsyncClient,
    *,
    token: str,
    site_id: int,
    item_id: int,
    notes: str = "agent draft",
) -> dict:
    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": token},
        json={
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": item_id, "qty": 5}],
            "notes": notes,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Policy unit tests (no DB)
# ---------------------------------------------------------------------------

def _agent_identity() -> Identity:
    user = User(
        username=f"agent-{uuid4().hex[:6]}",
        email=f"agent-{uuid4().hex[:6]}@example.com",
        full_name="Agent",
        is_active=True,
        is_root=False,
        role="agent",
        default_site_id=None,
    )
    return Identity.from_user_and_device(user=user, device=None, scopes=[])


def _operation(created_by_user_id, *, status: str = "draft"):
    return type("Op", (), {"created_by_user_id": created_by_user_id, "status": status})()


def test_require_agent_own_draft_passes_for_own_draft() -> None:
    identity = _agent_identity()
    OperationsPolicy.require_agent_own_draft(identity, _operation(identity.user_id, status="draft"))


def test_require_agent_own_draft_rejects_other_users_draft() -> None:
    identity = _agent_identity()
    with pytest.raises(Exception) as exc_info:
        OperationsPolicy.require_agent_own_draft(identity, _operation(uuid4(), status="draft"))
    assert getattr(exc_info.value, "status_code", None) == 403


def test_require_agent_own_draft_rejects_submitted() -> None:
    identity = _agent_identity()
    with pytest.raises(Exception) as exc_info:
        OperationsPolicy.require_agent_own_draft(identity, _operation(identity.user_id, status="submitted"))
    assert getattr(exc_info.value, "status_code", None) == 403


def test_require_agent_own_draft_is_noop_for_non_agent() -> None:
    user = User(
        username=f"sk-{uuid4().hex[:6]}",
        email=f"sk-{uuid4().hex[:6]}@example.com",
        full_name="Storekeeper",
        is_active=True,
        is_root=False,
        role="storekeeper",
        default_site_id=None,
    )
    identity = Identity.from_user_and_device(user=user, device=None, scopes=[])
    # Non-agent: no-op even for someone else's submitted operation.
    OperationsPolicy.require_agent_own_draft(identity, _operation(uuid4(), status="submitted"))


# ---------------------------------------------------------------------------
# Read access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_reads_operations_list_and_get(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    listing = await client.get("/api/v1/operations", headers={"X-User-Token": seed["agent_token"]})
    assert listing.status_code == 200, listing.text
    assert any(op["id"] == operation["id"] for op in listing.json()["items"])

    detail = await client.get(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "draft"
    assert detail.json()["created_by_user_id"] == operation["created_by_user_id"]


# ---------------------------------------------------------------------------
# Draft create / PATCH / cancel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_creates_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )
    assert operation["status"] == "draft"
    assert operation["operation_type"] == "RECEIVE"


@pytest.mark.asyncio
async def test_agent_patches_own_draft_notes_and_effective_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from datetime import UTC, datetime

    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    new_effective_at = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
        json={"notes": "updated by agent", "effective_at": new_effective_at.isoformat()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notes"] == "updated by agent"
    assert datetime.fromisoformat(body["effective_at"]) == new_effective_at
    assert body["version"] == 2


@pytest.mark.asyncio
async def test_agent_patches_own_draft_lines(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
        json={"lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 7}]},
    )
    assert response.status_code == 200, response.text
    lines = response.json()["lines"]
    assert len(lines) == 1
    assert str(lines[0]["qty"]) in {"7", "7.000"}


@pytest.mark.asyncio
async def test_agent_patches_own_draft_effective_at_endpoint(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from datetime import UTC, datetime

    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    new_effective_at = datetime(2026, 8, 2, 9, 0, tzinfo=UTC)
    response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["agent_token"]},
        json={"effective_at": new_effective_at.isoformat()},
    )
    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["effective_at"]) == new_effective_at


@pytest.mark.asyncio
async def test_agent_patches_own_move_draft_without_site_operate(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Agent may edit MOVE draft fields without require_move_access auth gate
    (TZ §6.4); structural validation stays in OperationsService."""
    seed = await _seed(session_factory)
    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["agent_token"]},
        json={
            "operation_type": "MOVE",
            "site_id": seed["site_id"],
            "source_site_id": seed["site_id"],
            "destination_site_id": seed["second_site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 3}],
            "notes": "agent move",
        },
    )
    assert response.status_code == 200, response.text
    operation_id = response.json()["id"]

    patch = await client.patch(
        f"/api/v1/operations/{operation_id}",
        headers={"X-User-Token": seed["agent_token"]},
        json={"notes": "agent move updated"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["notes"] == "agent move updated"


@pytest.mark.asyncio
async def test_agent_cannot_patch_other_users_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
        json={"notes": "hijack"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cannot_patch_other_agents_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["other_agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
        json={"notes": "hijack"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cannot_patch_submitted_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    submit = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit.status_code == 200, submit.text

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
        json={"notes": "too late"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cancels_own_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["agent_token"]},
        json={"cancel": True, "reason": "agent changed mind"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_agent_cannot_cancel_other_users_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["agent_token"]},
        json={"cancel": True, "reason": "hijack"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cannot_cancel_submitted_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    submit = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit.status_code == 200, submit.text

    response = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["agent_token"]},
        json={"cancel": True, "reason": "too late"},
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Submit / lifecycle fail-closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_cannot_submit(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["agent_token"]},
        json={"submit": True},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cannot_restore(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )
    cancelled = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["agent_token"]},
        json={"cancel": True, "reason": "test"},
    )
    assert cancelled.status_code == 200, cancelled.text

    response = await client.post(
        f"/api/v1/operations/{operation['id']}/restore",
        headers={"X-User-Token": seed["agent_token"]},
        json={"restore": True},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cannot_accept_lines(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )
    submit = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit.status_code == 200, submit.text
    line_id = submit.json()["lines"][0]["id"]

    response = await client.post(
        f"/api/v1/operations/{operation['id']}/accept-lines",
        headers={"X-User-Token": seed["agent_token"]},
        json={"lines": [{"line_id": line_id, "accepted_qty": 5}]},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cannot_delete_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )
    cancelled = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["agent_token"]},
        json={"cancel": True, "reason": "test"},
    )
    assert cancelled.status_code == 200, cancelled.text

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Temporary items fail-closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_cannot_create_draft_with_temporary_item(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["agent_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": f"temp-{uuid4().hex[:8]}",
            "lines": [
                {
                    "line_number": 1,
                    "temporary_item": {
                        "client_key": f"tk-{uuid4().hex[:8]}",
                        "name": "Temp Item",
                        "unit_id": seed["unit_id"],
                    },
                    "qty": 5,
                }
            ],
        },
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_agent_cannot_add_temporary_item_line_via_patch(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["agent_token"]},
        json={
            "lines": [
                {
                    "line_number": 1,
                    "temporary_item": {
                        "client_key": f"tk-{uuid4().hex[:8]}",
                        "name": "Temp Item",
                        "unit_id": seed["unit_id"],
                    },
                    "qty": 5,
                }
            ],
        },
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Regression sanity: existing roles unaffected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_regression_observer_reads_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.get(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["observer_token"]},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_regression_chief_submits_agent_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TZ §11: agent draft -> chief submit remains the core workflow."""
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_regression_storekeeper_cannot_patch_other_users_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Storekeeper with operate scope on the site still cannot PATCH another
    user's draft (owner/supervisor guard preserved for non-agent)."""
    seed = await _seed(session_factory)
    operation = await _create_draft(
        client,
        token=seed["agent_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"notes": "hijack"},
    )
    assert response.status_code == 403, response.text
