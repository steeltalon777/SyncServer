"""0024_audit_events_extended: extend audit_events with outcome/correlation/parent/source

TZ-AUDIT_BACKEND_FOUNDATION §7.1 — Storage Foundation Phase 1.

Adds event_version (with backfill to 1 for existing rows), outcome,
correlation_id, parent_event_id (self-FK RESTRICT), credential_* (Phase 2
hooks, columns only), source_client, actor_username_snapshot,
external_event_id (unique).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0024_audit_events_extended"
down_revision = "0023_add_operation_client_request_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns as nullable first; event_version gets a server default and a
    # backfill from NULL to 1, then we tighten its nullability. The other columns
    # stay nullable — they participate in optional audit metadata.
    op.add_column(
        "audit_events",
        sa.Column("event_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("outcome", sa.String(32), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column(
            "parent_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "audit_events",
        sa.Column("credential_kind", sa.String(16), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("credential_fingerprint", sa.String(128), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("source_client", sa.String(32), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_username_snapshot", sa.String(128), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("external_event_id", sa.String(128), nullable=True),
    )

    # Backfill event_version: existing rows are v1 (free-form JSONB changes).
    op.execute("UPDATE audit_events SET event_version = 1 WHERE event_version IS NULL")

    # Tighten: now NOT NULL with default = 2 for forward-looking inserts.
    op.alter_column(
        "audit_events",
        "event_version",
        nullable=False,
        server_default="2",
    )

    # Indexes supporting the new query shapes (correlation, parent, outcome).
    op.create_index(
        "ix_audit_events_correlation_id",
        "audit_events",
        ["correlation_id"],
    )
    op.create_index(
        "ix_audit_events_parent_event_id",
        "audit_events",
        ["parent_event_id"],
    )
    op.create_index(
        "ix_audit_events_outcome",
        "audit_events",
        ["outcome"],
    )

    # external_event_id is the idempotency key for incoming events (Phase 2);
    # unique at the DB level because a duplicate must be deduped deterministically.
    op.create_index(
        "ix_audit_events_external_event_id",
        "audit_events",
        ["external_event_id"],
        unique=True,
        postgresql_where=sa.text("external_event_id IS NOT NULL"),
    )

    # Self-FK parent_event_id → audit_events.event_id with RESTRICT:
    # child events cannot outlive their parent. Because parent_event_id references
    # event_id (UUID) not the integer PK, no surrogate FK semantics shift.
    op.create_foreign_key(
        "fk_audit_events_parent_event_id",
        "audit_events",
        "audit_events",
        ["parent_event_id"],
        ["event_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_audit_events_parent_event_id",
        "audit_events",
        type_="foreignkey",
    )
    op.drop_index("ix_audit_events_external_event_id", table_name="audit_events")
    op.drop_index("ix_audit_events_outcome", table_name="audit_events")
    op.drop_index("ix_audit_events_parent_event_id", table_name="audit_events")
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_column("audit_events", "external_event_id")
    op.drop_column("audit_events", "actor_username_snapshot")
    op.drop_column("audit_events", "source_client")
    op.drop_column("audit_events", "credential_fingerprint")
    op.drop_column("audit_events", "credential_kind")
    op.drop_column("audit_events", "parent_event_id")
    op.drop_column("audit_events", "correlation_id")
    op.drop_column("audit_events", "outcome")
    # event_version last because it carries the NOT NULL constraint:
    # relax it before dropping to avoid sqlite-style ordering issues.
    op.alter_column(
        "audit_events",
        "event_version",
        nullable=True,
        server_default=None,
    )
    op.drop_column("audit_events", "event_version")
