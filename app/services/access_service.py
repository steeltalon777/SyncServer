from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.user_access_scope import UserAccessScope
from app.services.uow import UnitOfWork


ROLE_ROOT = "root"
ROLE_CHIEF_STOREKEEPER = "chief_storekeeper"
ROLE_STOREKEEPER = "storekeeper"
ROLE_OBSERVER = "observer"

class AccessService:
    """Domain access and permission service using new UserAccessScope model."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    @staticmethod
    def _has_global_business_access(user) -> bool:
        return user is not None and user.is_active and (user.is_root or user.role == ROLE_CHIEF_STOREKEEPER)

    async def validate_acting_user_uuid(self, acting_user_id: UUID) -> None:
        """Validate acting user using UUID."""
        user = await self.uow.users.get_by_id(acting_user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acting user is not registered or inactive",
            )

    async def validate_root_permission_uuid(self, acting_user_id: UUID) -> None:
        """Validate root permission using UUID."""
        await self.validate_acting_user_uuid(acting_user_id)

        user = await self.uow.users.get_by_id(acting_user_id)
        if not user.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Root permission required",
            )

    # ============================================================================
    # USER PROPERTIES
    # ============================================================================

    async def is_root(self, user_id: UUID) -> bool:
        """Check if user is root (global root flag)."""
        user = await self.uow.users.get_by_id(user_id)
        return user is not None and user.is_active and user.is_root

    async def get_user_role(self, user_id: UUID) -> str | None:
        """Get user's domain role."""
        user = await self.uow.users.get_by_id(user_id)
        return user.role if user else None

    async def get_default_site_id(self, user_id: UUID) -> int | None:
        """Get user's default site ID."""
        user = await self.uow.users.get_by_id(user_id)
        return user.default_site_id if user else None

    async def get_accessible_scopes(self, user_id: UUID) -> list[UserAccessScope]:
        """Get all accessible scopes for user."""
        return list(await self.uow.user_access_scopes.list_user_scopes(user_id))

    # ============================================================================
    # SITE PERMISSION CHECKS
    # ============================================================================

    async def can_view_site(self, user_id: UUID, site_id: int) -> bool:
        """Check if user can view site data."""
        user = await self.uow.users.get_by_id(user_id)
        if not user or not user.is_active:
            return False
        
        # Root and chief_storekeeper users can view everything
        if self._has_global_business_access(user):
            return True
        
        # Non-root users need explicit scope with can_view=True
        scope = await self.uow.user_access_scopes.get_by_user_and_site(user_id, site_id)
        return scope is not None and scope.is_active and scope.can_view

    async def can_operate_site(self, user_id: UUID, site_id: int) -> bool:
        """Check if user can perform operations at site."""
        user = await self.uow.users.get_by_id(user_id)
        if not user or not user.is_active:
            return False
        
        # Root and chief_storekeeper users can operate everywhere
        if self._has_global_business_access(user):
            return True
        
        # Non-root users need explicit scope with can_view=True and can_operate=True
        scope = await self.uow.user_access_scopes.get_by_user_and_site(user_id, site_id)
        return (
            scope is not None 
            and scope.is_active 
            and scope.can_view 
            and scope.can_operate
        )

    async def can_manage_catalog(self, user_id: UUID, site_id: int) -> bool:
        """Check if user can manage catalog at site."""
        user = await self.uow.users.get_by_id(user_id)
        if not user or not user.is_active:
            return False
        
        # Root and chief_storekeeper users can manage catalog everywhere
        if self._has_global_business_access(user):
            return True
        
        # Non-root users need explicit scope with all permissions
        scope = await self.uow.user_access_scopes.get_by_user_and_site(user_id, site_id)
        return (
            scope is not None 
            and scope.is_active 
            and scope.can_view 
            and scope.can_operate
            and scope.can_manage_catalog
        )

    async def can_manage_root_admin(self, user_id: UUID) -> bool:
        """Check if user can manage root admin functions."""
        return await self.is_root(user_id)

    async def get_user_permissions_uuid(
        self,
        user_id: UUID,
        site_id: int,
    ) -> dict[str, bool]:
        """NEW: Get comprehensive permissions using new model."""
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

        # Root and chief_storekeeper users have full business permissions.
        if self._has_global_business_access(user):
            return {
                "can_read_operations": True,
                "can_create_operations": True,
                "can_read_balances": True,
                "can_manage_catalog": True,
                "can_manage_root_admin": user.is_root,
                "is_root": user.is_root,
            }

        # Check scope for non-root users
        scope = await self.uow.user_access_scopes.get_by_user_and_site(user_id, site_id)
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
            "can_manage_root_admin": False,  # Only via is_root
            "is_root": False,
        }

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

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
        
        # Root and chief_storekeeper users have access to all sites
        if self._has_global_business_access(user):
            # Simplified: get all sites
            # In production, implement proper pagination
            from app.schemas.admin import SiteFilter
            sites = await self.uow.sites.list_sites(SiteFilter(), None, 1, 1000)
            return [site.id for site in sites[0]]
        
        return await self.uow.user_access_scopes.list_accessible_site_ids(
            user_id,
            require_can_view=require_can_view,
            require_can_operate=require_can_operate,
            require_can_manage_catalog=require_can_manage_catalog,
        )
