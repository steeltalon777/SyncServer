from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.diagnostics_service import DiagnosticsService
from app.services.identity_service import Identity
from app.services.uow import UnitOfWork
from app.api.deps import require_user_identity

router = APIRouter(prefix="/diagnostics")

# Max batch size in bytes (per contract §5.2 — 100 KB)
MAX_BATCH_BYTES = 100 * 1024

# Allowed event types (per contract §3.1)
ALLOWED_EVENT_TYPES = frozenset({
    "form_opened",
    "form_closed",
    "submit_clicked",
    "validation_failed",
    "request_started",
    "request_succeeded",
    "request_failed",
    "outcome_unknown",
    "response_processing_failed",
    "navigation_away_with_unsaved",
    "unexpected_error",
})

ALLOWED_SEVERITIES = frozenset({"debug", "info", "warning", "error", "critical"})


class DiagnosticEventIn(BaseModel):
    event_id: UUID
    event_type: str
    occurred_at: datetime
    session_id: UUID
    tab_id: Optional[UUID] = None
    frontend_version: Optional[str] = Field(default=None, max_length=50)
    route: Optional[str] = Field(default=None, max_length=200)
    operation_type: Optional[str] = Field(default=None, max_length=20)
    draft_id: Optional[UUID] = None
    idempotency_key: Optional[UUID] = None
    http_request_id: Optional[UUID] = None
    server_request_id: Optional[UUID] = None
    user_id: Optional[str] = Field(default=None, max_length=50)
    device_id: Optional[str] = Field(default=None, max_length=50)
    site_id: Optional[str] = Field(default=None, max_length=50)
    severity: str
    details: Optional[dict] = None
    batch_sequence: Optional[int] = None

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        if v not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"invalid event_type: {v}")
        return v

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        if v not in ALLOWED_SEVERITIES:
            raise ValueError(f"invalid severity: {v}")
        return v


class DiagnosticBatchIn(BaseModel):
    events: list[DiagnosticEventIn] = Field(min_length=1)
    sent_at: datetime
    sequence: int = Field(ge=0)


@router.post("/ui-events/batch", status_code=status.HTTP_204_NO_CONTENT)
async def post_ui_events_batch(
    request: Request,
    body: DiagnosticBatchIn,
    db: AsyncSession = Depends(get_db),
    identity: Identity = Depends(require_user_identity),
) -> None:
    """Receive a batch of UI diagnostic events from the Angular frontend.

    Per contract §5:
    - 204 on success
    - 400 on empty/invalid batch
    - 413 if body > 100 KB
    - 429 if rate limit exceeded (per session, 10 req/min — checked in BFF)
    """
    # Defense-in-depth size check (BFF should also check, but we re-check here)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_BATCH_BYTES:
                raise HTTPException(status_code=413, detail="batch too large")
        except ValueError:
            pass

    # Per-row size check (in case content-length is missing/misleading)
    # Each row is approximately len(json.dumps(event)); use a fast estimate.
    if len(body.events) > 1000:
        raise HTTPException(status_code=413, detail="batch has too many events")

    # Convert to dicts for bulk insert; preserve schema_version = 1.
    rows = []
    for e in body.events:
        rows.append({
            "event_id": e.event_id,
            "event_type": e.event_type,
            "occurred_at": e.occurred_at,
            "session_id": e.session_id,
            "tab_id": e.tab_id,
            "frontend_version": e.frontend_version,
            "route": e.route,
            "operation_type": e.operation_type,
            "draft_id": e.draft_id,
            "idempotency_key": e.idempotency_key,
            "http_request_id": e.http_request_id,
            "server_request_id": e.server_request_id,
            "user_id": e.user_id,
            "device_id": e.device_id,
            "site_id": e.site_id,
            "severity": e.severity,
            "details": e.details,
            "batch_sequence": e.batch_sequence,
            "schema_version": 1,
        })

    async with UnitOfWork(db) as uow:
        await DiagnosticsService.bulk_insert(uow, rows)
        await uow.commit()
