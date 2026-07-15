from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DiagnosticEvent(Base):
    """Diagnostic UI event for frontend performance and error tracking.

    Append-only log of UI diagnostics events sent by the Angular frontend.
    See docs/contracts/DIAGNOSTICS_CONTRACTS.md §6 for DDL.
    """

    __tablename__ = "diagnostics_ui_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), unique=True, nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False,
    )
    tab_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )
    frontend_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )
    route: Mapped[str | None] = mapped_column(String(200), nullable=True)
    operation_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    draft_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )
    idempotency_key: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )
    http_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )
    server_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )
    user_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    site_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    batch_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_diag_events_session_time", "session_id", "occurred_at"),
        Index("idx_diag_events_type_time", "event_type", "occurred_at"),
        Index(
            "idx_diag_events_draft",
            "draft_id",
            postgresql_where=draft_id.isnot(None),
        ),
        Index("idx_diag_received_at", "received_at"),
    )
