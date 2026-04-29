from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.admin import SiteFilter, UserCreate
from app.services.access_service import AccessService
from app.services.uow import UnitOfWork
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


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


def _has_global_business_access(user: User) -> bool:
    return user.is_root or user.role == "chief_storekeeper"


def _user_sync_payload(user: User) -> dict:
    payload = _user_payload(user)
    payload["user_token"] = str(user.user_token)
    return payload


async def _validate_default_site(uow: UnitOfWork, default_site_id: int | None) -> None:
    if default_site_id is None:
        return

    site = await uow.sites.get_by_id(default_site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="default site not found",
        )


async def _build_visible_sites_payload(uow: UnitOfWork, user: User) -> list[dict]:
    is_global = _has_global_business_access(user)
    sites, _ = await uow.sites.list_sites(
        filter=SiteFilter(is_active=True),
        user_site_ids=None,
        page=1,
        page_size=1000,
    )

    scope_by_site = {}
    if not is_global:
        scopes = list(await uow.user_access_scopes.list_user_scopes(user.id))
        scope_by_site = {scope.site_id: scope for scope in scopes if scope.is_active}

    site_payload = []
    for site in sites:
        scope = scope_by_site.get(site.id)
        site_payload.append(
            {
                "site_id": site.id,
                "code": site.code,
                "name": site.name,
                "is_active": site.is_active,
                "permissions": {
                    "can_view": True,
                    "can_operate": True if is_global else bool(scope and scope.can_view and scope.can_operate),
                    "can_manage_catalog": True
                    if is_global
                    else bool(scope and scope.can_view and scope.can_operate and scope.can_manage_catalog),
                },
            }
        )
    return site_payload


@router.post("/sync-user")
async def sync_user(
    payload: UserCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """
    Sync user registry record (Django-compatible), authenticated by user token.
    Root-only operation.
    """
    async with uow:
        if not identity.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="root permissions required for sync-user",
            )

        if payload.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="sync-user cannot create or update root users",
            )

        await _validate_default_site(uow, payload.default_site_id)

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
            if target_user.is_root:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="sync-user cannot create or update root users",
                )
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
        "user": _user_sync_payload(target_user),
        "synced_by": {
            "id": str(identity.user_id),
            "username": identity.username,
            "device_id": identity.device_id,
        },
    }


@router.get("/me")
async def get_me(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    user = identity.user
    device = identity.device

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
    identity: Identity = Depends(require_user_identity),
):
    user = identity.user

    async with uow:
        available_sites = await _build_visible_sites_payload(uow, user)

        return {
            "is_root": user.is_root,
            "available_sites": available_sites,
        }


@router.get("/context")
async def get_auth_context(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    user = identity.user
    device = identity.device

    async with uow:
        access_service = AccessService(uow)

        available_sites = await _build_visible_sites_payload(uow, user)
        accessible_site_ids = [site["site_id"] for site in available_sites]

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
            permissions_summary["can_read_operations"] = True
            permissions_summary["can_read_balances"] = True
        else:
            permissions_summary = {
                "can_read_operations": True,
                "can_create_operations": False,
                "can_read_balances": True,
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
