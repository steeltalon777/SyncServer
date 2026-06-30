"""add sync_state table

Revision ID: 0019_add_sync_state
Revises: 0018_fix_item_id_nullable
Create Date: 2026-06-19

Adds per-device sync state tracking (ADR-0016). The sync_state table stores
the last server_seq a device has consumed (via pull), last activity timestamps,
status, and the last error message. This enables operators to detect stuck or
lagging devices and to expose per-device status via /api/v1/sync/status.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_add_sync_state"
down_revision: str | None = "0018_fix_item_id_nullable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column(
            "last_sequence_number",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_sync_state_device_id_devices"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_sync_state_device_id"),
    )
    op.create_index("ix_sync_state_status", "sync_state", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sync_state_status", table_name="sync_state")
    op.drop_table("sync_state")
