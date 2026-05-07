"""add GIN index on temporary_items.hashtags

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-04 18:00:00.000000

"""

from collections.abc import Sequence

from alembic import op


revision: str = "0010"
down_revision: str | None = "0009_add_temporary_draft_payload"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_temporary_items_hashtags "
        "ON temporary_items USING gin (hashtags)"
    )


def downgrade() -> None:
    op.drop_index("idx_temporary_items_hashtags", table_name="temporary_items")
