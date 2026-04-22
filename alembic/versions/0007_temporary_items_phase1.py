"""temporary items phase1

Revision ID: 0007_temporary_items_phase1
Revises: 0006_document_sources
Create Date: 2026-04-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_temporary_items_phase1"
down_revision = "0006_document_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "temporary_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hashtags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_item_id", sa.Integer(), nullable=True),
        sa.Column("resolution_type", sa.String(length=32), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_item_id"], ["items.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", name="uq_temporary_items_item_id"),
    )
    op.create_index("ix_temporary_items_status", "temporary_items", ["status"])
    op.create_index("ix_temporary_items_created_by_user_id", "temporary_items", ["created_by_user_id"])
    op.create_index("ix_temporary_items_normalized_name", "temporary_items", ["normalized_name"])


def downgrade() -> None:
    op.drop_index("ix_temporary_items_normalized_name", table_name="temporary_items")
    op.drop_index("ix_temporary_items_created_by_user_id", table_name="temporary_items")
    op.drop_index("ix_temporary_items_status", table_name="temporary_items")
    op.drop_table("temporary_items")
