from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site import Site
from app.schemas.admin import SiteFilter


class SitesRepo:
    """Data access for sites table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, site_id: UUID) -> Site | None:
        result = await self.session.execute(select(Site).where(Site.id == site_id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Site | None:
        result = await self.session.execute(select(Site).where(Site.code == code))
        return result.scalar_one_or_none()

    async def create_site(
        self,
        name: str,
        code: str,
        description: str | None = None,
        is_active: bool = True,
    ) -> Site:
        """Create a new site."""
        site = Site(
            name=name,
            code=code,
            description=description,
            is_active=is_active,
        )
        self.session.add(site)
        await self.session.flush()
        return site

    async def update_site(
        self,
        site_id: UUID,
        name: str | None = None,
        code: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Site | None:
        """Update a site."""
        site = await self.get_by_id(site_id)
        if site:
            if name is not None:
                site.name = name
            if code is not None:
                site.code = code
            if description is not None:
                site.description = description
            if is_active is not None:
                site.is_active = is_active
            await self.session.flush()
        return site

    async def list_sites(
        self,
        filter: SiteFilter,
        user_site_ids: list[UUID] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Site], int]:
        """List sites with filtering and pagination."""
        stmt = select(Site)
        where_clauses = []

        # Apply user site access filter if provided
        if user_site_ids is not None:
            where_clauses.append(Site.id.in_(user_site_ids))

        # Apply filters
        if filter.is_active is not None:
            where_clauses.append(Site.is_active == filter.is_active)
        if filter.search:
            search_term = f"%{filter.search}%"
            where_clauses.append(
                or_(
                    Site.name.ilike(search_term),
                    Site.code.ilike(search_term),
                    Site.description.ilike(search_term),
                )
            )

        if where_clauses:
            stmt = stmt.where(and_(*where_clauses))

        # Count total
        count_stmt = select(func.count()).select_from(Site)
        if where_clauses:
            count_stmt = count_stmt.where(and_(*where_clauses))
        total_result = await self.session.execute(count_stmt)
        total_count = total_result.scalar_one()

        # Apply ordering and pagination
        stmt = stmt.order_by(desc(Site.created_at))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        sites = list(result.scalars().all())

        return sites, total_count

    async def get_user_sites(self, user_id: int) -> list[Site]:
        """Get all sites accessible by a user."""
        from app.models.user_site_role import UserSiteRole

        stmt = (
            select(Site)
            .join(UserSiteRole, Site.id == UserSiteRole.site_id)
            .where(
                and_(
                    UserSiteRole.user_id == user_id,
                    UserSiteRole.role.in_(["root", "chief_storekeeper", "storekeeper"]),
                )
            )
            .order_by(Site.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def site_exists(self, site_id: UUID) -> bool:
        """Check if a site exists."""
        site = await self.get_by_id(site_id)
        return site is not None
