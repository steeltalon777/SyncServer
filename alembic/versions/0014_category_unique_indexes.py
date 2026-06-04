"""fix category unique constraints for root and children

Revision ID: 0014_category_unique_indexes
Revises: 0013_issue_object_categories
Create Date: 2026-06-04 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0014_category_unique_indexes"
down_revision: Union[str, Sequence[str], None] = "0013_issue_object_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_io_categories_parent_normalized", "issue_object_categories", type_="unique")
    op.create_index(
        "uq_io_categories_root_normalized_key",
        "issue_object_categories",
        ["normalized_key"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
    )
    op.create_index(
        "uq_io_categories_child_parent_normalized_key",
        "issue_object_categories",
        ["parent_id", "normalized_key"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_io_categories_child_parent_normalized_key", table_name="issue_object_categories")
    op.drop_index("uq_io_categories_root_normalized_key", table_name="issue_object_categories")
    op.create_unique_constraint(
        "uq_io_categories_parent_normalized",
        "issue_object_categories",
        ["parent_id", "normalized_key"],
    )
