from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.deps import get_uow, require_service_auth
from app.schemas.admin import UserCreate
from app.services.access_service import AccessService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sync-user")
async def sync_user(
    payload: UserCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        existing = await uow.users.get(payload.user_id)

        if existing:
            user = await uow.users.update(
                user_id=payload.user_id,
                username=payload.username,
                email=payload.email,
                full_name=payload.full_name,
                is_active=payload.is_active,
            )
        else:
            user = await uow.users.create(
                user_id=payload.user_id,
                username=payload.username,
                email=payload.email,
                full_name=payload.full_name,
                is_active=payload.is_active,
            )

    return {
        "user_id": user.id,
        "username": user.username,
        "status": "synced",
    }


@router.get("/me")
async def get_me(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
):
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user = await uow.users.get(x_acting_user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not found",
            )

    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
    }


@router.get("/sites")
async def get_user_sites(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
):
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        accesses = await uow.user_site_roles.get_sites_for_user(x_acting_user_id)

        result = []
        for access in accesses:
            site = await uow.sites.get_by_id(access.site_id)
            if not site:
                continue

            result.append(
                {
                    "site_id": str(site.id),
                    "site_name": site.name,
                    "site_code": site.code,
                    "role": access.role,
                    "is_active": access.is_active,
                }
            )

    return {"sites": result}


@router.get("/context")
async def get_auth_context(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID | None = Header(default=None, alias="X-Acting-Site-Id"),
):
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user = await uow.users.get(x_acting_user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="user not found",
            )

        access_service = AccessService(uow)
        accesses = await uow.user_site_roles.get_sites_for_user(x_acting_user_id)

        sites = []
        acting_site_entry = None

        for access in accesses:
            site = await uow.sites.get_by_id(access.site_id)
            if not site:
                continue

            entry = {
                "site_id": str(site.id),
                "site_name": site.name,
                "site_code": site.code,
                "role": access.role,
                "is_active": access.is_active,
            }

            sites.append(entry)

            if x_acting_site_id is not None and access.site_id == x_acting_site_id:
                acting_site_entry = entry

        if x_acting_site_id is None:
            permissions = {
                "can_read_operations": False,
                "can_create_operations": False,
                "can_read_balances": False,
                "can_manage_catalog": False,
                "can_manage_root_admin": False,
            }
        else:
            permissions = await access_service.get_user_permissions(
                x_acting_user_id,
                x_acting_site_id,
            )

        return {
            "user": {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
            },
            "acting_site_id": str(x_acting_site_id) if x_acting_site_id else None,
            "acting_site": acting_site_entry,
            "sites": sites,
            "permissions": permissions,
        }