"""add_operations_deleted_fields

Revision ID: 7538376fd139
Revises: 0009_add_temporary_draft_payload
Create Date: 2026-05-19 18:36:15.153606

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '7538376fd139'
down_revision: Union[str, Sequence[str], None] = '0009_add_temporary_draft_payload'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('operations', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('operations', sa.Column('deleted_by_user_id', sa.UUID(), nullable=True))
    op.create_index('ix_operations_deleted_at', 'operations', ['deleted_at'], unique=False)
    op.create_foreign_key(
        'fk_operations_deleted_by_user',
        'operations', 'users',
        ['deleted_by_user_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_operations_deleted_by_user', 'operations', type_='foreignkey')
    op.drop_index('ix_operations_deleted_at', table_name='operations')
    op.drop_column('operations', 'deleted_by_user_id')
    op.drop_column('operations', 'deleted_at')
