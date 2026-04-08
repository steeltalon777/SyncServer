"""reconcile legacy items hashtags column

Revision ID: 0003_items_hashtags_reconcile
Revises: 0002_machine_api_stage1
Create Date: 2026-04-08 18:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = "0003_items_hashtags_reconcile"
down_revision: str | None = "0002_machine_api_stage1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS hashtags JSONB")
    op.execute("CREATE INDEX IF NOT EXISTS idx_items_hashtags ON items USING gin (hashtags)")


def downgrade() -> None:
    op.drop_index("idx_items_hashtags", table_name="items")
    op.drop_column("items", "hashtags")
