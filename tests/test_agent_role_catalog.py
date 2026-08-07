"""
Tests for the ``agent`` domain role catalog surface (TZ-AGENT-ROLE-SYNCSERVER §10.3–10.5).

Covers: business read, admin list/detail read, create, PATCH allow-list,
merge, and lifecycle denials (delete/deactivate/batch), plus regression for
root/chief/storekeeper/observer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Balance, Category, InventorySubject, Item, Operation, OperationLine, Unit, User
from app.schemas.catalog import (
    CategoryCreateRequest,
    ItemCreateRequest,
    UnitCreateRequest,
)
from app.services.catalog_admin_service import CatalogAdminService
from app.services.uow import UnitOfWork


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
async def agent_user(db_session: AsyncSession, site) -> User:
    """Тестовый пользователь роли agent (ADR-0030)."""
    user_obj = User(
        username=f"agent-{uuid4().hex[:8]}",
        email=f"agent-{uuid4().hex[:8]}@example.com",
        full_name="Agent Test",
        is_active=True,
        is_root=False,
        role="agent",
        default_site_id=site.id,
    )
    db_session.add(user_obj)
    await db_session.flush()
    return user_obj


@pytest.fixture
async def agent_headers(agent_user: User) -> dict[str, str]:
    return {"X-User-Token": str(agent_user.user_token)}


@pytest.fixture
async def storekeeper_user(db_session: AsyncSession, site) -> User:
    user_obj = User(
        username=f"sk-{uuid4().hex[:8]}",
        email=f"sk-{uuid4().hex[:8]}@example.com",
        full_name="Storekeeper Test",
        is_active=True,
        is_root=False,
        role="storekeeper",
        default_site_id=site.id,
    )
    db_session.add(user_obj)
    await db_session.flush()
    return user_obj


async def _create_unit(uow: UnitOfWork, name: str = "Agent Unit", symbol: str = "AU") -> Unit:
    return await CatalogAdminService().create_unit(
        uow,
        UnitCreateRequest(name=name, symbol=symbol),
    )


async def _create_category(
    uow: UnitOfWork, name: str = "Agent Category", code: str | None = None
) -> Category:
    return await CatalogAdminService().create_category(
        uow,
        CategoryCreateRequest(name=name, code=code),
    )


async def _create_item(
    uow: UnitOfWork,
    *,
    unit: Unit,
    category: Category,
    name: str = "Agent Item",
    sku: str | None = None,
) -> Item:
    return await CatalogAdminService().create_item(
        uow,
        ItemCreateRequest(name=name, sku=sku, unit_id=unit.id, category_id=category.id),
    )


async def _merge_setup(
    uow: UnitOfWork, site, actor: User
) -> tuple[Item, Item, Unit, Category]:
    """Setup source/target items with inventory subjects and balance (mirrors test_catalog_merge)."""
    unit = await _create_unit(uow, name="Merge Unit", symbol="MU")
    category = await _create_category(uow, name="Merge Cat 1")
    source = await _create_item(uow, unit=unit, category=category, name="Merge Source", sku="MRG-SRC")
    target = await _create_item(uow, unit=unit, category=category, name="Merge Target", sku="MRG-TGT")

    source_subject = InventorySubject(subject_type="catalog_item", item_id=source.id)
    uow.session.add(source_subject)
    await uow.session.flush()

    target_subject = InventorySubject(subject_type="catalog_item", item_id=target.id)
    uow.session.add(target_subject)
    await uow.session.flush()

    uow.session.add(
        Balance(
            site_id=site.id,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("10.000"),
        )
    )
    await uow.session.flush()

    op = Operation(
        site_id=site.id,
        operation_type="ADJUSTMENT",
        status="submitted",
        created_by_user_id=actor.id,
        effective_at=datetime.now(UTC),
    )
    uow.session.add(op)
    await uow.session.flush()

    uow.session.add(
        OperationLine(
            operation_id=op.id,
            line_number=1,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("10.000"),
        )
    )
    await uow.session.flush()

    return source, target, unit, category


# ─── Business read (TZ §10.2) ────────────────────────────────────────


class TestAgentBusinessRead:
    @pytest.mark.asyncio
    async def test_agent_reads_catalog_primary_endpoints(
        self, client: AsyncClient, agent_headers: dict[str, str]
    ):
        for path in (
            "/api/v1/catalog/items",
            "/api/v1/catalog/categories",
            "/api/v1/catalog/units",
            "/api/v1/catalog/categories/tree",
        ):
            resp = await client.get(path, headers=agent_headers)
            assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"

    @pytest.mark.asyncio
    async def test_agent_reads_browse_endpoints(
        self, client: AsyncClient, agent_headers: dict[str, str]
    ):
        for path in (
            "/api/v1/catalog/read/items",
            "/api/v1/catalog/read/categories",
        ):
            resp = await client.get(path, headers=agent_headers)
            assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"

    @pytest.mark.asyncio
    async def test_agent_sites_permissions(
        self, client: AsyncClient, agent_headers: dict[str, str], site
    ):
        resp = await client.get("/api/v1/catalog/sites", headers=agent_headers)
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload["sites"]) >= 1
        site_payload = next(s for s in payload["sites"] if s["site_id"] == site.id)
        assert site_payload["permissions"] == {
            "can_view": True,
            "can_operate": False,
            "can_manage_catalog": True,
        }

    @pytest.mark.asyncio
    async def test_agent_reads_admin_list_and_detail(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        unit = await _create_unit(uow)
        category = await _create_category(uow)
        item = await _create_item(uow, unit=unit, category=category)

        for path in (
            "/api/v1/catalog/admin/units",
            "/api/v1/catalog/admin/categories",
            "/api/v1/catalog/admin/items",
            f"/api/v1/catalog/admin/units/{unit.id}",
            f"/api/v1/catalog/admin/categories/{category.id}",
            f"/api/v1/catalog/admin/items/{item.id}",
        ):
            resp = await client.get(path, headers=agent_headers)
            assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"


# ─── Create (TZ §10.3 / §5.3) ────────────────────────────────────────


class TestAgentCatalogCreate:
    @pytest.mark.asyncio
    async def test_agent_creates_unit_category_item(
        self, client: AsyncClient, agent_headers: dict[str, str]
    ):
        resp = await client.post(
            "/api/v1/catalog/admin/units",
            headers=agent_headers,
            json={"name": "Unit-КГ", "symbol": "кг"},
        )
        assert resp.status_code == 200, resp.text
        unit_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/catalog/admin/categories",
            headers=agent_headers,
            json={"name": "Cat-Инструменты", "code": "INSTR"},
        )
        assert resp.status_code == 200, resp.text
        category_id = resp.json()["id"]

        resp = await client.post(
            "/api/v1/catalog/admin/items",
            headers=agent_headers,
            json={"name": "Item-Отвёртка", "unit_id": unit_id, "category_id": category_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] > 0
        assert body["is_active"] is True
        assert body["requires_review"] is False


# ─── PATCH allow-list (TZ §10.4 / §5.2) ──────────────────────────────


class TestAgentCatalogPatch:
    @pytest.mark.asyncio
    async def test_agent_patch_item_allowed_fields(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        unit = await _create_unit(uow)
        category = await _create_category(uow)
        other_unit = await _create_unit(uow, name="Second Unit", symbol="SU")
        other_category = await _create_category(uow, name="Second Category", code="SEC")
        item = await _create_item(uow, unit=unit, category=category)

        resp = await client.patch(
            f"/api/v1/catalog/admin/items/{item.id}",
            headers=agent_headers,
            json={
                "name": "Item-Updated",
                "sku": "NEW-SKU-1",
                "description": "updated by agent",
                "category_id": other_category.id,
                "unit_id": other_unit.id,
                "hashtags": ["tool", "agent"],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Item-Updated"
        assert body["sku"] == "NEW-SKU-1"
        assert body["description"] == "updated by agent"
        assert body["category_id"] == other_category.id
        assert body["unit_id"] == other_unit.id
        assert body["hashtags"] == ["tool", "agent"]
        assert body["is_active"] is True

    @pytest.mark.asyncio
    async def test_agent_patch_item_is_active_403(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        unit = await _create_unit(uow)
        category = await _create_category(uow)
        item = await _create_item(uow, unit=unit, category=category)

        resp = await client.patch(
            f"/api/v1/catalog/admin/items/{item.id}",
            headers=agent_headers,
            json={"is_active": False},
        )
        assert resp.status_code == 403

        resp = await client.patch(
            f"/api/v1/catalog/admin/items/{item.id}",
            headers=agent_headers,
            json={"name": "Renamed", "is_active": False},
        )
        assert resp.status_code == 403

        item_after = await uow.catalog.get_item_by_id(item.id)
        assert item_after.is_active is True
        assert item_after.name == "Agent Item"

    @pytest.mark.asyncio
    async def test_agent_patch_category_allowed_fields(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        parent = await _create_category(uow, name="Parent Cat")
        category = await _create_category(uow, name="Child Cat", code="CHILD")

        resp = await client.patch(
            f"/api/v1/catalog/admin/categories/{category.id}",
            headers=agent_headers,
            json={"name": "Child-Updated", "code": "CHILD2", "parent_id": parent.id, "sort_order": 7},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Child-Updated"
        assert body["code"] == "CHILD2"
        assert body["parent_id"] == parent.id
        assert body["sort_order"] == 7
        assert body["is_active"] is True

    @pytest.mark.asyncio
    async def test_agent_patch_category_is_active_403(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        category = await _create_category(uow)

        resp = await client.patch(
            f"/api/v1/catalog/admin/categories/{category.id}",
            headers=agent_headers,
            json={"is_active": False},
        )
        assert resp.status_code == 403

        category_after = await uow.catalog.get_category_by_id(category.id)
        assert category_after.is_active is True

    @pytest.mark.asyncio
    async def test_agent_patch_unit_allowed_fields(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        unit = await _create_unit(uow)

        resp = await client.patch(
            f"/api/v1/catalog/admin/units/{unit.id}",
            headers=agent_headers,
            json={"name": "Kilogramm", "symbol": "kg", "sort_order": 3},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Kilogramm"
        assert body["symbol"] == "kg"
        assert body["sort_order"] == 3
        assert body["is_active"] is True

    @pytest.mark.asyncio
    async def test_agent_patch_unit_is_active_403(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        unit = await _create_unit(uow)

        resp = await client.patch(
            f"/api/v1/catalog/admin/units/{unit.id}",
            headers=agent_headers,
            json={"is_active": False},
        )
        assert resp.status_code == 403

        unit_after = await uow.catalog.get_unit_by_id(unit.id)
        assert unit_after.is_active is True

    @pytest.mark.asyncio
    async def test_agent_patch_merge_system_field_not_applied(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        """TZ §10.5: direct merge-field mutation remains impossible through ordinary PATCH."""
        unit = await _create_unit(uow)
        category = await _create_category(uow)
        item = await _create_item(uow, unit=unit, category=category)

        resp = await client.patch(
            f"/api/v1/catalog/admin/items/{item.id}",
            headers=agent_headers,
            json={"name": "Clean Rename", "merged_into_id": 123},
        )
        assert resp.status_code == 200, resp.text
        item_after = await uow.catalog.get_item_by_id(item.id)
        assert item_after.name == "Clean Rename"
        assert item_after.merged_into_id is None


# ─── Merge (TZ §10.5 / §5.4) ─────────────────────────────────────────


class TestAgentCatalogMerge:
    @pytest.mark.asyncio
    async def test_agent_merge_items_via_existing_endpoint(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        agent_user: User,
        uow: UnitOfWork,
        site,
    ):
        source, target, _, _ = await _merge_setup(uow, site, agent_user)

        resp = await client.post(
            "/api/v1/catalog/admin/items/merge",
            headers=agent_headers,
            json={"source_item_id": source.id, "target_item_id": target.id, "comment": "agent merge"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == target.id

        source_after = await uow.catalog.get_item_by_id(source.id)
        assert source_after.is_active is False
        assert source_after.merged_into_id == target.id

    @pytest.mark.asyncio
    async def test_agent_merge_categories_via_existing_endpoint(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        service = CatalogAdminService()
        unit = await _create_unit(uow)
        source_cat = await _create_category(uow, name="Merge Cat Source", code="MCS")
        target_cat = await _create_category(uow, name="Merge Cat Target", code="MCT")
        await service.create_item(
            uow,
            ItemCreateRequest(name="Item In Source Cat", unit_id=unit.id, category_id=source_cat.id),
        )

        resp = await client.post(
            "/api/v1/catalog/admin/categories/merge",
            headers=agent_headers,
            json={
                "source_category_id": source_cat.id,
                "target_category_id": target_cat.id,
                "comment": "agent cat merge",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == target_cat.id

        source_after = await uow.catalog.get_category_by_id(source_cat.id)
        assert source_after.is_active is False
        assert source_after.merged_into_id == target_cat.id


# ─── Lifecycle denials (TZ §10.5, §5.5) ──────────────────────────────


class TestAgentCatalogDenied:
    @pytest.mark.asyncio
    async def test_agent_delete_entities_403(
        self,
        client: AsyncClient,
        agent_headers: dict[str, str],
        uow: UnitOfWork,
    ):
        unit = await _create_unit(uow)
        category = await _create_category(uow)
        item = await _create_item(uow, unit=unit, category=category)

        for path in (
            f"/api/v1/catalog/admin/units/{unit.id}",
            f"/api/v1/catalog/admin/categories/{category.id}",
            f"/api/v1/catalog/admin/items/{item.id}",
        ):
            resp = await client.delete(path, headers=agent_headers)
            assert resp.status_code == 403, f"{path}: {resp.status_code}"

    @pytest.mark.asyncio
    async def test_agent_batch_403(
        self, client: AsyncClient, agent_headers: dict[str, str]
    ):
        resp = await client.post(
            "/api/v1/catalog/admin/batch",
            headers=agent_headers,
            json={
                "client_batch_id": "agent-batch-1",
                "mode": "atomic",
                "changes": [
                    {
                        "local_id": "u1",
                        "entity_type": "unit",
                        "action": "create",
                        "payload": {"name": "kg", "symbol": "kg"},
                    },
                ],
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_agent_bulk_create_403(
        self, client: AsyncClient, agent_headers: dict[str, str]
    ):
        resp = await client.post(
            "/api/v1/catalog/admin/units/bulk",
            headers=agent_headers,
            json={"items": [{"name": "kg", "symbol": "kg"}]},
        )
        assert resp.status_code == 403


# ─── Business read sanity: documents/reports/issue_objects (TZ §4.1) ─


class TestAgentBusinessReadParity:
    @pytest.mark.asyncio
    async def test_agent_reads_documents_reports_issue_objects(
        self, client: AsyncClient, agent_headers: dict[str, str]
    ):
        for path in (
            "/api/v1/documents",
            "/api/v1/reports/stock-summary",
            "/api/v1/reports/item-movement",
            "/api/v1/issue-objects",
            "/api/v1/issue-objects/tree",
            "/api/v1/issue-object-categories",
        ):
            resp = await client.get(path, headers=agent_headers)
            assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"


# ─── Regression (TZ §10.9) ───────────────────────────────────────────


class TestExistingRolesRegression:
    @pytest.mark.asyncio
    async def test_root_patch_is_active_ok(
        self, client: AsyncClient, admin_user: User, uow: UnitOfWork
    ):
        unit = await _create_unit(uow)
        category = await _create_category(uow)
        item = await _create_item(uow, unit=unit, category=category)

        resp = await client.patch(
            f"/api/v1/catalog/admin/items/{item.id}",
            headers={"X-User-Token": str(admin_user.user_token)},
            json={"is_active": False},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_chief_patch_is_active_and_delete_ok(
        self, client: AsyncClient, test_user: User, uow: UnitOfWork
    ):
        unit = await _create_unit(uow)

        resp = await client.patch(
            f"/api/v1/catalog/admin/units/{unit.id}",
            headers={"X-User-Token": str(test_user.user_token)},
            json={"is_active": False},
        )
        assert resp.status_code == 200, resp.text

        resp = await client.delete(
            f"/api/v1/catalog/admin/units/{unit.id}",
            headers={"X-User-Token": str(test_user.user_token)},
        )
        assert resp.status_code == 204, resp.text

    @pytest.mark.asyncio
    async def test_chief_batch_still_allowed(
        self, client: AsyncClient, test_user: User
    ):
        resp = await client.post(
            "/api/v1/catalog/admin/batch",
            headers={"X-User-Token": str(test_user.user_token)},
            json={
                "client_batch_id": "chief-batch-agent-reg",
                "mode": "atomic",
                "changes": [
                    {
                        "local_id": "u1",
                        "entity_type": "unit",
                        "action": "create",
                        "payload": {"name": "kg", "symbol": "kg"},
                    },
                ],
            },
        )
        assert resp.status_code != 403, resp.text

    @pytest.mark.asyncio
    async def test_observer_reads_catalog(
        self, client: AsyncClient, auth_headers_user_no_access: dict[str, str]
    ):
        resp = await client.get("/api/v1/catalog/items", headers=auth_headers_user_no_access)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_storekeeper_reads_catalog(
        self, client: AsyncClient, storekeeper_user: User
    ):
        resp = await client.get(
            "/api/v1/catalog/items",
            headers={"X-User-Token": str(storekeeper_user.user_token)},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_observer_catalog_admin_still_403(
        self, client: AsyncClient, auth_headers_user_no_access: dict[str, str]
    ):
        resp = await client.get("/api/v1/catalog/admin/items", headers=auth_headers_user_no_access)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_storekeeper_catalog_admin_still_403(
        self, client: AsyncClient, storekeeper_user: User
    ):
        resp = await client.patch(
            "/api/v1/catalog/admin/items/1",
            headers={"X-User-Token": str(storekeeper_user.user_token)},
            json={"name": "x"},
        )
        assert resp.status_code == 403
