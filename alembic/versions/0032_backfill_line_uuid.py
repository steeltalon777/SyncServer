"""Backfill line_uuid with random UUID for existing operation_lines.

Migration B (backfill) of TZ-OPERATION_CORRECTION_BY_DIFF:
- Fill line_uuid for all existing rows using gen_random_uuid()
- Uses pgcrypto extension (standard on PostgreSQL 13+)

Revision ID: 0032_backfill_line_uuid
Revises: 0031_add_line_uuid_to_operation_lines
"""
from __future__ import annotations

from alembic import op

revision = "0032_backfill_line_uuid"
down_revision = "0031_add_line_uuid_to_operation_lines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE operation_lines SET line_uuid = gen_random_uuid() WHERE line_uuid IS NULL",
    )


def downgrade() -> None:
    pass
