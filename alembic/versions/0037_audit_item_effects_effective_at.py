"""0037_audit_item_effects_effective_at: business effect timestamp

ADR-0028 §5/§6, TZ-HISTORICAL_INTEGRITY_STAGE_A §9.2.

Adds ``effective_at`` to ``audit_item_effects``: the immutable business
timestamp at which a concrete balance mutation became effective. This is
distinct from ``created_at`` (physical insert time). A late acceptance in
July must not be dated as if it happened in May, and a July cancel must
not erase the May forward effect date.

Migration stages (single revision):

1. Add nullable ``effective_at`` WITHOUT server default, so pre-existing
   rows never receive a fake migration-time value.
2. Event-aware deterministic backfill of ALL pre-existing rows:
   - ``operation.submit``          -> COALESCE(operations.effective_at, audit_events.created_at, effects.created_at)
   - ``operation.cancel``          -> COALESCE(operations.cancelled_at, audit_events.created_at, effects.created_at)
   - correction / all other events -> COALESCE(audit_events.created_at, effects.created_at)
3. Abort (with diagnostics) if any NULL remains after backfill. A silent
   ``now()`` backfill is forbidden.
4. Set ``server_default=now()`` as compatibility safety net, then NOT NULL.
5. Add ``ix_audit_item_effects_effective_at``.

Downgrade drops only the new column/index; it never rewrites operation
history.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0037_audit_item_effects_effective_at"
down_revision = "0036_operation_revision_lines_composite_pk"
branch_labels = None
depends_on = None


# Mapping of audit event types handled by a dedicated source timestamp vs
# the generic event-time fallback. Any event not listed here is treated as
# "correction/other" and backfilled from audit_events.created_at.
_SUBMIT_EVENT_TYPES = ("operation.submit",)
_CANCEL_EVENT_TYPES = ("operation.cancel",)

# Use ``expanding=True`` so SQLAlchemy renders ``IN (v1, v2, ...)`` from a
# tuple parameter (PostgreSQL/asyncpg does not accept a tuple-bound ``$N``
# placeholder in an ``IN`` clause). Same trick for the NOT IN branch.
#
# PostgreSQL forbids referencing the UPDATE target alias from a JOIN inside
# the UPDATE FROM clause (with or without ``AS``). The workaround is to
# resolve the operation timestamp inside a CTE first, then drive the UPDATE
# from that CTE.
_BACKFILL_SUBMIT_SQL = sa.text(
    """
    WITH targets AS (
        SELECT aie.id AS effect_id,
               ops.effective_at AS op_effective_at,
               ae.created_at AS event_created_at,
               aie.created_at AS effect_created_at
        FROM audit_item_effects aie
        JOIN audit_events ae ON ae.id = aie.audit_event_id
        LEFT JOIN operations ops ON ops.id = aie.operation_id
        WHERE ae.event_type IN :submit_types
    )
    UPDATE audit_item_effects
    SET effective_at = COALESCE(targets.op_effective_at, targets.event_created_at, targets.effect_created_at)
    FROM targets
    WHERE audit_item_effects.id = targets.effect_id
    """
).bindparams(sa.bindparam("submit_types", expanding=True))

_BACKFILL_CANCEL_SQL = sa.text(
    """
    WITH targets AS (
        SELECT aie.id AS effect_id,
               ops.cancelled_at AS op_cancelled_at,
               ae.created_at AS event_created_at,
               aie.created_at AS effect_created_at
        FROM audit_item_effects aie
        JOIN audit_events ae ON ae.id = aie.audit_event_id
        LEFT JOIN operations ops ON ops.id = aie.operation_id
        WHERE ae.event_type IN :cancel_types
    )
    UPDATE audit_item_effects
    SET effective_at = COALESCE(targets.op_cancelled_at, targets.event_created_at, targets.effect_created_at)
    FROM targets
    WHERE audit_item_effects.id = targets.effect_id
    """
).bindparams(sa.bindparam("cancel_types", expanding=True))

_BACKFILL_OTHER_SQL = sa.text(
    """
    WITH targets AS (
        SELECT aie.id AS effect_id,
               ae.created_at AS event_created_at,
               aie.created_at AS effect_created_at
        FROM audit_item_effects aie
        JOIN audit_events ae ON ae.id = aie.audit_event_id
        WHERE ae.event_type NOT IN :covered_types
    )
    UPDATE audit_item_effects
    SET effective_at = COALESCE(targets.event_created_at, targets.effect_created_at)
    FROM targets
    WHERE audit_item_effects.id = targets.effect_id
    """
).bindparams(sa.bindparam("covered_types", expanding=True))

_COUNT_NULL_SQL = sa.text(
    "SELECT COUNT(*) FROM audit_item_effects WHERE effective_at IS NULL"
)


def upgrade() -> None:
    # Stage 1: nullable column, no default. Existing rows keep NULL so the
    # backfill (not the migration run time) decides their value.
    op.add_column(
        "audit_item_effects",
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Stage 2: event-aware backfill. Each UPDATE is a separate statement so
    # a slow/large backfill remains diagnosable; all statements run inside
    # the migration's implicit transaction.
    op.execute(_BACKFILL_SUBMIT_SQL.params(submit_types=list(_SUBMIT_EVENT_TYPES)))
    op.execute(_BACKFILL_CANCEL_SQL.params(cancel_types=list(_CANCEL_EVENT_TYPES)))
    op.execute(_BACKFILL_OTHER_SQL.params(covered_types=list(_SUBMIT_EVENT_TYPES + _CANCEL_EVENT_TYPES)))

    # Stage 3: abort on NULL. Silent now() backfill is forbidden.
    conn = op.get_bind()
    null_count = conn.execute(_COUNT_NULL_SQL).scalar()
    if null_count:
        raise RuntimeError(
            f"audit_item_effects.effective_at backfill left {null_count} "
            "NULL row(s); refusing to apply now() silently. Investigate the "
            "affected rows before retrying the migration."
        )

    # Stage 4: server_default safety net, then NOT NULL.
    op.alter_column(
        "audit_item_effects",
        "effective_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "audit_item_effects",
        "effective_at",
        nullable=False,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

    # Stage 5: index for effective_at-filtered diagnostics.
    op.create_index(
        "ix_audit_item_effects_effective_at",
        "audit_item_effects",
        ["effective_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_item_effects_effective_at", table_name="audit_item_effects")
    op.drop_column("audit_item_effects", "effective_at")
