"""add temporary_draft_payload to operation_lines

Revision ID: 0009_add_temporary_draft_payload
Revises: 0008_inventory_subjects_backfill
Create Date: 2026-04-24 17:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_add_temporary_draft_payload"
down_revision: str | None = "0008_inventory_subjects_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operation_lines",
        sa.Column(
            "temporary_draft_payload",
            sa.JSON(none_as_null=True),
            nullable=True,
            comment="Deferred temporary creation payload (JSON). "
                    "Stores data for materializing temporary entities on submit. "
                    "When not null — line is considered draft-temporary. "
                    "Cleared after materialization on submit.",
        ),
    )


def downgrade() -> None:
    op.drop_column("operation_lines", "temporary_draft_payload")
