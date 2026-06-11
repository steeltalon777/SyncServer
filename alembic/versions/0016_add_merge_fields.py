"""add merge fields to items and categories

Revision ID: 0016_add_merge_fields
Revises: 0015_make_category_id_not_null
Create Date: 2026-06-09 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0016_add_merge_fields"
down_revision: Union[str, Sequence[str], None] = "0015_make_category_id_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Items merge fields
    op.add_column("items", sa.Column("merged_into_id", sa.Integer(), nullable=True))
    op.add_column("items", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("items", sa.Column("merged_by_user_id", sa.UUID(), nullable=True))
    op.add_column("items", sa.Column("merge_comment", sa.String(), nullable=True))
    op.create_foreign_key("fk_items_merged_into", "items", "items", ["merged_into_id"], ["id"])

    # Categories merge fields
    op.add_column("categories", sa.Column("merged_into_id", sa.Integer(), nullable=True))
    op.add_column("categories", sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("categories", sa.Column("merged_by_user_id", sa.UUID(), nullable=True))
    op.add_column("categories", sa.Column("merge_comment", sa.String(), nullable=True))
    op.create_foreign_key("fk_categories_merged_into", "categories", "categories", ["merged_into_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_items_merged_into", "items", type_="foreignkey")
    op.drop_column("items", "merge_comment")
    op.drop_column("items", "merged_by_user_id")
    op.drop_column("items", "merged_at")
    op.drop_column("items", "merged_into_id")

    op.drop_constraint("fk_categories_merged_into", "categories", type_="foreignkey")
    op.drop_column("categories", "merge_comment")
    op.drop_column("categories", "merged_by_user_id")
    op.drop_column("categories", "merged_at")
    op.drop_column("categories", "merged_into_id")
