from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.models.site import Site

class SiteRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, site_id: UUID) -> Site | None:
        query = select(Site).where(Site.id == site_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_code(self, code : str) -> Site | None:
        query = select(Site).where(Site.code == code)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, code: str, name: str) -> Site:
        site = Site(code=code, name=name)
        self.db.add(site)
        await self.db.flush()
        return site