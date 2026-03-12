from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.deps import (
    get_request_id,
    get_uow,
    require_service_auth,
    require_acting_user,
)
from app.schemas.admin import (
    DeviceCreate,
    DeviceFilter,
    DeviceListResponse,
    DeviceResponse,
    DeviceTokenResponse,
    DeviceUpdate,
    SiteCreate,
    SiteFilter,
    SiteListResponse,
    SiteResponse,
    SiteUpdate,
    UserCreate,
    UserFilter,
    UserListResponse,
    UserResponse,
    UserSiteAccessCreate,
    UserSiteAccessFilter,
    UserSiteAccessListResponse,
    UserSiteAccessResponse,
    UserSiteAccessUpdate,
    UserUpdate,
)
from app.services.access_service import AccessService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/admin")
logger = logging.getLogger(__name__)


# Sites endpoints
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
    """List sites (admin view)."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Only root can list all sites
    if not await AccessService.validate_root_permission(uow, user_context["user_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only root users can list all sites",
        )
    
    # Build filter
    filter_data = SiteFilter(
        is_active=is_active,
        search=search,
    )
    
    async with uow:
        sites, total_count = await uow.sites.list_sites(
            filter=filter_data,
            user_site_ids=None,  # Root sees all sites
            page=page,
            page_size=page_size,
        )
    
    # Convert to response models
    site_responses = [SiteResponse.model_validate(site) for site in sites]
    
    logger.info(
        "request_id=%s list_sites_admin user_id=%s returned=%s total=%s",
        get_request_id(request),
        user_context["user_id"],
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
    """Create a new site."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Only root can create sites
    if not await AccessService.validate_root_permission(uow, user_context["user_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only root users can create sites",
        )
    
    # Check if site code already exists
    async with uow:
        existing_site = await uow.sites.get_by_code(site_data.code)
        if existing_site:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Site with code '{site_data.code}' already exists",
            )
        
        # Create site
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
        user_context["user_id"],
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
    """Update a site."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Only root can update sites
    if not await AccessService.validate_root_permission(uow, user_context["user_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only root users can update sites",
        )
    
    async with uow:
        # Check if site exists
        site = await uow.sites.get_by_id(site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )
        
        # Check if new code already exists (if updating code)
        if update_data.code and update_data.code != site.code:
            existing_site = await uow.sites.get_by_code(update_data.code)
            if existing_site:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Site with code '{update_data.code}' already exists",
                )
        
        # Update site
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
        user_context["user_id"],
    )
    
    return SiteResponse.model_validate(updated_site)


# Devices endpoints
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
    """List devices."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Only root can list devices
    if not await AccessService.validate_root_permission(uow, user_context["user_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only root users can list devices",
        )
    
    # Build filter
    filter_data = DeviceFilter(
        site_id=site_id,
        is_active=is_active,
        search=search,
    )
    
    async with uow:
        # We need to implement list_devices method in DevicesRepo
        # For now, return empty list
        devices = []
        total_count = 0
    
    # Convert to response models
    device_responses = [DeviceResponse.model_validate(device) for device in devices]
    
    logger.info(
        "request_id=%s list_devices user_id=%s returned=%s total=%s",
        get_request_id(request),
        user_context["user_id"],
        len(device_responses),
        total_count,
    )
    
    return DeviceListResponse(
        devices=device_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


# User-site access endpoints
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
    """List user-site access entries."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Only root can list access entries
    if not await AccessService.validate_root_permission(uow, user_context["user_id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only root users can list access entries",
        )
    
    # Build filter
    filter_data = UserSiteAccessFilter(
        user_id=user_id,
        site_id=site_id,
        role=role,
        is_active=is_active,
    )
    
    async with uow:
        # We need to implement list_user_site_access method in UserSiteRolesRepo
        # For now, return empty list
        access_entries = []
        total_count = 0
    
    # Convert to response models
    access_responses = [UserSiteAccessResponse.model_validate(entry) for entry in access_entries]
    
    logger.info(
        "request_id=%s list_user_site_access user_id=%s returned=%s total=%s",
        get_request_id(request),
        user_context["user_id"],
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
    """Create user-site access entry."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    async with uow:
        result = await AccessService.create_user_site_access(
            uow=uow,
            access_data=access_data,
            created_by_user_id=user_context["user_id"],
        )
    
    logger.info(
        "request_id=%s create_user_site_access user_id=%s site_id=%s role=%s created_by=%s",
        get_request_id(request),
        access_data.user_id,
        access_data.site_id,
        access_data.role,
        user_context["user_id"],
    )
    
    return UserSiteAccessResponse.model_validate(result["access_entry"])


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
    """Update user-site access entry."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    async with uow:
        result = await AccessService.update_user_site_access(
            uow=uow,
            access_id=access_id,
            update_data=update_data,
            updated_by_user_id=user_context["user_id"],
        )
    
    logger.info(
        "request_id=%s update_user_site_access access_id=%s updated_by=%s",
        get_request_id(request),
        access_id,
        user_context["user_id"],
    )
    
    return UserSiteAccessResponse.model_validate(result["access_entry"])