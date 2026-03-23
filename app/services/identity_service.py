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

        # Device-token auth yields a device principal for sync flows.
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
