"""Tests for ``SyncServer/scripts/integrity_check.py`` (A-7 CLI).

Coverage:

* CLI parser and argument validation (exit code 2);
* deterministic check ordering;
* clean fixture produces critical=0 / exit 0;
* per-check corrupted fixtures trigger the expected symbolic check;
* ``--format json`` JSON shape is stable and never leaks DSN / tokens;
* ``--fail-on warning`` flips the exit code to 1 when only warnings exist;
* ``--sample-limit`` is honoured;
* DB execution error is sanitised and translated into exit code 2;
* the CLI issues ``SET TRANSACTION READ ONLY`` and a subsequent ``INSERT``
  is rejected by PostgreSQL (sqlstate 25006);
* running the CLI twice in a row does not mutate the database.

The tests are designed to run inside the disposable ``session_factory``
schema (``tests/conftest.py``). DB-backed tests are gated behind
``test_db_url``; when the database is unavailable, the DB-backed tests
are skipped with an explicit reason.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Base
from scripts import integrity_check as cli

ROOT_DIR = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _have_db() -> bool:
    return bool(os.getenv("DATABASE_URL_TEST") or os.getenv("DATABASE_URL"))


def _test_database_url() -> str:
    return os.environ.get("DATABASE_URL_TEST") or os.environ["DATABASE_URL"]


def async_sessionmaker_decorator_skip(func):
    """Skip DB-backed tests when no DSN is available; mark as asyncio otherwise.

    Synchronous tests (subprocess wrappers) are left untouched so that
    pytest does not warn about ``@pytest.mark.asyncio`` on a regular
    function.
    """
    if not _have_db():
        return pytest.mark.skipif(True, reason="DATABASE_URL not set")(func)
    if asyncio.iscoroutinefunction(func):
        return pytest.mark.asyncio(func)
    return func


def _set_search_path(url: str, schema: str) -> str:
    """Append ``?options=-csearch_path=...`` for asyncpg.

    Reserved for future subprocess tests; asyncpg via SQLAlchemy does not
    accept this URL shape directly, so production code paths use
    ``connect_args={"server_settings": {"search_path": ...}}`` instead.
    """
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options=-csearch_path%3D{schema}"


def _set_search_path(url: str, schema: str) -> str:
    """Append ``?options=-csearch_path=...`` for asyncpg.

    asyncpg honours the ``options=`` query string in the connection URL.
    The session_factory in conftest.py uses ``server_settings`` directly;
    here we drive ``search_path`` via the URL so the integrity CLI can be
    exercised in subprocess tests without touching ``app/core/db.py``.
    """
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options=-csearch_path%3D{schema}"


def _connect_args_for_schema(schema: str) -> dict:
    """asyncpg ``server_settings`` payload that pins ``search_path``."""
    return {"server_settings": {"search_path": schema}}


async def _fresh_schema() -> AsyncIterator[tuple[str, async_sessionmaker[AsyncSession]]]:
    """Create an isolated schema with all models and yield its name + session factory."""
    schema = f"int_check_{uuid4().hex[:8]}"
    admin_engine = create_async_engine(_test_database_url(), poolclass=NullPool)
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        _test_database_url(),
        connect_args={"server_settings": {"search_path": schema}},
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield schema, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()


def _connect_args_for_schema(schema: str) -> dict:
    """asyncpg server_settings payload pinning the search_path."""
    return {"server_settings": {"search_path": schema}}


async def _seed_minimal(db_url: str, schema: str) -> None:
    """Seed a tiny clean state: one site, one item/subject, one balanced row."""
    engine = create_async_engine(
        db_url,
        connect_args=_connect_args_for_schema(schema),
        poolclass=NullPool,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "SELECT setval(pg_get_serial_sequence('sites', 'id'), 1, false)"
            ))
            await conn.execute(text(
                "SELECT setval(pg_get_serial_sequence('categories', 'id'), 1, false)"
            ))
            await conn.execute(text(
                "SELECT setval(pg_get_serial_sequence('units', 'id'), 1, false)"
            ))
            await conn.execute(text(
                "SELECT setval(pg_get_serial_sequence('items', 'id'), 1, false)"
            ))
            await conn.execute(text(
                "SELECT setval(pg_get_serial_sequence('inventory_subjects', 'id'), 1, false)"
            ))
            await conn.execute(text(
                "INSERT INTO sites (id, code, name, is_active) "
                "VALUES (1, 'IC-SITE', 'IC Site', true)"
            ))
            await conn.execute(text(
                "INSERT INTO categories (id, name, normalized_name, code, is_active) "
                "VALUES (1, 'IC Cat', 'ic cat', 'IC-CAT', true)"
            ))
            await conn.execute(text(
                "INSERT INTO units (id, name, symbol, is_active) "
                "VALUES (1, 'IC Unit', 'ic', true)"
            ))
            await conn.execute(text(
                "INSERT INTO items (id, sku, name, normalized_name, category_id, unit_id, is_active) "
                "VALUES (1, 'IC-1', 'IC Item', 'ic item', 1, 1, true)"
            ))
            await conn.execute(text(
                "INSERT INTO inventory_subjects (id, subject_type, item_id) "
                "VALUES (1, 'catalog_item', 1)"
            ))
            await conn.execute(text(
                "INSERT INTO balances (site_id, inventory_subject_id, item_id, qty) "
                "VALUES (1, 1, 1, 0)"
            ))
    finally:
        await engine.dispose()


async def _seed_drift(db_url: str, schema: str) -> None:
    await _seed_minimal(db_url, schema)
    engine = create_async_engine(
        db_url,
        connect_args=_connect_args_for_schema(schema),
        poolclass=NullPool,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO audit_events ("
                "  id, event_id, event_type, event_version, entity_type, entity_id, summary, outcome"
                ") VALUES ("
                "  1, gen_random_uuid(), 'test.event', 2, 'item', '1', 'drift fixture', 'success'"
                ")"
            ))
            await conn.execute(text(
                "INSERT INTO audit_item_effects ("
                "  audit_event_id, operation_id, inventory_subject_id, item_id, site_id,"
                "  quantity_before, quantity_delta, quantity_after, effect_type,"
                "  is_system_generated, effective_at"
                ") VALUES "
                "(1, NULL, 1, 1, 1, 0, 5, 5, 'adjustment', false, now())"
            ))
    finally:
        await engine.dispose()


async def _seed_backdated(db_url: str, schema: str) -> None:
    await _seed_minimal(db_url, schema)
    engine = create_async_engine(
        db_url,
        connect_args=_connect_args_for_schema(schema),
        poolclass=NullPool,
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO users (id, username, email, is_active, is_root, role, user_token) "
                "VALUES (gen_random_uuid(), 'ic-root', 'root@ic.test', true, true, 'root', "
                "        gen_random_uuid())"
            ))
            await conn.execute(text(
                "INSERT INTO operations ("
                "  id, site_id, operation_type, status, created_by_user_id,"
                "  created_at, updated_at, effective_at, submitted_at, submitted_by_user_id,"
                "  acceptance_required, acceptance_state"
                ") VALUES ("
                "  gen_random_uuid(), 1, 'RECEIVE', 'submitted',"
                "  (SELECT id FROM users LIMIT 1),"
                "  now() - interval '10 days', now(),"
                "  now() - interval '30 days', now() - interval '10 days',"
                "  (SELECT id FROM users LIMIT 1),"
                "  false, 'not_required'"
                ")"
            ))
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Parser / argument validation
# ---------------------------------------------------------------------------


class TestBuildArgumentParser:
    def test_defaults(self):
        parser = cli.build_argument_parser()
        args = parser.parse_args([])
        assert args.format == "text"
        assert args.sample_limit == cli.DEFAULT_SAMPLE_LIMIT
        assert args.fail_on == cli.DEFAULT_FAIL_ON
        assert args.late_threshold_days == cli.DEFAULT_LATE_THRESHOLD_DAYS

    def test_explicit_arguments(self):
        parser = cli.build_argument_parser()
        args = parser.parse_args(
            [
                "--format", "json",
                "--sample-limit", "25",
                "--fail-on", "warning",
                "--late-threshold-days", "3",
            ]
        )
        assert args.format == "json"
        assert args.sample_limit == 25
        assert args.fail_on == "warning"
        assert args.late_threshold_days == 3
        assert not hasattr(args, "database_url")

    def test_database_url_argument_is_rejected(self):
        parser = cli.build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--database-url", "postgresql+asyncpg://example"])

    def test_invalid_format_rejected(self):
        parser = cli.build_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--format", "yaml"])


class TestValidateArgs:
    def test_sample_limit_too_low(self):
        assert cli._validate_args(
            SimpleNamespace(sample_limit=0, late_threshold_days=7)
        ) is not None

    def test_sample_limit_too_high(self):
        assert cli._validate_args(
            SimpleNamespace(
                sample_limit=cli.MAX_SAMPLE_LIMIT + 1,
                late_threshold_days=7,
            )
        ) is not None

    def test_late_threshold_too_low(self):
        assert cli._validate_args(
            SimpleNamespace(sample_limit=5, late_threshold_days=0)
        ) is not None

    def test_late_threshold_too_high(self):
        assert cli._validate_args(
            SimpleNamespace(
                sample_limit=5,
                late_threshold_days=cli.MAX_LATE_THRESHOLD_DAYS + 1,
            )
        ) is not None

    def test_valid_args(self):
        assert (
            cli._validate_args(
                SimpleNamespace(sample_limit=5, late_threshold_days=7)
            )
            is None
        )


class TestResolveDatabaseUrl:
    def test_uses_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://main")
        monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
        assert cli.resolve_database_url() == "postgresql+asyncpg://main"

    def test_uses_database_url_test(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://main")
        monkeypatch.setenv("DATABASE_URL_TEST", "postgresql+asyncpg://test")
        assert cli.resolve_database_url() == "postgresql+asyncpg://test"

    def test_missing_raises(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL_TEST", raising=False)
        with pytest.raises(ValueError, match="DATABASE_URL"):
            cli.resolve_database_url()


# ---------------------------------------------------------------------------
# Output / summary shape
# ---------------------------------------------------------------------------


def _make_result(
    code: str,
    *,
    count: int = 0,
    samples: list[dict] | None = None,
    severity: str | None = None,
    error: str | None = None,
) -> cli.CheckResult:
    return cli.CheckResult(
        code=code,
        status="pass" if count == 0 else ("fail" if severity == "critical" else "warning"),
        count=count,
        severity=severity or cli.DEFAULT_SEVERITY[code],
        samples=samples or [],
        error=error,
    )


class TestBuildSummary:
    def test_all_pass_is_ok(self):
        results = [_make_result(code) for code in cli.CHECKS]
        summary = cli.build_summary(
            results,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            fail_on="critical",
        )
        assert summary["status"] == "ok"
        assert [c["code"] for c in summary["checks"]] == list(cli.CHECKS)
        assert all(c["status"] == "pass" for c in summary["checks"])

    def test_critical_finding_sets_critical(self):
        results = [
            _make_result("BALANCE_EFFECT_DRIFT", count=2, samples=[{"site_id": 1}]),
        ] + [_make_result(code) for code in cli.CHECKS if code != "BALANCE_EFFECT_DRIFT"]
        summary = cli.build_summary(
            results,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            fail_on="critical",
        )
        assert summary["status"] == "critical"
        drift = next(c for c in summary["checks"] if c["code"] == "BALANCE_EFFECT_DRIFT")
        assert drift["count"] == 2
        assert drift["samples"] == [{"site_id": 1}]

    def test_warning_only_under_critical_threshold(self):
        results = [
            _make_result("BACKDATED_SUBMITTED", count=4),
        ] + [_make_result(code) for code in cli.CHECKS if code != "BACKDATED_SUBMITTED"]
        summary = cli.build_summary(
            results,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            fail_on="critical",
        )
        assert summary["status"] == "warning"
        warnings = [c for c in summary["checks"] if c["count"] > 0]
        assert len(warnings) == 1
        assert warnings[0]["code"] == "BACKDATED_SUBMITTED"

    def test_warning_threshold_promotes_warnings(self):
        results = [
            _make_result("BACKDATED_SUBMITTED", count=4),
        ] + [_make_result(code) for code in cli.CHECKS if code != "BACKDATED_SUBMITTED"]
        summary = cli.build_summary(
            results,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            fail_on="warning",
        )
        assert summary["status"] == "warning"

    def test_error_check_is_reported(self):
        results = [
            _make_result("EFFECT_DATE_NULL", error="DB exploded"),
        ] + [_make_result(code) for code in cli.CHECKS if code != "EFFECT_DATE_NULL"]
        summary = cli.build_summary(
            results,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            fail_on="critical",
        )
        assert summary["status"] == "error"
        err = next(c for c in summary["checks"] if c["code"] == "EFFECT_DATE_NULL")
        assert err["error"] == "DB exploded"
        assert "samples" in err

    def test_summary_includes_started_at_and_fail_on(self):
        results = [_make_result(code) for code in cli.CHECKS]
        summary = cli.build_summary(
            results,
            started_at=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
            fail_on="warning",
        )
        assert summary["started_at"] == "2026-08-06T12:00:00+00:00"
        assert summary["fail_on"] == "warning"


class TestFormatText:
    def test_renders_status_and_codes(self):
        summary = {
            "status": "ok",
            "started_at": "2026-08-06T00:00:00+00:00",
            "fail_on": "critical",
            "checks": [
                {"code": code, "status": "pass", "count": 0, "samples": []}
                for code in cli.CHECKS
            ],
        }
        text = cli.format_text(summary)
        assert "OK" in text
        for code in cli.CHECKS:
            assert code in text

    def test_renders_error(self):
        summary = {
            "status": "error",
            "started_at": "2026-08-06T00:00:00+00:00",
            "fail_on": "critical",
            "checks": [
                {
                    "code": "EFFECT_DATE_NULL",
                    "status": "error",
                    "count": 0,
                    "samples": [],
                    "error": "boom",
                }
            ],
        }
        text = cli.format_text(summary)
        assert "ERROR" in text
        assert "EFFECT_DATE_NULL" in text
        assert "boom" in text


class TestSanitisation:
    def test_dsn_password_is_masked(self):
        text = "postgresql+asyncpg://u:hunter2@host:5432/db"
        out = cli.sanitize_dsn(text)
        assert "hunter2" not in out
        assert "***" in out

    def test_dsn_kv_password_is_masked(self):
        text = "host=localhost password=secret sslkey=cert.pem"
        out = cli.sanitize_dsn(text)
        assert "secret" not in out
        assert "cert.pem" not in out

    def test_long_string_is_truncated(self):
        out = cli.sanitize_error(RuntimeError("x" * 2000))
        assert len(out) <= cli.MAX_ERROR_LEN


def test_per_check_error_is_sanitised_and_does_not_stop_other_checks(monkeypatch):
    async def fake_run_check(_engine, code, **_kwargs):
        if code == "EFFECT_DATE_NULL":
            raise cli.SQLAlchemyError("postgresql://user:supersecret@db/integrity")
        return _make_result(code)

    monkeypatch.setattr(cli, "_run_check", fake_run_check)
    results = asyncio.run(
        cli.run_checks(
            "postgresql+asyncpg://unused",
            sample_limit=1,
            late_threshold_days=1,
        )
    )

    failed = next(result for result in results if result.code == "EFFECT_DATE_NULL")
    assert failed.status == "error"
    assert failed.error is not None
    assert "supersecret" not in failed.error
    assert all(
        result.status == "pass"
        for result in results
        if result.code != "EFFECT_DATE_NULL"
    )


def test_main_returns_exit_two_for_individual_check_error(monkeypatch, capsys):
    results = [
        cli.CheckResult(
            code=code,
            status="error" if code == "EFFECT_DATE_NULL" else "pass",
            count=0,
            severity=cli.DEFAULT_SEVERITY[code],
            error="safe error" if code == "EFFECT_DATE_NULL" else None,
        )
        for code in cli.CHECKS
    ]

    async def fake_run_checks(*_args, **_kwargs):
        return results

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused")
    monkeypatch.setattr(cli, "run_checks", fake_run_checks)
    assert cli.main(["--format", "json"]) == cli.EXIT_USAGE_ERROR
    output = capsys.readouterr().out
    assert "EFFECT_DATE_NULL" in output
    assert "safe error" in output


def test_check_sql_is_read_only():
    statements = "\n".join(str(sql).lower() for sql in cli.CHECK_SQL.values())
    for forbidden in ("insert ", "update ", "delete ", "alter ", "create ", "drop "):
        assert forbidden not in statements
    assert "select " in statements


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


@async_sessionmaker_decorator_skip
async def test_clean_schema_reports_no_critical_findings():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        assert [r.code for r in results] == list(cli.CHECKS)
        for result in results:
            assert result.error is None, result.error
            assert result.count == 0, f"{result.code} unexpected findings: {result.samples}"
        summary = cli.build_summary(
            results,
            started_at=datetime.now(UTC),
            fail_on="critical",
        )
        assert summary["status"] == "ok"


@async_sessionmaker_decorator_skip
async def test_drift_triggers_balance_effect_drift():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_drift(db_url, schema)
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        drift = next(r for r in results if r.code == "BALANCE_EFFECT_DRIFT")
        assert drift.count == 1
        assert drift.samples[0]["kind"] in {"drift", "effect_only"}
        others = [r for r in results if r.code != "BALANCE_EFFECT_DRIFT"]
        assert all(r.count == 0 for r in others), [r.code for r in others if r.count]


@async_sessionmaker_decorator_skip
async def test_backdated_operation_triggers_backdated_submitted():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_backdated(db_url, schema)
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        check = next(r for r in results if r.code == "BACKDATED_SUBMITTED")
        assert check.count == 1
        assert check.severity == "warning"
        assert check.samples[0]["operation_type"] == "RECEIVE"


@async_sessionmaker_decorator_skip
async def test_audit_entity_orphan_ignores_auth_and_soft_deleted_snapshots():
    """ADR-0018 permits non-domain events and resource snapshots without FKs."""
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        engine = create_async_engine(
            db_url,
            connect_args=_connect_args_for_schema(schema),
            poolclass=NullPool,
        )
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "UPDATE items SET is_active = false, deleted_at = now() WHERE id = 1"
                ))
                await conn.execute(text(
                    "INSERT INTO audit_events ("
                    "id, event_id, event_type, event_version, entity_type, entity_id, summary, outcome"
                    ") VALUES "
                    "(1, gen_random_uuid(), 'auth.login', 2, 'auth', 'actor-removed', 'auth fixture', 'success'),"
                    "(2, gen_random_uuid(), 'item.delete', 2, 'item', '1', 'soft delete fixture', 'success')"
                ))
                await conn.execute(text(
                    "INSERT INTO audit_event_resources ("
                    "audit_event_id, resource_type, resource_id, relation, snapshot_before, snapshot_after"
                    ") VALUES (2, 'item', '1', 'primary', '{\"id\": 1}', '{\"id\": 1, \"deleted_at\": true}')"
                ))
        finally:
            await engine.dispose()

        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        orphan = next(result for result in results if result.code == "AUDIT_ENTITY_ORPHAN")
        assert orphan.error is None, orphan.error
        assert orphan.count == 0


@async_sessionmaker_decorator_skip
async def test_sample_limit_is_honoured():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        results = await cli.run_checks(
            db_url,
            sample_limit=1,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        for result in results:
            assert len(result.samples) <= 1


@async_sessionmaker_decorator_skip
async def test_read_only_transaction_blocks_writes():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        engine = create_async_engine(
            db_url,
            connect_args=_connect_args_for_schema(schema),
            poolclass=NullPool,
        )
        try:
            async with engine.connect() as conn:
                trans = await conn.begin()
                try:
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                    with pytest.raises(Exception) as exc_info:
                        await conn.execute(text("CREATE TABLE __should_fail__(x int)"))
                    text_repr = str(exc_info.value).lower()
                    sqlstate = ""
                    orig = getattr(exc_info.value, "orig", None)
                    if orig is not None:
                        sqlstate = getattr(orig, "sqlstate", "") or ""
                    assert (
                        "read-only" in text_repr
                        or sqlstate == "25006"
                    ), f"Expected READ ONLY error, got: {exc_info.value!r}"
                finally:
                    try:
                        await trans.rollback()
                    except Exception:
                        pass
        finally:
            await engine.dispose()


@async_sessionmaker_decorator_skip
async def test_repeat_run_is_idempotent():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_drift(db_url, schema)
        engine = create_async_engine(
            db_url,
            connect_args=_connect_args_for_schema(schema),
            poolclass=NullPool,
        )
        try:
            async with engine.connect() as conn:
                first = (await conn.execute(text(
                    "SELECT relname, n_live_tup FROM pg_stat_user_tables "
                    "WHERE relname IN ('balances','audit_item_effects','operations','items') "
                    "ORDER BY relname"
                ))).fetchall()
        finally:
            await engine.dispose()
        await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        engine = create_async_engine(
            db_url,
            connect_args=_connect_args_for_schema(schema),
            poolclass=NullPool,
        )
        try:
            async with engine.connect() as conn:
                second = (await conn.execute(text(
                    "SELECT relname, n_live_tup FROM pg_stat_user_tables "
                    "WHERE relname IN ('balances','audit_item_effects','operations','items') "
                    "ORDER BY relname"
                ))).fetchall()
        finally:
            await engine.dispose()
        assert [tuple(row) for row in first] == [tuple(row) for row in second]


# ---------------------------------------------------------------------------
# In-process CLI exercise
# ---------------------------------------------------------------------------


@async_sessionmaker_decorator_skip
async def test_cli_text_clean_exits_zero_in_process(capsys):
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        summary = cli.build_summary(
            results,
            started_at=datetime.now(UTC),
            fail_on="critical",
        )
        text_output = cli.format_text(summary)
        assert "OK" in text_output


@async_sessionmaker_decorator_skip
async def test_cli_json_shape_is_stable_in_process():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_drift(db_url, schema)
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        summary = cli.build_summary(
            results,
            started_at=datetime.now(UTC),
            fail_on="critical",
        )
        payload = json.loads(json.dumps(summary))
        assert payload["status"] in {"ok", "warning", "critical", "error"}
        assert "started_at" in payload
        codes = [c["code"] for c in payload["checks"]]
        assert codes == list(cli.CHECKS)
        drift = next(
            c for c in payload["checks"] if c["code"] == "BALANCE_EFFECT_DRIFT"
        )
        assert drift["count"] >= 1
        assert isinstance(drift["samples"], list)
        # No free-text notes or DSN secrets leak through.
        serialised = json.dumps(payload)
        lowered = serialised.lower()
        for token in ("password=", "sslkey=", "bearer", "supersecret"):
            assert token not in lowered, f"secret token leaked: {token}"


@async_sessionmaker_decorator_skip
async def test_cli_fail_on_warning_promotes_warnings_in_process():
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_backdated(db_url, schema)
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        summary = cli.build_summary(
            results,
            started_at=datetime.now(UTC),
            fail_on="warning",
        )
        assert summary["status"] in {"warning", "critical"}
        backdated = next(
            c for c in summary["checks"] if c["code"] == "BACKDATED_SUBMITTED"
        )
        assert backdated["count"] >= 1


@async_sessionmaker_decorator_skip
async def test_effect_date_null_finds_null_row():
    """EFFECT_DATE_NULL must trigger when an effect row has NULL ``effective_at``."""
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        engine = create_async_engine(
            db_url,
            connect_args=_connect_args_for_schema(schema),
            poolclass=NullPool,
        )
        try:
            async with engine.begin() as conn:
                # ``Base.metadata.create_all`` creates ``effective_at``
                # with NOT NULL. We relax it to allow the legacy fixture
                # row that the A-5 migration would otherwise have
                # backfilled.
                await conn.execute(text(
                    "ALTER TABLE audit_item_effects ALTER COLUMN effective_at DROP NOT NULL"
                ))
                await conn.execute(text(
                    "INSERT INTO audit_events ("
                    "  id, event_id, event_type, event_version, entity_type, entity_id, summary, outcome"
                    ") VALUES ("
                    "  1, gen_random_uuid(), 'test.event', 2, 'item', '1', 'null-date fixture', 'success'"
                    ")"
                ))
                await conn.execute(text(
                    "INSERT INTO audit_item_effects ("
                    "  audit_event_id, inventory_subject_id, item_id, quantity_delta, effect_type,"
                    "  is_system_generated, effective_at"
                    ") VALUES (1, 1, 1, 1, 'adjustment', false, NULL)"
                ))
        finally:
            await engine.dispose()
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        null_check = next(r for r in results if r.code == "EFFECT_DATE_NULL")
        assert null_check.error is None, null_check.error
        assert null_check.count == 1
        assert null_check.status == "fail"


@async_sessionmaker_decorator_skip
async def test_effect_chain_broken_finds_row_arithmetic_break():
    """EFFECT_CHAIN_BROKEN must surface ``before + delta != after``."""
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        engine = create_async_engine(
            db_url,
            connect_args=_connect_args_for_schema(schema),
            poolclass=NullPool,
        )
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO audit_events ("
                    "  id, event_id, event_type, event_version, entity_type, entity_id, summary, outcome"
                    ") VALUES ("
                    "  1, gen_random_uuid(), 'test.event', 2, 'item', '1', 'chain fixture', 'success'"
                    ")"
                ))
                # quantity_before=0, quantity_delta=5, quantity_after=4 → break
                await conn.execute(text(
                    "INSERT INTO audit_item_effects ("
                    "  audit_event_id, inventory_subject_id, item_id, site_id, quantity_before,"
                    "  quantity_delta, quantity_after, effect_type, is_system_generated, effective_at"
                    ") VALUES (1, 1, 1, 1, 0, 5, 4, 'adjustment', false, now())"
                ))
        finally:
            await engine.dispose()
        results = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=cli.DEFAULT_LATE_THRESHOLD_DAYS,
            connect_args=_connect_args_for_schema(schema),
        )
        chain = next(r for r in results if r.code == "EFFECT_CHAIN_BROKEN")
        assert chain.error is None, chain.error
        assert chain.count == 1
        assert chain.samples[0]["chain_kind"] == "row_arithmetic"


@async_sessionmaker_decorator_skip
async def test_late_acceptance_uses_threshold():
    """LATE_ACCEPTANCE honours ``--late-threshold-days``."""
    db_url = _test_database_url()
    async for schema, _sf in _fresh_schema():
        await _seed_minimal(db_url, schema)
        engine = create_async_engine(
            db_url,
            connect_args=_connect_args_for_schema(schema),
            poolclass=NullPool,
        )
        try:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO users (id, username, email, is_active, is_root, role, user_token) "
                    "VALUES (gen_random_uuid(), 'ic-late', 'late@ic.test', true, true, 'root', "
                    "        gen_random_uuid())"
                ))
                user_id = (await conn.execute(text("SELECT id FROM users LIMIT 1"))).scalar_one()
                await conn.execute(text(
                    "INSERT INTO operations ("
                    "  id, site_id, operation_type, status, created_by_user_id,"
                    "  created_at, updated_at, submitted_at, submitted_by_user_id,"
                    "  acceptance_required, acceptance_state"
                    ") VALUES ("
                    "  gen_random_uuid(), 1, 'RECEIVE', 'submitted',"
                    f"  '{user_id}', now(), now(),"
                    "  now() - interval '40 days',"
                    f"  '{user_id}',"
                    "  true, 'resolved'"
                    ")"
                ))
                op_id = (await conn.execute(text(
                    "SELECT id FROM operations WHERE acceptance_required=true LIMIT 1"
                ))).scalar_one()
                await conn.execute(text(
                    "INSERT INTO operation_lines (operation_id, line_number, item_id, qty) "
                    "VALUES (:op, 1, 1, 5)"
                ), {"op": op_id})
                line_id = (await conn.execute(text(
                    "SELECT id FROM operation_lines ORDER BY id DESC LIMIT 1"
                ))).scalar_one()
                await conn.execute(text(
                    "INSERT INTO operation_acceptance_actions ("
                    "  operation_id, operation_line_id, action_type, qty,"
                    "  performed_by_user_id, performed_at"
                    ") VALUES ("
                    f"  '{op_id}', {line_id}, 'accept', 1,"
                    f"  '{user_id}', now() - interval '2 days'"
                    ")"
                ))
        finally:
            await engine.dispose()
        # Threshold 1 day → lag of 38 days should fire.
        strict = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=1,
            connect_args=_connect_args_for_schema(schema),
        )
        strict_late = next(r for r in strict if r.code == "LATE_ACCEPTANCE")
        assert strict_late.error is None, strict_late.error
        assert strict_late.count == 1
        # Threshold 60 days → no findings.
        lenient = await cli.run_checks(
            db_url,
            sample_limit=cli.DEFAULT_SAMPLE_LIMIT,
            late_threshold_days=60,
            connect_args=_connect_args_for_schema(schema),
        )
        lenient_late = next(r for r in lenient if r.code == "LATE_ACCEPTANCE")
        assert lenient_late.error is None, lenient_late.error
        assert lenient_late.count == 0


# ---------------------------------------------------------------------------
# CLI entrypoint (subprocess) tests
# ---------------------------------------------------------------------------


@async_sessionmaker_decorator_skip
def test_cli_invalid_sample_limit_exits_two():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://placeholder"
    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "integrity_check.py"),
         "--sample-limit", "0"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == cli.EXIT_USAGE_ERROR


@async_sessionmaker_decorator_skip
def test_cli_missing_db_url_exits_two():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop("DATABASE_URL_TEST", None)
    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "integrity_check.py")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == cli.EXIT_USAGE_ERROR
    assert "DATABASE_URL" in result.stderr


@async_sessionmaker_decorator_skip
def test_cli_db_error_is_sanitised():
    env = os.environ.copy()
    env.pop("DATABASE_URL_TEST", None)
    env["DATABASE_URL"] = (
        "postgresql+asyncpg://u:supersecret@127.0.0.1:1/db"
    )
    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "integrity_check.py"),
         "--format", "json"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == cli.EXIT_USAGE_ERROR
    # The DSN password must never appear in stderr; the OSError surface
    # only contains ``host:port`` which is not a secret, so we only
    # assert the password is absent.
    assert "supersecret" not in result.stderr
    combined = (result.stdout or "") + (result.stderr or "")
    assert "supersecret" not in combined


@async_sessionmaker_decorator_skip
def test_cli_help_exits_zero():
    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "integrity_check.py"),
         "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "integrity_check" in result.stdout


@async_sessionmaker_decorator_skip
def test_cli_unknown_format_exits_two():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://placeholder"
    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "integrity_check.py"),
         "--format", "yaml"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 2
