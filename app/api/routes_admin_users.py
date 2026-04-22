from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.admin_common import user_with_token_payload
from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.admin import (
    UserAccessScopeReplaceRequest,
    UserAccessScopeResponse,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserSyncStateResponse,
    UserTokenResponse,
    UserUpdate,
)
from app.services.admin_users_service import AdminUsersService, require_root
from app.services.uow import UnitOfWork

router = APIRouter(tags=["admin"])


@router.get("/users", response_model=UserListResponse)
async def list_users(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    is_active: bool | None = Query(default=None),
    is_root: bool | None = Query(default=None),
    role: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> UserListResponse:
    async with uow:
        require_root(identity)
        page_items, total_count = await AdminUsersService.list_users(
            uow,
            is_active=is_active,
            is_root=is_root,
            role=role,
            search=search,
            page=page,
            page_size=page_size,
        )

    return UserListResponse(
        users=[UserResponse.model_validate(user) for user in page_items],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserResponse:
    async with uow:
        require_root(identity)
        user = await AdminUsersService.get_user_required(uow, user_id)
    return UserResponse.model_validate(user)


@router.post("/users", response_model=UserResponse)
async def create_user(
    payload: UserCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserResponse:
    async with uow:
        require_root(identity)
        user = await AdminUsersService.create_user(uow, payload=payload)
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserResponse:
    async with uow:
        require_root(identity)
        user = await AdminUsersService.update_user(
            uow,
            user_id=user_id,
            payload=payload,
        )
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserResponse:
    async with uow:
        require_root(identity)
        user = await AdminUsersService.delete_user(
            uow,
            user_id=user_id,
            actor_user_id=identity.user_id,
        )
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}/sync-state", response_model=UserSyncStateResponse)
async def get_user_sync_state(
    user_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserSyncStateResponse:
    async with uow:
        require_root(identity)
        user, scopes = await AdminUsersService.get_user_sync_state(uow, user_id=user_id)

    return UserSyncStateResponse(
        user=user_with_token_payload(user),
        scopes=[UserAccessScopeResponse.model_validate(scope) for scope in scopes],
    )


@router.put("/users/{user_id}/scopes", response_model=list[UserAccessScopeResponse])
async def replace_user_scopes(
    user_id: UUID,
    payload: UserAccessScopeReplaceRequest,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> list[UserAccessScopeResponse]:
    async with uow:
        require_root(identity)
        scopes = await AdminUsersService.replace_user_scopes(
            uow,
            user_id=user_id,
            payload=payload,
        )

    return [UserAccessScopeResponse.model_validate(scope) for scope in scopes]


@router.post("/users/{user_id}/rotate-token", response_model=UserTokenResponse)
async def rotate_user_token(
    user_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UserTokenResponse:
    async with uow:
        require_root(identity)
        user, generated_at = await AdminUsersService.rotate_user_token(uow, user_id=user_id)

        return UserTokenResponse(
            user_id=user.id,
            username=user.username,
            user_token=user.user_token,
            generated_at=generated_at,
        )
