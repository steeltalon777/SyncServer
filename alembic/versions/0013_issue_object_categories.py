"""create issue_object_categories, add category_id + comment to issue_objects

Revision ID: 0013_issue_object_categories
Revises: 0012_issue_objects
Create Date: 2026-06-03 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_issue_object_categories"
down_revision: Union[str, Sequence[str], None] = "0012_issue_objects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize(value: str) -> str:
    import re
    text = (value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()
    return text


def upgrade() -> None:
    """Upgrade schema: create categories, add columns, seed defaults."""

    # 1. Create issue_object_categories table
    op.create_table(
        "issue_object_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_key", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("issue_object_categories.id"), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id", "normalized_key", name="uq_io_categories_parent_normalized"),
    )
    op.create_index("ix_io_categories_normalized_key", "issue_object_categories", ["normalized_key"])
    op.create_index("ix_io_categories_parent_id", "issue_object_categories", ["parent_id"])
    op.create_index("ix_io_categories_deleted_at", "issue_object_categories", ["deleted_at"])

    # 2. Add comment and category_id columns to issue_objects
    op.add_column("issue_objects", sa.Column("comment", sa.String(500), nullable=True))
    op.add_column("issue_objects", sa.Column("category_id", sa.Integer(), sa.ForeignKey("issue_object_categories.id"), nullable=True))
    op.create_index("ix_issue_objects_comment", "issue_objects", ["comment"])
    op.create_index("ix_issue_objects_category_id", "issue_objects", ["category_id"])

    # 3. Seed default root categories
    conn = op.get_bind()
    default_categories = [
        ("Люди", _normalize("Люди")),
        ("Машины", _normalize("Машины")),
        ("Базы", _normalize("Базы")),
        ("Подразделения", _normalize("Подразделения")),
        ("Контрагенты", _normalize("Контрагенты")),
        ("Прочие объекты", _normalize("Прочие объекты")),
    ]

    other_category_id = None
    for i, (name, normalized_key) in enumerate(default_categories):
        result = conn.execute(
            sa.text(
                "INSERT INTO issue_object_categories (name, normalized_key, sort_order, is_active, created_at, updated_at) "
                "VALUES (:name, :normalized_key, :sort_order, true, now(), now()) "
                "ON CONFLICT (parent_id, normalized_key) WHERE parent_id IS NULL DO NOTHING "
                "RETURNING id"
            ),
            {"name": name, "normalized_key": normalized_key, "sort_order": i},
        )
        row = result.fetchone()
        cat_id = row[0] if row else None
        if cat_id and name == "Прочие объекты":
            other_category_id = cat_id

    # Get other category id if not found above
    if other_category_id is None:
        result = conn.execute(
            sa.text("SELECT id FROM issue_object_categories WHERE normalized_key = :nk AND parent_id IS NULL"),
            {"nk": _normalize("Прочие объекты")},
        )
        row = result.fetchone()
        if row:
            other_category_id = row[0]

    # 4. Map existing issue_objects to categories by object_type
    type_to_category = {
        "person": _normalize("Люди"),
        "vehicle": _normalize("Машины"),
        "base": _normalize("Базы"),
        "department": _normalize("Подразделения"),
        "contractor": _normalize("Контрагенты"),
        "other_object": _normalize("Прочие объекты"),
        "system_repo": _normalize("Прочие объекты"),
    }

    for object_type, cat_normalized in type_to_category.items():
        conn.execute(
            sa.text(
                "UPDATE issue_objects "
                "SET category_id = (SELECT id FROM issue_object_categories WHERE normalized_key = :cat_nk AND parent_id IS NULL LIMIT 1) "
                "WHERE object_type = :obj_type AND category_id IS NULL"
            ),
            {"cat_nk": cat_normalized, "obj_type": object_type},
        )

    # Fallback for any remaining objects without category
    if other_category_id:
        conn.execute(
            sa.text(
                "UPDATE issue_objects SET category_id = :cat_id WHERE category_id IS NULL"
            ),
            {"cat_id": other_category_id},
        )


def downgrade() -> None:
    """Downgrade schema: drop columns and table."""

    op.drop_index("ix_issue_objects_category_id", table_name="issue_objects")
    op.drop_index("ix_issue_objects_comment", table_name="issue_objects")
    op.drop_column("issue_objects", "category_id")
    op.drop_column("issue_objects", "comment")
    op.drop_table("issue_object_categories")
