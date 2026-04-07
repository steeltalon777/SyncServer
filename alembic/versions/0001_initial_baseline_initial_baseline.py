"""initial baseline

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-04-02 16:35:11.762334

"""
from collections.abc import Sequence

from alembic import op


revision: str = "0001_initial_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE categories (
        id SERIAL NOT NULL,
        name VARCHAR(255) NOT NULL,
        code VARCHAR(100),
        parent_id INTEGER,
        is_active BOOLEAN DEFAULT 'true' NOT NULL,
        sort_order INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_categories_parent_name UNIQUE (parent_id, name),
        FOREIGN KEY(parent_id) REFERENCES categories (id)
    )
    """,
    "CREATE INDEX ix_categories_parent_id ON categories (parent_id)",
    "CREATE INDEX ix_categories_updated_at ON categories (updated_at)",
    """
    CREATE TABLE sites (
        id SERIAL NOT NULL,
        code VARCHAR(64) NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        is_active BOOLEAN DEFAULT 'true' NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (code)
    )
    """,
    "CREATE UNIQUE INDEX ux_sites_code ON sites (code)",
    """
    CREATE TABLE units (
        id SERIAL NOT NULL,
        name VARCHAR(100) NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        is_active BOOLEAN DEFAULT 'true' NOT NULL,
        sort_order INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (name),
        UNIQUE (symbol)
    )
    """,
    "CREATE INDEX ix_units_updated_at ON units (updated_at)",
    """
    CREATE TABLE devices (
        id SERIAL NOT NULL,
        device_code VARCHAR(100) NOT NULL,
        device_name VARCHAR(255) NOT NULL,
        device_token UUID NOT NULL,
        site_id INTEGER,
        is_active BOOLEAN DEFAULT 'true' NOT NULL,
        last_seen_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (device_code),
        UNIQUE (device_token),
        FOREIGN KEY(site_id) REFERENCES sites (id)
    )
    """,
    "CREATE INDEX ix_devices_last_seen_at ON devices (last_seen_at)",
    "CREATE INDEX ix_devices_site_id ON devices (site_id)",
    "CREATE INDEX ix_devices_updated_at ON devices (updated_at)",
    """
    CREATE TABLE items (
        id SERIAL NOT NULL,
        sku VARCHAR(100),
        name VARCHAR(255) NOT NULL,
        category_id INTEGER NOT NULL,
        unit_id INTEGER NOT NULL,
        description TEXT,
        is_active BOOLEAN DEFAULT 'true' NOT NULL,
        hashtags JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (sku),
        FOREIGN KEY(category_id) REFERENCES categories (id),
        FOREIGN KEY(unit_id) REFERENCES units (id)
    )
    """,
    "CREATE INDEX idx_items_hashtags ON items USING gin (hashtags)",
    "CREATE INDEX ix_items_category_id ON items (category_id)",
    "CREATE INDEX ix_items_unit_id ON items (unit_id)",
    "CREATE INDEX ix_items_updated_at ON items (updated_at)",
    """
    CREATE TABLE users (
        id UUID NOT NULL,
        username VARCHAR(150) NOT NULL,
        email VARCHAR(255),
        full_name VARCHAR(255),
        user_token UUID NOT NULL,
        is_active BOOLEAN DEFAULT 'true' NOT NULL,
        is_root BOOLEAN DEFAULT 'false' NOT NULL,
        role VARCHAR(32) NOT NULL,
        default_site_id INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_users_role CHECK (role IN ('root', 'chief_storekeeper', 'storekeeper', 'observer')),
        UNIQUE (username),
        UNIQUE (user_token),
        FOREIGN KEY(default_site_id) REFERENCES sites (id)
    )
    """,
    "CREATE INDEX ix_users_default_site_id ON users (default_site_id)",
    "CREATE UNIQUE INDEX ux_users_email ON users (email)",
    "CREATE UNIQUE INDEX ux_users_user_token ON users (user_token)",
    "CREATE UNIQUE INDEX ux_users_username ON users (username)",
    """
    CREATE TABLE balances (
        site_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        qty NUMERIC(18, 3) DEFAULT '0' NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (site_id, item_id),
        FOREIGN KEY(site_id) REFERENCES sites (id),
        FOREIGN KEY(item_id) REFERENCES items (id)
    )
    """,
    """
    CREATE TABLE events (
        event_uuid UUID NOT NULL,
        site_id INTEGER NOT NULL,
        device_id INTEGER,
        user_id INTEGER,
        event_type VARCHAR(64) NOT NULL,
        event_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
        received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        schema_version INTEGER DEFAULT '1' NOT NULL,
        payload JSONB NOT NULL,
        server_seq BIGINT GENERATED BY DEFAULT AS IDENTITY,
        payload_hash VARCHAR(64) NOT NULL,
        PRIMARY KEY (event_uuid),
        FOREIGN KEY(site_id) REFERENCES sites (id),
        FOREIGN KEY(device_id) REFERENCES devices (id),
        UNIQUE (server_seq)
    )
    """,
    "CREATE INDEX ix_events_event_type ON events (event_type)",
    "CREATE INDEX ix_events_site_id_event_datetime ON events (site_id, event_datetime)",
    "CREATE INDEX ix_events_site_id_server_seq ON events (site_id, server_seq)",
    """
    CREATE TABLE operations (
        id UUID NOT NULL,
        site_id INTEGER NOT NULL,
        operation_type VARCHAR(32) NOT NULL,
        status VARCHAR(16) DEFAULT 'draft' NOT NULL,
        source_site_id INTEGER,
        destination_site_id INTEGER,
        issued_to_user_id UUID,
        issued_to_name VARCHAR(255),
        created_by_user_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        effective_at TIMESTAMP WITH TIME ZONE,
        submitted_at TIMESTAMP WITH TIME ZONE,
        submitted_by_user_id UUID,
        cancelled_at TIMESTAMP WITH TIME ZONE,
        cancelled_by_user_id UUID,
        notes TEXT,
        PRIMARY KEY (id),
        CONSTRAINT ck_operations_type CHECK (operation_type IN ('RECEIVE', 'EXPENSE', 'WRITE_OFF', 'MOVE', 'ADJUSTMENT', 'ISSUE', 'ISSUE_RETURN')),
        CONSTRAINT ck_operations_status CHECK (status IN ('draft', 'submitted', 'cancelled')),
        FOREIGN KEY(site_id) REFERENCES sites (id),
        FOREIGN KEY(source_site_id) REFERENCES sites (id),
        FOREIGN KEY(destination_site_id) REFERENCES sites (id),
        FOREIGN KEY(issued_to_user_id) REFERENCES users (id),
        FOREIGN KEY(created_by_user_id) REFERENCES users (id),
        FOREIGN KEY(submitted_by_user_id) REFERENCES users (id),
        FOREIGN KEY(cancelled_by_user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE user_access_scopes (
        id BIGSERIAL NOT NULL,
        user_id UUID NOT NULL,
        site_id INTEGER NOT NULL,
        can_view BOOLEAN DEFAULT 'true' NOT NULL,
        can_operate BOOLEAN DEFAULT 'false' NOT NULL,
        can_manage_catalog BOOLEAN DEFAULT 'false' NOT NULL,
        is_active BOOLEAN DEFAULT 'true' NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_user_access_scope_user_site UNIQUE (user_id, site_id),
        FOREIGN KEY(user_id) REFERENCES users (id),
        FOREIGN KEY(site_id) REFERENCES sites (id)
    )
    """,
    "CREATE INDEX ix_user_access_scope_site_id ON user_access_scopes (site_id)",
    "CREATE INDEX ix_user_access_scope_user_id ON user_access_scopes (user_id)",
    """
    CREATE TABLE operation_lines (
        id BIGSERIAL NOT NULL,
        operation_id UUID NOT NULL,
        line_number INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        qty NUMERIC(18, 3) NOT NULL,
        batch VARCHAR(100),
        comment TEXT,
        PRIMARY KEY (id),
        CONSTRAINT ck_operation_lines_qty_non_zero CHECK (qty <> 0),
        FOREIGN KEY(operation_id) REFERENCES operations (id),
        FOREIGN KEY(item_id) REFERENCES items (id)
    )
    """,
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("operation_lines")
    op.drop_table("user_access_scopes")
    op.drop_table("operations")
    op.drop_table("events")
    op.drop_table("balances")
    op.drop_table("users")
    op.drop_table("items")
    op.drop_table("devices")
    op.drop_table("units")
    op.drop_table("sites")
    op.drop_table("categories")
