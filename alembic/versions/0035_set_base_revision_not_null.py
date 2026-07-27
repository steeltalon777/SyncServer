"""ALTER base_operation_revision_id SET NOT NULL.

Migration 0035 of TZ-OPERATION_CORRECTION_BY_DIFF (rev.2 fix):
- operation_corrections.base_operation_revision_id was created nullable
  in 0034 for table creation order; this sets it NOT NULL now that
  both tables exist and the FK is in place.

Revision ID: 0035_set_base_revision_not_null
Revises: 0034_operation_correction_new_tables
"""
from __future__ import annotations

from alembic import op

revision = "0035_set_base_revision_not_null"
down_revision = "0034_operation_correction_new_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "operation_corrections",
        "base_operation_revision_id",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "operation_corrections",
        "base_operation_revision_id",
        nullable=True,
    )
