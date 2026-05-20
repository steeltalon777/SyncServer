"""add item review fields (requires_review, review_status, review audit)

Revision ID: 0010_add_item_review_fields
Revises: 7538376fd139
Create Date: 2026-05-20 21:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_add_item_review_fields"
down_revision: str | None = "7538376fd139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add requires_review flag
    op.add_column(
        "items",
        sa.Column(
            "requires_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True for fast-created catalog items that require user review",
        ),
    )
    # Add review_status: needs_review, confirmed, merged, archived
    op.add_column(
        "items",
        sa.Column(
            "review_status",
            sa.String(32),
            nullable=True,
            server_default=None,
            comment="Review lifecycle status: needs_review, confirmed, merged, archived",
        ),
    )
    # Add review audit fields
    op.add_column(
        "items",
        sa.Column(
            "review_created_by_user_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "review_resolved_by_user_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "review_resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "items",
        sa.Column(
            "review_note",
            sa.Text(),
            nullable=True,
        ),
    )

    # Create indexes for review queries
    op.create_index("ix_items_requires_review", "items", ["requires_review"])
    op.create_index("ix_items_review_status", "items", ["review_status"])

    # Foreign keys for review audit users
    op.create_foreign_key(
        "fk_items_review_created_by_user",
        "items", "users",
        ["review_created_by_user_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_items_review_resolved_by_user",
        "items", "users",
        ["review_resolved_by_user_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_items_review_resolved_by_user", "items", type_="foreignkey")
    op.drop_constraint("fk_items_review_created_by_user", "items", type_="foreignkey")
    op.drop_index("ix_items_review_status", table_name="items")
    op.drop_index("ix_items_requires_review", table_name="items")
    op.drop_column("items", "review_note")
    op.drop_column("items", "review_resolved_at")
    op.drop_column("items", "review_resolved_by_user_id")
    op.drop_column("items", "review_created_by_user_id")
    op.drop_column("items", "review_status")
    op.drop_column("items", "requires_review")
