from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


logger = logging.getLogger(__name__)

ALEMBIC_BASELINE_REVISION = "0001_initial_baseline"
MIGRATION_LOCK_ID = 2026040801

MigrationPlan = Literal[
    "upgrade_head",
    "stamp_head",
    "stamp_baseline_then_upgrade_head",
]

APP_TABLES = {
    "balances",
    "categories",
    "devices",
    "events",
    "items",
    "operation_lines",
    "operations",
    "sites",
    "units",
    "user_access_scopes",
    "users",
}

HEAD_TABLE_MARKERS = {
    "machine_batches",
    "machine_reports",
    "machine_snapshots",
}

HEAD_COLUMN_MARKERS = {
    "categories": {"normalized_name", "machine_last_batch_id"},
    "items": {
        "normalized_name",
        "source_system",
        "source_ref",
        "import_batch_id",
        "machine_last_batch_id",
    },
    "operations": {"version", "machine_last_batch_id"},
    "units": {"code", "machine_last_batch_id"},
}


async def ensure_database_ready(database_url: str | None = None) -> None:
    settings = get_settings()
    target_url = database_url or settings.DATABASE_URL
    engine = create_async_engine(target_url, poolclass=NullPool)

    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            try:
                plan = await _detect_migration_plan(conn)
                logger.info("database migration plan selected: %s", plan)
                await asyncio.to_thread(_run_migration_plan, target_url, plan)
            finally:
                await conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": MIGRATION_LOCK_ID},
                )
    finally:
        await engine.dispose()


async def _detect_migration_plan(conn: AsyncConnection) -> MigrationPlan:
    alembic_version_exists = (
        await conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'alembic_version'
                )
                """
            )
        )
    ).scalar_one()

    if alembic_version_exists:
        return "upgrade_head"

    existing_tables = {
        row[0]
        for row in (
            await conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
            )
        ).fetchall()
    }

    if not (APP_TABLES & existing_tables):
        return "upgrade_head"

    has_head_tables = HEAD_TABLE_MARKERS.issubset(existing_tables)
    has_head_columns = True

    for table_name, expected_columns in HEAD_COLUMN_MARKERS.items():
        actual_columns = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = :table_name
                        """
                    ),
                    {"table_name": table_name},
                )
            ).fetchall()
        }
        if not expected_columns.issubset(actual_columns):
            has_head_columns = False
            break

    if has_head_tables and has_head_columns:
        return "stamp_head"

    return "stamp_baseline_then_upgrade_head"


def _run_migration_plan(database_url: str, plan: MigrationPlan) -> None:
    config = _build_alembic_config(database_url)

    if plan == "stamp_head":
        command.stamp(config, "head")
        return

    if plan == "stamp_baseline_then_upgrade_head":
        command.stamp(config, ALEMBIC_BASELINE_REVISION)

    command.upgrade(config, "head")


def _build_alembic_config(database_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config
