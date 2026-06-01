"""add created_by_user_id and updated_by_user_id to catalog models (items, categories, units)

Revision ID: 0011_catalog_audit_fields
Revises: 0010_add_item_review_fields
Create Date: 2026-06-01 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_catalog_audit_fields"
down_revision: str | None = "0010_add_item_review_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_created_updated_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        table,
        sa.Column("updated_by_user_id", sa.UUID(), nullable=True),
    )


def _backfill_root_user(table: str, conn: sa.Connection, root_id) -> None:
    conn.execute(
        sa.text(
            f"UPDATE {table} "
            f"SET created_by_user_id = :uid, updated_by_user_id = :uid "
            f"WHERE created_by_user_id IS NULL"
        ),
        {"uid": root_id},
    )


def _add_foreign_keys(table: str, fk_prefix: str) -> None:
    op.create_foreign_key(
        f"fk_{fk_prefix}_created_by_user",
        table, "users",
        ["created_by_user_id"], ["id"],
    )
    op.create_foreign_key(
        f"fk_{fk_prefix}_updated_by_user",
        table, "users",
        ["updated_by_user_id"], ["id"],
    )


def _drop_foreign_keys(table: str, fk_prefix: str) -> None:
    op.drop_constraint(f"fk_{fk_prefix}_created_by_user", table, type_="foreignkey")
    op.drop_constraint(f"fk_{fk_prefix}_updated_by_user", table, type_="foreignkey")


def _add_indexes(table: str, idx_prefix: str) -> None:
    op.create_index(f"ix_{idx_prefix}_created_by_user_id", table, ["created_by_user_id"])
    op.create_index(f"ix_{idx_prefix}_updated_by_user_id", table, ["updated_by_user_id"])


def _drop_indexes(table: str, idx_prefix: str) -> None:
    op.drop_index(f"ix_{idx_prefix}_created_by_user_id", table_name=table)
    op.drop_index(f"ix_{idx_prefix}_updated_by_user_id", table_name=table)


def upgrade() -> None:
    # 1. Add columns to all three tables
    for table in ("items", "categories", "units"):
        _add_created_updated_columns(table)

    # 2. Data migration: backfill existing records with root user
    conn = op.get_bind()
    root_user = conn.execute(
        sa.text(
            "SELECT id FROM users WHERE is_root = true ORDER BY created_at ASC LIMIT 1"
        )
    ).fetchone()

    if root_user is not None:
        root_id = root_user[0]
        for table in ("items", "categories", "units"):
            _backfill_root_user(table, conn, root_id)

    # 3. Foreign keys
    fk_config = [
        ("items", "items"),
        ("categories", "categories"),
        ("units", "units"),
    ]
    for table, fk_prefix in fk_config:
        _add_foreign_keys(table, fk_prefix)

    # 4. Indexes for filtered queries
    idx_config = [
        ("items", "items"),
        ("categories", "categories"),
        ("units", "units"),
    ]
    for table, idx_prefix in idx_config:
        _add_indexes(table, idx_prefix)


def downgrade() -> None:
    # Reverse order: drop indexes, FK, columns
    idx_config = [
        ("items", "items"),
        ("categories", "categories"),
        ("units", "units"),
    ]
    for table, idx_prefix in idx_config:
        _drop_indexes(table, idx_prefix)

    fk_config = [
        ("items", "items"),
        ("categories", "categories"),
        ("units", "units"),
    ]
    for table, fk_prefix in fk_config:
        _drop_foreign_keys(table, fk_prefix)

    for table in ("items", "categories", "units"):
        op.drop_column(table, "updated_by_user_id")
        op.drop_column(table, "created_by_user_id")
