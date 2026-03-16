from __future__ import annotations

import logging
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.deps import (
    get_request_id,
    get_uow,
    require_acting_user,
    require_service_auth,
)
from app.schemas.admin import (
    DeviceCreate,
    DeviceListResponse,
    DeviceResponse,
    DeviceTokenResponse,
    DeviceUpdate,
    SiteCreate,
    SiteListResponse,
    SiteResponse,
    SiteUpdate,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserSiteAccessCreate,
    UserSiteAccessListResponse,
    UserSiteAccessResponse,
    UserSiteAccessUpdate,
    UserUpdate,
    SiteFilter
)
from app.services.access_service import AccessService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/admin")
logger = logging.getLogger(__name__)

ADMIN_ROLES = [
    "root",
    "chief_storekeeper",
    "storekeeper",
    "observer",
]


def _build_user_response(user) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _paginate_list(items: list, page: int, page_size: int) -> tuple[list, int]:
    total_count = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], total_count


# ------------------------
# Roles
# ------------------------
@router.get("/roles", response_model=list[str])
async def list_roles(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> list[str]:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

    logger.info(
        "request_id=%s list_roles user_id=%s returned=%s",
        get_request_id(request),
        x_acting_user_id,
        len(ADMIN_ROLES),
    )
    return ADMIN_ROLES


# ------------------------
# Sites
# ------------------------
@router.get("/sites", response_model=SiteListResponse)
async def list_sites_admin(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, description="Search in name, code, or description"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
) -> SiteListResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        site_filter = SiteFilter(
            is_active=is_active,
            search=search,
        )

        sites, total_count = await uow.sites.list_sites(
            filter=site_filter,
            user_site_ids=None,
            page=page,
            page_size=page_size,
        )
    site_responses = [SiteResponse.model_validate(site) for site in sites]

    logger.info(
        "request_id=%s list_sites_admin user_id=%s returned=%s total=%s",
        get_request_id(request),
        x_acting_user_id,
        len(site_responses),
        total_count,
    )

    return SiteListResponse(
        sites=site_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/sites", response_model=SiteResponse)
async def create_site(
    site_data: SiteCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> SiteResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        existing_site = await uow.sites.get_by_code(site_data.code)
        if existing_site:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Site with code '{site_data.code}' already exists",
            )

        site = await uow.sites.create_site(
            name=site_data.name,
            code=site_data.code,
            description=site_data.description,
            is_active=site_data.is_active,
        )

    logger.info(
        "request_id=%s create_site site_id=%s code=%s user_id=%s",
        get_request_id(request),
        site.id,
        site.code,
        x_acting_user_id,
    )

    return SiteResponse.model_validate(site)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: UUID,
    update_data: SiteUpdate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> SiteResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        site = await uow.sites.get_by_id(site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )

        if update_data.code and update_data.code != site.code:
            existing_site = await uow.sites.get_by_code(update_data.code)
            if existing_site:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Site with code '{update_data.code}' already exists",
                )

        updated_site = await uow.sites.update_site(
            site_id=site_id,
            name=update_data.name,
            code=update_data.code,
            description=update_data.description,
            is_active=update_data.is_active,
        )

    logger.info(
        "request_id=%s update_site site_id=%s user_id=%s",
        get_request_id(request),
        site_id,
        x_acting_user_id,
    )

    return SiteResponse.model_validate(updated_site)


# ------------------------
# Devices
# ------------------------
@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
    site_id: UUID | None = Query(None, description="Filter by site ID"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, description="Search in device name or description"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
) -> DeviceListResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        # TODO: заменить на реальный DevicesRepo.list_devices(...)
        devices = []
        total_count = 0

    device_responses = [DeviceResponse.model_validate(device) for device in devices]

    logger.info(
        "request_id=%s list_devices user_id=%s returned=%s total=%s",
        get_request_id(request),
        x_acting_user_id,
        len(device_responses),
        total_count,
    )

    return DeviceListResponse(
        devices=device_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


# ------------------------
# Users
# ------------------------
@router.get("/users", response_model=UserListResponse)
async def list_users(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, description="Search in username, email, or full name"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
) -> UserListResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        users = list(await uow.users.list(is_active=is_active, limit=10000, offset=0))

        if search:
            search_lower = search.lower()
            users = [
                user
                for user in users
                if search_lower in user.username.lower()
                or (user.email and search_lower in user.email.lower())
                or (user.full_name and search_lower in user.full_name.lower())
            ]

        page_items, total_count = _paginate_list(users, page, page_size)

    user_responses = [_build_user_response(user) for user in page_items]

    logger.info(
        "request_id=%s list_users user_id=%s returned=%s total=%s",
        get_request_id(request),
        x_acting_user_id,
        len(user_responses),
        total_count,
    )

    return UserListResponse(
        users=user_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UserResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        user = await uow.users.get(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    logger.info(
        "request_id=%s get_user requested_user_id=%s by_user_id=%s",
        get_request_id(request),
        user_id,
        x_acting_user_id,
    )

    return _build_user_response(user)


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UserResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        existing_by_id = await uow.users.get(user_data.user_id)
        if existing_by_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with id {user_data.user_id} already exists",
            )

        existing_by_username = await uow.users.get_by_username(user_data.username)
        if existing_by_username is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with username '{user_data.username}' already exists",
            )

        user = await uow.users.create(
            user_id=user_data.user_id,
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            is_active=user_data.is_active,
        )

    logger.info(
        "request_id=%s create_user created_user_id=%s by_user_id=%s",
        get_request_id(request),
        user.id,
        x_acting_user_id,
    )

    return _build_user_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UserResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        existing_user = await uow.users.get(user_id)
        if existing_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if update_data.username and update_data.username != existing_user.username:
            existing_by_username = await uow.users.get_by_username(update_data.username)
            if existing_by_username is not None and existing_by_username.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User with username '{update_data.username}' already exists",
                )

        updated_user = await uow.users.update(
            user_id=user_id,
            username=update_data.username,
            email=update_data.email,
            full_name=update_data.full_name,
            is_active=update_data.is_active,
        )

    logger.info(
        "request_id=%s update_user updated_user_id=%s by_user_id=%s",
        get_request_id(request),
        user_id,
        x_acting_user_id,
    )

    return _build_user_response(updated_user)


# ------------------------
# User-site access
# ------------------------
@router.get("/access/user-sites", response_model=UserSiteAccessListResponse)
async def list_user_site_access(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
    user_id: int | None = Query(None, description="Filter by user ID"),
    site_id: UUID | None = Query(None, description="Filter by site ID"),
    role: str | None = Query(None, description="Filter by role"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
) -> UserSiteAccessListResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        access_entries = list(
            await access_service.list_user_access_entries(user_context["user_id"])
        )

        if user_id is not None:
            access_entries = [entry for entry in access_entries if entry.user_id == user_id]
        if site_id is not None:
            access_entries = [entry for entry in access_entries if entry.site_id == site_id]
        if role is not None:
            access_entries = [entry for entry in access_entries if entry.role == role]
        if is_active is not None:
            access_entries = [
                entry for entry in access_entries if entry.is_active == is_active
            ]

        page_items, total_count = _paginate_list(access_entries, page, page_size)

    access_responses = [
        UserSiteAccessResponse.model_validate(entry) for entry in page_items
    ]

    logger.info(
        "request_id=%s list_user_site_access by_user_id=%s returned=%s total=%s",
        get_request_id(request),
        x_acting_user_id,
        len(access_responses),
        total_count,
    )

    return UserSiteAccessListResponse(
        access_entries=access_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/access/user-sites", response_model=UserSiteAccessResponse)
async def create_user_site_access(
    access_data: UserSiteAccessCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UserSiteAccessResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)

        access_entry = await access_service.create_user_site_access(
            user_context["user_id"],
            access_data,
        )

    logger.info(
        "request_id=%s create_user_site_access target_user_id=%s site_id=%s role=%s by_user_id=%s",
        get_request_id(request),
        access_data.user_id,
        access_data.site_id,
        access_data.role,
        x_acting_user_id,
    )

    return UserSiteAccessResponse.model_validate(access_entry)


@router.patch("/access/user-sites/{access_id}", response_model=UserSiteAccessResponse)
async def update_user_site_access(
    access_id: int,
    update_data: UserSiteAccessUpdate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UserSiteAccessResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)

        access_entry = await access_service.update_user_site_access(
            user_context["user_id"],
            access_id,
            update_data,
        )

    logger.info(
        "request_id=%s update_user_site_access access_id=%s by_user_id=%s",
        get_request_id(request),
        access_id,
        x_acting_user_id,
    )

    return UserSiteAccessResponse.model_validate(access_entry)

@router.delete("/users/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UserResponse:
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        access_service = AccessService(uow)
        await access_service.validate_root_permission(user_context["user_id"])

        existing_user = await uow.users.get(user_id)
        if existing_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if user_id == 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Root user cannot be deactivated",
            )

        updated_user = await uow.users.update(
            user_id=user_id,
            is_active=False,
        )

    logger.info(
        "request_id=%s delete_user deactivated_user_id=%s by_user_id=%s",
        get_request_id(request),
        user_id,
        x_acting_user_id,
    )

    return _build_user_response(updated_user)