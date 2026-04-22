from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.core.identity import Identity
from app.services.uow import UnitOfWork


class IdentityService:
    """Service for resolvinging and validating identities from tokens."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    @staticmethod
    def _parse_uuid_token(value: UUID | str | None, header_name: str) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid {header_name}",
            ) from None

    async def resolve_identity(
        self,
        *,
        user_token: UUID | str | None = None,
        device_token: UUID | str | None = None,
        require_user: bool = False,
        require_device: bool = False,
        client_ip: str | None = None,
        client_version: str | None = None,
    ) -> Identity:
        """
        Resolve identity from available tokens.

        Args:
            user_token: Optional X-User-Token value
            device_token: Optional X-Device-Token value
            require_user: If True, X-User-Token must be present and valid
            require_device: If True, X-Device-Token must be present and valid
            client_ip: Client IP for device last_seen update
            client_version: Client version for device last_seen update

        Returns:
            Unified Identity object

        Raises:
            HTTPException: 401 if tokens missing/invalid, 403 if inactive
        """
        user = None
        device = None
        scopes: list = []
        parsed_user_token = self._parse_uuid_token(user_token, "X-User-Token")
        parsed_device_token = self._parse_uuid_token(device_token, "X-Device-Token")

        # --- User token resolution ---
        if parsed_user_token is not None:
            user = await self.uow.users.get_by_user_token(parsed_user_token)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid X-User-Token",
                )
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is inactive",
                )
            scopes = list(await self.uow.user_access_scopes.list_user_scopes(user.id))

        # --- Device token resolution ---
        if parsed_device_token is not None:
            device = await self.uow.devices.get_by_device_token(parsed_device_token)
            if not device:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="invalid X-Device-Token",
                )
            if not device.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Device is inactive",
                )
            await self.uow.devices.update_last_seen(
                device_id=device.id,
                ip=client_ip,
                client_version=client_version,
            )

        # --- Requirement checks ---
        if require_user and user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-User-Token is required",
            )

        if require_device and device is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Device-Token is required",
            )

        # --- At least one token must be provided ---
        if user is None and device is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No authentication tokens provided",
            )

        return Identity(
            user=user,
            device=device,
            scopes=scopes,
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
