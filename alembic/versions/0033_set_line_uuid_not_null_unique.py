"""SET NOT NULL + UNIQUE on operation_lines.line_uuid.

Migration C of TZ-OPERATION_CORRECTION_BY_DIFF:
- ALTER operation_lines.line_uuid SET NOT NULL
- CREATE UNIQUE INDEX on operation_lines.line_uuid

Revision ID: 0033_set_line_uuid_not_null_unique
Revises: 0032_backfill_line_uuid
"""
from __future__ import annotations

from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0033_set_line_uuid_not_null_unique"
down_revision = "0032_backfill_line_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("operation_lines", "line_uuid", nullable=False)
    op.create_unique_constraint("uq_ol_line_uuid", "operation_lines", ["line_uuid"])


def downgrade() -> None:
    op.drop_constraint("uq_ol_line_uuid", "operation_lines", type_="unique")
    op.alter_column("operation_lines", "line_uuid", nullable=True)
