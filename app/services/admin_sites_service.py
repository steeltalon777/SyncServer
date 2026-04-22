from __future__ import annotations

from fastapi import HTTPException, status

from app.schemas.admin import SiteFilter
from app.services.uow import UnitOfWork


class AdminSitesService:
    @staticmethod
    async def list_sites(
        uow: UnitOfWork,
        *,
        is_active: bool | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list, int]:
        return await uow.sites.list_sites(
            filter=SiteFilter(is_active=is_active, search=search),
            user_site_ids=None,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    async def get_site_required(uow: UnitOfWork, site_id: int):
        site = await uow.sites.get_by_id(site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")
        return site

    @staticmethod
    async def validate_site_code_unique(
        uow: UnitOfWork,
        *,
        code: str,
        current_site_id: int | None = None,
    ) -> None:
        existing = await uow.sites.get_by_code(code)
        if existing is not None and existing.id != current_site_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"site code '{code}' already exists",
            )

    @staticmethod
    async def create_site(uow: UnitOfWork, *, payload):
        await AdminSitesService.validate_site_code_unique(uow, code=payload.code)
        return await uow.sites.create_site(
            name=payload.name,
            code=payload.code,
            description=payload.description,
            is_active=payload.is_active,
        )

    @staticmethod
    async def update_site(
        uow: UnitOfWork,
        *,
        site_id: int,
        payload,
    ):
        site = await AdminSitesService.get_site_required(uow, site_id)
        if payload.code and payload.code != site.code:
            await AdminSitesService.validate_site_code_unique(
                uow,
                code=payload.code,
                current_site_id=site.id,
            )

        return await uow.sites.update_site(
            site_id=site_id,
            name=payload.name,
            code=payload.code,
            description=payload.description,
            is_active=payload.is_active,
        )
