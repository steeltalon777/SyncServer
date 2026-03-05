from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site import Site


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
