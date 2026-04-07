from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MachineSnapshot(Base):
    __tablename__ = "machine_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    datasets: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_machine_snapshots_created_at", "created_at"),
    )


class MachineReport(Base):
    __tablename__ = "machine_reports"

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("machine_snapshots.snapshot_id"),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    findings: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    references: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        Index("ix_machine_reports_snapshot_id", "snapshot_id"),
        Index("ix_machine_reports_created_at", "created_at"),
    )


class MachineBatch(Base):
    __tablename__ = "machine_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_format: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="atomic")
    client_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("machine_snapshots.snapshot_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_client: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    errors: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    applied_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'validating', 'preview_ready', 'applying', 'applied', 'failed')",
            name="ck_machine_batches_status",
        ),
        CheckConstraint(
            "mode IN ('atomic')",
            name="ck_machine_batches_mode",
        ),
        Index("ix_machine_batches_domain_created_at", "domain", "created_at"),
        Index("ix_machine_batches_snapshot_id", "snapshot_id"),
    )
