"""Add partial unique index for source-document idempotency.

Adds:
- ix_operations_source_document_ref: partial unique index on
  (source_ref, created_by_user_id) WHERE creation_source = 'source_document'
  AND deleted_at IS NULL

This prevents race-condition duplicates when two POST with the same
source_ref arrive concurrently.

TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING §4.2.1
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0030_source_document_idempotency_index"
down_revision = "0029_source_document_operation_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_operations_source_document_ref",
        "operations",
        ["source_ref", "created_by_user_id"],
        unique=True,
        postgresql_where=sa.text(
            "creation_source = 'source_document' AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operations_source_document_ref",
        table_name="operations",
        postgresql_where=sa.text(
            "creation_source = 'source_document' AND deleted_at IS NULL"
        ),
    )
