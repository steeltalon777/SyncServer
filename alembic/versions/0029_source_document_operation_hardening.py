"""Phase A: source-document operation hardening.

Adds:
- Operation.creation_source (NOT NULL DEFAULT 'legacy')
- Operation.source_ref (nullable)
- OperationLine.source_item_name, source_item_sku, source_unit_name, source_category_name
- OperationLine.resolution_mode computed property (Python-level, no DB column)

Backfill:
- Operation.creation_source:
    - 'system' для operations WHERE origin = 'system'
    - 'legacy' для ВСЕХ остальных существующих операций (консервативный fallback)
  НЕ классифицируем origin='user' как 'manual' — исторические операции
  могут быть как ручными, так и legacy-импортом, различать невозможно.

Indexes:
- ix_operations_creation_source (один индекс, без дублей)

TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING §6.1
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0029_source_document_operation_hardening"
down_revision = "0028_diagnostics_ui_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Operation columns
    op.add_column(
        "operations",
        sa.Column("creation_source", sa.String(32), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "operations",
        sa.Column("source_ref", sa.String(255), nullable=True),
    )

    # 2. Backfill Operation.creation_source
    op.execute(
        "UPDATE operations SET creation_source = 'system' WHERE origin = 'system'"
    )
    # Все остальные остаются 'legacy' (default) — НЕ backfill-ить как 'manual'

    # 3. Один индекс (без дублей)
    op.create_index(
        "ix_operations_creation_source",
        "operations",
        ["creation_source"],
        unique=False,
    )

    # 4. OperationLine SOURCE snapshot columns
    op.add_column(
        "operation_lines",
        sa.Column("source_item_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "operation_lines",
        sa.Column("source_item_sku", sa.String(100), nullable=True),
    )
    op.add_column(
        "operation_lines",
        sa.Column("source_unit_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "operation_lines",
        sa.Column("source_category_name", sa.String(255), nullable=True),
    )

    # 5. НЕ backfill-ить source_item_* from item_name_snapshot
    # Эти данные не являются достоверным исходным текстом накладной.
    # Для legacy операций source_* остаются NULL.
    # Существующий catalog snapshot (item_name_snapshot и др.) остаётся без изменений.


def downgrade() -> None:
    op.drop_index("ix_operations_creation_source", table_name="operations")
    op.drop_column("operations", "source_ref")
    op.drop_column("operations", "creation_source")
    op.drop_column("operation_lines", "source_category_name")
    op.drop_column("operation_lines", "source_unit_name")
    op.drop_column("operation_lines", "source_item_sku")
    op.drop_column("operation_lines", "source_item_name")
