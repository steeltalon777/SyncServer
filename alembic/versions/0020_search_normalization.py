"""search_normalization: Add normalized_name to sites/devices, backfill, trigram indexes

Revision ID: 0020_search_normalization
Revises: 0019_add_sync_state
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0020_search_normalization"
down_revision = "0019_add_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. pg_trgm extension for trigram-based ILIKE search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. New columns
    op.execute("ALTER TABLE sites ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255)")
    op.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255)")

    # 3. Backfill ALL normalized_name columns with correct logic:
    #    lowercase + ё→е + remove punctuation + collapse spaces + trim
    #    Using explicit Unicode-aware character classes for Cyrillic support
    op.execute("""
        UPDATE items SET normalized_name = btrim(
            regexp_replace(
                regexp_replace(replace(lower(name::text), 'ё', 'е'), '[^a-zа-яё0-9_\\s]', ' ', 'g'),
                '\\s+', ' ', 'g'
            )
        ) WHERE name IS NOT NULL
    """)

    op.execute("""
        UPDATE categories SET normalized_name = btrim(
            regexp_replace(
                regexp_replace(replace(lower(name::text), 'ё', 'е'), '[^a-zа-яё0-9_\\s]', ' ', 'g'),
                '\\s+', ' ', 'g'
            )
        ) WHERE name IS NOT NULL
    """)

    op.execute("""
        UPDATE sites SET normalized_name = btrim(
            regexp_replace(
                regexp_replace(replace(lower(name::text), 'ё', 'е'), '[^a-zа-яё0-9_\\s]', ' ', 'g'),
                '\\s+', ' ', 'g'
            )
        ) WHERE name IS NOT NULL
    """)

    op.execute("""
        UPDATE devices SET normalized_name = btrim(
            regexp_replace(
                regexp_replace(replace(lower(device_name::text), 'ё', 'е'), '[^a-zа-яё0-9_\\s]', ' ', 'g'),
                '\\s+', ' ', 'g'
            )
        ) WHERE device_name IS NOT NULL
    """)

    op.execute("""
        UPDATE temporary_items SET normalized_name = btrim(
            regexp_replace(
                regexp_replace(replace(lower(name::text), 'ё', 'е'), '[^a-zа-яё0-9_\\s]', ' ', 'g'),
                '\\s+', ' ', 'g'
            )
        ) WHERE name IS NOT NULL
    """)

    # 4. B-tree indexes (for exact match and prefix search)
    op.create_index("ix_sites_normalized_name", "sites", ["normalized_name"])
    op.create_index("ix_devices_normalized_name", "devices", ["normalized_name"])

    # 5. GIN trigram indexes for ILIKE '%term%' acceleration
    op.execute("CREATE INDEX IF NOT EXISTS ix_items_normalized_name_trgm ON items USING gin (normalized_name gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_categories_normalized_name_trgm ON categories USING gin (normalized_name gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sites_normalized_name_trgm ON sites USING gin (normalized_name gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_normalized_name_trgm ON devices USING gin (normalized_name gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_temporary_items_normalized_name_trgm ON temporary_items USING gin (normalized_name gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_temporary_items_normalized_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_devices_normalized_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_sites_normalized_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_categories_normalized_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_items_normalized_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_devices_normalized_name")
    op.execute("DROP INDEX IF EXISTS ix_sites_normalized_name")
    op.execute("ALTER TABLE devices DROP COLUMN IF EXISTS normalized_name")
    op.execute("ALTER TABLE sites DROP COLUMN IF EXISTS normalized_name")
