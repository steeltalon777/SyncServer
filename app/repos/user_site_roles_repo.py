from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_site_role import UserSiteRole


class UserSiteRolesRepo:
    """Repository for user_site_roles table operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_and_site(self, user_id: int, site_id: UUID) -> UserSiteRole | None:
        """Get user site role by user ID and site ID."""
        stmt = (
            select(UserSiteRole)
            .where(UserSiteRole.user_id == user_id)
            .where(UserSiteRole.site_id == site_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_roles_for_site(self, site_id: UUID) -> list[UserSiteRole]:
        """Get all user roles for a specific site."""
        stmt = select(UserSiteRole).where(UserSiteRole.site_id == site_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_sites_for_user(self, user_id: int) -> list[UserSiteRole]:
        """Get all sites and roles for a specific user."""
        stmt = select(UserSiteRole).where(UserSiteRole.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_user_site_role(
        self, user_id: int, site_id: UUID, role: str
    ) -> UserSiteRole:
        """Create a new user site role."""
        user_site_role = UserSiteRole(
            user_id=user_id,
            site_id=site_id,
            role=role,
        )
        self.session.add(user_site_role)
        await self.session.flush()
        return user_site_role

    async def update_user_site_role(
        self, user_id: int, site_id: UUID, role: str
    ) -> UserSiteRole | None:
        """Update user site role."""
        user_site_role = await self.get_by_user_and_site(user_id, site_id)
        if user_site_role:
            user_site_role.role = role
            await self.session.flush()
        return user_site_role

    async def delete_user_site_role(self, user_id: int, site_id: UUID) -> bool:
        """Delete user site role."""
        user_site_role = await self.get_by_user_and_site(user_id, site_id)
        if user_site_role:
            await self.session.delete(user_site_role)
            await self.session.flush()
            return True
        return False