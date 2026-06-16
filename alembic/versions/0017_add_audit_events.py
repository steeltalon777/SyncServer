"""add audit_events table for user actions journal

Revision ID: 0017_add_audit_events
Revises: 8e9a044a0fcf
Create Date: 2026-06-16 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "0017_add_audit_events"
down_revision: Union[str, Sequence[str], None] = "8e9a044a0fcf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_events table."""
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_user_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("actor_device_id", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(256), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("changes", JSONB(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["actor_device_id"],
            ["devices.id"],
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )

    op.create_index(
        "ix_audit_events_event_type",
        "audit_events",
        ["event_type"],
    )
    op.create_index(
        "ix_audit_events_actor_user_id",
        "audit_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_audit_events_entity_type_entity_id",
        "audit_events",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_audit_events_site_id",
        "audit_events",
        ["site_id"],
    )
    op.create_index(
        "ix_audit_events_created_at",
        "audit_events",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop audit_events table."""
    op.drop_table("audit_events")
