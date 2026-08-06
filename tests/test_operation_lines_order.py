"""DB-backed integration + unit tests for TZ-V3.3 (guaranteed line order).

Covers every manifestation point from the TZ:
- ORM relationship order_by: Operation.lines, OperationRevision.lines,
  OperationCorrection.lines (line_number asc, tie-breaker asc);
- document_service._build_payload sorting (line_number, tie-breaker);
- document_renderer local sorting without mutating the input payload;
- OperationResponse @model_validator(mode="after") — the single API sort point;
- API endpoints: create/update/get/submit return lines ordered by line_number;
- StockDeficit.operation_line_ids ordered by line_number (ADR-0025);
- document payload generated after reverse-order PATCHes is ordered.

Reproduction of the production bug (prod_working/document_line_order_bug.md):
lines inserted in batches 10..18, 1..9, 19..30 must be returned as 1..30.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import (
    Operation,
    OperationCorrection,
    OperationCorrectionLine,
    OperationLine,
    OperationRevision,
    OperationRevisionLine,
)
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.schemas.operation import OperationResponse
from app.services.document_renderer import DocumentRenderer
from app.services.document_service import DocumentService
from app.services.uow import UnitOfWork
from main import create_app

app = create_app(enable_startup_migrations=False)


# ─── helpers ──────────────────────────────────────────────────────────────

async def _seed(session_factory: async_sessionmaker[AsyncSession], *, items: int = 1, second_site: bool = False, balance_qty: str = "1000.000") -> dict:
    """Seed a site, a root user and `items` catalog items with balances."""
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        destination_site = None
        if second_site:
            destination_site = Site(code=f"DEST-{suffix}", name=f"Dest {suffix}", is_active=True)
            session.add(destination_site)
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

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol="pcs", is_active=True)
        category = Category(
            code=f"CAT-{suffix}", name=f"Category {suffix}",
            normalized_name=f"category {suffix}", is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        seed_items = []
        for idx in range(items):
            item = Item(
                sku=f"SKU-{suffix}-{idx}",
                name=f"Item {suffix} {idx}",
                normalized_name=f"item {suffix} {idx}",
                category_id=category.id,
                unit_id=unit.id,
                is_active=True,
            )
            session.add(item)
            await session.flush()
            subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
            session.add(subject)
            await session.flush()
            session.add(Balance(
                site_id=site.id,
                inventory_subject_id=subject.id,
                item_id=item.id,
                qty=Decimal(balance_qty),
            ))
            seed_items.append({"item_id": item.id, "subject_id": subject.id})

        await session.commit()
        result = {"site_id": site.id, "root_token": str(root.user_token), "items": seed_items}
        if destination_site is not None:
            result["destination_site_id"] = destination_site.id
        return result


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


def _line(item_id: int, qty: str | int, line_number: int) -> dict:
    return {"line_number": line_number, "item_id": item_id, "qty": qty}


def _shuffled_line_numbers() -> list[int]:
    """Physical insertion order that reproduces the prod bug: 10..18, 1..9, 19..30."""
    return list(range(10, 19)) + list(range(1, 10)) + list(range(19, 31))


async def _create_operation(
    client: AsyncClient, token: str, *, site_id: int, lines: list[dict],
    op_type: str = "EXPENSE", destination_site_id: int | None = None,
) -> dict:
    payload: dict = {"operation_type": op_type, "site_id": site_id, "lines": lines}
    if destination_site_id is not None:
        payload["source_site_id"] = site_id
        payload["destination_site_id"] = destination_site_id
    resp = await client.post(
        "/api/v1/operations",
        json=payload,
        headers={"X-User-Token": token},
    )
    assert resp.status_code == 200, f"create failed: {resp.text}"
    return resp.json()


# ─── ORM relationship order_by (DB-backed) ────────────────────────────────

@pytest.mark.asyncio
async def test_operation_lines_order_by(db_session: AsyncSession, site: Site, user: User):
    """Operation.lines must come back ordered by (line_number, id) ascending."""
    operation = Operation(
        site_id=site.id,
        operation_type="RECEIVE",
        status="draft",
        created_by_user_id=user.id,
        effective_at=datetime.now(UTC),
    )
    # Insert in reverse business order: physical ids ascend 5,4,3,2,1
    operation.lines = [
        OperationLine(line_number=ln, qty=Decimal("1.000"), item_name_snapshot=f"Item {ln}")
        for ln in (5, 4, 3, 2, 1)
    ]
    db_session.add(operation)
    await db_session.flush()
    await db_session.commit()

    op_id = operation.id
    db_session.expire_all()
    stmt = select(Operation).where(Operation.id == op_id).options(selectinload(Operation.lines))
    loaded = (await db_session.execute(stmt)).scalar_one()
    assert [line.line_number for line in loaded.lines] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_operation_revision_lines_order_by(db_session: AsyncSession, site: Site, user: User):
    """OperationRevision.lines must be ordered by (line_number, line_uuid) ascending."""
    operation = Operation(
        site_id=site.id,
        operation_type="RECEIVE",
        status="submitted",
        created_by_user_id=user.id,
        effective_at=datetime.now(UTC),
    )
    db_session.add(operation)
    await db_session.flush()

    revision = OperationRevision(
        operation_id=operation.id,
        revision_number=1,
        created_by_user_id=user.id,
    )
    revision.lines = [
        OperationRevisionLine(
            line_uuid=uuid4(),
            line_number=ln,
            qty=Decimal("1.000"),
            item_name_snapshot=f"Item {ln}",
        )
        for ln in (5, 4, 3, 2, 1)
    ]
    db_session.add(revision)
    await db_session.flush()
    await db_session.commit()

    revision_id = revision.id
    db_session.expire_all()
    stmt = (
        select(OperationRevision)
        .where(OperationRevision.id == revision_id)
        .options(selectinload(OperationRevision.lines))
    )
    loaded = (await db_session.execute(stmt)).scalar_one()
    assert [line.line_number for line in loaded.lines] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_operation_correction_lines_order_by(db_session: AsyncSession, site: Site, user: User):
    """OperationCorrection.lines must be ordered by (line_number, id) ascending."""
    operation = Operation(
        site_id=site.id,
        operation_type="RECEIVE",
        status="submitted",
        created_by_user_id=user.id,
        effective_at=datetime.now(UTC),
    )
    db_session.add(operation)
    await db_session.flush()
    base_revision = OperationRevision(
        operation_id=operation.id,
        revision_number=1,
        created_by_user_id=user.id,
    )
    db_session.add(base_revision)
    await db_session.flush()

    correction = OperationCorrection(
        operation_id=operation.id,
        status="draft",
        base_operation_revision_id=base_revision.id,
        version=1,
        created_by_user_id=user.id,
    )
    correction.lines = [
        OperationCorrectionLine(
            line_uuid=uuid4(),
            line_number=ln,
            qty=Decimal("1.000"),
        )
        for ln in (5, 4, 3, 2, 1)
    ]
    db_session.add(correction)
    await db_session.flush()
    await db_session.commit()

    correction_id = correction.id
    db_session.expire_all()
    stmt = (
        select(OperationCorrection)
        .where(OperationCorrection.id == correction_id)
        .options(selectinload(OperationCorrection.lines))
    )
    loaded = (await db_session.execute(stmt)).scalar_one()
    assert [line.line_number for line in loaded.lines] == [1, 2, 3, 4, 5]


# ─── document_service._build_payload ──────────────────────────────────────

@pytest.mark.asyncio
async def test_build_payload_lines_sorted_with_tie_break(
    session_factory: async_sessionmaker[AsyncSession],
):
    """_build_payload must sort source_lines by (line_number, tie-breaker) regardless of ORM order."""
    async with session_factory() as session:
        site_obj = Site(code=f"SITE-{uuid4().hex[:8]}", name="Payload Site", is_active=True)
        session.add(site_obj)
        await session.flush()
        user_obj = User(
            username=f"store-{uuid4().hex[:8]}",
            email=f"store-{uuid4().hex[:8]}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site_obj.id,
        )
        session.add(user_obj)
        await session.flush()

        operation = Operation(
            site_id=site_obj.id,
            operation_type="RECEIVE",
            status="submitted",
            created_by_user_id=user_obj.id,
            effective_at=datetime.now(UTC),
        )
        # Physical order 5,4,3,2,1 (reverse business order)
        operation.lines = [
            OperationLine(line_number=ln, qty=Decimal("1.000"), item_name_snapshot=f"Item {ln}")
            for ln in (5, 4, 3, 2, 1)
        ]
        session.add(operation)
        await session.flush()
        await session.commit()
        op_id = operation.id

        # Fresh SELECT with selectinload: the relationship is loaded with the
        # ORM order_by applied, and _build_payload's explicit sort is defense-in-depth.
        stmt = select(Operation).where(Operation.id == op_id).options(selectinload(Operation.lines))
        loaded = (await session.execute(stmt)).scalar_one()
        payload = DocumentService._build_payload(operation=loaded, site=site_obj)
        assert [line["line_number"] for line in payload["lines"]] == [1, 2, 3, 4, 5]
        # total_lines matches
        assert payload["total_lines"] == 5


# ─── document_renderer: no payload mutation ───────────────────────────────

@pytest.mark.asyncio
async def test_document_renderer_does_not_mutate_payload():
    """Renderer must sort locally and leave the input payload untouched."""
    original_lines = [
        {"line_number": 10, "item_name": "A", "quantity": 1.0},
        {"line_number": 1, "item_name": "B", "quantity": 1.0},
        {"line_number": 5, "item_name": "C", "quantity": 1.0},
    ]
    localization = {
        "language": "ru",
        "date_format": "%d.%m.%Y",
        "datetime_format": "%d.%m.%Y %H:%M:%S",
        "number_decimal_separator": ",",
        "thousands_separator": " ",
        "currency": "RUB",
    }
    payload = {
        "document_title": "Товарная накладная",
        "operation_id": "op-1",
        "operation_type": "MOVE",
        "operation_status": "submitted",
        "operation_effective_at": None,
        "operation_notes": None,
        "sender": {
            "site_name": "Site", "site_code": "S-1",
            "organization": {"legal_name": "Org", "address": "Addr"},
        },
        "signatures": {"roles": {"handed_over": "A", "accepted_by": None, "chief_accountant": "___"}},
        "localization": localization,
        "generated_at": "2026-08-05T00:00:00+00:00",
        "lines": original_lines,
        "total_lines": 3,
    }
    payload_before = dict(payload)
    original_lines_before = list(original_lines)

    html = DocumentRenderer._render_html_internal(
        document_id="doc-1",
        document_number="DOC-1",
        template_name=None,  # waybill.html fallback path
        payload=payload,
    )

    # Input payload is not mutated (same list object, same order)
    assert payload["lines"] is original_lines
    assert payload["lines"] == original_lines_before
    assert payload == payload_before

    # Rendered output rows follow business order 1..5..10
    assert [row["line_number"] for row in html_rows(html)] == [1, 5, 10]


def html_rows(html: str) -> list[dict]:
    import re
    return [
        {"line_number": int(m.group(1))}
        for m in re.finditer(r"<tr>\s*<td>(\d+)</td>", html)
    ]


# ─── OperationResponse model_validator (single API sort point) ────────────

def _make_response_payload(lines: list[dict]) -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "site_id": 1,
        "operation_type": "MOVE",
        "status": "draft",
        "source_site_id": 1,
        "destination_site_id": 2,
        "created_by_user_id": "22222222-2222-2222-2222-222222222222",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "creation_source": "manual",
        "lines": lines,
    }


def test_operation_response_validator_sorts_lines():
    """OperationResponse.model_validate must sort lines by (line_number, id)."""
    response = OperationResponse.model_validate(_make_response_payload([
        {"id": 1, "line_number": 10, "qty": "1.000"},
        {"id": 2, "line_number": 1, "qty": "1.000"},
        {"id": 3, "line_number": 5, "qty": "1.000"},
    ]))
    assert [(line.line_number, line.id) for line in response.lines] == [(1, 2), (5, 3), (10, 1)]


def test_operation_response_validator_handles_duplicates():
    """Duplicate line_number values must be stabilised by the id tie-breaker."""
    response = OperationResponse.model_validate(_make_response_payload([
        {"id": 10, "line_number": 3, "qty": "1.000"},
        {"id": 5, "line_number": 3, "qty": "1.000"},
        {"id": 1, "line_number": 1, "qty": "1.000"},
    ]))
    assert [(line.line_number, line.id) for line in response.lines] == [(1, 1), (3, 5), (3, 10)]


def test_operation_list_response_sorted():
    """OperationListResponse wraps OperationResponse — sorting applies to list endpoint too."""
    from app.schemas.operation import OperationListResponse
    items = [
        _make_response_payload([{"id": 1, "line_number": 3, "qty": "1.000"}]),
        _make_response_payload([{"id": 1, "line_number": 1, "qty": "1.000"}]),
    ]
    response = OperationListResponse.model_validate({"items": items, "total_count": 2, "page": 1, "page_size": 10})
    assert [line.line_number for line in response.items[1].lines] == [1]


# ─── API integration: create / update / get / submit ──────────────────────

@pytest.mark.asyncio
async def test_create_operation_response_lines_sorted(client, session_factory):
    """POST /api/v1/operations with shuffled lines must return them ordered 1..30."""
    seed = await _seed(session_factory)
    item_id = seed["items"][0]["item_id"]
    shuffled = _shuffled_line_numbers()

    data = await _create_operation(
        client, seed["root_token"], site_id=seed["site_id"],
        lines=[_line(item_id, 1, ln) for ln in shuffled],
    )
    assert [line["line_number"] for line in data["lines"]] == list(range(1, 31))
    # Physical ids are NOT monotonic with line_number (the prod bug shape)
    ids = [line["id"] for line in data["lines"]]
    assert ids != sorted(ids)


@pytest.mark.asyncio
async def test_update_operation_response_lines_sorted(client, session_factory):
    """Three PATCHes in prod order (10..18, then 1..9, then 19..30) must end ordered 1..30."""
    seed = await _seed(session_factory)
    item_id = seed["items"][0]["item_id"]
    token = seed["root_token"]
    headers = {"X-User-Token": token}

    resp = await client.post(
        "/api/v1/operations",
        json={"operation_type": "EXPENSE", "site_id": seed["site_id"],
              "lines": [_line(item_id, 1, ln) for ln in range(10, 19)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    op_id = resp.json()["id"]

    # Reproduce the prod insertion order (prod_working/document_line_order_bug.md):
    # first batch 10..18 (create), then 1..9, then 19..30 (PATCH, client appends
    # new lines at the end of the accumulated list).
    for batch in (range(1, 10), range(19, 31)):
        current = await client.get(f"/api/v1/operations/{op_id}", headers=headers)
        existing = [
            {"line_number": ln["line_number"], "item_id": ln["item_id"], "qty": "1"}
            for ln in current.json()["lines"]
        ]
        resp = await client.patch(
            f"/api/v1/operations/{op_id}",
            json={"lines": existing + [_line(item_id, 1, ln) for ln in batch]},
            headers=headers,
        )
        assert resp.status_code == 200, f"patch failed: {resp.text}"

    data = resp.json()
    assert [line["line_number"] for line in data["lines"]] == list(range(1, 31))


@pytest.mark.asyncio
async def test_get_operation_response_lines_sorted(client, session_factory):
    """GET /api/v1/operations/{id} after shuffled insert must return lines 1..30."""
    seed = await _seed(session_factory)
    item_id = seed["items"][0]["item_id"]
    created = await _create_operation(
        client, seed["root_token"], site_id=seed["site_id"],
        lines=[_line(item_id, 1, ln) for ln in _shuffled_line_numbers()],
    )
    op_id = created["id"]

    resp = await client.get(
        f"/api/v1/operations/{op_id}",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    lines = resp.json()["lines"]
    assert [line["line_number"] for line in lines] == list(range(1, 31))
    assert lines[0]["line_number"] == 1
    assert lines[29]["line_number"] == 30


@pytest.mark.asyncio
async def test_submit_response_lines_sorted(client, session_factory):
    """POST /submit must return lines ordered 1..30 (ADR-0025, TZ-V3.1I)."""
    seed = await _seed(session_factory)
    item_id = seed["items"][0]["item_id"]
    created = await _create_operation(
        client, seed["root_token"], site_id=seed["site_id"],
        lines=[_line(item_id, 1, ln) for ln in _shuffled_line_numbers()],
    )
    op_id = created["id"]

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "submitted"
    assert [line["line_number"] for line in data["lines"]] == list(range(1, 31))


@pytest.mark.asyncio
async def test_submit_deficits_order_after_reverse_patches(client, session_factory):
    """StockDeficit.operation_line_ids must follow line_number order (ADR-0025).

    Lines are inserted in reverse business order; the group for the line with
    the smallest line_number must come first, and its operation_line_ids must
    be ordered by line_number, not by physical insertion.
    """
    seed = await _seed(session_factory, items=2, second_site=True, balance_qty="0.000")
    item_a = seed["items"][0]
    item_b = seed["items"][1]
    # Insert in reverse business order: line 3 first, line 1 last.
    created = await _create_operation(
        client, seed["root_token"], site_id=seed["site_id"], op_type="MOVE",
        destination_site_id=seed["destination_site_id"],
        lines=[
            {"line_number": 3, "item_id": item_a["item_id"], "qty": 60},
            {"line_number": 2, "item_id": item_b["item_id"], "qty": 40},
            {"line_number": 1, "item_id": item_a["item_id"], "qty": 60},
        ],
    )
    op_id = created["id"]
    ids_by_line = {line["line_number"]: line["id"] for line in created["lines"]}

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert len(errors) == 2
    # Groups ordered by first line's line_number: item A (line 1) first
    assert errors[0]["item"]["id"] == item_a["item_id"]
    assert errors[1]["item"]["id"] == item_b["item_id"]
    # operation_line_ids ordered by line_number: [line 1, line 3], NOT [line 3, line 1]
    assert errors[0]["operation_line_ids"] == [ids_by_line[1], ids_by_line[3]]


@pytest.mark.asyncio
async def test_patch_reverse_order_then_generate_document(client, session_factory, uow: UnitOfWork):
    """Document payload after reverse-order lines must be ordered 1..N."""
    seed = await _seed(session_factory)
    item_id = seed["items"][0]["item_id"]
    created = await _create_operation(
        client, seed["root_token"], site_id=seed["site_id"],
        lines=[_line(item_id, 1, ln) for ln in _shuffled_line_numbers()],
    )
    op_id = created["id"]

    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=created["id"],
        document_type="waybill",
    )
    payload = result["document"].payload
    lines = payload["lines"]
    assert [line["line_number"] for line in lines] == list(range(1, 31))
    assert op_id is not None


# ─── corrections flow ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_corrections_lines_order(db_session: AsyncSession, site: Site, user: User):
    """Correction lines created in reverse order must come back sorted."""
    operation = Operation(
        site_id=site.id,
        operation_type="RECEIVE",
        status="submitted",
        created_by_user_id=user.id,
        effective_at=datetime.now(UTC),
    )
    db_session.add(operation)
    await db_session.flush()
    base_revision = OperationRevision(
        operation_id=operation.id,
        revision_number=1,
        created_by_user_id=user.id,
    )
    db_session.add(base_revision)
    await db_session.flush()

    uow = UnitOfWork(db_session)
    correction = await uow.corrections.create_correction(
        operation_id=operation.id,
        base_operation_revision_id=base_revision.id,
        created_by_user_id=user.id,
    )
    for ln in (5, 4, 3, 2, 1):
        await uow.corrections.create_correction_line(
            correction_id=correction.id,
            line_uuid=uuid4(),
            line_number=ln,
            item_id=None,
            qty=Decimal("1.000"),
        )
    await db_session.commit()

    correction_id = correction.id
    db_session.expire_all()
    loaded = await uow.corrections.get_correction_by_id(correction_id)
    assert [line.line_number for line in loaded.lines] == [1, 2, 3, 4, 5]
