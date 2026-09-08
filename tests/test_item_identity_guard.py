"""ADR-0033 Item Identity Guard v1 — тесты AC-1..AC-10, AC-14.

Unit/классификация + интеграция с БД через реальные точки входа:
submit-materialize, admin create/rename, review confirm, legacy approve,
read-контракты.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from app.core.db import get_db
from app.models.audit_event import AuditEvent
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation
from app.models.site import Site
from app.models.temporary_item import TemporaryItem
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from app.schemas.catalog import ItemCreateRequest, ItemUpdateRequest
from app.schemas.review_item import ReviewItemConfirmRequest
from app.services.catalog_admin_service import CatalogAdminService
from app.services.item_identity_service import ItemIdentityService
from app.services.review_items_service import ReviewItemsService
from app.services.temporary_items_resolution_service import (
    TemporaryItemsResolutionService,
)
from app.services.uow import UnitOfWork
from main import create_app

app = create_app()


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
        site = Site(code=f"ST-{suffix}", name=f"Site {suffix}")
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
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
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

        unit1 = Unit(code=f"U1-{suffix}", name=f"Штука {suffix}", symbol="шт", is_active=True)
        unit2 = Unit(code=f"U2-{suffix}", name=f"Килограмм {suffix}", symbol="кг", is_active=True)
        cat1 = Category(code=f"C1-{suffix}", name=f"Крепёж {suffix}", normalized_name=f"крепеж {suffix}", is_active=True)
        cat2 = Category(code=f"C2-{suffix}", name=f"Прочее {suffix}", normalized_name=f"прочее {suffix}", is_active=True)
        session.add_all([unit1, unit2, cat1, cat2])
        await session.flush()

        bolt = Item(
            sku=f"BOLT-{suffix}",
            name="Болт М8",
            normalized_name="болт м8",
            category_id=cat1.id,
            unit_id=unit1.id,
            is_active=True,
        )
        session.add(bolt)
        await session.flush()

        subject = InventorySubject(subject_type="catalog_item", item_id=bolt.id)
        session.add(subject)
        await session.commit()
        return {
            "suffix": suffix,
            "site_id": site.id,
            "chief_user_id": chief.id,
            "chief_token": str(chief.user_token),
            "storekeeper_token": str(storekeeper.user_token),
            "unit1_id": unit1.id,
            "unit2_id": unit2.id,
            "cat1_id": cat1.id,
            "cat2_id": cat2.id,
            "bolt_id": bolt.id,
        }


async def _create_inline_operation(
    client: AsyncClient,
    seed: dict,
    *,
    client_request_id: str,
    lines: list[dict],
) -> dict:
    resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": client_request_id,
            "lines": lines,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _inline_line(line_number: int, client_key: str, name: str, seed: dict, *, unit_id: int | None = None, category_id: int | None = None) -> dict:
    return {
        "line_number": line_number,
        "qty": 5,
        "temporary_item": {
            "client_key": client_key,
            "name": name,
            "sku": None,
            "unit_id": unit_id if unit_id is not None else seed["unit1_id"],
            "category_id": category_id if category_id is not None else seed["cat1_id"],
        },
    }


async def _submit(client: AsyncClient, seed: dict, operation_id: str):
    return await client.post(
        f"/api/v1/operations/{operation_id}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )


# ============================================================
# AC-1 / AC-14: submit EXACT-duplicate → 409 envelope, nothing created
# ============================================================


@pytest.mark.asyncio
async def test_ac1_submit_exact_duplicate_blocks_with_envelope(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    op = await _create_inline_operation(
        client,
        seed,
        client_request_id="guard-ac1",
        lines=[
            _inline_line(1, "tmp-a", "болт  м8.", seed),
            _inline_line(2, "tmp-a", "болт  м8.", seed),
        ],
    )
    line_ids = sorted(int(line["id"]) for line in op["lines"])

    submit_resp = await _submit(client, seed, op["id"])
    assert submit_resp.status_code == 409
    body = submit_resp.json()
    assert body["type"] == "urn:warehouse:problem:operation-submit-rejected"
    assert body["status"] == 409
    assert body["code"] == "operation_submit_rejected"
    assert len(body["errors"]) == 1
    err = body["errors"][0]
    assert err["code"] == "item_identity_duplicate"
    assert err["scope"] == "line_group"
    assert sorted(err["operation_line_ids"]) == line_ids
    assert err["requested_name"] == "болт  м8."
    assert err["candidates"], err
    candidate = err["candidates"][0]
    assert candidate["id"] == seed["bolt_id"]
    assert candidate["match"] == "exact"
    assert candidate["unit"]["id"] == seed["unit1_id"]
    assert candidate["category"]["id"] == seed["cat1_id"]

    async with session_factory() as session:
        # Ни один Item не создан; временный черновик не очищен; операция в draft.
        items = list((await session.execute(select(Item))).scalars().all())
        assert {item.id for item in items} == {seed["bolt_id"]}
        from uuid import UUID

        from app.models.operation import OperationLine

        operation = await session.get(Operation, UUID(op["id"]))
        assert operation is not None
        assert operation.status == "draft"
        lines_rows = list(
            (
                await session.execute(
                    select(OperationLine).where(OperationLine.operation_id == operation.id)
                )
            )
            .scalars()
            .all()
        )
        assert lines_rows
        for line_row in lines_rows:
            assert line_row.temporary_draft_payload is not None
            assert line_row.item_id is None
        # AC-14: остатки и inventory subjects не тронуты.
        subject_count = (
            await session.execute(select(func.count()).select_from(InventorySubject))
        ).scalar_one()
        assert subject_count == 1


# ============================================================
# AC-2: только PARTIAL → создан review-item + item_identity.flag
# ============================================================


@pytest.mark.asyncio
async def test_ac2_submit_partial_creates_review_item_and_flags(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    op = await _create_inline_operation(
        client,
        seed,
        client_request_id="guard-ac2",
        lines=[_inline_line(1, "tmp-p", "Болт М8", seed, category_id=seed["cat2_id"])],
    )
    with capture_logs() as logs:
        submit_resp = await _submit(client, seed, op["id"])
    assert submit_resp.status_code == 200, submit_resp.text
    review_item_id = submit_resp.json()["lines"][0]["item_id"]

    flags = [entry for entry in logs if entry.get("event") == "item_identity.flag"]
    assert flags, logs
    assert seed["bolt_id"] in flags[0]["candidate_ids"]
    assert flags[0]["created_item_id"] == review_item_id

    async with session_factory() as session:
        item = await session.get(Item, review_item_id)
        assert item is not None
        assert item.requires_review is True
        assert item.review_status == "needs_review"


# ============================================================
# AC-4: intra-batch конфликт двух client_key в одной операции
# ============================================================


@pytest.mark.asyncio
async def test_ac4_intra_batch_duplicate_blocks(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    op = await _create_inline_operation(
        client,
        seed,
        client_request_id="guard-ac4",
        lines=[
            _inline_line(1, "tmp-x", "Гайка М8", seed),
            _inline_line(2, "tmp-y", " гайка  м8 ", seed, unit_id=seed["unit2_id"]),
        ],
    )
    line_ids = sorted(int(line["id"]) for line in op["lines"])

    submit_resp = await _submit(client, seed, op["id"])
    assert submit_resp.status_code == 409
    body = submit_resp.json()
    assert body["code"] == "operation_submit_rejected"
    err = body["errors"][0]
    assert err["code"] == "item_identity_duplicate"
    assert sorted(err["operation_line_ids"]) == line_ids
    assert err["candidates"] == []
    assert "разными client_key" in body["detail"] or "client_key" in body["detail"]

    async with session_factory() as session:
        inline_items = list(
            (
                await session.execute(
                    select(Item).where(Item.normalized_name == "гайка м8")
                )
            )
            .scalars()
            .all()
        )
        assert inline_items == []


# ============================================================
# AC-5: deleted/merged не кандидаты; точное имя освобождено
# ============================================================


@pytest.mark.asyncio
async def test_ac5_deleted_and_merged_items_are_not_candidates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    async with session_factory() as session:
        uow = UnitOfWork(session)
        async with uow:
            suffix = seed["suffix"]
            deleted_item = Item(
                sku=f"DEL-{suffix}",
                name="Гвоздь 100",
                normalized_name="гвоздь 100",
                category_id=seed["cat1_id"],
                unit_id=seed["unit1_id"],
                is_active=False,
                deleted_at=datetime.now(UTC),
            )
            merged_target = Item(
                sku=f"MT-{suffix}",
                name="Метизы",
                normalized_name="метизы",
                category_id=seed["cat1_id"],
                unit_id=seed["unit1_id"],
                is_active=True,
            )
            session.add_all([deleted_item, merged_target])
            await session.flush()
            merged_source = Item(
                sku=f"MS-{suffix}",
                name="Гайка 10",
                normalized_name="гайка 10",
                category_id=seed["cat1_id"],
                unit_id=seed["unit1_id"],
                is_active=False,
                merged_into_id=merged_target.id,
            )
            session.add(merged_source)
            await session.flush()

            service = ItemIdentityService(uow)
            res_deleted = await service.find_candidates(
                "Гвоздь 100", unit_id=seed["unit1_id"], category_id=seed["cat1_id"]
            )
            assert not res_deleted.has_candidates
            res_merged = await service.find_candidates(
                "Гайка 10", unit_id=seed["unit1_id"], category_id=seed["cat1_id"]
            )
            assert not res_merged.has_candidates

            # Создание с «освобождённым» именем разрешено (admin guard не блокирует).
            created = await CatalogAdminService().create_item(
                uow,
                ItemCreateRequest(name="Гвоздь 100", unit_id=seed["unit1_id"], category_id=seed["cat1_id"]),
                created_by_user_id=seed["chief_user_id"],
            )
            assert created.id is not None


# ============================================================
# AC-6: review confirm — EXACT после коррекций → 409; PARTIAL → confirm + flag
# ============================================================


@pytest.mark.asyncio
async def test_ac6_review_confirm_exact_blocked(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    op = await _create_inline_operation(
        client,
        seed,
        client_request_id="guard-ac6",
        lines=[_inline_line(1, "tmp-c", "Кран 1\" Ду15", seed)],
    )
    submit_resp = await _submit(client, seed, op["id"])
    assert submit_resp.status_code == 200, submit_resp.text
    review_item_id = submit_resp.json()["lines"][0]["item_id"]

    # Активный не-review товар с тем же нормализованным именем, unit, category.
    async with session_factory() as session:
        uow = UnitOfWork(session)
        async with uow:
            twin = await CatalogAdminService().create_item(
                uow,
                ItemCreateRequest(
                    name="Кран 1 Ду15",
                    sku=None,
                    unit_id=seed["unit1_id"],
                    category_id=seed["cat1_id"],
                ),
                created_by_user_id=seed["chief_user_id"],
            )
            twin_id = twin.id

    confirm_resp = await client.post(
        f"/api/v1/review-items/{review_item_id}/confirm",
        headers={"X-User-Token": seed["chief_token"]},
        json={},
    )
    assert confirm_resp.status_code == 409, confirm_resp.text
    detail = confirm_resp.json()["detail"]
    assert detail["code"] == "item_identity_duplicate"
    assert "merge" in detail["message"]
    assert twin_id in [candidate["id"] for candidate in detail["candidates"]]
    assert any(candidate["match"] == "exact" for candidate in detail["candidates"])

    async with session_factory() as session:
        item = await session.get(Item, review_item_id)
        assert item is not None
        assert item.review_status == "needs_review"
        assert item.requires_review is True


@pytest.mark.asyncio
async def test_ac6_review_confirm_partial_flags_audit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    async with session_factory() as session:
        uow = UnitOfWork(session)
        async with uow:
            suffix = seed["suffix"]
            inactive_twin = Item(
                sku=f"IN-{suffix}",
                name="Фланец Ду50",
                normalized_name="фланец ду50",
                category_id=seed["cat1_id"],
                unit_id=seed["unit1_id"],
                is_active=False,
            )
            session.add(inactive_twin)
            await session.flush()

            review_item = Item(
                sku=f"RV-{suffix}",
                name="Фланец Ду50",
                normalized_name="фланец ду50",
                category_id=seed["cat1_id"],
                unit_id=seed["unit1_id"],
                is_active=True,
                requires_review=True,
                review_status="needs_review",
            )
            session.add(review_item)
            await session.flush()
            review_item_id = review_item.id
            inactive_id = inactive_twin.id

        with capture_logs() as logs:
            async with uow:
                await ReviewItemsService.confirm_review_item(
                    uow,
                    item_id=review_item_id,
                    resolved_by_user_id=seed["chief_user_id"],
                    payload=ReviewItemConfirmRequest(),
                )
        flags = [entry for entry in logs if entry.get("event") == "item_identity.flag"]
        assert flags and inactive_id in flags[0]["candidate_ids"]

        async with session_factory() as session:
            event = (
                await session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.event_type == "review_item.confirm")
                    .order_by(AuditEvent.id.desc())
                )
            ).scalars().first()
            assert event is not None
            assert isinstance(event.changes, dict)
            assert event.changes["identity_candidates"], event.changes
            assert event.changes["identity_candidates"][0]["id"] == inactive_id


# ============================================================
# AC-7: admin create/rename
# ============================================================


@pytest.mark.asyncio
async def test_ac7_admin_create_exact_blocked_sku_still_works(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    resp = await client.post(
        "/api/v1/catalog/admin/items",
        headers={"X-User-Token": seed["chief_token"]},
        json={"name": "болт м8", "unit_id": seed["unit1_id"], "category_id": seed["cat1_id"]},
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "item_identity_duplicate"
    assert detail["candidates"][0]["id"] == seed["bolt_id"]
    assert detail["candidates"][0]["match"] == "exact"

    # SKU-конфликт продолжает работать как раньше.
    resp_sku = await client.post(
        "/api/v1/catalog/admin/items",
        headers={"X-User-Token": seed["chief_token"]},
        json={
            "name": f"Уникальное {seed['suffix']}",
            "sku": f"BOLT-{seed['suffix']}",
            "unit_id": seed["unit1_id"],
            "category_id": seed["cat1_id"],
        },
    )
    assert resp_sku.status_code == 409
    assert resp_sku.json()["detail"] == "item sku already exists"

    # PARTIAL (другая категория) — создан с флагом в audit changes item.create.
    resp_partial = await client.post(
        "/api/v1/catalog/admin/items",
        headers={"X-User-Token": seed["chief_token"]},
        json={"name": "Болт М8", "unit_id": seed["unit1_id"], "category_id": seed["cat2_id"]},
    )
    assert resp_partial.status_code == 200, resp_partial.text
    partial_item_id = resp_partial.json()["id"]
    async with session_factory() as session:
        event = (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.event_type == "item.create")
                .order_by(AuditEvent.id.desc())
            )
        ).scalars().first()
        assert event is not None
        assert event.changes["identity_candidates"][0]["id"] == seed["bolt_id"]
        assert event.changes["identity_candidates"][0]["match"] == "partial"
    assert partial_item_id


@pytest.mark.asyncio
async def test_ac7_admin_rename_exact_blocked_self_name_ok(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    async with session_factory() as session:
        uow = UnitOfWork(session)
        async with uow:
            other = await CatalogAdminService().create_item(
                uow,
                ItemCreateRequest(
                    name=f"Шпилька {seed['suffix']}",
                    unit_id=seed["unit1_id"],
                    category_id=seed["cat1_id"],
                ),
                created_by_user_id=seed["chief_user_id"],
            )
            other_id = other.id

    resp = await client.patch(
        f"/api/v1/catalog/admin/items/{other_id}",
        headers={"X-User-Token": seed["chief_token"]},
        json={"name": "Болт М8"},
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "item_identity_duplicate"
    assert detail["candidates"][0]["id"] == seed["bolt_id"]

    # Переименование в собственное имя — self-exclusion работает.
    resp_self = await client.patch(
        f"/api/v1/catalog/admin/items/{other_id}",
        headers={"X-User-Token": seed["chief_token"]},
        json={"name": f"Шпилька {seed['suffix']}"},
    )
    assert resp_self.status_code == 200, resp_self.text


# ============================================================
# AC-8: legacy approve_as_item — flag-only, без блокировки
# ============================================================


@pytest.mark.asyncio
async def test_ac8_legacy_approve_flag_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    async with session_factory() as session:
        uow = UnitOfWork(session)
        async with uow:
            suffix = seed["suffix"]
            backing = Item(
                sku=f"BK-{suffix}",
                name="Переходник 3/4",
                normalized_name="переходник 3/4",
                category_id=seed["cat1_id"],
                unit_id=seed["unit1_id"],
                is_active=False,
            )
            session.add(backing)
            await session.flush()
            temp = TemporaryItem(
                item_id=backing.id,
                name="Переходник 3/4",
                normalized_name="переходник 3/4",
                unit_id=seed["unit1_id"],
                category_id=seed["cat1_id"],
                status="active",
                created_by_user_id=seed["chief_user_id"],
            )
            session.add(temp)
            await session.flush()
            subject = InventorySubject(
                subject_type="temporary_item", temporary_item_id=temp.id
            )
            session.add(subject)
            temp_id = temp.id
            backing_id = backing.id
            bolt_id = seed["bolt_id"]

        # EXACT-кандидат: «Болт М8» с тем же именем, что у temp — не дубль;
        # сделаем дубль: активный товар «Переходник 3/4».
        async with session_factory() as session:
            uow = UnitOfWork(session)
            async with uow:
                twin = Item(
                    sku=f"TW-{seed['suffix']}",
                    name="Переходник 3/4",
                    normalized_name="переходник 3/4",
                    category_id=seed["cat1_id"],
                    unit_id=seed["unit1_id"],
                    is_active=True,
                )
                session.add(twin)
                await session.flush()
                twin_id = twin.id

        with capture_logs() as logs:
            async with uow:
                result = await TemporaryItemsResolutionService.approve_as_item(
                    uow,
                    temporary_item_id=temp_id,
                    resolved_by_user_id=seed["chief_user_id"],
                )
        assert result["resolution_type"] == "approve_as_item"
        flags = [entry for entry in logs if entry.get("event") == "item_identity.flag"]
        assert flags, [entry.get("event") for entry in logs]
        assert flags[0]["entry_point"] == "legacy_approve_as_item"
        candidate_ids = flags[0]["candidate_ids"]
        assert twin_id in candidate_ids
        assert backing_id not in candidate_ids
        assert result["resolved_item_id"] not in candidate_ids


# ============================================================
# AC-9: read-эндпоинт identity-candidates
# ============================================================


@pytest.mark.asyncio
async def test_ac9_identity_candidates_endpoint_tiers(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    headers = {"X-User-Token": seed["chief_token"]}

    resp = await client.get(
        "/api/v1/catalog/items/identity-candidates",
        params={"name": "болт м8", "unit_id": seed["unit1_id"], "category_id": seed["cat1_id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    candidates = resp.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["id"] == seed["bolt_id"]
    assert candidates[0]["match"] == "exact"
    assert candidates[0]["unit"]["symbol"] == "шт"
    assert candidates[0]["category"]["name"].startswith("Крепёж")
    assert candidates[0]["is_active"] is True
    assert candidates[0]["requires_review"] is False

    # unit_id не передан → tier понижен до partial.
    resp_no_unit = await client.get(
        "/api/v1/catalog/items/identity-candidates",
        params={"name": "Болт М8", "category_id": seed["cat1_id"]},
        headers=headers,
    )
    assert resp_no_unit.status_code == 200
    assert resp_no_unit.json()["candidates"][0]["match"] == "partial"

    # category не та → partial.
    resp_wrong_cat = await client.get(
        "/api/v1/catalog/items/identity-candidates",
        params={"name": "Болт М8", "unit_id": seed["unit1_id"], "category_id": seed["cat2_id"]},
        headers=headers,
    )
    assert resp_wrong_cat.json()["candidates"][0]["match"] == "partial"

    # whitespace-only name → 200 [] (без 422).
    resp_blank = await client.get(
        "/api/v1/catalog/items/identity-candidates",
        params={"name": "   "},
        headers=headers,
    )
    assert resp_blank.status_code == 200
    assert resp_blank.json() == {"candidates": []}

    # Нет авторизации → штатный 401.
    resp_anon = await client.get(
        "/api/v1/catalog/items/identity-candidates",
        params={"name": "Болт М8"},
    )
    assert resp_anon.status_code == 401


# ============================================================
# AC-10: review detail содержит identity_candidates (self-excluded)
# ============================================================


@pytest.mark.asyncio
async def test_ac10_review_detail_has_identity_candidates(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    op = await _create_inline_operation(
        client,
        seed,
        client_request_id="guard-ac10",
        lines=[_inline_line(1, "tmp-d", "Болт М8", seed, category_id=seed["cat2_id"])],
    )
    submit_resp = await _submit(client, seed, op["id"])
    assert submit_resp.status_code == 200, submit_resp.text
    review_item_id = submit_resp.json()["lines"][0]["item_id"]

    detail_resp = await client.get(
        f"/api/v1/review-items/{review_item_id}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()
    assert "identity_candidates" in detail
    candidate_ids = [candidate["id"] for candidate in detail["identity_candidates"]]
    assert review_item_id not in candidate_ids
    assert seed["bolt_id"] in candidate_ids
    # Совпадение по имени, category отличается → tier partial.
    exact = [
        candidate
        for candidate in detail["identity_candidates"]
        if candidate["id"] == seed["bolt_id"]
    ]
    assert exact[0]["match"] == "partial"


# ============================================================
# Unit: классификация и name→None
# ============================================================


@pytest.mark.asyncio
async def test_item_identity_service_classification_rules(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)
    async with session_factory() as session:
        uow = UnitOfWork(session)
        async with uow:
            service = ItemIdentityService(uow)

            # Пустое имя → None-normalized, кандидатов нет.
            empty = await service.find_candidates("  ...  ")
            assert empty.normalized_name is None
            assert not empty.has_candidates

            result = await service.find_candidates(
                "болт м8", unit_id=seed["unit1_id"], category_id=seed["cat1_id"]
            )
            assert [c.item_id for c in result.exact] == [seed["bolt_id"]]
            assert result.partial == []

            # Кандидат-review-item с таким же именем → partial.
            suffix = seed["suffix"]
            review_twin = Item(
                sku=f"RVT-{suffix}",
                name="Болт М8",
                normalized_name="болт м8",
                category_id=seed["cat1_id"],
                unit_id=seed["unit1_id"],
                is_active=True,
                requires_review=True,
                review_status="needs_review",
            )
            session.add(review_twin)
            await session.flush()
            result2 = await service.find_candidates(
                "Болт М8", unit_id=seed["unit1_id"], category_id=seed["cat1_id"]
            )
            assert len(result2.exact) == 1
            assert len(result2.partial) == 1
            assert result2.partial[0].item_id == review_twin.id

            # self-exclusion
            result3 = await service.find_candidates(
                "Болт М8",
                unit_id=seed["unit1_id"],
                category_id=seed["cat1_id"],
                exclude_item_id=seed["bolt_id"],
            )
            assert [c.item_id for c in result3.candidates] == [review_twin.id]
            assert result3.exact == []
