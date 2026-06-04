"""make issue_objects.category_id NOT NULL (backfill done in 0013)

Revision ID: 0015_make_category_id_not_null
Revises: 0014_fix_category_unique_constraints
Create Date: 2026-06-04 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0015_make_category_id_not_null"
down_revision: Union[str, Sequence[str], None] = "0014_fix_category_unique_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("issue_objects", "category_id", nullable=False)


def downgrade() -> None:
    op.alter_column("issue_objects", "category_id", nullable=True)
