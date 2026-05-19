"""Alembic migration integration test.

Verifies that all migrations can be applied cleanly against a fresh test schema
and that all expected tables exist after upgrade head.

Requires a real PostgreSQL database (DATABASE_URL_TEST or DATABASE_URL).
"""

import os
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _test_database_url() -> str:
    url = os.getenv("DATABASE_URL_TEST") or os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL_TEST or DATABASE_URL is required")
    return url


# Full list of tables expected after all migrations are applied.
# Compiled from all migration files in alembic/versions/.
EXPECTED_TABLES = {
    # 0001_initial_baseline
    "categories",
    "sites",
    "units",
    "devices",
    "items",
    "users",
    "balances",
    "events",
    "operations",
    "user_access_scopes",
    "operation_lines",
    # 0002_machine_api_stage1
    "machine_snapshots",
    "machine_reports",
    "machine_batches",
    # 0004_operations_acceptance_asset_registers
    "recipients",
    "recipient_aliases",
    "pending_acceptance_balances",
    "lost_asset_balances",
    "issued_asset_balances",
    "operation_acceptance_actions",
    # 0005_documents_tables
    "documents",
    "document_operations",
    # 0006_document_sources
    "document_sources",
    # 0007_temporary_items_phase1
    "temporary_items",
    # 0008_inventory_subjects_backfill
    "inventory_subjects",
}

# Valid migration revision IDs (for stale entry cleanup)
VALID_REVISIONS = (
    "'0001_initial_baseline'",
    "'0002_machine_api_stage1'",
    "'0003_items_hashtags_reconcile'",
    "'1d1801ed5535'",
    "'0004_operations_acceptance_asset_registers'",
    "'0005_documents_tables'",
    "'0006_document_sources'",
    "'0007_temporary_items_phase1'",
    "'0008_inventory_subjects_backfill'",
    "'0009_add_temporary_draft_payload'",
)


def _run_alembic_in_schema(project_root: str, alembic_ini: str, db_url: str, schema: str) -> subprocess.CompletedProcess:
    """Run alembic upgrade head in a specific PostgreSQL schema.

    Creates a temporary alembic directory with a modified env.py that sets
    search_path before running migrations, since asyncpg doesn't support
    the 'options' URL parameter.
    """
    src_alembic = os.path.join(project_root, "alembic")

    with tempfile.TemporaryDirectory(prefix="alembic_test_") as tmpdir:
        # Copy versions directory
        tmp_versions = os.path.join(tmpdir, "versions")
        shutil.copytree(os.path.join(src_alembic, "versions"), tmp_versions)

        # Write modified env.py that sets search_path via connect_args
        # so every connection from the engine uses the test schema.
        env_py = os.path.join(tmpdir, "env.py")
        with open(env_py, "w", encoding="utf-8") as f:
            f.write(f'''
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.models import Base

TEST_SCHEMA = {repr(schema)}

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = config.attributes.get("database_url")
if not database_url:
    settings = get_settings()
    database_url = settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", str(database_url).replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={{"paramstyle": "named"}},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {{}}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={{"server_settings": {{"search_path": TEST_SCHEMA}}}},
    )

    async def run_async_migrations():
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    asyncio.run(run_async_migrations())


def do_run_migrations(connection: Connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
''')

        # Write a minimal alembic.ini pointing to our temp directory
        tmp_ini = os.path.join(tmpdir, "alembic.ini")
        with open(tmp_ini, "w", encoding="utf-8") as f:
            f.write(f"""
[alembic]
script_location = {tmpdir}
sqlalchemy.url = {db_url}
path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %%H:%%M:%%S
""")

        env = os.environ.copy()
        env["DATABASE_URL"] = db_url

        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", tmp_ini, "upgrade", "head"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_alembic_upgrade_head():
    """Run alembic upgrade head on a fresh test schema and verify tables.

    Creates an isolated schema, runs migrations there, verifies all expected
    tables exist, then drops the schema entirely.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(project_root, "alembic.ini")
    test_db_url = _test_database_url()
    schema = f"test_alembic_{uuid4().hex[:8]}"

    # Admin engine for schema creation/dropping and stale cleanup
    admin_engine = create_async_engine(test_db_url, poolclass=NullPool)

    try:
        # Create isolated test schema
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            # Widen alembic_version.version_num to accommodate long revision IDs
            # like '0004_operations_acceptance_asset_registers' (42 chars).
            # Default VARCHAR(32) is too short.
            await conn.execute(text(
                f'CREATE TABLE "{schema}".alembic_version ('
                'version_num VARCHAR(128) NOT NULL PRIMARY KEY'
                ')'
            ))

        # Clean up any stale alembic_version entries in public schema that
        # reference non-existent migration revisions.
        async with admin_engine.begin() as conn:
            await conn.execute(text(
                "DELETE FROM public.alembic_version "
                f"WHERE version_num NOT IN ({', '.join(VALID_REVISIONS)})"
            ))

        # Run alembic upgrade head in the test schema
        result = _run_alembic_in_schema(project_root, alembic_ini, test_db_url, schema)
        assert result.returncode == 0, (
            f"alembic upgrade head failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

        # Engine targeting the test schema via search_path
        schema_engine = create_async_engine(
            test_db_url,
            connect_args={"server_settings": {"search_path": schema}},
            poolclass=NullPool,
        )

        # Verify all expected tables exist
        async with schema_engine.connect() as conn:
            tbl_result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
                )
            )
            actual_tables = {row[0] for row in tbl_result}

        missing = EXPECTED_TABLES - actual_tables
        assert not missing, f"Tables missing after alembic upgrade head: {missing}"

        # Verify alembic_version table exists and has the head revision
        async with schema_engine.connect() as conn:
            ver_result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            version = ver_result.scalar()
        assert version is not None, "alembic_version table is empty after upgrade"

        await schema_engine.dispose()

    finally:
        # Clean up: drop the entire schema
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()
