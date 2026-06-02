"""create issue_objects table, migrate from recipients

Revision ID: 0012_issue_objects
Revises: 0011_catalog_audit_fields
Create Date: 2026-06-02 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_issue_objects"
down_revision: Union[str, Sequence[str], None] = "0011_catalog_audit_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create issue_objects, migrate data, drop recipients."""

    # 1. Create issue_objects table
    op.create_table(
        "issue_objects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("object_type", sa.String(24), nullable=False, server_default="person"),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("normalized_key", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("merged_into_id", sa.Integer(), sa.ForeignKey("issue_objects.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_index("ix_issue_objects_display_name", "issue_objects", ["display_name"])
    op.create_index("ix_issue_objects_deleted_at", "issue_objects", ["deleted_at"])

    # 2. Create issue_object_aliases table
    op.create_table(
        "issue_object_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_object_id", sa.Integer(), sa.ForeignKey("issue_objects.id"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("normalized_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_index("ix_issue_object_aliases_issue_object_id", "issue_object_aliases", ["issue_object_id"])

    # 3. Migrate recipient data to issue_objects if any exists
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT COUNT(*) FROM recipients")).scalar()
    if result and int(result) > 0:
        # Copy existing recipients to issue_objects
        conn.execute(sa.text("""
            INSERT INTO issue_objects (id, display_name, object_type, code, normalized_key, is_active,
                                       merged_into_id, created_at, updated_at, deleted_at, deleted_by_user_id)
            SELECT id, display_name, recipient_type, NULL, normalized_key, is_active,
                   merged_into_id, created_at, updated_at, deleted_at, deleted_by_user_id
            FROM recipients
        """))
        # Copy recipient aliases
        conn.execute(sa.text("""
            INSERT INTO issue_object_aliases (issue_object_id, alias, normalized_key, created_at)
            SELECT recipient_id, alias, normalized_key, created_at
            FROM recipient_aliases
        """))

    # 4. Add issue_object_id and issue_object_name_snapshot to operations
    op.add_column("operations", sa.Column("issue_object_id", sa.Integer(), nullable=True))
    op.add_column("operations", sa.Column("issue_object_name_snapshot", sa.String(255), nullable=True))
    op.create_foreign_key("fk_operations_issue_object_id", "operations", "issue_objects", ["issue_object_id"], ["id"])

    # Migrate data from recipient fields if present
    if result and int(result) > 0:
        conn.execute(sa.text("""
            UPDATE operations
            SET issue_object_id = recipient_id,
                issue_object_name_snapshot = recipient_name_snapshot
            WHERE recipient_id IS NOT NULL
        """))

    # 5. Add issue_object_id to issued_asset_balances
    # Drop existing PK constraint first (recipient_id is part of composite PK)
    op.drop_constraint("ck_issued_asset_qty_non_negative", "issued_asset_balances", type_="check")
    op.drop_constraint("issued_asset_balances_pkey", "issued_asset_balances", type_="primary")

    op.add_column("issued_asset_balances", sa.Column("issue_object_id", sa.Integer(), nullable=True))

    if result and int(result) > 0:
        conn.execute(sa.text("""
            UPDATE issued_asset_balances
            SET issue_object_id = recipient_id
            WHERE recipient_id IS NOT NULL
        """))

    # Set NOT NULL after migration and recreate PK
    op.alter_column("issued_asset_balances", "issue_object_id", nullable=False)
    op.create_primary_key("issued_asset_balances_pkey", "issued_asset_balances", ["issue_object_id", "inventory_subject_id"])
    op.create_foreign_key("fk_iab_issue_object_id", "issued_asset_balances", "issue_objects", ["issue_object_id"], ["id"])
    op.create_check_constraint("ck_issued_asset_qty_non_negative", "issued_asset_balances", sa.text("qty >= 0"))

    # 6. Update operation_acceptance_actions FK from recipients to issue_objects
    op.drop_constraint("operation_acceptance_actions_recipient_id_fkey", "operation_acceptance_actions", type_="foreignkey")
    op.create_foreign_key("fk_oaa_issue_object_id", "operation_acceptance_actions", "issue_objects", ["recipient_id"], ["id"])

    # 7. Drop old recipient columns from operations
    op.drop_column("operations", "recipient_id")
    op.drop_column("operations", "recipient_name_snapshot")

    # 8. Drop old recipient column from issued_asset_balances
    op.drop_column("issued_asset_balances", "recipient_id")

    # 9. Drop recipients and recipient_aliases tables
    op.drop_table("recipient_aliases")
    op.drop_table("recipients")

    # 10. Add check constraint for object_type
    op.create_check_constraint(
        "ck_issue_objects_type",
        "issue_objects",
        sa.text("object_type IN ('person', 'base', 'vehicle', 'department', 'contractor', 'other_object', 'system_repo')"),
    )


def downgrade() -> None:
    """Downgrade schema: restore recipients, drop issue_objects."""

    # 1. Restore recipients table
    op.create_table(
        "recipients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_type", sa.String(24), nullable=False, server_default="person"),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("normalized_key", sa.String(255), nullable=False),
        sa.Column("personnel_no", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("merged_into_id", sa.Integer(), sa.ForeignKey("recipients.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_index("ix_recipients_display_name", "recipients", ["display_name"])
    op.create_index("ix_recipients_personnel_no", "recipients", ["personnel_no"])
    op.create_index("ix_recipients_deleted_at", "recipients", ["deleted_at"])
    op.create_check_constraint(
        "ck_recipients_type",
        "recipients",
        sa.text("recipient_type IN ('person', 'group', 'department', 'contractor', 'system_repo')"),
    )

    # 2. Restore recipient_aliases table
    op.create_table(
        "recipient_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("recipients.id"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("normalized_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_index("ix_recipient_aliases_recipient_id", "recipient_aliases", ["recipient_id"])

    # 3. Migrate data back
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT COUNT(*) FROM issue_objects")).scalar()
    if result and int(result) > 0:
        conn.execute(sa.text("""
            INSERT INTO recipients (id, display_name, recipient_type, personnel_no, normalized_key, is_active,
                                    merged_into_id, created_at, updated_at, deleted_at, deleted_by_user_id)
            SELECT id, display_name, object_type, NULL, normalized_key, is_active,
                   merged_into_id, created_at, updated_at, deleted_at, deleted_by_user_id
            FROM issue_objects
        """))
        conn.execute(sa.text("""
            INSERT INTO recipient_aliases (recipient_id, alias, normalized_key, created_at)
            SELECT issue_object_id, alias, normalized_key, created_at
            FROM issue_object_aliases
        """))

    # 4. Drop issue_object FKs and restore old columns
    op.drop_constraint("fk_operations_issue_object_id", "operations", type_="foreignkey")
    op.add_column("operations", sa.Column("recipient_id", sa.Integer(), nullable=True))
    op.add_column("operations", sa.Column("recipient_name_snapshot", sa.String(255), nullable=True))
    op.create_foreign_key("fk_operations_recipient_id", "operations", "recipients", ["recipient_id"], ["id"])

    if result and int(result) > 0:
        conn.execute(sa.text("""
            UPDATE operations
            SET recipient_id = issue_object_id,
                recipient_name_snapshot = issue_object_name_snapshot
            WHERE issue_object_id IS NOT NULL
        """))

    op.drop_column("operations", "issue_object_id")
    op.drop_column("operations", "issue_object_name_snapshot")

    # 5. Restore issued_asset_balances
    op.drop_constraint("ck_issued_asset_qty_non_negative", "issued_asset_balances", type_="check")
    op.drop_constraint("issued_asset_balances_pkey", "issued_asset_balances", type_="primary")
    op.drop_constraint("fk_iab_issue_object_id", "issued_asset_balances", type_="foreignkey")

    op.add_column("issued_asset_balances", sa.Column("recipient_id", sa.Integer(), nullable=True))

    if result and int(result) > 0:
        conn.execute(sa.text("""
            UPDATE issued_asset_balances
            SET recipient_id = issue_object_id
            WHERE issue_object_id IS NOT NULL
        """))

    op.alter_column("issued_asset_balances", "recipient_id", nullable=False)
    op.create_primary_key("issued_asset_balances_pkey", "issued_asset_balances", ["recipient_id", "inventory_subject_id"])
    op.create_foreign_key("fk_iab_recipient_id", "issued_asset_balances", "recipients", ["recipient_id"], ["id"])
    op.create_check_constraint("ck_issued_asset_qty_non_negative", "issued_asset_balances", sa.text("qty >= 0"))

    op.drop_column("issued_asset_balances", "issue_object_id")

    # 6. Restore operation_acceptance_actions FK
    op.drop_constraint("fk_oaa_issue_object_id", "operation_acceptance_actions", type_="foreignkey")
    op.create_foreign_key(
        "operation_acceptance_actions_recipient_id_fkey",
        "operation_acceptance_actions", "recipients",
        ["recipient_id"], ["id"],
    )

    # 7. Drop issue_objects tables
    op.drop_table("issue_object_aliases")
    op.drop_table("issue_objects")
