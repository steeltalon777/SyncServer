"""fix_active_deleted_items: set is_active=false where deleted_at is set

Revision ID: 0022_fix_active_deleted_items
Revises: 0021_add_operation_display_number
Create Date: 2026-07-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_fix_active_deleted_items"
down_revision = "0021_add_operation_display_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE items SET is_active = false "
        "WHERE deleted_at IS NOT NULL AND is_active = true"
    )


def downgrade() -> None:
    # Downgrade is intentionally a no-op: we cannot safely reactivate
    # rows that were previously in an inconsistent state without
    # full business review and verified backup restoration.
    pass
