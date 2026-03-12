from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status

from app.schemas.admin import (
    UserSiteAccessCreate,
    UserSiteAccessUpdate,
)
from app.services.uow import UnitOfWork

logger = logging.getLogger(__name__)


class AccessService:
    """Service for access control and role management."""

    @staticmethod
    async def validate_root_permission(
        uow: UnitOfWork,
        user_id: int,
    ) -> bool:
        """Validate that user has root permission."""
        # Get all user-site roles
        user_roles = await uow.user_site_roles.get_sites_for_user(user_id)
        
        # Check if user has root role on any site
        for user_role in user_roles:
            if user_role.role == "root":
                return True
        
        return False

    @staticmethod
    async def validate_chief_storekeeper_permission(
        uow: UnitOfWork,
        user_id: int,
        site_id: UUID | None = None,
    ) -> bool:
        """Validate that user has chief_storekeeper or root permission."""
        if site_id:
            # Check specific site
            user_role = await uow.user_site_roles.get_by_user_and_site(user_id, site_id)
            if user_role:
                return user_role.role in ["chief_storekeeper", "root"]
            return False
        else:
            # Check any site
            user_roles = await uow.user_site_roles.get_sites_for_user(user_id)
            for user_role in user_roles:
                if user_role.role in ["chief_storekeeper", "root"]:
                    return True
            return False

    @staticmethod
    async def get_user_sites_with_roles(
        uow: UnitOfWork,
        user_id: int,
    ) -> list[tuple[UUID, str]]:
        """Get all sites and roles for a user."""
        user_roles = await uow.user_site_roles.get_sites_for_user(user_id)
        return [(role.site_id, role.role) for role in user_roles]

    @staticmethod
    async def create_user_site_access(
        uow: UnitOfWork,
        access_data: UserSiteAccessCreate,
        created_by_user_id: int,
    ) -> dict:
        """Create user-site access entry."""
        # Only root can create access entries
        if not await AccessService.validate_root_permission(uow, created_by_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only root users can create access entries",
            )
        
        # Validate site exists
        site = await uow.sites.get_by_id(access_data.site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )
        
        # Check if access entry already exists
        existing_access = await uow.user_site_roles.get_by_user_and_site(
            access_data.user_id,
            access_data.site_id,
        )
        
        if existing_access:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already has access to this site",
            )
        
        # Create access entry
        user_site_role = await uow.user_site_roles.create_user_site_role(
            user_id=access_data.user_id,
            site_id=access_data.site_id,
            role=access_data.role,
        )
        
        logger.info(
            f"Created user-site access: user {access_data.user_id} -> "
            f"site {access_data.site_id} with role {access_data.role} "
            f"by user {created_by_user_id}"
        )
        
        return {"access_entry": user_site_role}

    @staticmethod
    async def update_user_site_access(
        uow: UnitOfWork,
        access_id: int,
        update_data: UserSiteAccessUpdate,
        updated_by_user_id: int,
    ) -> dict:
        """Update user-site access entry."""
        # Only root can update access entries
        if not await AccessService.validate_root_permission(uow, updated_by_user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only root users can update access entries",
            )
        
        # Get the access entry
        # Note: We need to implement get_by_id method in UserSiteRolesRepo
        # For now, we'll get it differently
        from sqlalchemy import select
        from app.models.user_site_role import UserSiteRole
        
        stmt = select(UserSiteRole).where(UserSiteRole.id == access_id)
        result = await uow.session.execute(stmt)
        access_entry = result.scalar_one_or_none()
        
        if not access_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Access entry not found",
            )
        
        # Update fields
        if update_data.role is not None:
            access_entry.role = update_data.role
        if update_data.is_active is not None:
            access_entry.is_active = update_data.is_active
        
        await uow.session.flush()
        
        logger.info(
            f"Updated user-site access {access_id}: "
            f"role={update_data.role}, is_active={update_data.is_active} "
            f"by user {updated_by_user_id}"
        )
        
        return {"access_entry": access_entry}

    @staticmethod
    async def get_user_permissions(
        uow: UnitOfWork,
        user_id: int,
        site_id: UUID,
    ) -> dict:
        """Get user permissions for a specific site."""
        user_role = await uow.user_site_roles.get_by_user_and_site(user_id, site_id)
        
        if not user_role:
            return {
                "has_access": False,
                "role": None,
                "permissions": {},
            }
        
        # Define permissions based on role
        permissions = {
            "can_view_operations": True,
            "can_view_balances": True,
            "can_view_catalog": True,
            "can_create_operations": user_role.role in ["storekeeper", "chief_storekeeper", "root"],
            "can_edit_catalog": user_role.role in ["chief_storekeeper", "root"],
            "can_manage_users": user_role.role == "root",
            "can_manage_sites": user_role.role == "root",
            "can_manage_devices": user_role.role == "root",
        }
        
        return {
            "has_access": True,
            "role": user_role.role,
            "permissions": permissions,
        }

    @staticmethod
    async def validate_operation_permission(
        uow: UnitOfWork,
        user_id: int,
        site_id: UUID,
        operation_type: str,
    ) -> bool:
        """Validate if user can perform specific operation type on site."""
        user_role = await uow.user_site_roles.get_by_user_and_site(user_id, site_id)
        
        if not user_role:
            return False
        
        # All roles can perform all operation types
        # Additional validation happens in OperationsService
        return user_role.role in ["storekeeper", "chief_storekeeper", "root"]