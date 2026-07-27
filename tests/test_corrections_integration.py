from __future__ import annotations

import pytest
from decimal import Decimal
from uuid import uuid4

from app.models.item import Item
from app.models.balance import Balance
from app.models.inventory_subject import InventorySubject
from app.models.unit import Unit
from app.models.category import Category

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def seed(db_session, site):
    """Seed minimal data for correction tests."""
    cat = Category(name="Test Category", code="TSTCAT", is_active=True)
    db_session.add(cat)
    await db_session.flush()

    unit = Unit(name="pcs", symbol="pcs")
    db_session.add(unit)
    await db_session.flush()

    item = Item(name="Test Item", sku="TST-001", category_id=cat.id, unit_id=unit.id, is_active=True)
    db_session.add(item)
    await db_session.flush()

    subj = InventorySubject(subject_type="catalog_item", item_id=item.id)
    db_session.add(subj)
    await db_session.flush()

    bal = Balance(site_id=site.id, inventory_subject_id=subj.id, item_id=item.id, qty=Decimal("1000"))
    db_session.add(bal)
    await db_session.flush()

    return {"site_id": site.id, "item_id": item.id, "subject_id": subj.id}


TOK = lambda u: str(u.user_token)
OP_LINE = lambda item_id, qty: {"line_number": 1, "item_id": item_id, "qty": qty}


class TestCorrectionFlow:
    async def _create_op(self, client, admin_user, seed, qty=100):
        r = await client.post("/api/v1/operations", headers={"X-User-Token": TOK(admin_user)},
            json={"site_id": seed["site_id"], "operation_type": "RECEIVE", "acceptance_required": False,
                  "lines": [OP_LINE(seed["item_id"], qty)]})
        assert r.status_code == 200, f"create op: {r.text}"
        return r.json()["id"]

    async def _submit_op(self, client, admin_user, op_id):
        r = await client.post(f"/api/v1/operations/{op_id}/submit",
            headers={"X-User-Token": TOK(admin_user)}, json={"submit": True})
        assert r.status_code == 200, f"submit op: {r.text}"

    @pytest.mark.asyncio
    async def test_full_happy_path(self, client, admin_user, seed):
        op_id = await self._create_op(client, admin_user, seed, qty=100)
        await self._submit_op(client, admin_user, op_id)

        r = await client.post(f"/api/v1/operations/{op_id}/corrections", headers={"X-User-Token": TOK(admin_user)})
        assert r.status_code == 200, r.text
        corr = r.json()
        assert corr["status"] == "draft"
        assert len(corr["lines"]) == 1
        corr_id = corr["id"]
        line_uuid = corr["lines"][0]["line_uuid"]

        r = await client.put(f"/api/v1/operations/{op_id}/corrections/{corr_id}", headers={"X-User-Token": TOK(admin_user)},
            json={"expected_version": 1, "lines": [{"line_uuid": line_uuid, "line_number": 1, "item_id": seed["item_id"], "qty": 120}]})
        assert r.status_code == 200, f"PUT correction: {r.text}"

        r = await client.post(f"/api/v1/operations/{op_id}/corrections/{corr_id}/submit",
            headers={"X-User-Token": TOK(admin_user)}, json={"expected_version": 2})
        assert r.status_code == 200, f"submit correction: {r.text}"
        result = r.json()
        assert result["correction"]["status"] == "applied", f"correction not applied: {r.text}"
        assert result["operation"]["current_revision_number"] >= 1

    @pytest.mark.asyncio
    async def test_client_cannot_submit_correction_kind(self, client, admin_user, seed):
        op_id = await self._create_op(client, admin_user, seed, qty=10)
        await self._submit_op(client, admin_user, op_id)

        r = await client.post(f"/api/v1/operations/{op_id}/corrections", headers={"X-User-Token": TOK(admin_user)})
        assert r.status_code == 200
        corr_id = r.json()["id"]
        line_uuid = r.json()["lines"][0]["line_uuid"]

        r = await client.put(f"/api/v1/operations/{op_id}/corrections/{corr_id}", headers={"X-User-Token": TOK(admin_user)},
            json={"expected_version": 1, "lines": [{"line_uuid": line_uuid, "line_number": 1, "item_id": seed["item_id"], "qty": 10, "correction_kind": "unchanged"}]})
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "correction_kind_not_allowed_in_request"

    @pytest.mark.asyncio
    async def test_begin_correction_clones_baseline(self, client, admin_user, seed):
        op_id = await self._create_op(client, admin_user, seed, qty=50)
        await self._submit_op(client, admin_user, op_id)

        r = await client.post(f"/api/v1/operations/{op_id}/corrections", headers={"X-User-Token": TOK(admin_user)})
        assert r.status_code == 200, r.text
        corr = r.json()
        assert len(corr["lines"]) == 1
        assert corr["lines"][0]["qty"] == 50

    @pytest.mark.asyncio
    async def test_duplicate_line_uuid_rejected(self, client, admin_user, seed):
        op_id = await self._create_op(client, admin_user, seed, qty=10)
        await self._submit_op(client, admin_user, op_id)

        r = await client.post(f"/api/v1/operations/{op_id}/corrections", headers={"X-User-Token": TOK(admin_user)})
        assert r.status_code == 200
        corr_id = r.json()["id"]

        same_lu = str(uuid4())
        r = await client.put(f"/api/v1/operations/{op_id}/corrections/{corr_id}", headers={"X-User-Token": TOK(admin_user)},
            json={"expected_version": 1, "lines": [
                {"line_uuid": same_lu, "line_number": 1, "item_id": seed["item_id"], "qty": 10},
                {"line_uuid": same_lu, "line_number": 2, "item_id": seed["item_id"], "qty": 20},
            ]})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "correction_duplicate_line_uuid"

    @pytest.mark.asyncio
    async def test_version_conflict_rejected(self, client, admin_user, seed):
        op_id = await self._create_op(client, admin_user, seed, qty=10)
        await self._submit_op(client, admin_user, op_id)

        r = await client.post(f"/api/v1/operations/{op_id}/corrections", headers={"X-User-Token": TOK(admin_user)})
        assert r.status_code == 200
        corr_id = r.json()["id"]

        # Submit with wrong expected_version → 409
        r = await client.post(f"/api/v1/operations/{op_id}/corrections/{corr_id}/submit",
            headers={"X-User-Token": TOK(admin_user)}, json={"expected_version": 99})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "correction_version_conflict"

    @pytest.mark.asyncio
    async def test_begin_correction_reuses_baseline(self, client, admin_user, seed):
        op_id = await self._create_op(client, admin_user, seed, qty=200)
        await self._submit_op(client, admin_user, op_id)

        r = await client.post(f"/api/v1/operations/{op_id}/corrections", headers={"X-User-Token": TOK(admin_user)})
        assert r.status_code == 200
        corr = r.json()
        assert len(corr["lines"]) == 1
        assert float(corr["lines"][0]["qty"]) == 200.0
