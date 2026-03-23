from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.user_access_scope import UserAccessScope
from app.schemas.admin import SiteFilter
from app.services.uow import UnitOfWork


class AccessServiceV2:
    """Domain access and permission service using new UserAccessScope model."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def validate_acting_user(self, acting_user_id: UUID) -> None:
        user = await self.uow.users.get_by_id(acting_user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acting user is not registered or inactive",
            )

    async def validate_root_permission(self, acting_user_id: UUID) -> None:
        await self.validate_acting_user(acting_user_id)

        user = await self.uow.users.get_by_id(acting_user_id)
        if not user.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Root permission required",
            )

    async def get_user_access_scope(
        self,
        user_id: UUID,
        site_id: int,
    ) -> UserAccessScope | None:
        scope = await self.uow.user_access_scopes.get_by_user_and_site(user_id, site_id)
        return scope

    async def has_site_access(
        self,
        user_id: UUID,
        site_id: int,
        *,
        require_can_view: bool = True,
        require_can_operate: bool = False,
        require_can_manage_catalog: bool = False,
    ) -> bool:
        """Check if user has access to site with specified permissions."""
        user = await self.uow.users.get_by_id(user_id)
        if user is None or not user.is_active:
            return False
        
        # Root users have unrestricted access
        if user.is_root:
            return True
        
        scope = await self.get_user_access_scope(user_id, site_id)
        if scope is None or not scope.is_active:
            return False
        
        if require_can_view and not scope.can_view:
            return False
        
        if require_can_operate and not scope.can_operate:
            return False
        
        if require_can_manage_catalog and not scope.can_manage_catalog:
            return False
        
        return True

    async def can_read_site(self, user_id: UUID, site_id: int) -> bool:
        """Check if user can read site data."""
        return await self.has_site_access(user_id, site_id, require_can_view=True)

    async def can_operate_site(self, user_id: UUID, site_id: int) -> bool:
        """Check if user can perform operations on site."""
        return await self.has_site_access(user_id, site_id, require_can_view=True, require_can_operate=True)

    async def can_manage_catalog(self, user_id: UUID, site_id: int) -> bool:
        """Check if user can manage catalog on site."""
        return await self.has_site_access(
            user_id, 
            site_id, 
            require_can_view=True, 
            require_can_operate=True,
            require_can_manage_catalog=True
        )

    async def can_manage_root_admin(self, user_id: UUID) -> bool:
        """Check if user has root admin permissions."""
        user = await self.uow.users.get_by_id(user_id)
        return user is not None and user.is_active and user.is_root

    async def list_user_access_scopes(self, acting_user_id: UUID) -> list[UserAccessScope]:
        """List all access scopes (root only)."""
        await self.validate_root_permission(acting_user_id)
        return list(await self.uow.user_access_scopes.list_all_scopes())

    async def create_user_site_access(
        self,
        acting_user_id: UUID,
        user_id: UUID,
        site_id: int,
        *,
        can_view: bool = True,
        can_operate: bool = False,
        can_manage_catalog: bool = False,
    ) -> UserAccessScope:
        """Create a new user access scope (root only)."""
        await self.validate_root_permission(acting_user_id)

        user = await self.uow.users.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User {user_id} is inactive",
            )

        site = await self.uow.sites.get_by_id(site_id)
        if site is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )

        existing = await self.uow.user_access_scopes.get_by_user_and_site(user_id, site_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Access for this user and site already exists",
            )

        return await self.uow.user_access_scopes.create_scope(
            user_id=user_id,
            site_id=site_id,
            can_view=can_view,
            can_operate=can_operate,
            can_manage_catalog=can_manage_catalog,
            is_active=True,
        )

    async def update_user_site_access(
        self,
        acting_user_id: UUID,
        scope_id: int,
        *,
        can_view: bool | None = None,
        can_operate: bool | None = None,
        can_manage_catalog: bool | None = None,
        is_active: bool | None = None,
    ) -> UserAccessScope:
        """Update an existing access scope (root only)."""
        await self.validate_root_permission(acting_user_id)

        scope = await self.uow.user_access_scopes.get_by_id(scope_id)
        if scope is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Access scope not found",
            )

        return await self.uow.user_access_scopes.update_scope(
            scope_id,
            can_view=can_view,
            can_operate=can_operate,
            can_manage_catalog=can_manage_catalog,
            is_active=is_active,
        )

    async def get_user_permissions(
        self,
        user_id: UUID,
        site_id: int,
    ) -> dict[str, bool]:
        """Get comprehensive permissions for user at site."""
        user = await self.uow.users.get_by_id(user_id)
        if user is None or not user.is_active:
            return {
                "can_read_operations": False,
                "can_create_operations": False,
                "can_read_balances": False,
                "can_manage_catalog": False,
                "can_manage_root_admin": False,
                "is_root": False,
            }

        # Root users have all permissions
        if user.is_root:
            return {
                "can_read_operations": True,
                "can_create_operations": True,
                "can_read_balances": True,
                "can_manage_catalog": True,
                "can_manage_root_admin": True,
                "is_root": True,
            }

        scope = await self.get_user_access_scope(user_id, site_id)
        if scope is None or not scope.is_active:
            return {
                "can_read_operations": False,
                "can_create_operations": False,
                "can_read_balances": False,
                "can_manage_catalog": False,
                "can_manage_root_admin": False,
                "is_root": False,
            }

        return {
            "can_read_operations": scope.can_view,
            "can_create_operations": scope.can_operate,
            "can_read_balances": scope.can_view,
            "can_manage_catalog": scope.can_manage_catalog,
            "can_manage_root_admin": False,
            "is_root": False,
        }

    async def list_accessible_site_ids(
        self,
        user_id: UUID,
        *,
        require_can_view: bool = True,
        require_can_operate: bool = False,
        require_can_manage_catalog: bool = False,
    ) -> list[int]:
        """Get list of site IDs accessible by user with specified permissions."""
        user = await self.uow.users.get_by_id(user_id)
        if user is None or not user.is_active:
            return []
        
        # Root users have access to all sites
        if user.is_root:
            # We need to get all site IDs - this is a simplified version
            # In production, you might want to implement a proper method
            sites = await self.uow.sites.list_sites(SiteFilter(), None, 1, 1000)
            return [site.id for site in sites[0]]
        
        return await self.uow.user_access_scopes.list_accessible_site_ids(
            user_id,
            require_can_view=require_can_view,
            require_can_operate=require_can_operate,
            require_can_manage_catalog=require_can_manage_catalog,
        )
