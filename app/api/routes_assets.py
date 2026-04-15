from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.schemas.asset_register import (
    IssuedAssetListResponse,
    IssuedAssetRow,
    LostAssetListResponse,
    LostAssetResolveRequest,
    LostAssetRow,
    PendingAcceptanceListResponse,
    PendingAcceptanceRow,
)
from app.services.operations_service import OperationsService
from app.services.uow import UnitOfWork

router = APIRouter()

READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}


def _require_read_access(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in READ_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read assets permission required")


def _require_lost_resolve_access(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="only chief_storekeeper or root may resolve lost assets",
    )


async def _resolve_visible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
    if identity.has_global_business_access:
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=None),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        return [site.id for site in sites]

    scopes = list(await uow.user_access_scopes.list_user_scopes(identity.user_id))
    return [scope.site_id for scope in scopes if scope.is_active and scope.can_view]


@router.get("/pending-acceptance", response_model=PendingAcceptanceListResponse)
async def list_pending_acceptance(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    site_id: int | None = Query(None),
    operation_id: UUID | None = Query(None),
    item_id: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PendingAcceptanceListResponse:
    _require_read_access(identity)

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        if site_id is not None and site_id not in visible_site_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no access to requested site")

        rows, total_count = await uow.asset_registers.list_pending(
            user_site_ids=visible_site_ids,
            site_id=site_id,
            operation_id=operation_id,
            item_id=item_id,
            search=search,
            page=page,
            page_size=page_size,
        )

    return PendingAcceptanceListResponse(
        items=[PendingAcceptanceRow.model_validate(row) for row in rows],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/lost-assets", response_model=LostAssetListResponse)
async def list_lost_assets(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    site_id: int | None = Query(None),
    source_site_id: int | None = Query(None),
    operation_id: UUID | None = Query(None),
    item_id: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> LostAssetListResponse:
    _require_read_access(identity)

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        if site_id is not None and site_id not in visible_site_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no access to requested site")

        rows, total_count = await uow.asset_registers.list_lost(
            user_site_ids=visible_site_ids,
            site_id=site_id,
            source_site_id=source_site_id,
            operation_id=operation_id,
            item_id=item_id,
            search=search,
            page=page,
            page_size=page_size,
        )

    return LostAssetListResponse(
        items=[LostAssetRow.model_validate(row) for row in rows],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/lost-assets/{operation_line_id}/resolve")
async def resolve_lost_asset(
    operation_line_id: int,
    payload: LostAssetResolveRequest,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> dict[str, object]:
    _require_lost_resolve_access(identity)

    async with uow:
        result = await OperationsService.resolve_lost_asset(
            uow=uow,
            operation_line_id=operation_line_id,
            action=payload.action,
            qty=Decimal(payload.qty),
            user_id=identity.user_id,
            note=payload.note,
            responsible_recipient_id=payload.responsible_recipient_id,
        )
    return result


@router.get("/issued-assets", response_model=IssuedAssetListResponse)
async def list_issued_assets(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    recipient_id: int | None = Query(None),
    item_id: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> IssuedAssetListResponse:
    _require_read_access(identity)

    async with uow:
        rows, total_count = await uow.asset_registers.list_issued(
            recipient_id=recipient_id,
            item_id=item_id,
            search=search,
            page=page,
            page_size=page_size,
        )

    return IssuedAssetListResponse(
        items=[IssuedAssetRow.model_validate(row) for row in rows],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
