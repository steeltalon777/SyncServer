"""Fix operation_revision_lines PK to composite (revision_id, line_uuid).

Aligns the database primary key with the SQLAlchemy model and the
original intent documented in migration 0034 (header: "composite PK:
revision_id + line_uuid"). Migration 0034 only marked ``revision_id``
as ``primary_key=True`` on the ``sa.Column``, which produced a
single-column ``PRIMARY KEY (revision_id)`` in the DDL. The model
declares both columns as ``primary_key=True`` (composite).

A single-column PK on ``revision_id`` allows at most one row per
revision. The submit service (``operations_service.py``) inserts one
``operation_revision_lines`` row per operation line inside a loop,
so any submit with two or more lines raised::

    asyncpg.exceptions.UniqueViolationError: duplicate key value
    violates unique constraint "operation_revision_lines_pkey"
    DETAIL: Key (revision_id)=(...) already exists.

This surfaced as the E2E submit-error scenario 5 (success-after-fix)
and also affects any other multi-line submit. The fix is to promote
the PK to ``(revision_id, line_uuid)`` so a revision can carry many
lines. Existing data (19 rows, each revision currently has exactly
one row) is already valid under the composite PK: ``revision_id``
is unique across rows, and ``line_uuid`` is NOT NULL, so every
existing row keeps its uniqueness guarantee.

Revision ID: 0036_operation_revision_lines_composite_pk
Revises: 0035_set_base_revision_not_null
"""
from __future__ import annotations

from alembic import op


revision = "0036_operation_revision_lines_composite_pk"
down_revision = "0035_set_base_revision_not_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "operation_revision_lines_pkey",
        "operation_revision_lines",
        type_="primary",
    )
    op.create_primary_key(
        "operation_revision_lines_pkey",
        "operation_revision_lines",
        ["revision_id", "line_uuid"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "operation_revision_lines_pkey",
        "operation_revision_lines",
        type_="primary",
    )
    op.create_primary_key(
        "operation_revision_lines_pkey",
        "operation_revision_lines",
        ["revision_id"],
    )