"""document sources

Revision ID: 0006_document_sources
Revises: 0005_documents_tables
Create Date: 2026-04-15 15:30:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = "0006_document_sources"
down_revision: str | None = "0005_documents_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS document_sources (
        document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        source_type VARCHAR(50) NOT NULL,
        source_id VARCHAR(100) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (document_id, source_type, source_id),
        CONSTRAINT ck_document_sources_source_type_non_empty CHECK (btrim(source_type) <> ''),
        CONSTRAINT ck_document_sources_source_id_non_empty CHECK (btrim(source_id) <> '')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_document_sources_document_id ON document_sources (document_id)",
    "CREATE INDEX IF NOT EXISTS ix_document_sources_source_lookup ON document_sources (source_type, source_id)",
    """
    INSERT INTO document_sources (document_id, source_type, source_id)
    SELECT document_id, 'operation', operation_id::text
    FROM document_operations
    ON CONFLICT DO NOTHING
    """,
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_document_sources_source_lookup", table_name="document_sources")
    op.drop_index("ix_document_sources_document_id", table_name="document_sources")
    op.drop_table("document_sources")
