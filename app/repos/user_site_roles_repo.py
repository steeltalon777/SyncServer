from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_site_role import UserSiteRole


class UserSiteRolesRepo:
    """LEGACY repository for user_site_roles table operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, access_id: int) -> UserSiteRole | None:
        stmt = select(UserSiteRole).where(UserSiteRole.id == access_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_site(
        self, user_id: int, site_id: UUID
    ) -> UserSiteRole | None:
        stmt = (
            select(UserSiteRole)
            .where(UserSiteRole.user_id == user_id)
            .where(UserSiteRole.site_id == site_id)
            .where(UserSiteRole.is_active == True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sites_for_user(self, user_id: int) -> list[UserSiteRole]:
        stmt = (
            select(UserSiteRole)
            .where(UserSiteRole.user_id == user_id)
            .where(UserSiteRole.is_active == True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_users_for_site(self, site_id: UUID) -> list[UserSiteRole]:
        stmt = (
            select(UserSiteRole)
            .where(UserSiteRole.site_id == site_id)
            .where(UserSiteRole.is_active == True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_access_entries(self) -> list[UserSiteRole]:
        stmt = select(UserSiteRole).order_by(UserSiteRole.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, user_id: int, site_id: UUID, role: str
    ) -> UserSiteRole:
        access = UserSiteRole(
            user_id=user_id,
            site_id=site_id,
            role=role,
            is_active=True,
        )
        self.session.add(access)
        await self.session.flush()
        return access

    async def update_role(
        self, user_id: int, site_id: UUID, role: str
    ) -> UserSiteRole | None:
        access = await self.get_by_user_and_site(user_id, site_id)

        if access is None:
            return None

        access.role = role
        await self.session.flush()
        return access

    async def deactivate(
        self, user_id: int, site_id: UUID
    ) -> bool:
        access = await self.get_by_user_and_site(user_id, site_id)

        if access is None:
            return False

        access.is_active = False
        await self.session.flush()
        return True
