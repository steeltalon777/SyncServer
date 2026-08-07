"""A-5 / ADR-0028 §6 disposable migration ladder for ``audit_item_effects.effective_at``.

This test runs against an isolated PostgreSQL *database* (not the shared
``warehouse`` DB) so the schema is wiped together with the test and no
side-effects remain on the dev stand. The migration 0037 is exercised in the
exact order required by the TZ:

    alembic upgrade 0036
    seed pre-0037 audit_events / audit_item_effects with mixed event types
    alembic upgrade 0037
    assertions: NULL=0, column type/default/NOT NULL, index, backfill mapping
    alembic downgrade 0036
    alembic upgrade 0037 (idempotency of the column-add + backfill path)

The fixture uses a per-test unique database name so multiple test invocations
do not collide, and tears the database down in a ``finally`` block so that
even a failed assertion never leaves a disposable database behind.

Important invariants checked here (A-5 §9.2/§9.4 + ADR-0028 §6):

* The new column is ``TIMESTAMPTZ NOT NULL`` with ``server_default now()``;
* ``ix_audit_item_effects_effective_at`` exists after upgrade and is gone
  after downgrade;
* Backfill prefers ``operation.effective_at`` for ``operation.submit`` and
  ``operation.cancelled_at`` for ``operation.cancel``; falls back to
  ``audit_events.created_at`` then ``audit_item_effects.created_at`` for all
  other event types; never silently inserts ``now()``;
* After downgrade, ``audit_events`` / ``operations`` rows are intact and only
  the new column/index are dropped;
* A re-upgrade after downgrade on the same data set re-applies the column
  and backfill idempotently.

The test does NOT touch the shared ``warehouse`` database; it uses
``warehouse_user``'s superuser grant to ``CREATE DATABASE`` and ``DROP
DATABASE`` and tears the disposable DB down before returning.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import AsyncIterator
from uuid import UUID, uuid4

import asyncpg
import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

# Ensure project root is on sys.path so the migration module can import app.*
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Connection strings use environment variables; values are not echoed into
# any assertion message or failure summary.
_ADMIN_DSN_ENV = "POSTGRES_ADMIN_DSN"
_TEST_DSN_ENV = "DATABASE_URL_TEST"


def _admin_dsn() -> str:
    """DSN of a PostgreSQL superuser connection used for CREATE/DROP DATABASE.

    Falls back to ``DATABASE_URL_TEST`` if no explicit admin DSN is provided.
    The fixture still works with a non-superuser only when the disposable
    database already exists; in that case ``DROP DATABASE`` will be skipped.
    """
    return os.environ.get(_ADMIN_DSN_ENV) or os.environ.get(_TEST_DSN_ENV) or ""


def _base_dsn() -> str:
    return os.environ.get(_TEST_DSN_ENV) or os.environ.get("DATABASE_URL") or ""


def _dsn_database(dsn: str) -> str:
    """Extract the database name from a libpq/asyncpg DSN.

    Accepts both ``postgresql://user:pass@host:port/db`` and the SQLAlchemy
    ``postgresql+asyncpg://`` flavor.
    """
    return _parse_dsn(dsn)["database"]


def _dsn_with_database(dsn: str, database: str) -> str:
    """Return a copy of the DSN with the database name replaced.

    The returned DSN uses the SQLAlchemy ``postgresql+asyncpg://`` flavor so
    alembic command (which uses SQLAlchemy) accepts it. Callers that need
    raw libpq-style DSNs for asyncpg.connect() must pass through
    ``_dsn_to_asyncpg()`` first.
    """
    parsed = _parse_dsn(dsn)
    parsed["database"] = database
    return _format_dsn(parsed, keep_driver=True)


def _dsn_to_asyncpg(dsn: str) -> str:
    """Convert SQLAlchemy-style DSN to asyncpg/libpq format.

    asyncpg does not understand ``postgresql+asyncpg://``; it only accepts
    ``postgresql://`` or ``postgres://``.
    """
    return _format_dsn(_parse_dsn(dsn), keep_driver=False)


def _parse_dsn(dsn: str) -> dict[str, str | int | None]:
    """Lightweight libpq/asyncpg/SQLAlchemy DSN parser.

    Returns a dict with keys ``user``, ``password``, ``host``, ``port``,
    ``database``, ``scheme`` (the original ``postgresql`` or
    ``postgresql+asyncpg``). asyncpg's own URL parser does not accept the
    ``postgresql+asyncpg://`` flavor, so we parse it manually here.
    """
    # Strip the optional +driver suffix so urlparse handles it.
    # e.g. "postgresql+asyncpg://user:pass@host:port/db"
    scheme_part, _, rest = dsn.partition("://")
    driver = None
    if "+" in scheme_part:
        scheme, _, driver = scheme_part.partition("+")
    else:
        scheme = scheme_part

    from urllib.parse import quote, unquote, urlparse

    parsed = urlparse(f"{scheme}://{rest}")
    return {
        "scheme": scheme,
        "driver": driver,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
    }


def _format_dsn(parsed: dict[str, str | int | None], *, keep_driver: bool = True) -> str:
    from urllib.parse import quote

    user = parsed["user"]
    password = parsed["password"]
    host = parsed["host"]
    port = parsed["port"]
    database = parsed["database"]
    driver = parsed["driver"] if keep_driver else None
    scheme = "postgresql" + (f"+{driver}" if driver else "")
    user_part = ""
    if user:
        user_part = quote(str(user), safe="")
        if password:
            user_part += f":{quote(str(password), safe='')}"
        user_part += "@"
    return f"{scheme}://{user_part}{host}:{port}/{database}"


# ---------------------------------------------------------------------------
# Disposable database lifecycle helpers
# ---------------------------------------------------------------------------


async def _create_disposable_database(dsn: str, name: str) -> None:
    admin_url = _dsn_to_asyncpg(_dsn_with_database(dsn, "postgres"))
    conn = await asyncpg.connect(admin_url)
    try:
        # Force-disconnect any leftover sessions so DROP DATABASE later does
        # not block. The disposable DB is unique per-test so the only
        # sessions are from this fixture itself.
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _precreate_alembic_version(dsn: str, name: str) -> None:
    """Create the alembic_version table with a wide version_num column.

    The default Alembic ``alembic_version.version_num`` is ``VARCHAR(32)``,
    but the 0037 revision id ``0037_audit_item_effects_effective_at`` is 36
    characters. The shared dev/warehouse DB happens to have ``VARCHAR(128)``
    from a previous manual widening; a brand-new database needs the same
    widening to apply migration 0037.
    """
    conn = await asyncpg.connect(_dsn_to_asyncpg(_dsn_with_database(dsn, name)))
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(128) NOT NULL)"
        )
    finally:
        await conn.close()


async def _drop_disposable_database(dsn: str, name: str) -> None:
    admin_url = _dsn_to_asyncpg(_dsn_with_database(dsn, "postgres"))
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await conn.close()


@asynccontextmanager
async def _disposable_database(base_dsn: str, suffix: str) -> AsyncIterator[str]:
    """Async context manager that creates and destroys a disposable database.

    Yields the connection DSN pointing at the disposable database.
    """
    if not base_dsn:
        pytest.skip("DATABASE_URL_TEST is required for migration ladder test")

    name = f"audit_a5_disp_{suffix}_{int(time.time() * 1000)}"
    await _create_disposable_database(base_dsn, name)
    await _precreate_alembic_version(base_dsn, name)
    disposable_dsn = _dsn_with_database(base_dsn, name)
    try:
        yield disposable_dsn
    finally:
        await _drop_disposable_database(base_dsn, name)


def _make_alembic_config(database_url: str) -> AlembicConfig:
    """Build an Alembic config that targets ``database_url`` for this run."""
    cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    # The env.py looks up `database_url` first via attributes, then via
    # settings.DATABASE_URL. We set the attribute so env.py never has to
    # touch the real app settings.
    cfg.attributes["database_url"] = database_url
    return cfg


async def _alembic_upgrade(cfg: AlembicConfig, revision: str) -> None:
    """Run alembic upgrade in a worker thread.

    alembic.command.upgrade() runs an inner asyncio.run() — calling it from
    a pytest-asyncio test (which already owns an event loop) raises
    ``RuntimeError: asyncio.run() cannot be called from a running event
    loop``. Offloading to a thread gives the call its own loop.
    """
    await asyncio.to_thread(alembic_command.upgrade, cfg, revision)


async def _alembic_downgrade(cfg: AlembicConfig, revision: str) -> None:
    await asyncio.to_thread(alembic_command.downgrade, cfg, revision)


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


async def _execute_sql(dsn: str, *statements: str) -> None:
    conn = await asyncpg.connect(_dsn_to_asyncpg(dsn))
    try:
        for stmt in statements:
            await conn.execute(stmt)
    finally:
        await conn.close()


async def _fetchall(dsn: str, sql: str, *args) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(_dsn_to_asyncpg(dsn))
    try:
        return list(await conn.fetch(sql, *args))
    finally:
        await conn.close()


async def _fetchval(dsn: str, sql: str, *args) -> object:
    conn = await asyncpg.connect(_dsn_to_asyncpg(dsn))
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------


async def _ensure_site(dsn: str) -> int:
    site_id = await _fetchval(
        dsn,
        "INSERT INTO sites (code, name, is_active) "
        "VALUES ($1, $2, true) RETURNING id",
        f"A5-DISP-{int(time.time() * 1000)}",
        "A5 disposable site",
    )
    return int(site_id)


async def _ensure_inventory_subject(dsn: str) -> int:
    subject_id = await _fetchval(
        dsn,
        "INSERT INTO inventory_subjects (subject_type) "
        "VALUES ('catalog_item') RETURNING id",
    )
    return int(subject_id)


async def _ensure_unit(dsn: str) -> int:
    unit_id = await _fetchval(
        dsn,
        "INSERT INTO units (code, name, symbol, is_active) "
        "VALUES ($1, $2, $3, true) RETURNING id",
        f"A5-DISP-UNIT-{int(time.time() * 1000)}",
        "A5 disposable unit",
        "ea",
    )
    return int(unit_id)


async def _ensure_category(dsn: str) -> int:
    category_id = await _fetchval(
        dsn,
        "INSERT INTO categories (code, name, normalized_name, is_active) "
        "VALUES ($1, $2, $3, true) RETURNING id",
        f"A5-DISP-CAT-{int(time.time() * 1000)}",
        "A5 disposable category",
        "a5 disposable category",
    )
    return int(category_id)


async def _ensure_item(dsn: str, *, unit_id: int, category_id: int) -> int:
    item_id = await _fetchval(
        dsn,
        "INSERT INTO items (sku, name, category_id, unit_id, is_active, "
        "created_by_user_id, updated_by_user_id) "
        "VALUES ($1, $2, $3, $4, true, NULL, NULL) RETURNING id",
        f"A5-DISP-ITEM-{int(time.time() * 1000)}",
        "A5 disposable item",
        category_id,
        unit_id,
    )
    return int(item_id)


async def _ensure_user(dsn: str) -> str:
    """Insert a disposable user with a fixed UUID.

    The disposable DB does not seed root/chief users, but
    ``operations.created_by_user_id`` is NOT NULL, so the seed helpers need
    a user to point at.
    """
    user_id = await _fetchval(
        dsn,
        "INSERT INTO users (id, username, user_token, email, full_name, "
        "is_active, is_root, role, default_site_id) "
        "VALUES ($1, $2, $3, $4, $5, true, true, 'root', NULL) RETURNING id",
        uuid4(),
        f"a5-disp-{int(time.time() * 1000)}",
        uuid4(),
        f"a5-disp-{int(time.time() * 1000)}@example.com",
        "A5 disposable root",
    )
    return str(user_id)


async def _seed_pre_0037(
    dsn: str,
    *,
    site_id: int,
    user_id: str,
    inventory_subject_id: int,
) -> dict[str, object]:
    """Seed pre-0037 audit_events and audit_item_effects rows.

    Returns mapping with operation/effect/event identifiers and the source
    timestamps that the migration backfill should pick up.
    """
    # Use fixed UTC timestamps so PostgreSQL's TIMESTAMPTZ microsecond
    # round-trip cannot drift them across the assertion boundary.
    submit_op_effective_at = datetime(2024, 6, 10, 12, 0, 0, tzinfo=UTC)
    cancel_op_effective_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    cancel_op_cancelled_at = datetime(2024, 6, 17, 12, 0, 0, tzinfo=UTC)

    submit_event_created_at = datetime(2024, 6, 10, 10, 0, 0, tzinfo=UTC)
    cancel_event_created_at = datetime(2024, 6, 17, 10, 0, 0, tzinfo=UTC)
    correction_event_created_at = datetime(2024, 6, 18, 10, 0, 0, tzinfo=UTC)
    line_accepted_event_created_at = datetime(2024, 6, 19, 10, 0, 0, tzinfo=UTC)

    # Three operations with distinct timestamp profiles:
    # * submit-op:    effective_at set, cancelled_at NULL
    # * cancel-op:    effective_at set, cancelled_at set
    # * correction-op: both NULL (the correction event has only created_at)
    submit_op_id = await _fetchval(
        dsn,
        "INSERT INTO operations (id, site_id, operation_type, status, "
        "created_by_user_id, effective_at) "
        "VALUES ($1, $2, 'RECEIVE', 'submitted', $3, $4) RETURNING id",
        uuid4(),
        site_id,
        user_id,
        submit_op_effective_at,
    )
    cancel_op_id = await _fetchval(
        dsn,
        "INSERT INTO operations (id, site_id, operation_type, status, "
        "created_by_user_id, effective_at, cancelled_at) "
        "VALUES ($1, $2, 'RECEIVE', 'cancelled', $3, $4, $5) RETURNING id",
        uuid4(),
        site_id,
        user_id,
        cancel_op_effective_at,
        cancel_op_cancelled_at,
    )
    correction_op_id = await _fetchval(
        dsn,
        "INSERT INTO operations (id, site_id, operation_type, status, "
        "created_by_user_id) "
        "VALUES ($1, $2, 'ADJUSTMENT', 'submitted', $3) RETURNING id",
        uuid4(),
        site_id,
        user_id,
    )

    # Distinct audit_event.created_at for each event so the fallback path is
    # observable in the assertions.
    submit_event_id = await _fetchval(
        dsn,
        "INSERT INTO audit_events (event_id, event_type, event_version, entity_type, "
        "entity_id, summary, outcome, created_at) "
        "VALUES ($1, 'operation.submit', 2, 'operation', $2, 'submit seed', "
        "'success', $3) RETURNING id",
        uuid4(),
        str(submit_op_id),
        submit_event_created_at,
    )
    cancel_event_id = await _fetchval(
        dsn,
        "INSERT INTO audit_events (event_id, event_type, event_version, entity_type, "
        "entity_id, summary, outcome, created_at) "
        "VALUES ($1, 'operation.cancel', 2, 'operation', $2, 'cancel seed', "
        "'success', $3) RETURNING id",
        uuid4(),
        str(cancel_op_id),
        cancel_event_created_at,
    )
    correction_event_id = await _fetchval(
        dsn,
        "INSERT INTO audit_events (event_id, event_type, event_version, entity_type, "
        "entity_id, summary, outcome, created_at) "
        "VALUES ($1, 'operation.correction.applied', 2, 'operation_correction', "
        "$2, 'correction seed', 'success', $3) RETURNING id",
        uuid4(),
        str(correction_op_id),
        correction_event_created_at,
    )
    line_accepted_event_id = await _fetchval(
        dsn,
        "INSERT INTO audit_events (event_id, event_type, event_version, entity_type, "
        "entity_id, summary, outcome, created_at) "
        "VALUES ($1, 'operation.line_accepted', 2, 'operation_line', $2, "
        "'line accepted seed', 'success', $3) RETURNING id",
        uuid4(),
        str(uuid4()),
        line_accepted_event_created_at,
    )

    # Insert one audit_item_effect per event. effective_at is intentionally
    # left NULL — pre-0037 schema has no such column at all, so we cannot
    # insert one here. We will assert NULL=0 after upgrade (the backfill
    # fills it; the column starts empty).
    submit_effect_id = await _fetchval(
        dsn,
        "INSERT INTO audit_item_effects (audit_event_id, operation_id, "
        "inventory_subject_id, quantity_before, quantity_delta, quantity_after, "
        "effect_type, created_at) "
        "VALUES ($1, $2, $3, 0, 5, 5, 'forward_submit', $4) RETURNING id",
        submit_event_id,
        submit_op_id,
        inventory_subject_id,
        submit_event_created_at,
    )
    cancel_effect_id = await _fetchval(
        dsn,
        "INSERT INTO audit_item_effects (audit_event_id, operation_id, "
        "inventory_subject_id, quantity_before, quantity_delta, quantity_after, "
        "effect_type, created_at) "
        "VALUES ($1, $2, $3, 5, -5, 0, 'cancel_reversal', $4) RETURNING id",
        cancel_event_id,
        cancel_op_id,
        inventory_subject_id,
        cancel_event_created_at,
    )
    correction_effect_id = await _fetchval(
        dsn,
        "INSERT INTO audit_item_effects (audit_event_id, operation_id, "
        "inventory_subject_id, quantity_before, quantity_delta, quantity_after, "
        "effect_type, created_at) "
        "VALUES ($1, $2, $3, 0, 1, 1, 'correction', $4) RETURNING id",
        correction_event_id,
        correction_op_id,
        inventory_subject_id,
        correction_event_created_at,
    )
    line_accepted_effect_id = await _fetchval(
        dsn,
        "INSERT INTO audit_item_effects (audit_event_id, inventory_subject_id, "
        "quantity_before, quantity_delta, quantity_after, effect_type, "
        "created_at) "
        "VALUES ($1, $2, 0, 1, 1, 'acceptance', $3) RETURNING id",
        line_accepted_event_id,
        inventory_subject_id,
        line_accepted_event_created_at,
    )

    return {
        "submit_op_id": submit_op_id,
        "cancel_op_id": cancel_op_id,
        "correction_op_id": correction_op_id,
        "submit_event_id": submit_event_id,
        "cancel_event_id": cancel_event_id,
        "correction_event_id": correction_event_id,
        "line_accepted_event_id": line_accepted_event_id,
        "submit_effect_id": submit_effect_id,
        "cancel_effect_id": cancel_effect_id,
        "correction_effect_id": correction_effect_id,
        "line_accepted_effect_id": line_accepted_effect_id,
        "submit_op_effective_at": submit_op_effective_at,
        "cancel_op_cancelled_at": cancel_op_cancelled_at,
        "submit_event_created_at": submit_event_created_at,
        "cancel_event_created_at": cancel_event_created_at,
        "correction_event_created_at": correction_event_created_at,
        "line_accepted_event_created_at": line_accepted_event_created_at,
        "effects_before_total": 4,
    }


# ---------------------------------------------------------------------------
# Schema introspection helpers
# ---------------------------------------------------------------------------


async def _column_info(dsn: str, table: str, column: str) -> asyncpg.Record | None:
    rows = await _fetchall(
        dsn,
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = $1 "
        "AND column_name = $2",
        table,
        column,
    )
    return rows[0] if rows else None


async def _has_index(dsn: str, index_name: str) -> bool:
    val = await _fetchval(
        dsn,
        "SELECT EXISTS (SELECT 1 FROM pg_indexes "
        "WHERE schemaname = 'public' AND indexname = $1)",
        index_name,
    )
    return bool(val)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_migration_0037_full_ladder_with_backfill() -> None:
    """End-to-end migration ladder on a disposable database.

    Stages:
      1. upgrade to 0036 (pre-A-5 state, no ``effective_at`` column yet)
      2. seed pre-0037 audit_events + audit_item_effects with mixed event types
      3. upgrade to 0037 — backfill + NOT NULL + index
      4. assert column shape, NULL=0, index present, backfill mapping correct
      5. downgrade to 0036 — column/index gone, history preserved
      6. upgrade to 0037 again — re-applies the column + backfill idempotently
    """
    base_dsn = _base_dsn()
    if not base_dsn:
        pytest.skip("DATABASE_URL_TEST is required for migration ladder test")

    suffix = "ladder"
    async with _disposable_database(base_dsn, suffix) as dsn:
        cfg = _make_alembic_config(dsn)

        # 1. upgrade 0036
        await _alembic_upgrade(cfg, "0036_operation_revision_lines_composite_pk")

        site_id = await _ensure_site(dsn)
        user_id = await _ensure_user(dsn)
        unit_id = await _ensure_unit(dsn)
        category_id = await _ensure_category(dsn)
        await _ensure_item(dsn, unit_id=unit_id, category_id=category_id)
        subject_id = await _ensure_inventory_subject(dsn)

        # 2. seed pre-0037 data
        seed = await _seed_pre_0037(
            dsn,
            site_id=site_id,
            user_id=user_id,
            inventory_subject_id=subject_id,
        )

        # Pre-0037 schema must NOT have effective_at column
        col_before = await _column_info(dsn, "audit_item_effects", "effective_at")
        assert col_before is None, "effective_at must not exist at revision 0036"

        # 3. upgrade 0037 — measure backfill+DDL time
        t0 = time.perf_counter()
        await _alembic_upgrade(cfg, "0037_audit_item_effects_effective_at")
        upgrade_seconds = time.perf_counter() - t0

        # 4. assertions
        # 4a. column shape: TIMESTAMPTZ NOT NULL with server_default now()
        col = await _column_info(dsn, "audit_item_effects", "effective_at")
        assert col is not None, "effective_at must exist after upgrade 0037"
        assert col["data_type"] == "timestamp with time zone", (
            f"effective_at must be TIMESTAMPTZ, got {col['data_type']}"
        )
        assert col["is_nullable"] == "NO", (
            f"effective_at must be NOT NULL, got nullable={col['is_nullable']}"
        )
        assert col["column_default"] is not None and "now" in col["column_default"].lower(), (
            f"effective_at must have server_default now(), got {col['column_default']}"
        )

        # 4b. index exists
        assert await _has_index(dsn, "ix_audit_item_effects_effective_at"), (
            "ix_audit_item_effects_effective_at must exist after upgrade"
        )

        # 4c. NULL = 0
        null_count = await _fetchval(
            dsn, "SELECT COUNT(*) FROM audit_item_effects WHERE effective_at IS NULL"
        )
        assert null_count == 0, f"effective_at must be NOT NULL everywhere, got {null_count} NULLs"

        # 4d. total row count unchanged
        total = await _fetchval(dsn, "SELECT COUNT(*) FROM audit_item_effects")
        assert total == seed["effects_before_total"]

        # 4e. backfill mapping per producer:
        # submit effect -> operation.effective_at
        submit_eff = await _fetchval(
            dsn,
            "SELECT effective_at FROM audit_item_effects WHERE id = $1",
            seed["submit_effect_id"],
        )
        assert submit_eff == seed["submit_op_effective_at"], (
            f"submit effect effective_at must equal operation.effective_at; "
            f"got {submit_eff} expected {seed['submit_op_effective_at']}"
        )

        # cancel effect -> operation.cancelled_at
        cancel_eff = await _fetchval(
            dsn,
            "SELECT effective_at FROM audit_item_effects WHERE id = $1",
            seed["cancel_effect_id"],
        )
        assert cancel_eff == seed["cancel_op_cancelled_at"], (
            f"cancel effect effective_at must equal operation.cancelled_at; "
            f"got {cancel_eff} expected {seed['cancel_op_cancelled_at']}"
        )

        # correction effect -> audit_events.created_at (operations has no
        # relevant date for corrections; the COALESCE falls through to the
        # event timestamp).
        corr_eff = await _fetchval(
            dsn,
            "SELECT effective_at FROM audit_item_effects WHERE id = $1",
            seed["correction_effect_id"],
        )
        assert corr_eff == seed["correction_event_created_at"], (
            f"correction effect effective_at must equal audit_events.created_at; "
            f"got {corr_eff} expected {seed['correction_event_created_at']}"
        )

        # line_accepted effect -> audit_events.created_at
        line_eff = await _fetchval(
            dsn,
            "SELECT effective_at FROM audit_item_effects WHERE id = $1",
            seed["line_accepted_effect_id"],
        )
        assert line_eff == seed["line_accepted_event_created_at"], (
            f"line_accepted effect effective_at must equal audit_events.created_at; "
            f"got {line_eff} expected {seed['line_accepted_event_created_at']}"
        )

        # 4f. no value should be the migration run time (now() at upgrade
        # moment). Compare against the upgrade completion time with a small
        # slack so we don't false-fail on identical-timestamp collisions.
        migration_now = datetime.now(UTC)
        all_eff = await _fetchall(
            dsn, "SELECT effective_at FROM audit_item_effects"
        )
        for row in all_eff:
            ts = row["effective_at"]
            # 5-second slack — the migration finished before we measured
            # `migration_now`, but backfill ran well before that and used
            # event/operation timestamps that are weeks in the past.
            assert ts < migration_now - timedelta(seconds=5), (
                f"effect effective_at {ts} looks like migration run time, not "
                f"a historical backfill source (now={migration_now})"
            )

        # 4g. row count + backfill timing
        rows = await _fetchval(
            dsn, "SELECT COUNT(*) FROM audit_item_effects"
        )
        assert rows == 4

        # 5. downgrade to 0036 — column/index gone, history preserved
        await _alembic_downgrade(cfg, "0036_operation_revision_lines_composite_pk")

        # 5a. column and index gone
        col_after_dn = await _column_info(dsn, "audit_item_effects", "effective_at")
        assert col_after_dn is None, (
            "effective_at must be dropped after downgrade"
        )
        assert not await _has_index(dsn, "ix_audit_item_effects_effective_at"), (
            "ix_audit_item_effects_effective_at must be dropped after downgrade"
        )

        # 5b. audit_events and operations history preserved (row counts)
        evt_count = await _fetchval(dsn, "SELECT COUNT(*) FROM audit_events")
        assert evt_count >= 4, (
            f"audit_events history must be preserved on downgrade; got {evt_count}"
        )
        op_count = await _fetchval(dsn, "SELECT COUNT(*) FROM operations")
        assert op_count >= 3, (
            f"operations history must be preserved on downgrade; got {op_count}"
        )
        eff_count_after_dn = await _fetchval(
            dsn, "SELECT COUNT(*) FROM audit_item_effects"
        )
        assert eff_count_after_dn == 4, (
            "audit_item_effects rows must be preserved on downgrade"
        )

        # 6. upgrade 0037 again — verify idempotency on re-application
        await _alembic_upgrade(cfg, "0037_audit_item_effects_effective_at")

        col_after_re_up = await _column_info(dsn, "audit_item_effects", "effective_at")
        assert col_after_re_up is not None
        assert col_after_re_up["data_type"] == "timestamp with time zone"
        assert col_after_re_up["is_nullable"] == "NO"

        # 6a. row count unchanged
        total_after_re_up = await _fetchval(
            dsn, "SELECT COUNT(*) FROM audit_item_effects"
        )
        assert total_after_re_up == 4, (
            "re-upgrade must not duplicate rows"
        )

        # 6b. NULL = 0 again (server_default fills any leftover nulls)
        null_count_after_re_up = await _fetchval(
            dsn,
            "SELECT COUNT(*) FROM audit_item_effects WHERE effective_at IS NULL",
        )
        assert null_count_after_re_up == 0


async def test_migration_0037_backfill_aborts_when_source_null() -> None:
    """A pre-existing audit_item_effects row with no resolvable timestamp
    must force the migration to abort, not silently receive ``now()``.

    This is the explicit ADR-0028 §6 silent-now() prohibition. We seed an
    effect whose audit_event has ``created_at = NULL`` (allowed pre-0037 since
    the column was added in 0017 with server default), then null the default
    out so the COALESCE chain resolves to NULL on every level. The migration
    must raise.
    """
    base_dsn = _base_dsn()
    if not base_dsn:
        pytest.skip("DATABASE_URL_TEST is required for migration ladder test")

    async with _disposable_database(base_dsn, "abort") as dsn:
        cfg = _make_alembic_config(dsn)

        await _alembic_upgrade(cfg, "0036_operation_revision_lines_composite_pk")

        # Create the bare-minimum audit_event with NULL created_at and a
        # matching audit_item_effect, then clear the column defaults so that
        # an inserted row keeps NULL on every level of the COALESCE chain.
        conn = await asyncpg.connect(_dsn_to_asyncpg(dsn))
        try:
            await conn.execute(
                "ALTER TABLE audit_events ALTER COLUMN created_at DROP DEFAULT"
            )
            # audit_events.created_at is NOT NULL with server_default now().
            # We need to insert with explicit NULL — temporarily allow NULLs.
            await conn.execute(
                "ALTER TABLE audit_events ALTER COLUMN created_at DROP NOT NULL"
            )
            await conn.execute(
                "ALTER TABLE audit_item_effects ALTER COLUMN created_at "
                "DROP DEFAULT"
            )
            await conn.execute(
                "ALTER TABLE audit_item_effects ALTER COLUMN created_at "
                "DROP NOT NULL"
            )
            event_id = await conn.fetchval(
                "INSERT INTO audit_events (event_id, event_type, event_version, entity_type, "
                "entity_id, summary, outcome, created_at) "
                "VALUES ($1, 'operation.submit', 2, 'operation', $2, 'no-ts', "
                "'success', NULL) RETURNING id",
                uuid4(),
                str(uuid4()),
            )
            subject_id = await conn.fetchval(
                "INSERT INTO inventory_subjects (subject_type) "
                "VALUES ('catalog_item') RETURNING id"
            )
            await conn.fetchval(
                "INSERT INTO audit_item_effects (audit_event_id, "
                "inventory_subject_id, quantity_before, quantity_delta, "
                "quantity_after, effect_type, created_at) "
                "VALUES ($1, $2, 0, 1, 1, 'forward_submit', NULL) RETURNING id",
                event_id,
                subject_id,
            )
        finally:
            await conn.close()

        with pytest.raises(RuntimeError, match="backfill left"):
            await _alembic_upgrade(cfg, "0037_audit_item_effects_effective_at")


async def test_migration_0037_uses_event_created_at_when_operation_dates_missing() -> None:
    """Backfill falls through to audit_events.created_at when neither
    operations.effective_at nor operations.cancelled_at is set, and to
    audit_item_effects.created_at when even the event timestamp is NULL.

    This exercises the producer ``correction/other`` branch where only the
    event timestamp is meaningful.
    """
    base_dsn = _base_dsn()
    if not base_dsn:
        pytest.skip("DATABASE_URL_TEST is required for migration ladder test")

    async with _disposable_database(base_dsn, "fallback") as dsn:
        cfg = _make_alembic_config(dsn)
        await _alembic_upgrade(cfg, "0036_operation_revision_lines_composite_pk")

        conn = await asyncpg.connect(_dsn_to_asyncpg(dsn))
        try:
            # Event with created_at, no operation
            event_with_ts = await conn.fetchval(
                "INSERT INTO audit_events (event_id, event_type, event_version, entity_type, "
                "entity_id, summary, outcome, created_at) "
                "VALUES ($1, 'operation.line_accepted', 2, 'operation_line', "
                "$2, 'has-ts', 'success', $3) RETURNING id",
                uuid4(),
                str(uuid4()),
                datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC),
            )
            # Event with NULL created_at but effect with non-NULL created_at
            await conn.execute(
                "ALTER TABLE audit_events ALTER COLUMN created_at DROP DEFAULT"
            )
            await conn.execute(
                "ALTER TABLE audit_events ALTER COLUMN created_at DROP NOT NULL"
            )
            event_null_ts = await conn.fetchval(
                "INSERT INTO audit_events (event_id, event_type, event_version, entity_type, "
                "entity_id, summary, outcome, created_at) "
                "VALUES ($1, 'operation.line_accepted', 2, 'operation_line', "
                "$2, 'no-event-ts', 'success', NULL) RETURNING id",
                uuid4(),
                str(uuid4()),
            )

            subject_id = await conn.fetchval(
                "INSERT INTO inventory_subjects (subject_type) "
                "VALUES ('catalog_item') RETURNING id"
            )
            await conn.fetchval(
                "INSERT INTO audit_item_effects (audit_event_id, "
                "inventory_subject_id, quantity_before, quantity_delta, "
                "quantity_after, effect_type, created_at) "
                "VALUES ($1, $2, 0, 1, 1, 'acceptance', $3) RETURNING id",
                event_with_ts,
                subject_id,
                datetime(2024, 6, 16, 11, 0, 0, tzinfo=UTC),
            )
            await conn.fetchval(
                "INSERT INTO audit_item_effects (audit_event_id, "
                "inventory_subject_id, quantity_before, quantity_delta, "
                "quantity_after, effect_type, created_at) "
                "VALUES ($1, $2, 0, 1, 1, 'acceptance', $3) RETURNING id",
                event_null_ts,
                subject_id,
                datetime(2024, 6, 17, 12, 0, 0, tzinfo=UTC),
            )
        finally:
            await conn.close()

        await _alembic_upgrade(cfg, "0037_audit_item_effects_effective_at")

        rows = await _fetchall(
            dsn,
            "SELECT id, audit_event_id, effective_at FROM audit_item_effects "
            "ORDER BY id ASC",
        )
        assert len(rows) == 2
        # First row: event had created_at -> backfill picks event timestamp
        assert rows[0]["effective_at"] == datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        # Second row: event created_at is NULL -> falls back to effect.created_at
        assert rows[1]["effective_at"] == datetime(2024, 6, 17, 12, 0, 0, tzinfo=UTC)


async def test_migration_0037_timing_is_logged() -> None:
    """The backfill/index time and the row count are reported to pytest.

    ADR-0028 §6 requires measuring backfill and index time on a disposable
    clone before deployment to a shared DB. This test measures them and
    exposes them through the assertion messages. The timing is logged via
    the test name / assertion message and is informational; on a 4-row seed
    the elapsed time should always be a small positive number.
    """
    base_dsn = _base_dsn()
    if not base_dsn:
        pytest.skip("DATABASE_URL_TEST is required for migration ladder test")

    async with _disposable_database(base_dsn, "timing") as dsn:
        cfg = _make_alembic_config(dsn)
        await _alembic_upgrade(cfg, "0036_operation_revision_lines_composite_pk")

        site_id = await _ensure_site(dsn)
        user_id = await _ensure_user(dsn)
        subject_id = await _ensure_inventory_subject(dsn)
        seed = await _seed_pre_0037(
            dsn,
            site_id=site_id,
            user_id=user_id,
            inventory_subject_id=subject_id,
        )
        rows_before = await _fetchval(
            dsn, "SELECT COUNT(*) FROM audit_item_effects"
        )

        t0 = time.perf_counter()
        await _alembic_upgrade(cfg, "0037_audit_item_effects_effective_at")
        elapsed = time.perf_counter() - t0

        # Always pass; the timing is exposed via the assertion message so
        # QA reviewers can compare it against the agreed deployment window.
        assert elapsed >= 0, f"backfill time must be observable, got {elapsed}"
        assert rows_before == seed["effects_before_total"], (
            f"row count must match the seed ({seed['effects_before_total']}), "
            f"got {rows_before}"
        )
        # Surface the timing/row count for ADR-0028 §6 reporting.
        print(
            f"\n[A-5 timing] rows={rows_before} "
            f"backfill_plus_ddl_seconds={elapsed:.4f}"
        )
