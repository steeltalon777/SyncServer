"""0027_operations_origin: system-generated operations support

TZ-AUDIT_BACKEND_FOUNDATION §7.4.

Adds three columns to operations so that we can distinguish user-driven
operations from those created automatically as part of an item.merge
or temporary-item resolution:

- origin = "user" | "system" (NOT NULL, default "user"),
- system_reason = NULL for user ops; for system ops, one of
  "item_merge", "temporary_merge", "review_merge",
- initiated_by_user_id = NULL for user ops; for system ops, the user
  who triggered the merge flow.

We backfill existing rows with origin="user" before tightening NOT NULL.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027_operations_origin"
down_revision = "0026_audit_item_effects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations",
        sa.Column("origin", sa.String(16), nullable=True, server_default="user"),
    )
    op.add_column(
        "operations",
        sa.Column("system_reason", sa.String(32), nullable=True),
    )
    op.add_column(
        "operations",
        sa.Column(
            "initiated_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.execute(
        "UPDATE operations SET origin = 'user' WHERE origin IS NULL"
    )
    op.alter_column("operations", "origin", nullable=False)

    op.create_foreign_key(
        "fk_operations_initiated_by_user_id",
        "operations",
        "users",
        ["initiated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_operations_initiated_by_user_id",
        "operations",
        type_="foreignkey",
    )
    op.drop_column("operations", "initiated_by_user_id")
    op.drop_column("operations", "system_reason")
    # origin drops last; relax NOT NULL first to keep some DBs happy.
    op.alter_column("operations", "origin", nullable=True, server_default=None)
    op.drop_column("operations", "origin")
