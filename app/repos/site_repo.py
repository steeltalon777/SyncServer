"""Репозиторий для работы с сайтами (`sites`)."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.models.site import Site


class SiteRepo:
    """CRUD-операции для модели Site."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, site_id: UUID) -> Site | None:
        """Возвращает сайт по ID."""
        query = select(Site).where(Site.id == site_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Site | None:
        """Возвращает сайт по уникальному коду."""
        query = select(Site).where(Site.code == code)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, code: str, name: str) -> Site:
        """Создаёт сайт и делает `flush()`."""
        site = Site(code=code, name=name)
        self.db.add(site)
        await self.db.flush()
        return site
