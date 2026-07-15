"""add_operation_display_number: Add display_number column to operations

Revision ID: 0021_add_operation_display_number
Revises: 0020_search_normalization
Create Date: 2026-07-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0021_add_operation_display_number"
down_revision = "0020_search_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operations", sa.Column("display_number", sa.String(100), nullable=True))
    op.create_index("ix_operations_display_number", "operations", ["display_number"])


def downgrade() -> None:
    op.drop_index("ix_operations_display_number")
    op.drop_column("operations", "display_number")
