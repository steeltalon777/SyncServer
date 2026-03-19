from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_access_scope import UserAccessScope


class UserAccessScopesRepo:
    """Repository for user_access_scopes table operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, scope_id: int) -> UserAccessScope | None:
        stmt = select(UserAccessScope).where(UserAccessScope.id == scope_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_site(
        self, user_id: UUID, site_id: int
    ) -> UserAccessScope | None:
        stmt = (
            select(UserAccessScope)
            .where(UserAccessScope.user_id == user_id)
            .where(UserAccessScope.site_id == site_id)
            .where(UserAccessScope.is_active == True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_any_by_user_and_site(
        self,
        user_id: UUID,
        site_id: int,
    ) -> UserAccessScope | None:
        stmt = (
            select(UserAccessScope)
            .where(UserAccessScope.user_id == user_id)
            .where(UserAccessScope.site_id == site_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_scopes(self, user_id: UUID) -> Sequence[UserAccessScope]:
        """Get all active access scopes for a user."""
        stmt = (
            select(UserAccessScope)
            .where(UserAccessScope.user_id == user_id)
            .where(UserAccessScope.is_active == True)
            .order_by(UserAccessScope.site_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_accessible_site_ids(
        self, 
        user_id: UUID, 
        *,
        require_can_view: bool = True,
        require_can_operate: bool = False,
        require_can_manage_catalog: bool = False,
    ) -> list[int]:
        """
        Get list of site IDs accessible by user with specified permissions.
        
        Args:
            user_id: User UUID
            require_can_view: If True, only include sites where can_view=True
            require_can_operate: If True, only include sites where can_operate=True
            require_can_manage_catalog: If True, only include sites where can_manage_catalog=True
        
        Returns:
            List of site IDs
        """
        stmt = select(UserAccessScope.site_id).where(
            UserAccessScope.user_id == user_id,
            UserAccessScope.is_active == True,
        )
        
        if require_can_view:
            stmt = stmt.where(UserAccessScope.can_view == True)
        
        if require_can_operate:
            stmt = stmt.where(UserAccessScope.can_operate == True)
        
        if require_can_manage_catalog:
            stmt = stmt.where(UserAccessScope.can_manage_catalog == True)
        
        stmt = stmt.order_by(UserAccessScope.site_id)
        
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def list_scopes_for_site(self, site_id: int) -> Sequence[UserAccessScope]:
        """Get all active access scopes for a site."""
        stmt = (
            select(UserAccessScope)
            .where(UserAccessScope.site_id == site_id)
            .where(UserAccessScope.is_active == True)
            .order_by(UserAccessScope.user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_all_scopes(
        self,
        *,
        user_id: UUID | None = None,
        site_id: int | None = None,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[UserAccessScope]:
        """List all access scopes with optional filtering."""
        stmt: Select[tuple[UserAccessScope]] = select(UserAccessScope).order_by(UserAccessScope.id)

        if user_id is not None:
            stmt = stmt.where(UserAccessScope.user_id == user_id)
        
        if site_id is not None:
            stmt = stmt.where(UserAccessScope.site_id == site_id)
        
        if is_active is not None:
            stmt = stmt.where(UserAccessScope.is_active == is_active)

        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_scope(
        self,
        *,
        user_id: UUID,
        site_id: int,
        can_view: bool = True,
        can_operate: bool = False,
        can_manage_catalog: bool = False,
        is_active: bool = True,
    ) -> UserAccessScope:
        """Create a new user access scope."""
        scope = UserAccessScope(
            user_id=user_id,
            site_id=site_id,
            can_view=can_view,
            can_operate=can_operate,
            can_manage_catalog=can_manage_catalog,
            is_active=is_active,
        )
        self.session.add(scope)
        await self.session.flush()
        await self.session.refresh(scope)
        return scope

    async def update_scope(
        self,
        scope_id: int,
        *,
        can_view: bool | None = None,
        can_operate: bool | None = None,
        can_manage_catalog: bool | None = None,
        is_active: bool | None = None,
    ) -> UserAccessScope | None:
        """Update an existing access scope."""
        scope = await self.get_by_id(scope_id)
        if scope is None:
            return None

        if can_view is not None:
            scope.can_view = can_view
        
        if can_operate is not None:
            scope.can_operate = can_operate
        
        if can_manage_catalog is not None:
            scope.can_manage_catalog = can_manage_catalog
        
        if is_active is not None:
            scope.is_active = is_active

        await self.session.flush()
        await self.session.refresh(scope)
        return scope

    async def update_scope_by_user_and_site(
        self,
        user_id: UUID,
        site_id: int,
        *,
        can_view: bool | None = None,
        can_operate: bool | None = None,
        can_manage_catalog: bool | None = None,
        is_active: bool | None = None,
    ) -> UserAccessScope | None:
        """Update scope by user and site combination."""
        scope = await self.get_by_user_and_site(user_id, site_id)
        if scope is None:
            return None

        return await self.update_scope(
            scope.id,
            can_view=can_view,
            can_operate=can_operate,
            can_manage_catalog=can_manage_catalog,
            is_active=is_active,
        )

    async def deactivate_scope(self, scope_id: int) -> bool:
        """Deactivate a scope (soft delete)."""
        scope = await self.get_by_id(scope_id)
        if scope is None:
            return False

        scope.is_active = False
        await self.session.flush()
        return True

    async def deactivate_scope_by_user_and_site(self, user_id: UUID, site_id: int) -> bool:
        """Deactivate scope by user and site combination."""
        scope = await self.get_by_user_and_site(user_id, site_id)
        if scope is None:
            return False

        return await self.deactivate_scope(scope.id)

    async def replace_user_scopes(
        self,
        user_id: UUID,
        scopes: list[dict],
    ) -> list[UserAccessScope]:
        """
        Replace all scopes for a user with new ones.
        
        Args:
            user_id: User UUID
            scopes: List of scope definitions with keys:
                - site_id: int
                - can_view: bool (default True)
                - can_operate: bool (default False)
                - can_manage_catalog: bool (default False)
        
        Returns:
            List of created/updated scopes
        """
        existing_scopes = list(await self.list_all_scopes(user_id=user_id, limit=10000, offset=0))
        existing_by_site = {scope.site_id: scope for scope in existing_scopes}
        requested_site_ids = {scope_def["site_id"] for scope_def in scopes}

        for scope in existing_scopes:
            if scope.site_id not in requested_site_ids:
                scope.is_active = False

        new_scopes = []
        for scope_def in scopes:
            scope = existing_by_site.get(scope_def["site_id"])
            if scope is None:
                scope = UserAccessScope(
                    user_id=user_id,
                    site_id=scope_def["site_id"],
                )
                self.session.add(scope)

            scope.can_view = scope_def.get("can_view", True)
            scope.can_operate = scope_def.get("can_operate", False)
            scope.can_manage_catalog = scope_def.get("can_manage_catalog", False)
            scope.is_active = True
            new_scopes.append(scope)

        await self.session.flush()
        for scope in new_scopes:
            await self.session.refresh(scope)
        return new_scopes
