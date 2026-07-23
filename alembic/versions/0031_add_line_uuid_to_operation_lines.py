"""Add line_uuid to operation_lines (nullable).

Migration A of TZ-OPERATION_CORRECTION_BY_DIFF:
- Add line_uuid column to operation_lines (nullable, 2-step migration)
- Backfill with random UUID is done separately (0032)
- NOT NULL + UNIQUE is set in Migration B (0033)

Revision ID: 0031_add_line_uuid_to_operation_lines
Revises: 0030_source_document_idempotency_index
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0031_add_line_uuid_to_operation_lines"
down_revision = "0030_source_document_idempotency_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operation_lines",
        sa.Column("line_uuid", PGUUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operation_lines", "line_uuid")
