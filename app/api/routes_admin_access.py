from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.admin import UserAccessScopeCreate, UserAccessScopeResponse, UserAccessScopeUpdate
from app.services.admin_access_scopes_service import AdminAccessScopesService
from app.services.admin_users_service import require_root
from app.services.uow import UnitOfWork

router = APIRouter(tags=["admin"])


@router.get("/access/scopes", response_model=list[UserAccessScopeResponse])
async def list_access_scopes(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    user_id: UUID | None = Query(default=None),
    site_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[UserAccessScopeResponse]:
    async with uow:
        require_root(identity)
        scopes = await AdminAccessScopesService.list_scopes(
            uow,
            user_id=user_id,
            site_id=site_id,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )
    return [UserAccessScopeResponse.model_validate(scope) for scope in scopes]


@router.post("/access/scopes", response_model=UserAccessScopeResponse)
async def create_access_scope(
    payload: UserAccessScopeCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserAccessScopeResponse:
    async with uow:
        require_root(identity)
        scope = await AdminAccessScopesService.create_scope(uow, payload=payload)
    return UserAccessScopeResponse.model_validate(scope)


@router.patch("/access/scopes/{scope_id}", response_model=UserAccessScopeResponse)
async def update_access_scope(
    scope_id: int,
    payload: UserAccessScopeUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserAccessScopeResponse:
    async with uow:
        require_root(identity)
        scope = await AdminAccessScopesService.update_scope(uow, scope_id=scope_id, payload=payload)
    return UserAccessScopeResponse.model_validate(scope)
