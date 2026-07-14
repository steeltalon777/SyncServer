"""add_operation_client_request_id: web idempotency columns

Revision ID: 0023_add_operation_client_request_id
Revises: 0022_fix_active_deleted_items
Create Date: 2026-07-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023_add_operation_client_request_id"
down_revision = "0022_fix_active_deleted_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations",
        sa.Column("client_request_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "operations",
        sa.Column("client_request_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_operations_client_request_id",
        "operations",
        ["created_by_user_id", "client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_operations_client_request_id", table_name="operations")
    op.drop_column("operations", "client_request_hash")
    op.drop_column("operations", "client_request_id")
