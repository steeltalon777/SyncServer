from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.admin_common import require_admin_basic
from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.admin import SiteCreate, SiteListResponse, SiteResponse, SiteUpdate
from app.services.admin_sites_service import AdminSitesService
from app.services.uow import UnitOfWork

router = APIRouter(tags=["admin"])


@router.get("/sites", response_model=SiteListResponse)
async def list_sites_admin(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> SiteListResponse:
    async with uow:
        require_admin_basic(identity)
        sites, total_count = await AdminSitesService.list_sites(
            uow,
            is_active=is_active,
            search=search,
            page=page,
            page_size=page_size,
        )
    return SiteListResponse(
        sites=[SiteResponse.model_validate(site) for site in sites],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/sites", response_model=SiteResponse)
async def create_site(
    payload: SiteCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> SiteResponse:
    async with uow:
        require_admin_basic(identity)
        site = await AdminSitesService.create_site(uow, payload=payload)
    return SiteResponse.model_validate(site)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: int,
    payload: SiteUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> SiteResponse:
    async with uow:
        require_admin_basic(identity)
        updated = await AdminSitesService.update_site(uow, site_id=site_id, payload=payload)
    return SiteResponse.model_validate(updated)
