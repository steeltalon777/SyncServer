from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.schemas.admin import SiteFilter, UserCreate
from app.services.access_service import AccessService
from app.services.uow import UnitOfWork
from app.api.deps import get_uow
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


async def _resolve_current_user(
    uow: UnitOfWork,
    x_user_token: UUID | None,
) -> User:
    if not x_user_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-User-Token",
        )

    user = await uow.users.get_by_user_token(x_user_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid X-User-Token",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user is inactive",
        )
    return user


async def _resolve_current_device(
    uow: UnitOfWork,
    x_device_token: UUID | None,
    x_device_id: str | None = None,
):
    if not x_device_token:
        return None

    device = await uow.devices.get_by_device_token(x_device_token)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid X-Device-Token",
        )
    if not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="device is inactive",
        )
    if x_device_id is not None and str(device.id) != str(x_device_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Device-Token does not match X-Device-Id",
        )
    return device


def _user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_root": user.is_root,
        "role": user.role,
        "default_site_id": user.default_site_id,
    }


@router.post("/sync-user")
async def sync_user(
    payload: UserCreate,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_device_token: UUID | None = Header(default=None, alias="X-Device-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
):
    """
    Sync user registry record (Django-compatible), authenticated by user token.
    Root-only operation.
    """
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        current_device = await _resolve_current_device(uow, x_device_token, x_device_id)

        if not current_user.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="root permissions required for sync-user",
            )

        target_user = None
        if payload.id is not None:
            target_user = await uow.users.get_by_id(payload.id)

        if target_user is None:
            by_username = await uow.users.get_by_username(payload.username)
            if by_username is not None:
                if payload.id is not None and by_username.id != payload.id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="username already bound to another user id",
                    )
                target_user = by_username

        if target_user is None:
            target_user = User(
                id=payload.id or uuid4(),
                username=payload.username,
                email=payload.email,
                full_name=payload.full_name,
                is_active=payload.is_active,
                is_root=payload.is_root,
                role=payload.role,
                default_site_id=payload.default_site_id,
            )
            uow.session.add(target_user)
            await uow.session.flush()
            await uow.session.refresh(target_user)
            status_value = "created"
        else:
            target_user.username = payload.username
            target_user.email = payload.email
            target_user.full_name = payload.full_name
            target_user.is_active = payload.is_active
            target_user.is_root = payload.is_root
            target_user.role = payload.role
            target_user.default_site_id = payload.default_site_id
            await uow.session.flush()
            await uow.session.refresh(target_user)
            status_value = "updated"

    return {
        "status": status_value,
        "user": _user_payload(target_user),
        "synced_by": {
            "id": str(current_user.id),
            "username": current_user.username,
            "device_id": current_device.id if current_device else None,
        },
    }


@router.get("/me")
async def get_me(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_device_token: UUID | None = Header(default=None, alias="X-Device-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
):
    async with uow:
        user = await _resolve_current_user(uow, x_user_token)
        device = await _resolve_current_device(uow, x_device_token, x_device_id)

    return {
        "user": _user_payload(user),
        "device": (
            {
                "device_id": device.id,
                "device_code": device.device_code,
                "device_name": device.device_name,
                "site_id": device.site_id,
                "is_active": device.is_active,
            }
            if device
            else None
        ),
    }


@router.get("/sites")
async def get_user_sites(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_device_token: UUID | None = Header(default=None, alias="X-Device-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
):
    async with uow:
        user = await _resolve_current_user(uow, x_user_token)
        await _resolve_current_device(uow, x_device_token, x_device_id)

        if user.is_root:
            sites, _ = await uow.sites.list_sites(
                filter=SiteFilter(is_active=True),
                user_site_ids=None,
                page=1,
                page_size=1000,
            )
            return {
                "is_root": True,
                "available_sites": [
                    {
                        "site_id": site.id,
                        "code": site.code,
                        "name": site.name,
                        "is_active": site.is_active,
                        "permissions": {
                            "can_view": True,
                            "can_operate": True,
                            "can_manage_catalog": True,
                        },
                    }
                    for site in sites
                ],
            }

        scopes = list(await uow.user_access_scopes.list_user_scopes(user.id))
        scope_by_site = {scope.site_id: scope for scope in scopes if scope.is_active and scope.can_view}
        site_ids = list(scope_by_site.keys())

        if not site_ids:
            return {"is_root": False, "available_sites": []}

        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=True),
            user_site_ids=site_ids,
            page=1,
            page_size=1000,
        )

        return {
            "is_root": False,
            "available_sites": [
                {
                    "site_id": site.id,
                    "code": site.code,
                    "name": site.name,
                    "is_active": site.is_active,
                    "permissions": {
                        "can_view": scope_by_site[site.id].can_view,
                        "can_operate": scope_by_site[site.id].can_operate,
                        "can_manage_catalog": scope_by_site[site.id].can_manage_catalog,
                    },
                }
                for site in sites
            ],
        }


@router.get("/context")
async def get_auth_context(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_device_token: UUID | None = Header(default=None, alias="X-Device-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
):
    async with uow:
        user = await _resolve_current_user(uow, x_user_token)
        device = await _resolve_current_device(uow, x_device_token, x_device_id)
        access_service = AccessService(uow)

        if user.is_root:
            sites, _ = await uow.sites.list_sites(
                filter=SiteFilter(is_active=True),
                user_site_ids=None,
                page=1,
                page_size=1000,
            )
            available_sites = [
                {
                    "site_id": site.id,
                    "code": site.code,
                    "name": site.name,
                    "is_active": site.is_active,
                    "permissions": {
                        "can_view": True,
                        "can_operate": True,
                        "can_manage_catalog": True,
                    },
                }
                for site in sites
            ]
            accessible_site_ids = [site["site_id"] for site in available_sites]
        else:
            scopes = list(await uow.user_access_scopes.list_user_scopes(user.id))
            scope_by_site = {scope.site_id: scope for scope in scopes if scope.is_active and scope.can_view}
            accessible_site_ids = list(scope_by_site.keys())
            if accessible_site_ids:
                sites, _ = await uow.sites.list_sites(
                    filter=SiteFilter(is_active=True),
                    user_site_ids=accessible_site_ids,
                    page=1,
                    page_size=1000,
                )
            else:
                sites = []
            available_sites = [
                {
                    "site_id": site.id,
                    "code": site.code,
                    "name": site.name,
                    "is_active": site.is_active,
                    "permissions": {
                        "can_view": scope_by_site[site.id].can_view,
                        "can_operate": scope_by_site[site.id].can_operate,
                        "can_manage_catalog": scope_by_site[site.id].can_manage_catalog,
                    },
                }
                for site in sites
            ]

        default_site = None
        if user.default_site_id in accessible_site_ids:
            default_site = next(
                (site for site in available_sites if site["site_id"] == user.default_site_id),
                None,
            )
        elif available_sites:
            default_site = available_sites[0]

        if default_site is not None:
            permissions_summary = await access_service.get_user_permissions_uuid(
                user_id=user.id,
                site_id=default_site["site_id"],
            )
        else:
            permissions_summary = {
                "can_read_operations": False,
                "can_create_operations": False,
                "can_read_balances": False,
                "can_manage_catalog": False,
                "can_manage_root_admin": user.is_root,
                "is_root": user.is_root,
            }

    return {
        "user": _user_payload(user),
        "role": user.role,
        "is_root": user.is_root,
        "default_site": default_site,
        "available_sites": available_sites,
        "permissions_summary": permissions_summary,
        "device": (
            {
                "device_id": device.id,
                "device_code": device.device_code,
                "device_name": device.device_name,
                "site_id": device.site_id,
                "is_active": device.is_active,
            }
            if device
            else None
        ),
    }
