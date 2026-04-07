from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


MachineDomain = Literal["catalog", "operations"]
MachineMode = Literal["atomic"]


class MachineSnapshotResponse(ORMBaseModel):
    snapshot_id: str
    created_at: datetime
    schema_version: str
    datasets: list[str]
    counts: dict[str, int]
    request_id: str


class MachineReadResponse(ORMBaseModel):
    schema_version: str
    snapshot_id: str
    request_id: str
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class MachineAnalysisResponse(ORMBaseModel):
    schema_version: str
    snapshot_id: str
    request_id: str
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class MachineReportCreateRequest(BaseModel):
    report_type: str = Field(min_length=1, max_length=100)
    snapshot_id: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MachineReportResponse(ORMBaseModel):
    report_id: str
    report_type: str
    snapshot_id: str
    created_by: str
    created_at: datetime
    summary: str
    findings: list[dict[str, Any]]
    references: list[str]
    request_id: str
    schema_version: str


class MachineBatchEnvelope(BaseModel):
    domain: MachineDomain
    payload_format: str = Field(min_length=1, max_length=64)
    mode: MachineMode = "atomic"
    client_request_id: str | None = Field(default=None, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    payload: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class MachineBatchApplyRequest(BaseModel):
    batch_id: str = Field(min_length=1, max_length=64)
    plan_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=128)

    model_config = ConfigDict(extra="forbid")


class MachineBatchResponse(ORMBaseModel):
    batch_id: str
    plan_id: str
    snapshot_id: str
    status: str
    schema_version: str
    request_id: str
    summary: dict[str, int]
    records: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    result: dict[str, Any] | None = None
