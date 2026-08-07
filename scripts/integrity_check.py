#!/usr/bin/env python3
"""A-7 read-only integrity CLI for SyncServer (TZ-HISTORICAL_INTEGRITY_STAGE_A §11).

The script runs the ten symbolic A-7 checks documented in
``docs/adr/0028-historical-integrity-stage-a.md`` against a SyncServer
database. It is intentionally read-only: every connection starts a
transaction with ``SET TRANSACTION READ ONLY`` and executes only ``SELECT``
statements. No repair / update / delete options are accepted.

The CLI supports a human-readable text summary and a deterministic
JSON document. Exit codes:

* ``0`` — no findings at/above ``--fail-on`` (default ``critical``);
* ``1`` — at least one finding at/above the configured threshold;
* ``2`` — invalid arguments, configuration or DB execution error.

The script never prints DSN strings, tokens, free-text notes, or other
secrets: errors are sanitised and ``samples`` only contain stable numeric
identifiers, classifications, quantities, dates and booleans.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE_ERROR = 2

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
THRESHOLDS = ("critical", "warning")
DEFAULT_FAIL_ON = "critical"
DEFAULT_SAMPLE_LIMIT = 10
MAX_SAMPLE_LIMIT = 100
DEFAULT_LATE_THRESHOLD_DAYS = 7
MAX_LATE_THRESHOLD_DAYS = 365

# Checks are evaluated in this exact order. The JSON / text outputs follow the
# same order so the verdict is stable across runs.
CHECKS: tuple[str, ...] = (
    "BALANCE_EFFECT_DRIFT",
    "EXPECTED_EFFECT_GAP",
    "ACCEPTANCE_EFFECT_GAP",
    "EFFECT_DATE_NULL",
    "EFFECT_CHAIN_BROKEN",
    "MERGE_CHAIN_CYCLE",
    "BACKDATED_SUBMITTED",
    "LATE_ACCEPTANCE",
    "MERGE_AUDIT_GAP",
    "AUDIT_ENTITY_ORPHAN",
)

# Default severity for each check; operators may reclassify via CLI flags
# in the future but for now the defaults match ADR-0028 §8 and TZ §11.2.
DEFAULT_SEVERITY: dict[str, str] = {
    "BALANCE_EFFECT_DRIFT": "critical",
    "EXPECTED_EFFECT_GAP": "critical",
    "ACCEPTANCE_EFFECT_GAP": "critical",
    "EFFECT_DATE_NULL": "critical",
    "EFFECT_CHAIN_BROKEN": "critical",
    "MERGE_CHAIN_CYCLE": "critical",
    "BACKDATED_SUBMITTED": "warning",
    "LATE_ACCEPTANCE": "warning",
    "MERGE_AUDIT_GAP": "warning",
    "AUDIT_ENTITY_ORPHAN": "warning",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CheckResult:
    code: str
    status: str
    count: int
    severity: str
    samples: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# SQL definitions
# ---------------------------------------------------------------------------
#
# All queries are READ ONLY. The sample is bounded by :sample_limit. The
# total count is computed via COUNT(*) OVER () to keep a single statement
# per check. Order is deterministic by stable identifiers.

BALANCE_EFFECT_DRIFT_SQL = text(
    """
    WITH eff AS (
        SELECT site_id,
               inventory_subject_id,
               ROUND(SUM(quantity_delta), 3) AS eff_sum
        FROM audit_item_effects
        WHERE site_id IS NOT NULL
        GROUP BY site_id, inventory_subject_id
    )
    SELECT
        COALESCE(b.site_id, e.site_id)                AS site_id,
        COALESCE(b.inventory_subject_id, e.inventory_subject_id)
                                                     AS inventory_subject_id,
        CASE
            WHEN b.site_id IS NULL THEN 'effect_only'
            WHEN e.site_id IS NULL THEN 'balance_only'
            ELSE 'drift'
        END                                          AS kind,
        b.qty                                        AS balance_qty,
        e.eff_sum                                    AS effect_sum,
        s.archived_at IS NOT NULL                    AS subject_archived,
        COUNT(*) OVER ()                             AS _total_count
    FROM balances b
    FULL OUTER JOIN eff e
        ON b.site_id = e.site_id
       AND b.inventory_subject_id = e.inventory_subject_id
    LEFT JOIN inventory_subjects s
        ON s.id = COALESCE(b.inventory_subject_id, e.inventory_subject_id)
    WHERE (
            b.site_id IS NULL
         OR (e.site_id IS NULL AND COALESCE(b.qty, 0) <> 0)
         OR (
                e.site_id IS NOT NULL
            AND ROUND(COALESCE(e.eff_sum, 0), 3) <> COALESCE(b.qty, 0)
         )
    )
    ORDER BY site_id, inventory_subject_id, kind
    LIMIT :sample_limit
    """
)

EXPECTED_EFFECT_GAP_SQL = text(
    """
    WITH classified AS (
        SELECT
            o.id                AS operation_id,
            o.operation_type,
            o.status,
            o.acceptance_required,
            o.acceptance_state,
            o.issue_object_id,
            o.acceptance_resolved_at,
            EXISTS (
                SELECT 1
                FROM audit_item_effects aie
                WHERE aie.operation_id = o.id
                  AND aie.effect_type <> 'cancel_reversal'
            ) AS has_forward_effect,
            EXISTS (
                SELECT 1
                FROM audit_item_effects aie
                WHERE aie.operation_id = o.id
                  AND aie.effect_type = 'acceptance'
            ) AS has_acceptance_effect,
            EXISTS (
                SELECT 1
                FROM operation_acceptance_actions oaa
                WHERE oaa.operation_id = o.id
            ) AS has_acceptance_action
        FROM operations o
        WHERE o.status = 'submitted'
          AND o.deleted_at IS NULL
    ),
    verdicts AS (
        SELECT
            operation_id,
            operation_type,
            status,
            acceptance_required,
            acceptance_state,
            issue_object_id,
            has_forward_effect,
            has_acceptance_effect,
            has_acceptance_action,
            CASE
                WHEN operation_type = 'WRITE_OFF'
                     AND issue_object_id IS NOT NULL
                    THEN NULL
                WHEN operation_type = 'WRITE_OFF'
                     AND issue_object_id IS NULL
                     AND NOT has_forward_effect
                    THEN 'critical'
                WHEN operation_type IN ('EXPENSE', 'ISSUE', 'ISSUE_RETURN')
                     AND NOT has_forward_effect
                    THEN 'critical'
                WHEN operation_type = 'ADJUSTMENT'
                     AND NOT has_forward_effect
                    THEN 'critical'
                WHEN operation_type = 'RECEIVE'
                     AND NOT acceptance_required
                     AND NOT has_forward_effect
                    THEN 'critical'
                WHEN operation_type = 'MOVE'
                     AND NOT acceptance_required
                     AND NOT has_forward_effect
                    THEN 'critical'
                WHEN operation_type = 'MOVE'
                     AND acceptance_required
                     AND acceptance_state IN ('pending', 'in_progress')
                    THEN 'warning'
                WHEN operation_type = 'MOVE'
                     AND acceptance_required
                     AND acceptance_state = 'resolved'
                     AND (
                         NOT has_forward_effect
                         OR NOT has_acceptance_effect
                     )
                    THEN 'critical'
                WHEN operation_type = 'RECEIVE'
                     AND acceptance_required
                     AND acceptance_state IN ('pending', 'in_progress')
                    THEN 'warning'
                WHEN operation_type = 'RECEIVE'
                     AND acceptance_required
                     AND acceptance_state = 'resolved'
                     AND NOT has_acceptance_effect
                    THEN 'critical'
                ELSE NULL
            END AS severity
        FROM classified
    )
    SELECT
        operation_id,
        operation_type,
        status,
        acceptance_required,
        acceptance_state,
        issue_object_id,
        has_forward_effect,
        has_acceptance_effect,
        severity,
        COUNT(*) OVER () AS _total_count
    FROM verdicts
    WHERE severity IS NOT NULL
    ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END,
             operation_id
    LIMIT :sample_limit
    """
)

ACCEPTANCE_EFFECT_GAP_SQL = text(
    """
    WITH action_event AS (
        SELECT
            (ae.changes ->> 'action_id')::bigint AS action_id,
            ae.id                                AS audit_event_id,
            ae.event_type
        FROM audit_events ae
        WHERE ae.event_type IN (
            'operation.line_accepted',
            'operation.line_mark_lost',
            'operation.line_lost_resolved'
        )
          AND ae.outcome = 'success'
    ),
    bound AS (
        SELECT
            oaa.id                    AS action_id,
            oaa.operation_id          AS operation_id,
            oaa.operation_line_id     AS operation_line_id,
            oaa.action_type           AS action_type,
            oaa.qty                   AS qty,
            oaa.performed_at          AS performed_at,
            ae.audit_event_id         AS audit_event_id,
            CASE
                WHEN oaa.action_type IN ('accept', 'found_to_destination', 'return_to_source')
                    THEN 'requires_effect'
                ELSE 'forbidden_effect'
            END AS rule
        FROM operation_acceptance_actions oaa
        LEFT JOIN action_event ae
            ON ae.action_id = oaa.id
    )
    SELECT
        b.action_id,
        b.operation_id,
        b.operation_line_id,
        b.action_type,
        b.qty,
        b.performed_at,
        b.audit_event_id,
        b.rule,
        CASE
            WHEN b.rule = 'requires_effect' AND b.audit_event_id IS NULL
                THEN 'legacy_missing_event'
            WHEN b.rule = 'requires_effect'
                 AND b.audit_event_id IS NOT NULL
                 AND NOT EXISTS (
                     SELECT 1
                     FROM audit_item_effects aie
                     WHERE aie.audit_event_id = b.audit_event_id
                       AND aie.effect_type = 'acceptance'
                 )
                THEN 'critical_missing_effect'
            WHEN b.rule = 'forbidden_effect'
                 AND b.audit_event_id IS NOT NULL
                 AND EXISTS (
                     SELECT 1
                     FROM audit_item_effects aie
                     WHERE aie.audit_event_id = b.audit_event_id
                       AND aie.effect_type = 'acceptance'
                 )
                THEN 'critical_forbidden_effect'
        END AS gap_kind,
        CASE
            WHEN b.audit_event_id IS NULL THEN 'warning'
            ELSE 'critical'
        END AS severity,
        COUNT(*) OVER () AS _total_count
    FROM bound b
    WHERE (
        (b.rule = 'requires_effect' AND b.audit_event_id IS NULL)
        OR (b.rule = 'requires_effect'
            AND b.audit_event_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1
                FROM audit_item_effects aie
                WHERE aie.audit_event_id = b.audit_event_id
                  AND aie.effect_type = 'acceptance'
            ))
        OR (b.rule = 'forbidden_effect'
            AND b.audit_event_id IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM audit_item_effects aie
                WHERE aie.audit_event_id = b.audit_event_id
                  AND aie.effect_type = 'acceptance'
            ))
    )
    ORDER BY CASE WHEN b.audit_event_id IS NULL THEN 1 ELSE 0 END,
             b.performed_at NULLS LAST,
             b.action_id
    LIMIT :sample_limit
    """
)

EFFECT_DATE_NULL_SQL = text(
    """
    SELECT
        aie.id              AS effect_id,
        aie.audit_event_id  AS audit_event_id,
        aie.operation_id    AS operation_id,
        aie.inventory_subject_id AS inventory_subject_id,
        aie.effect_type     AS effect_type,
        aie.created_at      AS created_at,
        COUNT(*) OVER ()    AS _total_count
    FROM audit_item_effects aie
    WHERE aie.effective_at IS NULL
    ORDER BY aie.id
    LIMIT :sample_limit
    """
)

EFFECT_CHAIN_BROKEN_SQL = text(
    """
    WITH ordered AS (
        SELECT
            aie.id,
            aie.audit_event_id,
            aie.operation_id,
            aie.site_id,
            aie.inventory_subject_id,
            aie.quantity_before,
            aie.quantity_delta,
            aie.quantity_after,
            aie.effective_at,
            LAG(aie.quantity_after) OVER (
                PARTITION BY aie.site_id, aie.inventory_subject_id
                ORDER BY aie.effective_at, aie.id
            ) AS prev_quantity_after
        FROM audit_item_effects aie
        WHERE aie.site_id IS NOT NULL
          AND aie.quantity_before IS NOT NULL
          AND aie.quantity_after IS NOT NULL
    ),
    row_break AS (
        SELECT
            id,
            audit_event_id,
            operation_id,
            site_id,
            inventory_subject_id,
            quantity_before,
            quantity_delta,
            quantity_after,
            NULL::numeric AS prev_quantity_after,
            NULL::timestamptz AS effective_at,
            'row_arithmetic'::text AS chain_kind,
            'critical'::text AS severity
        FROM ordered
        WHERE quantity_before + quantity_delta <> quantity_after
    ),
    chain_break AS (
        SELECT
            id,
            audit_event_id,
            operation_id,
            site_id,
            inventory_subject_id,
            quantity_before,
            NULL::numeric AS quantity_delta,
            quantity_after,
            prev_quantity_after,
            effective_at,
            'running_chain'::text AS chain_kind,
            'critical'::text AS severity
        FROM ordered
        WHERE prev_quantity_after IS NOT NULL
          AND prev_quantity_after <> quantity_before
    ),
    unified AS (
        SELECT * FROM row_break
        UNION ALL
        SELECT * FROM chain_break
    )
    SELECT
        id,
        audit_event_id,
        operation_id,
        site_id,
        inventory_subject_id,
        quantity_before,
        quantity_delta,
        quantity_after,
        prev_quantity_after,
        effective_at,
        chain_kind,
        severity,
        COUNT(*) OVER () AS _total_count
    FROM unified
    ORDER BY site_id, inventory_subject_id, effective_at NULLS LAST, id
    LIMIT :sample_limit
    """
)

MERGE_CHAIN_CYCLE_SQL = text(
    """
    WITH RECURSIVE chain AS (
        SELECT
            i.id              AS start_id,
            i.id              AS current_id,
            i.merged_into_id  AS next_id,
            1                 AS depth,
            ARRAY[i.id]       AS path,
            false             AS cycle
        FROM items i
        WHERE i.merged_into_id IS NOT NULL
          AND i.deleted_at IS NULL
        UNION ALL
        SELECT
            c.start_id,
            next_i.id,
            next_i.merged_into_id,
            c.depth + 1,
            c.path || next_i.id,
            next_i.id = ANY(c.path)
        FROM chain c
        JOIN items next_i
            ON next_i.id = c.next_id
        WHERE c.cycle = false
          AND c.depth < 32
    )
    SELECT
        start_id        AS item_id,
        depth,
        cycle,
        path            AS path_ids,
        COUNT(*) OVER () AS _total_count
    FROM chain
    WHERE cycle = true OR depth >= 32
    ORDER BY start_id, depth
    LIMIT :sample_limit
    """
)

BACKDATED_SUBMITTED_SQL = text(
    """
    SELECT
        o.id            AS operation_id,
        o.operation_type,
        o.status,
        o.effective_at,
        o.created_at,
        EXTRACT(EPOCH FROM (o.created_at - o.effective_at))::bigint
                          AS back_seconds,
        COUNT(*) OVER () AS _total_count
    FROM operations o
    WHERE o.status = 'submitted'
      AND o.effective_at IS NOT NULL
      AND o.effective_at < o.created_at
    ORDER BY back_seconds DESC, operation_id
    LIMIT :sample_limit
    """
)

LATE_ACCEPTANCE_SQL = text(
    """
    WITH submitted AS (
        SELECT
            o.id        AS operation_id,
            o.operation_type,
            o.submitted_at
        FROM operations o
        WHERE o.status = 'submitted'
          AND o.acceptance_required = TRUE
          AND o.submitted_at IS NOT NULL
    )
    SELECT
        s.operation_id,
        s.operation_type,
        s.submitted_at,
        MAX(a.performed_at)                 AS last_acceptance_at,
        EXTRACT(EPOCH FROM (MAX(a.performed_at) - s.submitted_at))::bigint
                                              AS lag_seconds,
        COUNT(*) OVER ()                    AS _total_count
    FROM submitted s
    JOIN operation_acceptance_actions a
        ON a.operation_id = s.operation_id
    GROUP BY s.operation_id, s.operation_type, s.submitted_at
    HAVING MAX(a.performed_at) - s.submitted_at
        > make_interval(secs => :late_threshold_seconds)
    ORDER BY lag_seconds DESC, s.operation_id
    LIMIT :sample_limit
    """
)

MERGE_AUDIT_GAP_SQL = text(
    """
    SELECT
        a.id                              AS audit_event_id,
        a.event_type,
        a.entity_id,
        a.created_at,
        (a.changes ->> 'op_lines_reassigned_count')::bigint
                                          AS op_lines_reassigned_count,
        COUNT(*) OVER ()                  AS _total_count
    FROM audit_events a
    WHERE a.event_type IN (
        'item.merge',
        'category.merge',
        'issue_object.merge',
        'temporary_item.merge',
        'review_item.merge'
    )
      AND a.outcome = 'success'
      AND (
          a.changes ->> 'merge_resources_complete' IS NULL
          OR (a.changes ->> 'op_lines_reassigned_count')::bigint > 0
      )
    ORDER BY a.id
    LIMIT :sample_limit
    """
)

AUDIT_ENTITY_ORPHAN_SQL = text(
    """
    WITH target AS (
        SELECT
            a.id                AS audit_event_id,
            a.event_type,
            a.entity_type,
            a.entity_id,
            a.created_at,
            CASE
                WHEN a.entity_type = 'operation'
                    THEN (
                        SELECT 1 FROM operations o
                        WHERE o.id::text = a.entity_id
                        LIMIT 1
                    )
                WHEN a.entity_type = 'item'
                    THEN (
                        SELECT 1 FROM items i
                        WHERE i.id::text = a.entity_id
                        LIMIT 1
                    )
                WHEN a.entity_type = 'category'
                    THEN (
                        SELECT 1 FROM categories c
                        WHERE c.id::text = a.entity_id
                        LIMIT 1
                    )
                WHEN a.entity_type = 'unit'
                    THEN (
                        SELECT 1 FROM units u
                        WHERE u.id::text = a.entity_id
                        LIMIT 1
                    )
                WHEN a.entity_type = 'issue_object'
                    THEN (
                        SELECT 1 FROM issue_objects io
                        WHERE io.id::text = a.entity_id
                        LIMIT 1
                    )
                -- Audit events intentionally support entity types without a
                -- live domain row (for example auth and batch summaries).
                -- Resource edges have no domain FK by ADR-0018 and are
                -- therefore outside this live-target check.
                ELSE 1
            END AS live_target
        FROM audit_events a
    )
    SELECT
        audit_event_id,
        event_type,
        entity_type,
        entity_id,
        created_at,
        live_target,
        CASE
            WHEN live_target IS NULL THEN 'critical'
            ELSE 'warning'
        END AS severity,
        COUNT(*) OVER () AS _total_count
    FROM target
    WHERE live_target IS NULL
    ORDER BY audit_event_id
    LIMIT :sample_limit
    """
)


CHECK_SQL: dict[str, Any] = {
    "BALANCE_EFFECT_DRIFT": BALANCE_EFFECT_DRIFT_SQL,
    "EXPECTED_EFFECT_GAP": EXPECTED_EFFECT_GAP_SQL,
    "ACCEPTANCE_EFFECT_GAP": ACCEPTANCE_EFFECT_GAP_SQL,
    "EFFECT_DATE_NULL": EFFECT_DATE_NULL_SQL,
    "EFFECT_CHAIN_BROKEN": EFFECT_CHAIN_BROKEN_SQL,
    "MERGE_CHAIN_CYCLE": MERGE_CHAIN_CYCLE_SQL,
    "BACKDATED_SUBMITTED": BACKDATED_SUBMITTED_SQL,
    "LATE_ACCEPTANCE": LATE_ACCEPTANCE_SQL,
    "MERGE_AUDIT_GAP": MERGE_AUDIT_GAP_SQL,
    "AUDIT_ENTITY_ORPHAN": AUDIT_ENTITY_ORPHAN_SQL,
}


# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------

_DSN_SECRET_RE = re.compile(
    r"(?P<scheme>postgresql(\+\w+)?://)(?P<user>[^:\s]+):(?P<password>[^@\s]+)@",
    re.IGNORECASE,
)
_DSN_KV_RE = re.compile(
    r"(?P<key>password|host|port|database|sslkey|sslcert|sslrootcert)"
    r"\s*=\s*'?[^'\s&]+'?",
    re.IGNORECASE,
)

MAX_ERROR_LEN = 500


def sanitize_dsn(value: str) -> str:
    """Return ``value`` with passwords and sensitive DSN keys masked."""
    s = _DSN_SECRET_RE.sub(r"\g<scheme>\g<user>:***@", value)
    s = _DSN_KV_RE.sub(lambda m: f"{m.group('key')}=***", s)
    return s


def sanitize_error(exc: BaseException) -> str:
    """Return a short, secret-free string representation of ``exc``."""
    raw = str(exc) or exc.__class__.__name__
    safe = sanitize_dsn(raw)
    if len(safe) > MAX_ERROR_LEN:
        safe = safe[: MAX_ERROR_LEN - 3] + "..."
    return safe


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    """Coerce SQL/Decimal/UUID values into JSON-friendly primitives."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float)):
        return value
    return str(value)


def _row_to_sample(row: Any) -> dict[str, Any]:
    """Convert a ``Row`` mapping into a JSON-safe dict without ``_total_count``."""
    mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    mapping.pop("_total_count", None)
    return {key: _json_safe(value) for key, value in mapping.items()}


async def _run_check(
    engine: AsyncEngine,
    code: str,
    *,
    sample_limit: int,
    late_threshold_days: int,
) -> CheckResult:
    """Execute a single check in its own read-only transaction."""
    sql = CHECK_SQL[code]
    severity = DEFAULT_SEVERITY[code]
    params: dict[str, Any] = {
        "sample_limit": sample_limit,
        "late_threshold_seconds": int(late_threshold_days) * 86400,
    }

    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            try:
                rows = (await conn.execute(sql, params)).fetchall()
            except (DBAPIError, OperationalError, ProgrammingError) as exc:
                # Read-only + per-check isolation: a single failure must
                # not poison the whole run. Roll back this transaction
                # and surface the error.
                raise
            samples = [_row_to_sample(row) for row in rows]

            total = 0
            if rows:
                first = dict(rows[0]._mapping)
                total = int(first.get("_total_count") or 0)

            if total == 0:
                return CheckResult(
                    code=code, status="pass", count=0, severity=severity, samples=[]
                )
            return CheckResult(
                code=code,
                status="fail" if severity == "critical" else "warning",
                count=total,
                severity=severity,
                samples=samples,
            )
        finally:
            try:
                await trans.rollback()
            except SQLAlchemyError:
                pass


async def run_checks(
    database_url: str,
    *,
    sample_limit: int,
    late_threshold_days: int,
    connect_args: dict | None = None,
) -> list[CheckResult]:
    """Run every A-7 check; each in its own read-only transaction.

    Using a separate transaction per check means a single failure (e.g.
    a syntax error in one query) cannot abort the whole run, and the
    read-only contract is reasserted for every check.
    """
    engine: AsyncEngine = create_async_engine(
        database_url,
        poolclass=NullPool,
        future=True,
        connect_args=connect_args or {},
    )
    results: list[CheckResult] = []
    try:
        for code in CHECKS:
            try:
                result = await _run_check(
                    engine,
                    code,
                    sample_limit=sample_limit,
                    late_threshold_days=late_threshold_days,
                )
            except (DBAPIError, OperationalError, ProgrammingError, SQLAlchemyError) as exc:
                result = CheckResult(
                    code=code,
                    status="error",
                    count=0,
                    severity=DEFAULT_SEVERITY[code],
                    error=sanitize_error(exc),
                )
            results.append(result)
    finally:
        await engine.dispose()
    return results


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _check_payload(result: CheckResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": result.code,
        "status": result.status,
        "count": result.count,
        "samples": result.samples,
    }
    if result.error is not None:
        payload["error"] = result.error
    return payload


def build_summary(
    results: Sequence[CheckResult],
    *,
    started_at: datetime,
    fail_on: str,
) -> dict[str, Any]:
    """Return the JSON payload shared between text and JSON outputs."""
    threshold = SEVERITY_RANK[fail_on]
    has_threshold_finding = any(
        SEVERITY_RANK.get(result.severity, 99) <= threshold and result.count > 0
        for result in results
    )
    has_warning = any(
        result.severity == "warning" and result.count > 0 for result in results
    )
    has_error = any(result.error is not None for result in results)

    if has_error:
        overall = "error"
    elif has_threshold_finding:
        overall = "critical" if fail_on == "critical" else "warning"
    elif has_warning:
        overall = "warning"
    else:
        overall = "ok"

    return {
        "status": overall,
        "started_at": started_at.isoformat(),
        "fail_on": fail_on,
        "checks": [_check_payload(r) for r in results],
    }


def format_text(summary: dict[str, Any]) -> str:
    """Render a short human-readable summary."""
    lines: list[str] = []
    status = str(summary.get("status", "ok")).upper()
    started = summary.get("started_at", "")
    lines.append(f"Integrity check status: {status}")
    lines.append(f"Started: {started}")
    fail_on = summary.get("fail_on", DEFAULT_FAIL_ON)
    lines.append(f"Fail-on threshold: {fail_on}")
    lines.append("")
    for check in summary.get("checks", []):
        code = check.get("code", "?")
        check_status = check.get("status", "?")
        count = check.get("count", 0)
        lines.append(f"- {code}: {check_status} (count={count})")
        if check.get("error"):
            lines.append(f"    error: {check['error']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="integrity_check.py",
        description=(
            "Run A-7 read-only integrity checks for SyncServer. "
            "Only SELECT statements are issued; the connection is "
            "marked READ ONLY at the start of the transaction."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  integrity_check.py --format text\n"
            "  integrity_check.py --format json --sample-limit 25\n"
            "  integrity_check.py --fail-on warning --format json\n"
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help=(
            "Maximum sample rows per check "
            f"(default: {DEFAULT_SAMPLE_LIMIT}, max: {MAX_SAMPLE_LIMIT})"
        ),
    )
    parser.add_argument(
        "--fail-on",
        choices=THRESHOLDS,
        default=DEFAULT_FAIL_ON,
        help=(
            "Findings at/above this severity cause exit code 1 "
            f"(default: {DEFAULT_FAIL_ON})"
        ),
    )
    parser.add_argument(
        "--late-threshold-days",
        type=int,
        default=DEFAULT_LATE_THRESHOLD_DAYS,
        help=(
            "Acceptance lag (days) treated as late for LATE_ACCEPTANCE "
            f"(default: {DEFAULT_LATE_THRESHOLD_DAYS}, max: {MAX_LATE_THRESHOLD_DAYS})"
        ),
    )
    return parser


def resolve_database_url() -> str:
    """Read the connection URL solely from process environment configuration."""
    import os

    url = (
        os.environ.get("DATABASE_URL_TEST")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise ValueError(
            "DATABASE_URL or DATABASE_URL_TEST must be set"
        )
    return url


def _validate_args(args: argparse.Namespace) -> str | None:
    if args.sample_limit < 1 or args.sample_limit > MAX_SAMPLE_LIMIT:
        return (
            f"--sample-limit must be between 1 and {MAX_SAMPLE_LIMIT}, "
            f"got {args.sample_limit}"
        )
    if args.late_threshold_days < 1 or args.late_threshold_days > MAX_LATE_THRESHOLD_DAYS:
        return (
            f"--late-threshold-days must be between 1 and "
            f"{MAX_LATE_THRESHOLD_DAYS}, got {args.late_threshold_days}"
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    validation_error = _validate_args(args)
    if validation_error is not None:
        print(f"Error: {validation_error}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        database_url = resolve_database_url()
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    started_at = datetime.now(UTC)

    try:
        results = asyncio.run(
            run_checks(
                database_url,
                sample_limit=args.sample_limit,
                late_threshold_days=args.late_threshold_days,
            )
        )
    except (DBAPIError, OperationalError, ProgrammingError) as exc:
        print(
            f"DB error: {sanitize_error(exc)}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    except SQLAlchemyError as exc:
        print(
            f"DB error: {sanitize_error(exc)}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    except OSError as exc:
        # ``asyncpg`` raises plain ``OSError`` for connection refused /
        # DNS failures; the exception message contains ``host:port`` but
        # never the DSN password. We still run it through the sanitiser
        # so any future variant that leaks a credential is masked.
        print(
            f"DB error: {sanitize_error(exc)}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    except Exception as exc:  # pragma: no cover — defensive boundary
        print(
            f"Unexpected error: {sanitize_error(exc)}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    summary = build_summary(results, started_at=started_at, fail_on=args.fail_on)

    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=False))
    else:
        print(format_text(summary))

    if any(result.error is not None for result in results):
        return EXIT_USAGE_ERROR

    threshold = SEVERITY_RANK[args.fail_on]
    for result in results:
        if result.count > 0 and SEVERITY_RANK.get(result.severity, 99) <= threshold:
            return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
