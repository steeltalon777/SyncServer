"""fix item_id nullable for issued_asset_balances and balances

Revision ID: 0018_fix_item_id_nullable
Revises: 0017_add_audit_events
Create Date: 2026-06-18
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_fix_item_id_nullable"
down_revision: str | None = "0017_add_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make item_id nullable in issued_asset_balances and balances."""

    # issued_asset_balances — was manually fixed on prod, guard prevents duplicate
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE issued_asset_balances ALTER COLUMN item_id DROP NOT NULL;
        EXCEPTION
            WHEN others THEN
                -- column already nullable — ok
                NULL;
        END
        $$;
    """)

    # balances — currently NOT NULL on prod, must be fixed
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE balances ALTER COLUMN item_id DROP NOT NULL;
        EXCEPTION
            WHEN others THEN
                NULL;
        END
        $$;
    """)


def downgrade() -> None:
    """Restore item_id NOT NULL (best-effort; only succeeds if all rows have non-null item_id)."""

    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE balances ALTER COLUMN item_id SET NOT NULL;
        EXCEPTION
            WHEN others THEN
                NULL;
        END
        $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE issued_asset_balances ALTER COLUMN item_id SET NOT NULL;
        EXCEPTION
            WHEN others THEN
                NULL;
        END
        $$;
    """)
