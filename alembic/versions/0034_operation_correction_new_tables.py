"""Create operation correction immutable storage.

Migration D of TZ-OPERATION_CORRECTION_BY_DIFF:
- OperationRevision (immutable)
- OperationRevisionLine (immutable, composite PK: revision_id + line_uuid)
- OperationCorrection (3-state: draft/applied/abandoned)
- OperationCorrectionLine (target state only)
- Operation.current_revision_id (FK nullable)
- Operation.correction_count + last_corrected_at
- Document.operation_revision_id (FK nullable)

Revision ID: 0034_operation_correction_new_tables
Revises: 0033_set_line_uuid_not_null_unique
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0034_operation_correction_new_tables"
down_revision = "0033_set_line_uuid_not_null_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. New columns on operations
    op.add_column(
        "operations",
        sa.Column("current_revision_id", PGUUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "operations",
        sa.Column(
            "correction_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "operations",
        sa.Column("last_corrected_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. OperationCorrection (3-state) — must exist BEFORE OperationRevision FK
    op.create_table(
        "operation_corrections",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "operation_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("operations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "base_operation_revision_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(100)),
        sa.Column(
            "created_by_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "submitted_by_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('draft', 'applied', 'abandoned')",
            name="ck_operation_corrections_status",
        ),
    )
    op.create_index(
        "ix_operation_corrections_operation_id",
        "operation_corrections",
        ["operation_id"],
    )

    # 3. Partial unique index: one active draft per operation
    op.execute("""
        CREATE UNIQUE INDEX uq_active_correction_per_operation
        ON operation_corrections (operation_id)
        WHERE status = 'draft'
    """)

    # 4. OperationRevision (immutable) — FK to operation_corrections added separately
    op.create_table(
        "operation_revisions",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "operation_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("operations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer, nullable=False),
        sa.Column(
            "created_by_user_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by_correction_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "operation_id", "revision_number",
            name="uq_operation_revisions_op_rev",
        ),
    )

    # 5. FK from operation_revisions.created_by_correction_id → operation_corrections
    op.create_foreign_key(
        "fk_operation_revisions_correction",
        "operation_revisions", "operation_corrections",
        ["created_by_correction_id"], ["id"],
    )

    # 6. FK from operation_corrections.base_operation_revision_id → operation_revisions
    op.create_foreign_key(
        "fk_corrections_base_revision",
        "operation_corrections", "operation_revisions",
        ["base_operation_revision_id"], ["id"],
    )

    # 7. OperationRevisionLine (composite PK: revision_id + line_uuid)
    op.create_table(
        "operation_revision_lines",
        sa.Column(
            "revision_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("operation_revisions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("line_uuid", PGUUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id")),
        sa.Column(
            "inventory_subject_id",
            sa.Integer,
            sa.ForeignKey("inventory_subjects.id"),
        ),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False),
        sa.Column(
            "accepted_qty",
            sa.Numeric(18, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "lost_qty",
            sa.Numeric(18, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column("batch", sa.String(100)),
        sa.Column("comment", sa.Text),
        sa.Column("source_item_name", sa.String(255)),
        sa.Column("source_item_sku", sa.String(100)),
        sa.Column("source_unit_name", sa.String(100)),
        sa.Column("source_category_name", sa.String(255)),
        sa.Column("item_name_snapshot", sa.String(255)),
        sa.Column("item_sku_snapshot", sa.String(100)),
        sa.Column("unit_name_snapshot", sa.String(100)),
        sa.Column("unit_symbol_snapshot", sa.String(20)),
        sa.Column("category_name_snapshot", sa.String(255)),
    )

    # 8. FK from operations.current_revision_id → operation_revisions
    op.create_foreign_key(
        "fk_operations_current_revision",
        "operations", "operation_revisions",
        ["current_revision_id"], ["id"],
    )

    # 9. OperationCorrectionLine
    op.create_table(
        "operation_correction_lines",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "correction_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("operation_corrections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_uuid", PGUUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id")),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("batch", sa.String(100)),
        sa.Column("comment", sa.Text),
        sa.UniqueConstraint(
            "correction_id", "line_uuid",
            name="uq_correction_lines_line_uuid",
        ),
    )

    # 10. Document.operation_revision_id
    op.add_column(
        "documents",
        sa.Column("operation_revision_id", PGUUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_operation_revision",
        "documents", "operation_revisions",
        ["operation_revision_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_documents_operation_revision", "documents", type_="foreignkey",
    )
    op.drop_column("documents", "operation_revision_id")

    op.execute("DROP INDEX IF EXISTS uq_active_correction_per_operation")
    op.drop_table("operation_correction_lines")
    op.drop_index(
        "ix_operation_corrections_operation_id",
        table_name="operation_corrections",
    )
    op.drop_constraint(
        "fk_corrections_base_revision", "operation_corrections", type_="foreignkey",
    )
    op.drop_table("operation_corrections")

    op.drop_constraint(
        "fk_operations_current_revision", "operations", type_="foreignkey",
    )
    op.drop_column("operations", "last_corrected_at")
    op.drop_column("operations", "correction_count")
    op.drop_column("operations", "current_revision_id")

    op.drop_table("operation_revision_lines")
    op.drop_constraint(
        "fk_operation_revisions_correction", "operation_revisions", type_="foreignkey",
    )
    op.drop_table("operation_revisions")
