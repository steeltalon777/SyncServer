"""Migration ladder for ``0038_add_agent_role`` (ADR-0030, TZ rev.2 §3.2).

Runs against an isolated disposable PostgreSQL database, mirroring the
pattern of ``test_audit_item_effects_effective_at_migration.py``:

    alembic upgrade 0037
    seed users with the four legacy roles
    alembic upgrade 0038  -> ck_users_role now accepts 'agent';
                             'agent' insert works, bogus role fails
    alembic downgrade 0037 -> RuntimeError because agent rows still exist
    delete agent rows
    alembic downgrade 0037 -> ok, four-role constraint restored;
                             'agent' insert now fails
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import asyncpg
import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

_ADMIN_DSN_ENV = "POSTGRES_ADMIN_DSN"
_TEST_DSN_ENV = "DATABASE_URL_TEST"

REV_PRE_AGENT = "0037_audit_item_effects_effective_at"


def _base_dsn() -> str:
    return os.environ.get(_TEST_DSN_ENV) or os.environ.get("DATABASE_URL") or ""


def _dsn_with_database(dsn: str, database: str) -> str:
    parsed = _parse_dsn(dsn)
    parsed["database"] = database
    return _format_dsn(parsed, keep_driver=True)


def _dsn_to_asyncpg(dsn: str) -> str:
    return _format_dsn(_parse_dsn(dsn), keep_driver=False)


def _parse_dsn(dsn: str) -> dict[str, str | int | None]:
    scheme_part, _, rest = dsn.partition("://")
    driver = None
    if "+" in scheme_part:
        scheme, _, driver = scheme_part.partition("+")
    else:
        scheme = scheme_part
    from urllib.parse import unquote, urlparse

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


async def _create_disposable_database(dsn: str, name: str) -> None:
    admin_url = _dsn_to_asyncpg(_dsn_with_database(dsn, "postgres"))
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await conn.execute(f'CREATE DATABASE "{name}"')
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


async def _precreate_alembic_version(dsn: str, name: str) -> None:
    """Create alembic_version with a wide version_num column.

    Revision ids like ``0037_audit_item_effects_effective_at`` (37 chars)
    exceed the default VARCHAR(32); mirror the 0037 migration ladder test.
    """
    conn = await asyncpg.connect(_dsn_to_asyncpg(_dsn_with_database(dsn, name)))
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(128) NOT NULL)"
        )
    finally:
        await conn.close()


@asynccontextmanager
async def _disposable_database(base_dsn: str, suffix: str) -> AsyncIterator[str]:
    if not base_dsn:
        pytest.skip("DATABASE_URL_TEST/DATABASE_URL is required for migration ladder test")
    name = f"agent_role_mig_{suffix}_{int(time.time() * 1000)}"
    await _create_disposable_database(base_dsn, name)
    await _precreate_alembic_version(base_dsn, name)
    dsn = _dsn_with_database(base_dsn, name)
    try:
        yield dsn
    finally:
        await _drop_disposable_database(base_dsn, name)


def _make_alembic_config(database_url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    return cfg


async def _alembic_upgrade(cfg: AlembicConfig, revision: str) -> None:
    await asyncio.to_thread(alembic_command.upgrade, cfg, revision)


async def _alembic_downgrade(cfg: AlembicConfig, revision: str) -> None:
    await asyncio.to_thread(alembic_command.downgrade, cfg, revision)


async def _execute(dsn: str, sql: str, *args) -> None:
    conn = await asyncpg.connect(_dsn_to_asyncpg(dsn))
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _fetchval(dsn: str, sql: str, *args) -> object:
    conn = await asyncpg.connect(_dsn_to_asyncpg(dsn))
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


_INSERT_USER = """
INSERT INTO users (id, username, email, user_token, is_active, is_root, role)
VALUES ($1, $2, $3, $4, true, false, $5)
"""


@pytest.mark.asyncio
async def test_0038_agent_role_migration_ladder() -> None:
    suffix = uuid4().hex[:8]
    async with _disposable_database(_base_dsn(), suffix) as dsn:
        cfg = _make_alembic_config(dsn)
        await _alembic_upgrade(cfg, REV_PRE_AGENT)

        # Seed legacy users (upgrade to 0038 must not touch data).
        for idx, role in enumerate(("root", "chief_storekeeper", "storekeeper", "observer")):
            await _execute(
                dsn,
                _INSERT_USER,
                uuid4(), f"legacy-{idx}-{suffix}", f"legacy{idx}@{suffix}.example.com", uuid4(), role,
            )

        # Upgrade to head (0038) — constraint accepts 'agent'.
        await _alembic_upgrade(cfg, "head")
        await _execute(
            dsn,
            _INSERT_USER,
            uuid4(), f"agent-{suffix}", f"agent@{suffix}.example.com", uuid4(), "agent",
        )
        count = await _fetchval(dsn, "SELECT COUNT(*) FROM users WHERE role = 'agent'")
        assert count == 1

        # Bogus role still rejected by the (recreated) constraint.
        with pytest.raises(Exception) as excinfo:
            await _execute(
                dsn,
                _INSERT_USER,
                uuid4(), f"bogus-{suffix}", f"bogus@{suffix}.example.com", uuid4(), "bogus",
            )
        assert "ck_users_role" in str(excinfo.value) or "violates check constraint" in str(excinfo.value)

        # Downgrade with agent rows present -> explicit RuntimeError with operator instruction.
        with pytest.raises(Exception) as excinfo:
            await _alembic_downgrade(cfg, REV_PRE_AGENT)
        assert "role='agent'" in str(excinfo.value) or "agent" in str(excinfo.value)
        # Schema unchanged after refused downgrade.
        assert await _fetchval(dsn, "SELECT COUNT(*) FROM users WHERE role = 'agent'") == 1

        # Remove agent rows -> downgrade restores the four-role constraint.
        await _execute(dsn, "DELETE FROM users WHERE role = 'agent'")
        await _alembic_downgrade(cfg, REV_PRE_AGENT)
        version = await _fetchval(dsn, "SELECT version_num FROM alembic_version")
        assert version == REV_PRE_AGENT

        # Four-role constraint restored: agent insert now fails.
        with pytest.raises(Exception) as excinfo:
            await _execute(
                dsn,
                _INSERT_USER,
                uuid4(), f"agent-again-{suffix}", f"agent2@{suffix}.example.com", uuid4(), "agent",
            )
        assert "ck_users_role" in str(excinfo.value) or "violates check constraint" in str(excinfo.value)
