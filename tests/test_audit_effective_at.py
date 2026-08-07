"""A-5 / ADR-0028 §5 focused tests: `effective_at` on audit_item_effects.

Covers the producer contract of `OperationsService._write_captured_effects`
(per-row cause timestamp vs batch-level `effective_at`) without touching the
shared DB, the model metadata contract, the static contract of the migration
module (no migration execution), and DB-backed producer round-trips asserting
each A-5 producer writes the correct cause timestamp:

* submit effect → ``Operation.effective_at``
* cancel reversal → ``Operation.cancelled_at``
* acceptance / lost resolution → ``OperationAcceptanceAction.performed_at``
* correction → explicit apply timestamp (captured at ``apply_correction`` time)

`asyncio_mode = auto` (pytest.ini): async tests run without an explicit
marker, sync metadata tests stay plain.
"""
from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.models.audit_event import AuditEvent
from app.models.audit_item_effect import AuditItemEffect
from app.models.unit import Unit as UnitModel
from app.schemas.catalog import ItemCreateRequest
from app.schemas.operation import (
    OperationCreate,
    OperationLineCreate,
)
from app.services.catalog_admin_service import CatalogAdminService
from app.services.operations_service import OperationsService


# ---------------------------------------------------------------------------
# Fake UoW helpers (no DB, no shared state)
# ---------------------------------------------------------------------------


def _fake_uow(insert_effect_mock: AsyncMock) -> object:
    """UoW stand-in exposing `audit_events.insert_effect` only.

    `inventory_subjects = None` skips best-effort snapshot enrichment
    (the same contract the existing A-4.7 test relies on).
    """

    class _Repo:
        insert_effect = insert_effect_mock

    class _FakeUow:
        audit_events = _Repo()
        inventory_subjects = None

    return _FakeUow()


def _capture_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "site_id": 1,
        "inventory_subject_id": 1,
        "quantity_before": Decimal("0"),
        "quantity_delta": Decimal("1"),
        "quantity_after": Decimal("1"),
        "effect_type": "acceptance",
        "operation_line_id": 1,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Producer contract: _write_captured_effects timestamp precedence
# ---------------------------------------------------------------------------


async def test_per_row_cause_timestamp_becomes_effective_at() -> None:
    """Per-row `cause_timestamp` (and `effective_at`) win over batch arg."""
    insert_mock = AsyncMock()
    uow = _fake_uow(insert_mock)
    batch_ts = datetime(2025, 8, 1, 8, 0, 0, tzinfo=UTC)
    cause_ts = datetime(2025, 7, 15, 10, 30, 0, tzinfo=UTC)
    key_ts = datetime(2025, 7, 16, 11, 45, 0, tzinfo=UTC)
    capture = [
        _capture_row(cause_timestamp=cause_ts),
        _capture_row(effective_at=key_ts),
    ]

    await OperationsService._write_captured_effects(
        uow,
        capture=capture,
        audit_event_id=999,
        operation_id=uuid4(),
        is_system_generated=False,
        effective_at=batch_ts,
    )

    insert_mock.assert_awaited()
    assert insert_mock.await_count == 2
    effects = [call.args[0] for call in insert_mock.await_args_list]
    assert all(isinstance(e, AuditItemEffect) for e in effects)
    assert effects[0].effective_at == cause_ts
    assert effects[1].effective_at == key_ts


async def test_batch_effective_at_used_when_per_row_cause_missing() -> None:
    """Explicit `effective_at` arg fills rows without their own timestamp."""
    insert_mock = AsyncMock()
    uow = _fake_uow(insert_mock)
    batch_ts = datetime(2025, 8, 1, 8, 0, 0, tzinfo=UTC)
    capture = [_capture_row()]

    await OperationsService._write_captured_effects(
        uow,
        capture=capture,
        audit_event_id=999,
        operation_id=uuid4(),
        is_system_generated=False,
        effective_at=batch_ts,
    )

    insert_mock.assert_awaited_once()
    effect = insert_mock.await_args.args[0]
    assert isinstance(effect, AuditItemEffect)
    assert effect.effective_at == batch_ts


async def test_utc_now_safety_net_when_no_timestamp_anywhere() -> None:
    """Missing row and batch timestamps fall back to `now(UTC)` (never NULL)."""
    insert_mock = AsyncMock()
    uow = _fake_uow(insert_mock)
    before = datetime.now(UTC)

    await OperationsService._write_captured_effects(
        uow,
        capture=[_capture_row()],
        audit_event_id=999,
        operation_id=uuid4(),
        is_system_generated=False,
    )

    insert_mock.assert_awaited_once()
    effect = insert_mock.await_args.args[0]
    assert isinstance(effect, AuditItemEffect)
    assert effect.effective_at is not None
    assert effect.effective_at >= before
    assert effect.effective_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Model metadata contract
# ---------------------------------------------------------------------------


def test_effective_at_model_metadata() -> None:
    """effective_at: non-null, server_default present, index exists."""
    col = AuditItemEffect.__table__.columns["effective_at"]
    assert col.nullable is False
    assert col.server_default is not None

    index_names = {ix.name for ix in AuditItemEffect.__table__.indexes}
    assert "ix_audit_item_effects_effective_at" in index_names


# ---------------------------------------------------------------------------
# Migration static contract (no shared DB execution)
# ---------------------------------------------------------------------------


def test_0037_migration_static_contract() -> None:
    """0037 revision/down_revision and callable upgrade/downgrade exist."""
    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0037_audit_item_effects_effective_at.py"
    )
    assert mig_path.is_file()
    spec = importlib.util.spec_from_file_location("_mig_0037_effective_at", mig_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "0037_audit_item_effects_effective_at"
    assert mod.down_revision == "0036_operation_revision_lines_composite_pk"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


# ---------------------------------------------------------------------------
# DB-backed round-trip: submit writes operation.effective_at
# ---------------------------------------------------------------------------


async def test_submit_effect_effective_at_matches_operation_effective_at(
    uow, test_user, test_site
) -> None:
    """A-5 DB contract: submit effect timestamp equals operation.effective_at."""
    from app.models.audit_event import AuditEvent
    from app.models.unit import Unit as UnitModel
    from app.schemas.catalog import ItemCreateRequest
    from app.services.catalog_admin_service import CatalogAdminService
    from sqlalchemy import select

    unit = (
        await uow.session.execute(select(UnitModel).where(UnitModel.code == "A5-EA"))
    ).scalar_one_or_none()
    if unit is None:
        unit = UnitModel(code="A5-EA", name="A5 EA Unit", symbol="ea", is_active=True)
        uow.session.add(unit)
        await uow.session.flush()

    item = await CatalogAdminService().create_item(
        uow,
        ItemCreateRequest(
            sku=f"A5-EA-{uuid4().hex[:6]}",
            name="A5 Effective At Item",
            category_id=None,
            unit_id=int(unit.id),
            is_active=True,
        ),
        created_by_user_id=None,
    )

    effective_ts = datetime(2025, 9, 10, 12, 0, 0, tzinfo=UTC)
    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="RECEIVE",
        created_by_user_id=test_user.id,
        effective_at=effective_ts,
    )
    await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=Decimal("4"),
    )
    await uow.session.flush()

    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )

    submit_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.submit")
                & (AuditEvent.entity_id == str(op.id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    assert submit_row is not None
    submit_id = int(submit_row[0])

    effects = await uow.audit_events.list_effects(submit_id)
    assert len(effects) == 1
    assert effects[0].effective_at.astimezone(UTC) == effective_ts


# ---------------------------------------------------------------------------
# DB-backed producer integration: cancel reversal
# ---------------------------------------------------------------------------


async def test_cancel_reversal_effect_effective_at_matches_cancelled_at(
    uow, test_user, test_site
) -> None:
    """ADR-0028 §5: cancel reversal effect timestamp equals
    ``operation.cancelled_at``. A late cancellation in July must NOT
    back-date the May forward effect, but the reversal itself must be
    dated to the cancel moment.

    The cancel moment comes from ``OperationsService.cancel_operation``
    via ``Operation.cancelled_at`` which is set by
    ``OperationsRepo.cancel_operation`` to ``datetime.now(UTC)`` if not
    supplied. The assertion compares the effect's ``effective_at`` to the
    forward submit date plus a slack so Python/Postgres clock drift does
    not cause false negatives.
    """
    unit = (
        await uow.session.execute(select(UnitModel).where(UnitModel.code == "A5-EC"))
    ).scalar_one_or_none()
    if unit is None:
        unit = UnitModel(code="A5-EC", name="A5 EC Unit", symbol="ea", is_active=True)
        uow.session.add(unit)
        await uow.session.flush()

    item = await CatalogAdminService().create_item(
        uow,
        ItemCreateRequest(
            sku=f"A5-EC-{uuid4().hex[:6]}",
            name="A5 Cancel Item",
            category_id=None,
            unit_id=int(unit.id),
            is_active=True,
        ),
    )

    submit_ts = datetime(2024, 5, 15, 12, 0, 0, tzinfo=UTC)
    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="RECEIVE",
        created_by_user_id=test_user.id,
        effective_at=submit_ts,
    )
    line = await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=Decimal("3"),
    )
    await uow.session.flush()

    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )

    await OperationsService.cancel_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
        reason="audit-effective-at-cancel",
    )

    cancel_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.cancel")
                & (AuditEvent.entity_id == str(op.id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    assert cancel_row is not None
    cancel_id = int(cancel_row[0])

    effects = await uow.audit_events.list_effects(cancel_id)
    assert len(effects) == 1
    eff = effects[0]
    assert eff.effect_type == "cancel_reversal"
    assert eff.effective_at is not None
    eff_at = eff.effective_at.astimezone(UTC)
    now_after = datetime.now(UTC)
    # The reversal must be dated to the cancel moment, not the original
    # May forward date. Use 5-minute floor to absorb clock drift between
    # the Python and PostgreSQL clocks.
    assert eff_at > submit_ts + timedelta(minutes=5), (
        f"cancel reversal effect must be dated to cancel moment, not "
        f"forward submit date {submit_ts}: got {eff_at}"
    )
    assert eff_at <= now_after + timedelta(hours=1)


# ---------------------------------------------------------------------------
# DB-backed producer integration: acceptance and lost resolution
# ---------------------------------------------------------------------------


async def _seed_acceptance_fixture(
    uow, test_user, test_site, *, qty: Decimal = Decimal("6")
):
    """Create a RECEIVE+acceptance operation and submit it. Returns
    ``(op, line)`` ready for ``accept_operation_lines``.
    """
    unit = (
        await uow.session.execute(select(UnitModel).where(UnitModel.code == "A5-AC"))
    ).scalar_one_or_none()
    if unit is None:
        unit = UnitModel(code="A5-AC", name="A5 AC Unit", symbol="ea", is_active=True)
        uow.session.add(unit)
        await uow.session.flush()

    item = await CatalogAdminService().create_item(
        uow,
        ItemCreateRequest(
            sku=f"A5-AC-{uuid4().hex[:6]}",
            name="A5 Acceptance Item",
            category_id=None,
            unit_id=int(unit.id),
            is_active=True,
        ),
    )

    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="RECEIVE",
        created_by_user_id=test_user.id,
        effective_at=datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC),
        acceptance_required=True,
    )
    line = await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=qty,
    )
    await uow.operations.update_operation_line_progress(
        operation_line_id=line.id,
        accepted_delta=Decimal("0"),
        lost_delta=Decimal("0"),
    )
    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )
    return op, line


async def test_acceptance_effect_effective_at_matches_action_performed_at(
    uow, test_user, test_site
) -> None:
    """ADR-0028 §5: per-line acceptance effect timestamp equals
    ``OperationAcceptanceAction.performed_at``. A late acceptance in July
    must be dated to the action moment, not the May forward submit date.

    ``performed_at`` is set by PostgreSQL ``now()`` at INSERT time, so the
    value lives in the database clock; the assertion compares against the
    operation's submit date (May) plus a small drift tolerance — this catches
    the regression without depending on Python/Postgres clock alignment.
    """
    from app.schemas.asset_register import OperationAcceptLinePayload

    submit_date = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)
    op, line = await _seed_acceptance_fixture(uow, test_user, test_site)
    assert op.effective_at == submit_date, (
        f"fixture submit date mismatch: {op.effective_at} vs {submit_date}"
    )

    await OperationsService.accept_operation_lines(
        uow,
        operation_id=op.id,
        user_id=test_user.id,
        line_updates=[
            OperationAcceptLinePayload(
                line_id=line.id, accepted_qty=Decimal("2"), lost_qty=Decimal("0")
            )
        ],
    )

    line_event_ids = (
        await uow.session.execute(
            select(AuditEvent.id)
            .where(
                AuditEvent.event_type == "operation.line_accepted",
                AuditEvent.entity_id == str(line.id),
            )
            .order_by(AuditEvent.id.asc())
        )
    ).scalars().all()
    assert len(line_event_ids) == 1
    effects = await uow.audit_events.list_effects(int(line_event_ids[0]))
    assert len(effects) == 1
    eff = effects[0]
    assert eff.effect_type == "acceptance"
    assert eff.effective_at is not None
    eff_at = eff.effective_at.astimezone(UTC)
    # Acceptance effect is dated to "now" at action time, well after the
    # operation's submit date. Use a 5-minute floor (covers Python/Postgres
    # clock drift in disposable fixtures) and an upper bound of "now + 1h"
    # to catch accidental re-use of the submit date.
    now_after = datetime.now(UTC)
    assert eff_at > submit_date + timedelta(minutes=5), (
        f"acceptance effect must be dated to action time, not submit "
        f"date {submit_date}: got {eff_at}"
    )
    assert eff_at <= now_after + timedelta(hours=1), (
        f"acceptance effect timestamp in the future: got {eff_at}"
    )


async def test_lost_resolution_effect_effective_at_matches_action_performed_at(
    uow, test_user, test_site
) -> None:
    """ADR-0028 §5: lost resolution warehouse effect (found_to_destination)
    timestamp equals ``OperationAcceptanceAction.performed_at``.

    Same clock-drift caveat as the acceptance test: the effect timestamp
    comes from PostgreSQL ``now()`` and the assertion compares against the
    operation's submit date plus a slack, not against Python ``datetime.now``.
    """
    submit_date = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)
    op, line = await _seed_acceptance_fixture(uow, test_user, test_site)
    assert op.effective_at == submit_date

    # Mark all qty as lost to seed a lost register entry.
    from app.schemas.asset_register import OperationAcceptLinePayload

    await OperationsService.accept_operation_lines(
        uow,
        operation_id=op.id,
        user_id=test_user.id,
        line_updates=[
            OperationAcceptLinePayload(
                line_id=line.id, accepted_qty=Decimal("0"), lost_qty=Decimal("6")
            )
        ],
    )

    result = await OperationsService.resolve_lost_asset(
        uow,
        operation_line_id=line.id,
        action="found_to_destination",
        qty=Decimal("2"),
        user_id=test_user.id,
        note="lost-resolved",
        responsible_recipient_id=None,
    )
    assert result["status"] == "ok"

    event_ids = (
        await uow.session.execute(
            select(AuditEvent.id)
            .where(
                AuditEvent.event_type == "operation.line_lost_resolved",
                AuditEvent.entity_id == str(line.id),
            )
            .order_by(AuditEvent.id.asc())
        )
    ).scalars().all()
    assert len(event_ids) == 1
    effects = await uow.audit_events.list_effects(int(event_ids[0]))
    assert len(effects) == 1
    eff = effects[0]
    assert eff.effect_type == "acceptance"
    assert eff.effective_at is not None
    eff_at = eff.effective_at.astimezone(UTC)
    now_after = datetime.now(UTC)
    assert eff_at > submit_date + timedelta(minutes=5), (
        f"lost-resolution effect must be dated to action time, not submit "
        f"date {submit_date}: got {eff_at}"
    )
    assert eff_at <= now_after + timedelta(hours=1)


# ---------------------------------------------------------------------------
# DB-backed producer integration: correction explicit apply timestamp
# ---------------------------------------------------------------------------


async def test_correction_effect_effective_at_is_explicit_apply_timestamp(
    uow, test_user, test_site, secondary_site
) -> None:
    """ADR-0028 §5: correction delta uses an explicit apply timestamp
    captured at correction-submit time, distinct from the original
    operation date. ``CorrectionsService.submit_correction`` writes
    ``audit_item_effects`` with ``effective_at=apply_timestamp`` and must
    not back-date to ``operation.effective_at``.

    The apply timestamp is captured via ``datetime.now(UTC)`` in
    ``CorrectionsService.submit_correction`` and threaded through
    ``OperationsService._write_captured_effects``. The assertion compares
    against the operation's submit date (May) plus a slack so clock drift
    between Python and PostgreSQL does not cause false negatives.
    """
    from app.services.corrections_service import CorrectionsService

    unit = (
        await uow.session.execute(select(UnitModel).where(UnitModel.code == "A5-CR"))
    ).scalar_one_or_none()
    if unit is None:
        unit = UnitModel(code="A5-CR", name="A5 CR Unit", symbol="ea", is_active=True)
        uow.session.add(unit)
        await uow.session.flush()

    item = await CatalogAdminService().create_item(
        uow,
        ItemCreateRequest(
            sku=f"A5-CR-{uuid4().hex[:6]}",
            name="A5 Correction Item",
            category_id=None,
            unit_id=int(unit.id),
            is_active=True,
        ),
    )

    submit_ts = datetime(2024, 5, 15, 12, 0, 0, tzinfo=UTC)
    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="RECEIVE",
        created_by_user_id=test_user.id,
        effective_at=submit_ts,
    )
    line = await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=Decimal("5"),
    )
    await uow.session.flush()
    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )

    # Begin a correction by cloning the current baseline; then mutate the
    # qty of the existing line so the diff is non-empty.
    correction = await CorrectionsService.begin_correction(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )
    corr_id = UUID(correction["id"])
    initial_line = correction["lines"][0]

    await CorrectionsService.update_correction_put(
        uow=uow,
        correction_id=corr_id,
        expected_version=int(correction["version"]),
        lines=[
            {
                "line_uuid": initial_line["line_uuid"],
                "line_number": int(initial_line["line_number"]),
                "item_id": int(item.id),
                "qty": "7.000",
            }
        ],
    )
    result = await CorrectionsService.submit_correction(
        uow=uow,
        correction_id=corr_id,
        user_id=test_user.id,
        expected_version=int(correction["version"]) + 1,
        idempotency_key=f"a5-effective-at-{uuid4().hex[:8]}",
    )
    assert result["correction"]["status"] == "applied"

    corr_event_id_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.correction.applied")
                & (AuditEvent.entity_id == str(corr_id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    assert corr_event_id_row is not None
    corr_event_id = int(corr_event_id_row[0])

    effects = await uow.audit_events.list_effects(corr_event_id)
    assert len(effects) >= 1
    now_after = datetime.now(UTC)
    for eff in effects:
        assert eff.effective_at is not None
        eff_at = eff.effective_at.astimezone(UTC)
        # Correction apply timestamp is fresh — far later than the May
        # submit date — so backdated ``operation.effective_at`` cannot be
        # confused with the apply moment. Use 5-minute floor for clock
        # drift tolerance.
        assert eff_at > submit_ts + timedelta(minutes=5), (
            f"correction effect must be dated to apply time, not submit "
            f"date {submit_ts}: got {eff_at}"
        )
        assert eff_at <= now_after + timedelta(hours=1)
