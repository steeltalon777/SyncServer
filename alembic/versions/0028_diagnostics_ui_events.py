"""0028_diagnostics_ui_events: append-only log of UI diagnostic events

TZ-DIAGNOSTICS_STAGE3 §6. New table for Angular frontend diagnostics
events (form_opened, submit_clicked, request_started, etc.) with
30-day TTL. Bulk insert is idempotent on event_id.

Indexes:
  - (session_id, occurred_at) for session timeline
  - (event_type, occurred_at) for type filtering
  - (draft_id) partial WHERE draft_id IS NOT NULL
  - (received_at) for TTL cleanup
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0028_diagnostics_ui_events"
down_revision = "0027_operations_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagnostics_ui_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tab_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("frontend_version", sa.String(length=50), nullable=True),
        sa.Column("route", sa.String(length=200), nullable=True),
        sa.Column("operation_type", sa.String(length=20), nullable=True),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("http_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("server_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.String(length=50), nullable=True),
        sa.Column("device_id", sa.String(length=50), nullable=True),
        sa.Column("site_id", sa.String(length=50), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("batch_sequence", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_index(
        "idx_diag_events_session_time",
        "diagnostics_ui_events",
        ["session_id", "occurred_at"],
    )
    op.create_index(
        "idx_diag_events_type_time",
        "diagnostics_ui_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "idx_diag_events_draft",
        "diagnostics_ui_events",
        ["draft_id"],
        postgresql_where=sa.text("draft_id IS NOT NULL"),
    )
    op.create_index(
        "idx_diag_received_at",
        "diagnostics_ui_events",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_diag_received_at", table_name="diagnostics_ui_events")
    op.drop_index("idx_diag_events_draft", table_name="diagnostics_ui_events")
    op.drop_index("idx_diag_events_type_time", table_name="diagnostics_ui_events")
    op.drop_index("idx_diag_events_session_time", table_name="diagnostics_ui_events")
    op.drop_table("diagnostics_ui_events")
