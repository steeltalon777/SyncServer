"""documents tables

Revision ID: 0005_documents_tables
Revises: 1d1801ed5535
Create Date: 2026-04-15 13:40:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = "0005_documents_tables"
down_revision: str | None = "1d1801ed5535"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY,
        document_type VARCHAR(50) NOT NULL,
        document_number VARCHAR(100),
        revision INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(32) NOT NULL,
        site_id INTEGER NOT NULL REFERENCES sites(id),
        template_name VARCHAR(100),
        template_version VARCHAR(32),
        payload_schema_version VARCHAR(32),
        payload JSONB NOT NULL,
        payload_hash VARCHAR(64),
        created_by_user_id UUID REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finalized_at TIMESTAMPTZ,
        supersedes_document_id UUID REFERENCES documents(id),
        CONSTRAINT ck_documents_status CHECK (status IN ('draft', 'finalized', 'void', 'superseded'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_documents_document_type ON documents (document_type)",
    "CREATE INDEX IF NOT EXISTS ix_documents_document_number ON documents (document_number)",
    "CREATE INDEX IF NOT EXISTS ix_documents_status ON documents (status)",
    "CREATE INDEX IF NOT EXISTS ix_documents_site_id ON documents (site_id)",
    "CREATE INDEX IF NOT EXISTS ix_documents_created_at ON documents (created_at)",
    """
    CREATE TABLE IF NOT EXISTS document_operations (
        document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
        PRIMARY KEY (document_id, operation_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_document_operations_operation_id ON document_operations (operation_id)",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_document_operations_operation_id", table_name="document_operations")
    op.drop_table("document_operations")
    
    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_site_id", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_document_number", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_table("documents")
