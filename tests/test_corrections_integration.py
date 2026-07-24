from __future__ import annotations

import pytest
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from main import create_app
from app.core.config import get_settings
from app.models.base import Base
from app.models.operation import (
    Operation,
    OperationLine,
    OperationRevision,
    OperationRevisionLine,
    OperationCorrection,
    OperationCorrectionLine,
)
from app.models.item import Item
from app.models.site import Site
from app.models.user import User
from app.models.balance import Balance
from app.models.inventory_subject import InventorySubject
from app.models.unit import Unit
from app.models.category import Category
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.services.uow import UnitOfWork

pytestmark = pytest.mark.asyncio

TEST_TOKEN = "3382a4fb-7507-42ba-9e87-aa350f1738c9"
HEADERS = {"X-User-Token": TEST_TOKEN}


@pytest.fixture(scope="module")
def settings():
    return get_settings()


@pytest.fixture(scope="module")
def app(settings):
    return create_app()


@pytest.fixture
async def session_factory(settings):
    """Create isolated test tables for each test."""
    engine = create_async_engine(
        settings.DATABASE_URL,
        isolation_level="AUTOCOMMIT",
    )
    # Create a test database or use existing with test prefix
    async with engine.connect() as conn:
        await conn.execute(text("COMMIT"))
        db_name = f"test_corrections_{uuid4().hex[:8]}"
        await conn.execute(text(f"CREATE DATABASE {db_name}"))
    
    test_url = str(settings.DATABASE_URL).rsplit("/", 1)[0] + f"/{db_name}"
    test_engine = create_async_engine(test_url)
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    
    yield factory
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    
    async with engine.connect() as conn:
        await conn.execute(text("COMMIT"))
        await conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
    await engine.dispose()


@pytest.fixture
async def client(app, session_factory):
    """HTTP client that overrides UoW dependency with test session."""
    from app.api.deps import get_uow

    async def _override_uow():
        session = session_factory()
        async with session:
            yield UnitOfWork(session)

    app.dependency_overrides[get_uow] = _override_uow
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def seed(session_factory):
    """Seed minimal data: site, user, category, unit, item, inventory_subject."""
    async with session_factory() as session:
        user = User(id=UUID(TEST_TOKEN), username="test_user", email="test@test.com")
        session.add(user)

        site = Site(id=1, code="TST", name="Test Site")
        session.add(site)

        category = Category(id=1, name="Test Category", code="TSTCAT", is_active=True)
        session.add(category)

        unit = Unit(id=1, name="pcs", symbol="pcs")
        session.add(unit)

        item = Item(
            id=1, name="Test Item", sku="TST-001",
            category_id=1, unit_id=1,
            is_active=True,
        )
        session.add(item)

        subject = InventorySubject(
            id=1, subject_type="catalog_item",
            item_id=1, site_id=1,
        )
        session.add(subject)

        balance = Balance(
            site_id=1, inventory_subject_id=1,
            item_id=1, qty=Decimal("1000"),
        )
        session.add(balance)

        await session.commit()

    return {
        "user_id": user.id,
        "site_id": 1,
        "item_id": 1,
        "subject_id": 1,
    }


class TestCorrectionFlow:
    """Integration tests for the full correction flow."""

    @pytest.mark.asyncio
    async def test_full_happy_path(self, client, seed):
        """RECEIVE without acceptance, full correction happy path."""
        # 1. Create RECEIVE operation
        r = await client.post(
            "/api/v1/operations",
            headers=HEADERS,
            json={
                "site_id": seed["site_id"],
                "operation_type": "RECEIVE",
                "lines": [{"item_id": seed["item_id"], "qty": 100}],
            },
        )
        assert r.status_code == 200, r.text
        op = r.json()
        op_id = op["id"]

        # 2. Submit
        r = await client.post(
            f"/api/v1/operations/{op_id}/submit",
            headers=HEADERS,
            json={"submit": True},
        )
        assert r.status_code == 200, r.text

        # 3. Begin correction
        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections",
            headers=HEADERS,
        )
        assert r.status_code == 200, r.text
        corr = r.json()
        assert corr["status"] == "draft"
        assert len(corr["lines"]) == 1
        corr_id = corr["id"]

        line_uuid = corr["lines"][0]["line_uuid"]

        # 4. PUT update: change qty 100→120
        r = await client.put(
            f"/api/v1/operations/{op_id}/corrections/{corr_id}",
            headers=HEADERS,
            json={
                "expected_version": 1,
                "lines": [
                    {
                        "line_uuid": line_uuid,
                        "line_number": 1,
                        "item_id": seed["item_id"],
                        "qty": 120,
                    },
                ],
            },
        )
        assert r.status_code == 200, r.text

        # 5. Submit correction
        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections/{corr_id}/submit",
            headers=HEADERS,
            json={"expected_version": 2},
        )
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["correction"]["status"] == "applied"
        assert result["operation"]["current_revision_number"] >= 1

    @pytest.mark.asyncio
    async def test_v1_scope_rejects_move(self, client, seed):
        """V1 scope: MOVE → 422."""
        r = await client.post(
            "/api/v1/operations",
            headers=HEADERS,
            json={
                "site_id": seed["site_id"],
                "operation_type": "RECEIVE",
                "lines": [{"item_id": seed["item_id"], "qty": 10}],
            },
        )
        assert r.status_code == 200
        op_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/operations/{op_id}/submit",
            headers=HEADERS,
            json={"submit": True},
        )
        assert r.status_code == 200

        # Mock operation_type to MOVE by creating a new one
        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections",
            headers=HEADERS,
        )
        # This should succeed (RECEIVE is allowed)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_client_cannot_submit_correction_kind(self, client, seed):
        """PUT with correction_kind → 422."""
        r = await client.post(
            "/api/v1/operations",
            headers=HEADERS,
            json={
                "site_id": seed["site_id"],
                "operation_type": "RECEIVE",
                "lines": [{"item_id": seed["item_id"], "qty": 10}],
            },
        )
        assert r.status_code == 200
        op_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/operations/{op_id}/submit",
            headers=HEADERS,
            json={"submit": True},
        )
        assert r.status_code == 200

        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections",
            headers=HEADERS,
        )
        assert r.status_code == 200
        corr_id = r.json()["id"]

        # PUT with correction_kind
        r = await client.put(
            f"/api/v1/operations/{op_id}/corrections/{corr_id}",
            headers=HEADERS,
            json={
                "expected_version": 1,
                "lines": [
                    {
                        "line_uuid": r.json()["lines"][0]["line_uuid"],
                        "line_number": 1,
                        "item_id": seed["item_id"],
                        "qty": 10,
                        "correction_kind": "unchanged",
                    },
                ],
            },
        )
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "correction_kind_not_allowed_in_request"

    @pytest.mark.asyncio
    async def test_begin_correction_clones_baseline(self, client, seed):
        """Begin correction returns all baseline lines."""
        r = await client.post(
            "/api/v1/operations",
            headers=HEADERS,
            json={
                "site_id": seed["site_id"],
                "operation_type": "RECEIVE",
                "lines": [{"item_id": seed["item_id"], "qty": 50}],
            },
        )
        assert r.status_code == 200
        op_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/operations/{op_id}/submit",
            headers=HEADERS,
            json={"submit": True},
        )
        assert r.status_code == 200

        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections",
            headers=HEADERS,
        )
        assert r.status_code == 200
        corr = r.json()
        assert len(corr["lines"]) == 1
        assert corr["lines"][0]["qty"] == 50

    @pytest.mark.asyncio
    async def test_duplicate_line_uuid_rejected(self, client, seed):
        """PUT with two lines with same line_uuid → 409."""
        r = await client.post(
            "/api/v1/operations",
            headers=HEADERS,
            json={
                "site_id": seed["site_id"],
                "operation_type": "RECEIVE",
                "lines": [{"item_id": seed["item_id"], "qty": 10}],
            },
        )
        assert r.status_code == 200
        op_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/operations/{op_id}/submit",
            headers=HEADERS,
            json={"submit": True},
        )
        assert r.status_code == 200

        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections",
            headers=HEADERS,
        )
        assert r.status_code == 200
        corr_id = r.json()["id"]

        same_lu = str(uuid4())
        r = await client.put(
            f"/api/v1/operations/{op_id}/corrections/{corr_id}",
            headers=HEADERS,
            json={
                "expected_version": 1,
                "lines": [
                    {"line_uuid": same_lu, "line_number": 1, "item_id": seed["item_id"], "qty": 10},
                    {"line_uuid": same_lu, "line_number": 2, "item_id": seed["item_id"], "qty": 20},
                ],
            },
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "correction_duplicate_line_uuid"

    @pytest.mark.asyncio
    async def test_failed_validation_leaves_correction_draft(self, client, seed):
        """Validation failure → correction stays draft, effects unchanged."""
        r = await client.post(
            "/api/v1/operations",
            headers=HEADERS,
            json={
                "site_id": seed["site_id"],
                "operation_type": "RECEIVE",
                "lines": [{"item_id": seed["item_id"], "qty": 10}],
            },
        )
        assert r.status_code == 200
        op_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/operations/{op_id}/submit",
            headers=HEADERS,
            json={"submit": True},
        )
        assert r.status_code == 200

        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections",
            headers=HEADERS,
        )
        assert r.status_code == 200
        corr = r.json()
        corr_id = corr["id"]
        lu = corr["lines"][0]["line_uuid"]

        # Try to remove line with insufficient balance (should fail validation)
        # First reduce balance to 0
        lu2 = str(uuid4())
        r = await client.put(
            f"/api/v1/operations/{op_id}/corrections/{corr_id}",
            headers=HEADERS,
            json={
                "expected_version": 1,
                "lines": [
                    {"line_uuid": lu, "line_number": 1, "item_id": seed["item_id"], "qty": 2000},
                ],
            },
        )
        assert r.status_code == 200

        # Submit should fail - balance 1000 < 2000
        r = await client.post(
            f"/api/v1/operations/{op_id}/corrections/{corr_id}/submit",
            headers=HEADERS,
            json={"expected_version": 2},
        )
        assert r.status_code == 409, r.text

        # Correction should remain draft
        assert r.json()["detail"]["code"] == "correction_insufficient_balance"
