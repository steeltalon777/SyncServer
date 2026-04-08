from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import get_uow
from app.models.device import Device
from app.models.site import Site
from app.models.user import User
from app.schemas.admin import (
    DeviceCreate,
    DeviceFilter,
    DeviceListResponse,
    DeviceResponse,
    DeviceTokenResponse,
    DeviceWithTokenResponse,
    DeviceUpdate,
    SiteCreate,
    SiteFilter,
    SiteListResponse,
    SiteResponse,
    SiteUpdate,
    UserAccessScopeCreate,
    UserAccessScopeReplaceRequest,
    UserAccessScopeResponse,
    UserAccessScopeUpdate,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserSyncStateResponse,
    UserTokenResponse,
    UserUpdate,
    UserWithTokenResponse,
)
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/admin", tags=["admin"])

CANONICAL_ROLES = [
    "root",
    "chief_storekeeper",
    "storekeeper",
    "observer",
]


async def _resolve_current_user(uow: UnitOfWork, x_user_token: UUID | None) -> User:
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


def _require_root(user: User) -> None:
    if not user.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="root permissions required",
        )


def _require_admin_basic(user: User) -> None:
    if user.is_root:
        return
    if user.role != "chief_storekeeper":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin access denied",
        )


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total


async def _validate_default_site(uow: UnitOfWork, default_site_id: int | None) -> None:
    if default_site_id is None:
        return

    site = await uow.sites.get_by_id(default_site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="default site not found")


def _require_non_root_target(user: User, *, detail: str) -> None:
    if user.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


def _user_with_token_payload(user: User) -> UserWithTokenResponse:
    return UserWithTokenResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_root=user.is_root,
        role=user.role,
        default_site_id=user.default_site_id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        user_token=user.user_token,
    )


@router.get("/roles", response_model=list[str])
async def list_roles(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> list[str]:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)
    return CANONICAL_ROLES


# ------------------------
# Sites
# ------------------------
@router.get("/sites", response_model=SiteListResponse)
async def list_sites_admin(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> SiteListResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)

        sites, total_count = await uow.sites.list_sites(
            filter=SiteFilter(is_active=is_active, search=search),
            user_site_ids=None,
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
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> SiteResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)

        existing = await uow.sites.get_by_code(payload.code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"site code '{payload.code}' already exists",
            )

        site = await uow.sites.create_site(
            name=payload.name,
            code=payload.code,
            description=payload.description,
            is_active=payload.is_active,
        )
    return SiteResponse.model_validate(site)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: int,
    payload: SiteUpdate,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> SiteResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)

        site = await uow.sites.get_by_id(site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

        if payload.code and payload.code != site.code:
            code_taken = await uow.sites.get_by_code(payload.code)
            if code_taken:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"site code '{payload.code}' already exists",
                )

        updated = await uow.sites.update_site(
            site_id=site_id,
            name=payload.name,
            code=payload.code,
            description=payload.description,
            is_active=payload.is_active,
        )
    return SiteResponse.model_validate(updated)


# ------------------------
# Users (root only)
# ------------------------
@router.get("/users", response_model=UserListResponse)
async def list_users(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    is_active: bool | None = Query(default=None),
    is_root: bool | None = Query(default=None),
    role: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> UserListResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        users = list(
            await uow.users.list_users(
                is_active=is_active,
                is_root=is_root,
                role=role,
                limit=10000,
                offset=0,
            )
        )

        if search:
            needle = search.lower()
            users = [
                user
                for user in users
                if needle in user.username.lower()
                or (user.email and needle in user.email.lower())
                or (user.full_name and needle in user.full_name.lower())
            ]

        page_items, total_count = _paginate(users, page, page_size)

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
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return UserResponse.model_validate(user)


@router.post("/users", response_model=UserResponse)
async def create_user(
    payload: UserCreate,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        if payload.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="admin api cannot create root users",
            )

        await _validate_default_site(uow, payload.default_site_id)

        if payload.id is not None:
            exists_by_id = await uow.users.get_by_id(payload.id)
            if exists_by_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user id already exists")

        exists_by_username = await uow.users.get_by_username(payload.username)
        if exists_by_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

        user = User(
            id=payload.id or uuid4(),
            username=payload.username,
            email=payload.email,
            full_name=payload.full_name,
            is_active=payload.is_active,
            is_root=payload.is_root,
            role=payload.role,
            default_site_id=payload.default_site_id,
        )
        uow.session.add(user)
        await uow.session.flush()
        await uow.session.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        _require_non_root_target(user, detail="admin api cannot update root users")

        if payload.username is not None and payload.username != user.username:
            exists_by_username = await uow.users.get_by_username(payload.username)
            if exists_by_username and exists_by_username.id != user.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

        if payload.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="admin api cannot update root users",
            )

        default_site_id = payload.default_site_id if "default_site_id" in payload.model_fields_set else user.default_site_id
        await _validate_default_site(uow, default_site_id)

        if payload.username is not None:
            user.username = payload.username
        if payload.email is not None:
            user.email = payload.email
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.is_active is not None:
            user.is_active = payload.is_active
        if payload.is_root is not None:
            user.is_root = payload.is_root
        if payload.role is not None:
            user.role = payload.role
        if "default_site_id" in payload.model_fields_set:
            user.default_site_id = payload.default_site_id

        await uow.session.flush()
        await uow.session.refresh(user)
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        if user.is_root and user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot deactivate current root user",
            )

        user.is_active = False
        await uow.session.flush()
        await uow.session.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}/sync-state", response_model=UserSyncStateResponse)
async def get_user_sync_state(
    user_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserSyncStateResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        scopes = await uow.user_access_scopes.list_user_scopes(user.id)

    return UserSyncStateResponse(
        user=_user_with_token_payload(user),
        scopes=[UserAccessScopeResponse.model_validate(scope) for scope in scopes],
    )


@router.put("/users/{user_id}/scopes", response_model=list[UserAccessScopeResponse])
async def replace_user_scopes(
    user_id: UUID,
    payload: UserAccessScopeReplaceRequest,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> list[UserAccessScopeResponse]:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        _require_non_root_target(user, detail="cannot replace scopes for root users")

        seen_site_ids: set[int] = set()
        scopes_payload = []
        for scope in payload.scopes:
            if scope.site_id in seen_site_ids:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="duplicate site_id in scopes payload",
                )
            seen_site_ids.add(scope.site_id)

            site = await uow.sites.get_by_id(scope.site_id)
            if not site:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

            scopes_payload.append(
                {
                    "site_id": scope.site_id,
                    "can_view": scope.can_view,
                    "can_operate": scope.can_operate,
                    "can_manage_catalog": scope.can_manage_catalog,
                }
            )

        scopes = await uow.user_access_scopes.replace_user_scopes(user.id, scopes_payload)

    return [UserAccessScopeResponse.model_validate(scope) for scope in scopes]


@router.post("/users/{user_id}/rotate-token", response_model=UserTokenResponse)
async def rotate_user_token(
    user_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserTokenResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        _require_non_root_target(user, detail="root token rotation is not allowed via API")

        user.user_token = uuid4()
        await uow.session.flush()
        await uow.session.refresh(user)

        return UserTokenResponse(
            user_id=user.id,
            username=user.username,
            user_token=user.user_token,
            generated_at=datetime.now(UTC),
        )


# ------------------------
# Access scopes (root only)
# ------------------------
@router.get("/access/scopes", response_model=list[UserAccessScopeResponse])
async def list_access_scopes(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    user_id: UUID | None = Query(default=None),
    site_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[UserAccessScopeResponse]:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        scopes = await uow.user_access_scopes.list_all_scopes(
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
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserAccessScopeResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        user = await uow.users.get_by_id(payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        site = await uow.sites.get_by_id(payload.site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

        existing = await uow.user_access_scopes.get_any_by_user_and_site(payload.user_id, payload.site_id)
        if existing:
            existing.can_view = payload.can_view
            existing.can_operate = payload.can_operate
            existing.can_manage_catalog = payload.can_manage_catalog
            existing.is_active = payload.is_active
            await uow.session.flush()
            await uow.session.refresh(existing)
            scope = existing
        else:
            scope = await uow.user_access_scopes.create_scope(
                user_id=payload.user_id,
                site_id=payload.site_id,
                can_view=payload.can_view,
                can_operate=payload.can_operate,
                can_manage_catalog=payload.can_manage_catalog,
                is_active=payload.is_active,
            )
    return UserAccessScopeResponse.model_validate(scope)


@router.patch("/access/scopes/{scope_id}", response_model=UserAccessScopeResponse)
async def update_access_scope(
    scope_id: int,
    payload: UserAccessScopeUpdate,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> UserAccessScopeResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_root(current_user)

        scope = await uow.user_access_scopes.update_scope(
            scope_id=scope_id,
            can_view=payload.can_view,
            can_operate=payload.can_operate,
            can_manage_catalog=payload.can_manage_catalog,
            is_active=payload.is_active,
        )
        if not scope:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scope not found")
    return UserAccessScopeResponse.model_validate(scope)


# ------------------------
# Devices (root + chief_storekeeper)
# ------------------------
@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    site_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> DeviceListResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)

        stmt = select(Device)
        if site_id is not None:
            stmt = stmt.where(Device.site_id == site_id)
        if is_active is not None:
            stmt = stmt.where(Device.is_active == is_active)
        if search:
            token = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Device.device_code.ilike(token),
                    Device.device_name.ilike(token),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await uow.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Device.id).offset((page - 1) * page_size).limit(page_size)
        devices = list((await uow.session.execute(stmt)).scalars().all())

    return DeviceListResponse(
        devices=[DeviceResponse.model_validate(device) for device in devices],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/devices", response_model=DeviceWithTokenResponse)
async def create_device(
    payload: DeviceCreate,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> DeviceWithTokenResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)

        if payload.site_id is not None:
            site = await uow.sites.get_by_id(payload.site_id)
            if not site:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

        device = Device(
            device_code=payload.device_code or f"device-{uuid4().hex[:10]}",
            device_name=payload.device_name,
            site_id=payload.site_id,
            is_active=payload.is_active,
            device_token=uuid4(),
        )
        uow.session.add(device)
        await uow.session.flush()
        await uow.session.refresh(device)
    return DeviceWithTokenResponse.model_validate(device)


@router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> DeviceResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)

        device = await uow.devices.get_by_id(device_id)
        if not device:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")

        if payload.site_id is not None:
            site = await uow.sites.get_by_id(payload.site_id)
            if not site:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

        if payload.device_code is not None:
            device.device_code = payload.device_code
        if payload.device_name is not None:
            device.device_name = payload.device_name
        if "site_id" in payload.model_fields_set:
            device.site_id = payload.site_id
        if payload.is_active is not None:
            device.is_active = payload.is_active

        await uow.session.flush()
        await uow.session.refresh(device)
    return DeviceResponse.model_validate(device)


@router.post("/devices/{device_id}/rotate-token", response_model=DeviceTokenResponse)
async def rotate_device_token(
    device_id: int,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> DeviceTokenResponse:
    async with uow:
        current_user = await _resolve_current_user(uow, x_user_token)
        _require_admin_basic(current_user)

        device = await uow.devices.get_by_id(device_id)
        if not device:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")

        device.device_token = uuid4()
        await uow.session.flush()
        await uow.session.refresh(device)

        return DeviceTokenResponse(
            device_id=device.id,
            device_token=device.device_token,
            generated_at=datetime.now(UTC),
        )
