"""merge prod GIN index branch with dev schema branch

Revision ID: 8e9a044a0fcf
Revises: 0010, 0016_add_merge_fields
Create Date: 2026-06-10 14:56:02.503203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e9a044a0fcf'
down_revision: Union[str, Sequence[str], None] = ('0010', '0016_add_merge_fields')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
