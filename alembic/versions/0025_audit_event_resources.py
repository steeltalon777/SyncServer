"""0025_audit_event_resources: per-resource links for audit events

TZ-AUDIT_BACKEND_FOUNDATION §7.2.

audit_event_resources is a (event × resource × relation) edge table.
It lets us record which domain entities participate in an event with
which role (primary, merge_source, merge_target, generated, etc.).

FK on audit_event_id uses RESTRICT because audit events are append-only.
No FKs to the linked resources — by design.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0025_audit_event_resources"
down_revision = "0024_audit_events_extended"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_event_resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_event_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(256), nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.Column("snapshot_before", postgresql.JSONB(), nullable=True),
        sa.Column("snapshot_after", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["audit_event_id"],
            ["audit_events.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_audit_event_resources_event_id",
        "audit_event_resources",
        ["audit_event_id"],
    )
    op.create_index(
        "ix_audit_event_resources_type_id",
        "audit_event_resources",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_event_resources_type_id", table_name="audit_event_resources")
    op.drop_index("ix_audit_event_resources_event_id", table_name="audit_event_resources")
    op.drop_table("audit_event_resources")
