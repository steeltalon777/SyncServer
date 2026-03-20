from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.services.access_service import AccessService


class AccessGuard:
    """Access guard for permission checks using new access model."""

    # ============================================================================
    # USER VALIDATION
    # ============================================================================

    @staticmethod
    async def require_active_user(
        access_service: AccessService,
        user_id: UUID,
    ) -> None:
        """Require that user exists and is active."""
        await access_service.validate_acting_user_uuid(user_id)
    # ============================================================================
    # ROOT PERMISSIONS
    # ============================================================================

    @staticmethod
    async def require_root(
        access_service: AccessService,
        user_id: UUID,
    ) -> None:
        """Require that user has root permissions."""
        is_root = await access_service.is_root(user_id)
        if not is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Root permission required",
            )

    # ============================================================================
    # SITE PERMISSION CHECKS
    # ============================================================================

    @staticmethod
    async def require_view_access(
        access_service: AccessService,
        user_id: UUID,
        site_id: int,
    ) -> None:
        """Require that user can view site data."""
        can_view = await access_service.can_view_site(user_id, site_id)
        if not can_view:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="View permission required for this site",
            )
    @staticmethod
    async def require_operate_access(
        access_service: AccessService,
        user_id: UUID,
        site_id: int,
    ) -> None:
        """Require that user can perform operations at site."""
        can_operate = await access_service.can_operate_site(user_id, site_id)
        if not can_operate:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation permission required for this site",
            )

    @staticmethod
    async def require_catalog_manage_access(
        access_service: AccessService,
        user_id: UUID,
        site_id: int,
    ) -> None:
        """Require that user can manage catalog at site."""
        can_manage = await access_service.can_manage_catalog(user_id, site_id)
        if not can_manage:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Catalog management permission required for this site",
            )

    # ============================================================================
    # CATALOG PERMISSION CHECKS
    # ============================================================================

    @staticmethod
    async def require_catalog_admin_access(
        access_service: AccessService,
        user_id: UUID,
        site_id: int,
    ) -> None:
        """
        Require that user can manage catalog at site.

        Rules:
        - root -> full access
        - chief_storekeeper -> global business access
        - storekeeper -> denied
        - observer -> denied
        """
        # First check if user is root
        is_root = await access_service.is_root(user_id)
        if is_root:
            return

        # For non-root users, check can_manage_catalog permission
        can_manage = await access_service.can_manage_catalog(user_id, site_id)
        if not can_manage:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Catalog management permission required",
            )

    @staticmethod
    async def require_catalog_admin_access_uuid(
        access_service: AccessService,
        user_id: UUID,
        site_id: UUID,
    ) -> None:
        """
        Require that user can manage catalog at site (using UUID site_id).
        Temporary method for compatibility during transition.
        """
        # Convert UUID site_id to integer
        # We need to get the site to find its integer ID
        from app.services.uow import UnitOfWork
        # This is a bit tricky because we need uow
        # For now, we'll use a simplified approach
        # In production, this should be properly implemented

        # For Phase 2, we'll use a placeholder
        # This will be implemented when we have access to uow
        raise NotImplementedError(
            "require_catalog_admin_access_uuid requires uow context. "
            "Use require_catalog_admin_access with integer site_id instead."
        )

    # ============================================================================
    # COMPOSITE PERMISSION CHECKS
    # ============================================================================

    @staticmethod
    async def require_read_operations_access(
        access_service: AccessService,
        user_id: UUID,
        site_id: int,
    ) -> None:
        """Require that user can read operations at site."""
        # Reading operations requires view access
        await AccessGuard.require_view_access(access_service, user_id, site_id)
    @staticmethod
    async def require_create_operations_access(
        access_service: AccessService,
        user_id: UUID,
        site_id: int,
    ) -> None:
        """Require that user can create operations at site."""
        # Creating operations requires operate access
        await AccessGuard.require_operate_access(access_service, user_id, site_id)

    @staticmethod
    async def require_move_operation_access(
        access_service: AccessService,
        user_id: UUID,
        source_site_id: int,
        destination_site_id: int,
    ) -> None:
        """
        Require that user can perform move operations between sites.

        Note: This is a placeholder for MOVE business logic.
        Later service layer will implement full validation including:
        - Source site operate access
        - Destination site operate access
        - Business rules for cross-site moves
        """
        # For now, require operate access at both sites
        await AccessGuard.require_operate_access(access_service, user_id, source_site_id)
        await AccessGuard.require_operate_access(access_service, user_id, destination_site_id)

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

    @staticmethod
    async def get_user_permissions_summary(
        access_service: AccessService,
        user_id: UUID,
        site_id: int,
    ) -> dict[str, bool]:
        """Get comprehensive permissions summary for user at site."""
        return await access_service.get_user_permissions_uuid(user_id, site_id)

    @staticmethod
    async def list_accessible_sites(
        access_service: AccessService,
        user_id: UUID,
        *,
        require_can_view: bool = True,
        require_can_operate: bool = False,
        require_can_manage_catalog: bool = False,
    ) -> list[int]:
        """Get list of site IDs accessible by user with specified permissions."""
        return await access_service.list_accessible_site_ids(
            user_id,
            require_can_view=require_can_view,
            require_can_operate=require_can_operate,
            require_can_manage_catalog=require_can_manage_catalog,
        )

    # ============================================================================
    # LEGACY METHODS (for backward compatibility - DEPRECATED)
    # ============================================================================

    @staticmethod
    async def require_role(
        access_service: AccessService,
        user_id: int,
        site_id,
        allowed_roles: list[str],
    ) -> None:
        """LEGACY: Require specific role at site."""
        role = await access_service.get_user_site_role(user_id, site_id)

        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"required roles: {allowed_roles}",
            )

    @staticmethod
    async def require_storekeeper(
        access_service: AccessService,
        user_id: int,
        site_id,
    ) -> None:
        """LEGACY: Require storekeeper or higher role."""
        await AccessGuard.require_role(
            access_service,
            user_id,
            site_id,
            ["root", "chief_storekeeper", "storekeeper"],
        )

    @staticmethod
    async def require_root_legacy(
        access_service: AccessService,
        user_id: int,
    ) -> None:
        """LEGACY: Require root permission."""
        allowed = await access_service.can_manage_root_admin(user_id)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="root permission required",
            )

    # ============================================================================
    # ROLE-BASED PERMISSION MAPPING (for transition)
    # ============================================================================

    @staticmethod
    def map_role_to_permissions(role: str) -> dict[str, bool]:
        """Map legacy role to new granular permissions."""
        if role == "root":
            return {
                "can_view": True,
                "can_operate": True,
                "can_manage_catalog": True,
            }
        elif role == "chief_storekeeper":
            return {
                "can_view": True,
                "can_operate": True,
                "can_manage_catalog": True,
            }
        elif role == "storekeeper":
            return {
                "can_view": True,
                "can_operate": True,
                "can_manage_catalog": False,
            }
        elif role == "observer":
            return {
                "can_view": True,
                "can_operate": False,
                "can_manage_catalog": False,
            }
        else:
            return {
                "can_view": False,
                "can_operate": False,
                "can_manage_catalog": False,
            }

    @staticmethod
    def map_permissions_to_role(
        can_view: bool,
        can_operate: bool,
        can_manage_catalog: bool,
    ) -> str:
        """Map granular permissions to legacy role."""
        if can_view and can_operate and can_manage_catalog:
            return "chief_storekeeper"
        elif can_view and can_operate:
            return "storekeeper"
        elif can_view:
            return "observer"
        else:
            return "no_access"
