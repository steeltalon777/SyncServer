from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.user_access_scope import UserAccessScope
from app.schemas.admin import UserSiteAccessCreate, UserSiteAccessUpdate
from app.services.uow import UnitOfWork


ROLE_ROOT = "root"
ROLE_CHIEF_STOREKEEPER = "chief_storekeeper"
ROLE_STOREKEEPER = "storekeeper"
ROLE_OBSERVER = "observer"

ROLE_PRIORITY: dict[str, int] = {
    ROLE_OBSERVER: 1,
    ROLE_STOREKEEPER: 2,
    ROLE_CHIEF_STOREKEEPER: 3,
    ROLE_ROOT: 4,
}


class AccessService:
    """Domain access and permission service using new UserAccessScope model."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    @staticmethod
    def _has_global_business_access(user) -> bool:
        return user is not None and user.is_active and (user.is_root or user.role == ROLE_CHIEF_STOREKEEPER)

    # ============================================================================
    # USER VALIDATION
    # ============================================================================

    async def validate_acting_user(self, acting_user_id: int) -> None:
        """LEGACY: Validate acting user (uses integer user_id)."""
        # This is a legacy method that needs integer user_id
        # In the new model, we should use UUID
        # For backward compatibility, we try to find the user
        
        # First try to get by integer ID (legacy)
        user = await self.uow.users.get(acting_user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acting user is not registered or inactive",
            )

    async def validate_acting_user_uuid(self, acting_user_id: UUID) -> None:
        """NEW: Validate acting user using UUID."""
        user = await self.uow.users.get_by_id(acting_user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acting user is not registered or inactive",
            )

    # ============================================================================
    # ROOT PERMISSIONS
    # ============================================================================

    async def validate_root_permission(self, acting_user_id: int) -> None:
        """LEGACY: Validate root permission (uses integer user_id)."""
        await self.validate_acting_user(acting_user_id)

        # Get user by integer ID (legacy)
        user = await self.uow.users.get(acting_user_id)
        if not user or not user.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Root permission required",
            )

    async def validate_root_permission_uuid(self, acting_user_id: UUID) -> None:
        """NEW: Validate root permission using UUID."""
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

    # ============================================================================
    # LEGACY COMPATIBILITY METHODS
    # ============================================================================

    async def get_user_site_role(
        self,
        user_id: int,
        site_id: UUID,
    ) -> str | None:
        """
        LEGACY: Get user's role at site (for backward compatibility).
        Maps new granular permissions to old role-based model.
        """
        # This is complex because:
        # 1. user_id is integer (legacy) but we need UUID
        # 2. site_id is UUID but new model uses int
        
        # For Phase 2, we'll implement a simplified version
        # that demonstrates the mapping concept
        
        # Step 1: Convert integer user_id to UUID (need mapping)
        # Step 2: Convert UUID site_id to int (need mapping)
        # Step 3: Check permissions and map to role
        
        # Since we don't have mapping tables yet, we'll return None
        # This will cause legacy code to fail, which is intentional
        # to force migration to new methods
        
        return None

    async def has_site_role(
        self,
        user_id: int,
        site_id: UUID,
        role: str,
    ) -> bool:
        """LEGACY: Check if user has specific role at site."""
        current_role = await self.get_user_site_role(user_id, site_id)
        return current_role == role

    async def has_minimum_site_role(
        self,
        user_id: int,
        site_id: UUID,
        minimum_role: str,
    ) -> bool:
        """LEGACY: Check if user has minimum role at site."""
        current_role = await self.get_user_site_role(user_id, site_id)
        if current_role is None:
            return False

        current_priority = ROLE_PRIORITY.get(current_role, 0)
        minimum_priority = ROLE_PRIORITY.get(minimum_role, 0)
        return current_priority >= minimum_priority

    async def can_read_site(self, user_id: int, site_id: UUID) -> bool:
        """LEGACY: Check if user can read site data."""
        # Map to new model: can_read = can_view
        # Need user_id and site_id conversion
        return False  # Placeholder

    async def can_create_operations(self, user_id: int, site_id: UUID) -> bool:
        """LEGACY: Check if user can create operations."""
        # Map to new model: can_create_operations = can_operate
        return False  # Placeholder

    async def can_manage_catalog_legacy(self, user_id: int, site_id: UUID) -> bool:
        """LEGACY: Check if user can manage catalog."""
        # Map to new model: can_manage_catalog = can_manage_catalog
        return False  # Placeholder

    # ============================================================================
    # ADMIN METHODS (ROOT ONLY)
    # ============================================================================

    async def list_user_access_entries(self, acting_user_id: int) -> list[UserAccessScope]:
        """LEGACY: List all access scopes (root only)."""
        await self.validate_root_permission(acting_user_id)
        return list(await self.uow.user_access_scopes.list_all_scopes())

    async def create_user_site_access(
        self,
        acting_user_id: int,
        payload: UserSiteAccessCreate,
    ) -> UserAccessScope:
        """LEGACY: Create user site access (uses legacy schemas)."""
        await self.validate_root_permission(acting_user_id)

        # Convert legacy payload to new model
        # Need to map integer user_id to UUID
        # Need to map UUID site_id to int
        
        # For Phase 2, we'll raise an error to force migration
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Legacy create_user_site_access not supported. "
                   "Use new methods with UUID user_id and int site_id.",
        )

    async def update_user_site_access(
        self,
        acting_user_id: int,
        access_id: int,
        payload: UserSiteAccessUpdate,
    ) -> UserAccessScope:
        """LEGACY: Update user site access."""
        await self.validate_root_permission(acting_user_id)

        # This should update UserAccessScope, not UserSiteRole
        scope = await self.uow.user_access_scopes.get_by_id(access_id)
        if scope is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Access scope not found",
            )

        # Map legacy role updates to granular permissions
        # This is complex and depends on business rules
        
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Legacy update_user_site_access not supported. "
                   "Use new methods with granular permissions.",
        )

    # ============================================================================
    # PERMISSION SUMMARIES
    # ============================================================================

    async def get_user_permissions(
        self,
        user_id: int,
        site_id: UUID,
    ) -> dict[str, bool]:
        """
        LEGACY: Get comprehensive permissions for user at site.
        Returns permissions in old format for backward compatibility.
        """
        # This is a legacy method that needs to be reimplemented
        # using new model with proper type conversions
        
        # Placeholder implementation that returns minimal permissions
        # This will cause legacy code to fail, forcing migration
        
        return {
            "can_read_operations": False,
            "can_create_operations": False,
            "can_read_balances": False,
            "can_manage_catalog": False,
            "can_manage_root_admin": False,
        }

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

        # Map granular permissions to legacy permission names
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
