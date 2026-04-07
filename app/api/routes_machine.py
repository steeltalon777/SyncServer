from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.api.deps import get_request_id, get_uow, require_token_auth
from app.core.identity import Identity
from app.schemas.machine import (
    MachineAnalysisResponse,
    MachineBatchApplyRequest,
    MachineBatchEnvelope,
    MachineBatchResponse,
    MachineReadResponse,
    MachineReportCreateRequest,
    MachineReportResponse,
    MachineSnapshotResponse,
)
from app.services.machine_service import (
    MACHINE_SCHEMA_VERSION,
    MachineService,
    apply_field_selection,
    make_report_id,
    next_cursor,
    parse_cursor,
    to_jsonl,
)
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/machine")

READ_FORMAT = Literal["json", "jsonl"]
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

ITEM_FIELDS = {
    "id",
    "sku",
    "name",
    "normalized_name",
    "unit_id",
    "unit_code",
    "unit_name",
    "category_id",
    "category_code",
    "category_name",
    "category_path",
    "is_active",
    "updated_at",
    "source_system",
    "source_ref",
    "import_batch_id",
}
CATEGORY_FIELDS = {
    "id",
    "code",
    "name",
    "normalized_name",
    "parent_id",
    "parent_code",
    "path",
    "level",
    "is_active",
    "updated_at",
}
UNIT_FIELDS = {
    "id",
    "code",
    "name",
    "symbol",
    "is_active",
    "updated_at",
}
OPERATION_FIELDS = {
    "id",
    "status",
    "operation_type",
    "site_id",
    "source_site_id",
    "destination_site_id",
    "created_at",
    "effective_at",
    "applied_at",
    "updated_at",
    "created_by",
    "line_count",
    "notes",
    "version",
    "lines",
}


def _meta_payload(*, request_id: str, snapshot_id: str) -> dict:
    return {
        "schema_version": MACHINE_SCHEMA_VERSION,
        "request_id": request_id,
        "snapshot_id": snapshot_id,
    }


def _json_or_jsonl(
    *,
    response_format: READ_FORMAT,
    request_id: str,
    snapshot_id: str,
    items: list[dict],
    next_page_cursor: str | None,
):
    meta = _meta_payload(request_id=request_id, snapshot_id=snapshot_id)
    if response_format == "jsonl":
        text = to_jsonl(
            {**meta, "next_cursor": next_page_cursor},
            items,
        )
        return PlainTextResponse(content=text, media_type="application/x-ndjson")
    return MachineReadResponse(
        schema_version=MACHINE_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        request_id=request_id,
        items=items,
        next_cursor=next_page_cursor,
    )


@router.get("/snapshots/latest", response_model=MachineSnapshotResponse)
async def get_latest_snapshot(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineSnapshotResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    async with uow:
        snapshot = await MachineService.ensure_latest_snapshot(uow, created_by_user_id=identity.user_id)

    return MachineSnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        created_at=snapshot.created_at,
        schema_version=snapshot.schema_version,
        datasets=list(snapshot.datasets or []),
        counts=dict(snapshot.counts or {}),
        request_id=request_id,
    )


@router.get("/snapshots/{snapshot_id}", response_model=MachineSnapshotResponse)
async def get_snapshot(
    snapshot_id: str,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineSnapshotResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    async with uow:
        snapshot = await uow.machine.get_snapshot(snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found")
    return MachineSnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        created_at=snapshot.created_at,
        schema_version=snapshot.schema_version,
        datasets=list(snapshot.datasets or []),
        counts=dict(snapshot.counts or {}),
        request_id=request_id,
    )


@router.get("/read/catalog/items", response_model=MachineReadResponse)
async def machine_read_catalog_items(
    request: Request,
    snapshot_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    fields: str | None = Query(default=None),
    format: READ_FORMAT = Query(default="json"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
):
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    offset = parse_cursor(cursor)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        items = await uow.machine.list_machine_items(snapshot_at=snapshot.created_at, limit=limit, offset=offset)
        items = apply_field_selection(items, fields=fields, allowed_fields=ITEM_FIELDS)

    return _json_or_jsonl(
        response_format=format,
        request_id=request_id,
        snapshot_id=snapshot.snapshot_id,
        items=items,
        next_page_cursor=next_cursor(offset=offset, returned_count=len(items), limit=limit),
    )


@router.get("/read/catalog/categories", response_model=MachineReadResponse)
async def machine_read_catalog_categories(
    request: Request,
    snapshot_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    fields: str | None = Query(default=None),
    format: READ_FORMAT = Query(default="json"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
):
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    offset = parse_cursor(cursor)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        categories = await uow.machine.list_machine_categories(snapshot_at=snapshot.created_at, limit=limit, offset=offset)
        categories = apply_field_selection(categories, fields=fields, allowed_fields=CATEGORY_FIELDS)

    return _json_or_jsonl(
        response_format=format,
        request_id=request_id,
        snapshot_id=snapshot.snapshot_id,
        items=categories,
        next_page_cursor=next_cursor(offset=offset, returned_count=len(categories), limit=limit),
    )


@router.get("/read/catalog/units", response_model=MachineReadResponse)
async def machine_read_catalog_units(
    request: Request,
    snapshot_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    fields: str | None = Query(default=None),
    format: READ_FORMAT = Query(default="json"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
):
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    offset = parse_cursor(cursor)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        units = await uow.machine.list_machine_units(snapshot_at=snapshot.created_at, limit=limit, offset=offset)
        units = apply_field_selection(units, fields=fields, allowed_fields=UNIT_FIELDS)

    return _json_or_jsonl(
        response_format=format,
        request_id=request_id,
        snapshot_id=snapshot.snapshot_id,
        items=units,
        next_page_cursor=next_cursor(offset=offset, returned_count=len(units), limit=limit),
    )


@router.get("/read/operations", response_model=MachineReadResponse)
async def machine_read_operations(
    request: Request,
    snapshot_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    fields: str | None = Query(default=None),
    format: READ_FORMAT = Query(default="json"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
):
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    offset = parse_cursor(cursor)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        visible_site_ids = await MachineService.resolve_visible_site_ids(uow, identity)
        operations = await uow.machine.list_machine_operations(
            snapshot_at=snapshot.created_at,
            user_site_ids=visible_site_ids if not identity.has_global_business_access else None,
            limit=limit,
            offset=offset,
        )
        operations = apply_field_selection(operations, fields=fields, allowed_fields=OPERATION_FIELDS)

    return _json_or_jsonl(
        response_format=format,
        request_id=request_id,
        snapshot_id=snapshot.snapshot_id,
        items=operations,
        next_page_cursor=next_cursor(offset=offset, returned_count=len(operations), limit=limit),
    )


@router.get("/read/operations/{operation_id}", response_model=MachineReadResponse)
async def machine_read_operation(
    operation_id: UUID,
    request: Request,
    snapshot_id: str | None = Query(default=None),
    fields: str | None = Query(default=None),
    format: READ_FORMAT = Query(default="json"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
):
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        operation = await uow.machine.get_machine_operation(operation_id=operation_id, snapshot_at=snapshot.created_at)
        if operation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        if not identity.has_global_business_access:
            visible_site_ids = await MachineService.resolve_visible_site_ids(uow, identity)
            if operation["site_id"] not in visible_site_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no access to requested operation site")
        items = apply_field_selection([operation], fields=fields, allowed_fields=OPERATION_FIELDS)

    return _json_or_jsonl(
        response_format=format,
        request_id=request_id,
        snapshot_id=snapshot.snapshot_id,
        items=items,
        next_page_cursor=None,
    )


@router.get("/analysis/duplicate-candidates/items", response_model=MachineAnalysisResponse)
async def machine_duplicate_items(
    request: Request,
    snapshot_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineAnalysisResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    offset = parse_cursor(cursor)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        groups = await uow.machine.find_duplicate_item_candidates(
            snapshot_at=snapshot.created_at,
            limit=limit,
            offset=offset,
        )
    return MachineAnalysisResponse(
        schema_version=MACHINE_SCHEMA_VERSION,
        snapshot_id=snapshot.snapshot_id,
        request_id=request_id,
        items=groups,
        next_cursor=next_cursor(offset=offset, returned_count=len(groups), limit=limit),
    )


@router.get("/analysis/duplicate-candidates/categories", response_model=MachineAnalysisResponse)
async def machine_duplicate_categories(
    request: Request,
    snapshot_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineAnalysisResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    offset = parse_cursor(cursor)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        groups = await uow.machine.find_duplicate_category_candidates(
            snapshot_at=snapshot.created_at,
            limit=limit,
            offset=offset,
        )
    return MachineAnalysisResponse(
        schema_version=MACHINE_SCHEMA_VERSION,
        snapshot_id=snapshot.snapshot_id,
        request_id=request_id,
        items=groups,
        next_cursor=next_cursor(offset=offset, returned_count=len(groups), limit=limit),
    )


@router.get("/analysis/integrity-issues", response_model=MachineAnalysisResponse)
async def machine_integrity_issues(
    request: Request,
    snapshot_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineAnalysisResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    offset = parse_cursor(cursor)
    async with uow:
        snapshot = await MachineService.resolve_snapshot(
            uow,
            requested_snapshot_id=snapshot_id,
            created_by_user_id=identity.user_id,
        )
        issues = await uow.machine.find_integrity_issues(
            snapshot_at=snapshot.created_at,
            limit=limit,
            offset=offset,
        )
    return MachineAnalysisResponse(
        schema_version=MACHINE_SCHEMA_VERSION,
        snapshot_id=snapshot.snapshot_id,
        request_id=request_id,
        items=issues,
        next_cursor=next_cursor(offset=offset, returned_count=len(issues), limit=limit),
    )


@router.post("/reports", response_model=MachineReportResponse)
async def create_machine_report(
    payload: MachineReportCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineReportResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    async with uow:
        snapshot = await uow.machine.get_snapshot(payload.snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="snapshot not found")
        report_id = make_report_id()
        report = await uow.machine.create_report(
            report_id=report_id,
            report_type=payload.report_type,
            snapshot_id=payload.snapshot_id,
            created_by_user_id=identity.user_id,
            summary=payload.summary,
            findings=payload.findings,
            references=payload.references,
        )
    return MachineReportResponse(
        report_id=report.report_id,
        report_type=report.report_type,
        snapshot_id=report.snapshot_id,
        created_by=str(report.created_by_user_id),
        created_at=report.created_at,
        summary=report.summary,
        findings=list(report.findings or []),
        references=list(report.references or []),
        request_id=request_id,
        schema_version=MACHINE_SCHEMA_VERSION,
    )


@router.get("/reports/{report_id}", response_model=MachineReportResponse)
async def get_machine_report(
    report_id: str,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineReportResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    async with uow:
        report = await uow.machine.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return MachineReportResponse(
        report_id=report.report_id,
        report_type=report.report_type,
        snapshot_id=report.snapshot_id,
        created_by=str(report.created_by_user_id),
        created_at=report.created_at,
        summary=report.summary,
        findings=list(report.findings or []),
        references=list(report.references or []),
        request_id=request_id,
        schema_version=MACHINE_SCHEMA_VERSION,
    )


@router.get("/reports/{report_id}/result", response_model=MachineAnalysisResponse)
async def get_machine_report_result(
    report_id: str,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineAnalysisResponse:
    MachineService.require_read_access(identity)
    request_id = get_request_id(request)
    async with uow:
        report = await uow.machine.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return MachineAnalysisResponse(
        schema_version=MACHINE_SCHEMA_VERSION,
        snapshot_id=report.snapshot_id,
        request_id=request_id,
        items=list(report.findings or []),
        next_cursor=None,
    )


@router.post("/batches/catalog/preview", response_model=MachineBatchResponse)
async def preview_catalog_batch(
    payload: MachineBatchEnvelope,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineBatchResponse:
    request_id = get_request_id(request)
    async with uow:
        scopes = await MachineService.resolve_scopes(uow, identity)
        MachineService.require_catalog_batch_access(identity, scopes)
        batch = await MachineService.preview_catalog_batch(
            uow,
            envelope=payload,
            identity=identity,
            source_client=request.headers.get("X-Client-Name"),
        )
        response_payload = MachineService.batch_response_payload(batch)
    return MachineBatchResponse(
        **response_payload,
        schema_version=MACHINE_SCHEMA_VERSION,
        request_id=request_id,
    )


@router.post("/batches/catalog/apply", response_model=MachineBatchResponse)
async def apply_catalog_batch(
    payload: MachineBatchApplyRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineBatchResponse:
    request_id = get_request_id(request)
    async with uow:
        scopes = await MachineService.resolve_scopes(uow, identity)
        MachineService.require_catalog_batch_access(identity, scopes)
        batch = await MachineService.apply_catalog_batch(
            uow,
            batch_id=payload.batch_id,
            plan_id=payload.plan_id,
            identity=identity,
        )
        response_payload = MachineService.batch_response_payload(batch)
    return MachineBatchResponse(
        **response_payload,
        schema_version=MACHINE_SCHEMA_VERSION,
        request_id=request_id,
    )


@router.post("/batches/operations/preview", response_model=MachineBatchResponse)
async def preview_operations_batch(
    payload: MachineBatchEnvelope,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineBatchResponse:
    request_id = get_request_id(request)
    async with uow:
        scopes = await MachineService.resolve_scopes(uow, identity)
        MachineService.require_operations_batch_access(identity, scopes)
        batch = await MachineService.preview_operations_batch(
            uow,
            envelope=payload,
            identity=identity,
            source_client=request.headers.get("X-Client-Name"),
        )
        response_payload = MachineService.batch_response_payload(batch)
    return MachineBatchResponse(
        **response_payload,
        schema_version=MACHINE_SCHEMA_VERSION,
        request_id=request_id,
    )


@router.post("/batches/operations/apply", response_model=MachineBatchResponse)
async def apply_operations_batch(
    payload: MachineBatchApplyRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_token_auth),
) -> MachineBatchResponse:
    request_id = get_request_id(request)
    async with uow:
        scopes = await MachineService.resolve_scopes(uow, identity)
        MachineService.require_operations_batch_access(identity, scopes)
        batch = await MachineService.apply_operations_batch(
            uow,
            batch_id=payload.batch_id,
            plan_id=payload.plan_id,
            identity=identity,
        )
        response_payload = MachineService.batch_response_payload(batch)
    return MachineBatchResponse(
        **response_payload,
        schema_version=MACHINE_SCHEMA_VERSION,
        request_id=request_id,
    )
