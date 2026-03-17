from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.core.identity import Identity
from app.services.uow import UnitOfWork


class IdentityService:
    """Service for resolving and validating identities from tokens."""
    
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
    
    async def resolve_user_by_token(self, user_token: UUID) -> Identity:
        """
        Resolve user identity by user token.
        
        Args:
            user_token: UUID user token from X-User-Token header
            
        Returns:
            Identity object with user information
            
        Raises:
            HTTPException: if user not found or inactive
        """
        user = await self.uow.users.get_by_user_token(user_token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user token",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )
        
        # Load user's access scopes
        scopes = list(await self.uow.user_access_scopes.list_user_scopes(user.id))
        
        return Identity.from_user_and_device(
            user=user,
            device=None,
            scopes=scopes,
        )
    
    async def resolve_device_by_token(
        self,
        device_id: int | str | UUID | None,
        device_token: UUID,
        *,
        update_last_seen: bool = True,
        client_ip: str | None = None,
        client_version: str | None = None,
    ) -> Identity:
        """
        Resolve device identity by device token.
        
        Args:
            device_id: UUID device ID from X-Device-Id header
            device_token: UUID device token from X-Device-Token header
            update_last_seen: Whether to update device's last seen timestamp
            client_ip: Client IP address for last seen update
            client_version: Client version for last seen update
            
        Returns:
            Identity object with device and associated user information
            
        Raises:
            HTTPException: if device not found, token invalid, or device inactive
        """
        device = await self.uow.devices.get_by_device_token(device_token)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid device token",
            )

        if not device.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device is inactive",
            )

        if device_id is not None and str(device.id) != str(device_id):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Device token does not match device id",
            )

        if update_last_seen:
            await self.uow.devices.update_last_seen(
                device_id=device.id,
                ip=client_ip,
                client_version=client_version,
            )

        # Device-token auth is primary. User binding for device principals
        # will be completed during endpoint migration.
        from app.models.user import User
        from uuid import uuid4

        device_user = User(
            id=uuid4(),
            username=f"device:{device.id}",
            email=None,
            full_name="Device Principal",
            user_token=uuid4(),
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=device.site_id,
        )

        return Identity.from_user_and_device(
            user=device_user,
            device=device,
            scopes=[],
        )
    
    async def resolve_current_identity(
        self,
        *,
        user_token: UUID | None = None,
        device_id: int | str | UUID | None = None,
        device_token: UUID | None = None,
        client_ip: str | None = None,
        client_version: str | None = None,
    ) -> Identity:
        """
        Resolve current identity based on available tokens.
        Prioritizes user token over device token.
        Args:
            user_token: Optional user token
            device_id: Optional device ID
            device_token: Optional device token
            client_ip: Optional client IP
            client_version: Optional client version
        Returns:
            Identity object

        Raises:
            HTTPException: if no valid tokens provided or authentication fails
        """
        if user_token:
            return await self.resolve_user_by_token(user_token)

        if device_token:
            return await self.resolve_device_by_token(
                device_id=device_id,
                device_token=device_token,
                client_ip=client_ip,
                client_version=client_version,
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication tokens provided",
        )

    async def resolve_service_identity(
        self,
        service_token: str,
    ) -> Identity:
        """
        Resolve identity for service-to-service authentication.
        This is the legacy path that will be replaced by token-based auth.

        Args:
            service_token: Service token from Authorization header

        Returns:
            Identity object representing service context

        Raises:
            HTTPException: if service token invalid
        """
        # This is a legacy method that simulates the old service auth
        # In the new model, services should use user tokens or device tokens
        # This is kept for backward compatibility during transition

        from app.core.config import get_settings
        settings = get_settings()

        if not settings.SYNC_SERVER_SERVICE_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Service authentication not configured",
            )

        if service_token != settings.SYNC_SERVER_SERVICE_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid service token",
            )

        # Service identity doesn't have a specific user
        # This is a placeholder that represents "system" identity
        # In production, you might want to create a system user

        # For now, return a minimal identity that represents system access
        # This should only be used for legacy compatibility

        from app.models.user import User
        from uuid import uuid4

        # Create a minimal system user representation
        system_user = User(
            id=uuid4(),
            username="system",
            email=None,
            full_name="System",
            user_token=uuid4(),
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=None,
        )

        return Identity.from_user_and_device(
            user=system_user,
            device=None,
            scopes=[],
        )

    async def validate_identity_for_site(
        self,
        identity: Identity,
        site_id: int,
        *,
        require_can_view: bool = True,
        require_can_operate: bool = False,
        require_can_manage_catalog: bool = False,
    ) -> bool:
        """
        Validate that identity has required permissions for a site.

        Args:
            identity: Identity to validate
            site_id: Site ID to check access for
            require_can_view: Require view permission
            require_can_operate: Require operate permission
            require_can_manage_catalog: Require catalog management permission
        Returns:
            True if identity has required permissions
        """
        if identity.is_root:
            return True

        if not identity.has_site_access(site_id):
            return False
        
        if require_can_operate and not identity.can_operate_at_site(site_id):
            return False

        if (require_can_manage_catalog and
            not identity.can_manage_catalog_at_site(site_id)):
            return False

        return True

    async def resolve_legacy_acting_user(
        self,
        acting_user_id: int,
        acting_site_id: int,
    ) -> Identity:
        """
        LEGACY: Resolve identity from legacy acting user/site IDs.
        This is for backward compatibility during transition.

        Args:
            acting_user_id: Legacy integer user ID
            acting_site_id: Legacy integer site ID

        Returns:
            Identity object

        Raises:
            HTTPException: if user not found or no access to site
        """
        # First, we need to find the user by legacy integer ID
        # Since new User model uses UUID, we need a mapping or alternative

        # This is a complex problem because:
        # 1. Old user_id is integer, new User.id is UUID
        # 2. We need to map between them or find another way

        # For Phase 2, we'll implement a simplified version that
        # demonstrates the concept but may not work in production

        # Option 1: Search users by some other field (username, email)
        # Option 2: Maintain a mapping table
        # Option 3: Migrate all data to new UUID format

        # For now, we'll raise an error indicating this needs implementation
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Legacy acting user resolution not implemented. "
                   "Need to implement mapping between integer user_id and UUID.",
        )
