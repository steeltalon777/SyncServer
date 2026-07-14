"""0026_audit_item_effects: balance-change journal

TZ-AUDIT_BACKEND_FOUNDATION §7.3.

audit_item_effects is the granular balance-change journal. One row per
actual delta applied to a balance as part of submitting (or cancelling)
a warehouse operation.

Key design:
- inventory_subject_id is mandatory (we always know the subject);
- item_id is nullable (for temporary items where the catalog row has
  not been materialised yet);
- snapshot fields survive subsequent domain-entity deletion;
- caused_by_event_id links an effect to its originating business event
  (e.g. an item.merge merge-event id is the parent of two ADJUSTMENT
  submit-events whose effects are caused by it).

FK policy:
- audit_event_id RESTRICT (events never deleted),
- operation_id SET NULL (operation may be hard-deleted later),
- inventory_subject_id RESTRICT (subject must exist),
- item_id RESTRICT (item history must not vanish),
- site_id SET NULL (sites are configuration data),
- caused_by_event_id RESTRICT (reasoning chain preserved).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0026_audit_item_effects"
down_revision = "0025_audit_event_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_item_effects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_event_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inventory_subject_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_name_snapshot", sa.String(256), nullable=True),
        sa.Column("item_sku_snapshot", sa.String(128), nullable=True),
        sa.Column("subject_type", sa.String(32), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("quantity_before", sa.Numeric(18, 4), nullable=True),
        sa.Column("quantity_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_after", sa.Numeric(18, 4), nullable=True),
        sa.Column("effect_type", sa.String(32), nullable=False),
        sa.Column(
            "is_system_generated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("caused_by_event_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_subject_id"],
            ["inventory_subjects.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["caused_by_event_id"],
            ["audit_events.id"],
            ondelete="RESTRICT",
        ),
    )
    for col in (
        "audit_event_id",
        "inventory_subject_id",
        "item_id",
        "site_id",
        "operation_id",
        "effect_type",
    ):
        op.create_index(
            f"ix_audit_item_effects_{col}",
            "audit_item_effects",
            [col],
        )


def downgrade() -> None:
    for col in (
        "effect_type",
        "operation_id",
        "site_id",
        "item_id",
        "inventory_subject_id",
        "audit_event_id",
    ):
        op.drop_index(f"ix_audit_item_effects_{col}", table_name="audit_item_effects")
    op.drop_table("audit_item_effects")
