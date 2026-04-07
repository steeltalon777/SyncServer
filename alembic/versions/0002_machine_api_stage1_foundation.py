"""machine api stage1 foundation

Revision ID: 0002_machine_api_stage1
Revises: 0001_initial_baseline
Create Date: 2026-04-07 18:10:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = "0002_machine_api_stage1"
down_revision: str | None = "0001_initial_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS = (
    "ALTER TABLE categories ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255)",
    "ALTER TABLE categories ADD COLUMN IF NOT EXISTS machine_last_batch_id VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_categories_normalized_name ON categories (normalized_name)",
    "UPDATE categories SET normalized_name = lower(trim(name)) WHERE normalized_name IS NULL",

    "ALTER TABLE items ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255)",
    "ALTER TABLE items ADD COLUMN IF NOT EXISTS source_system VARCHAR(100)",
    "ALTER TABLE items ADD COLUMN IF NOT EXISTS source_ref VARCHAR(255)",
    "ALTER TABLE items ADD COLUMN IF NOT EXISTS import_batch_id VARCHAR(64)",
    "ALTER TABLE items ADD COLUMN IF NOT EXISTS machine_last_batch_id VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_items_normalized_name ON items (normalized_name)",
    "CREATE INDEX IF NOT EXISTS ix_items_import_batch_id ON items (import_batch_id)",
    "UPDATE items SET normalized_name = lower(trim(name)) WHERE normalized_name IS NULL",

    "ALTER TABLE units ADD COLUMN IF NOT EXISTS code VARCHAR(50)",
    "ALTER TABLE units ADD COLUMN IF NOT EXISTS machine_last_batch_id VARCHAR(64)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_units_code ON units (code)",
    "CREATE INDEX IF NOT EXISTS ix_units_code ON units (code)",
    "UPDATE units SET code = upper(symbol) WHERE code IS NULL",

    "ALTER TABLE operations ADD COLUMN IF NOT EXISTS version INTEGER",
    "ALTER TABLE operations ADD COLUMN IF NOT EXISTS machine_last_batch_id VARCHAR(64)",
    "UPDATE operations SET version = 1 WHERE version IS NULL",
    "ALTER TABLE operations ALTER COLUMN version SET DEFAULT 1",
    "ALTER TABLE operations ALTER COLUMN version SET NOT NULL",

    """
    CREATE TABLE IF NOT EXISTS machine_snapshots (
        snapshot_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        datasets JSONB NOT NULL,
        counts JSONB NOT NULL,
        created_by_user_id UUID,
        PRIMARY KEY (snapshot_id),
        FOREIGN KEY(created_by_user_id) REFERENCES users (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_machine_snapshots_created_at ON machine_snapshots (created_at)",

    """
    CREATE TABLE IF NOT EXISTS machine_reports (
        report_id VARCHAR(64) NOT NULL,
        report_type VARCHAR(100) NOT NULL,
        snapshot_id VARCHAR(64) NOT NULL,
        created_by_user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        summary TEXT NOT NULL,
        findings JSONB NOT NULL,
        references JSONB NOT NULL,
        PRIMARY KEY (report_id),
        FOREIGN KEY(snapshot_id) REFERENCES machine_snapshots (snapshot_id),
        FOREIGN KEY(created_by_user_id) REFERENCES users (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_machine_reports_snapshot_id ON machine_reports (snapshot_id)",
    "CREATE INDEX IF NOT EXISTS ix_machine_reports_created_at ON machine_reports (created_at)",

    """
    CREATE TABLE IF NOT EXISTS machine_batches (
        batch_id VARCHAR(64) NOT NULL,
        plan_id VARCHAR(64) NOT NULL,
        domain VARCHAR(32) NOT NULL,
        payload_format VARCHAR(64) NOT NULL,
        mode VARCHAR(16) NOT NULL,
        client_request_id VARCHAR(128),
        idempotency_key VARCHAR(128) NOT NULL,
        snapshot_id VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        source_client VARCHAR(128),
        payload_hash VARCHAR(64) NOT NULL,
        payload JSONB NOT NULL,
        plan JSONB NOT NULL,
        result JSONB,
        warnings JSONB NOT NULL,
        errors JSONB NOT NULL,
        created_by_user_id UUID NOT NULL,
        applied_by_user_id UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        applied_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (batch_id),
        CONSTRAINT uq_machine_batches_plan_id UNIQUE (plan_id),
        CONSTRAINT uq_machine_batches_idempotency_key UNIQUE (idempotency_key),
        CONSTRAINT ck_machine_batches_status CHECK (status IN ('received', 'validating', 'preview_ready', 'applying', 'applied', 'failed')),
        CONSTRAINT ck_machine_batches_mode CHECK (mode IN ('atomic')),
        FOREIGN KEY(snapshot_id) REFERENCES machine_snapshots (snapshot_id),
        FOREIGN KEY(created_by_user_id) REFERENCES users (id),
        FOREIGN KEY(applied_by_user_id) REFERENCES users (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_machine_batches_domain_created_at ON machine_batches (domain, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_machine_batches_snapshot_id ON machine_batches (snapshot_id)",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_machine_batches_snapshot_id", table_name="machine_batches")
    op.drop_index("ix_machine_batches_domain_created_at", table_name="machine_batches")
    op.drop_table("machine_batches")

    op.drop_index("ix_machine_reports_created_at", table_name="machine_reports")
    op.drop_index("ix_machine_reports_snapshot_id", table_name="machine_reports")
    op.drop_table("machine_reports")

    op.drop_index("ix_machine_snapshots_created_at", table_name="machine_snapshots")
    op.drop_table("machine_snapshots")

    op.drop_column("operations", "machine_last_batch_id")
    op.drop_column("operations", "version")

    op.drop_index("ix_units_code", table_name="units")
    op.drop_index("uq_units_code", table_name="units")
    op.drop_column("units", "machine_last_batch_id")
    op.drop_column("units", "code")

    op.drop_index("ix_items_import_batch_id", table_name="items")
    op.drop_index("ix_items_normalized_name", table_name="items")
    op.drop_column("items", "machine_last_batch_id")
    op.drop_column("items", "import_batch_id")
    op.drop_column("items", "source_ref")
    op.drop_column("items", "source_system")
    op.drop_column("items", "normalized_name")

    op.drop_index("ix_categories_normalized_name", table_name="categories")
    op.drop_column("categories", "machine_last_batch_id")
    op.drop_column("categories", "normalized_name")
