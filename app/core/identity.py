from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User
    from app.models.user_access_scope import UserAccessScope


@dataclass
class Identity:
    """
    Unified identity for all authenticated requests.

    - user: real User or None (device-only auth)
    - device: Device or None
    - principal_kind: which tokens were successfully validated
    - scopes: user access scopes (empty for device-only)
    """
    user: User | None
    device: Device | None
    scopes: list[UserAccessScope] = field(default_factory=list)

    @property
    def principal_kind(self) -> str:
        if self.user is not None and self.device is not None:
            return "user_device"
        if self.user is not None:
            return "user"
        if self.device is not None:
            return "device"
        return "none"

    @property
    def is_root(self) -> bool:
        return self.user.is_root if self.user else False

    @property
    def role(self) -> str | None:
        return self.user.role if self.user else None

    @property
    def default_site_id(self) -> int | None:
        if self.user and self.user.default_site_id is not None:
            return self.user.default_site_id
        if self.device:
            return self.device.site_id
        return None

    @property
    def user_id(self) -> UUID | None:
        return self.user.id if self.user else None

    @property
    def username(self) -> str | None:
        return self.user.username if self.user else None

    @property
    def device_id(self) -> int | None:
        return self.device.id if self.device else None

    @property
    def device_site_id(self) -> int | None:
        return self.device.site_id if self.device else None

    @property
    def has_global_business_access(self) -> bool:
        """Business-supervisor access across all sites."""
        return self.is_root or self.role == "chief_storekeeper"

    def has_site_access(self, site_id: int) -> bool:
        """Check if identity has access to a specific site."""
        if self.has_global_business_access:
            return True

        for scope in self.scopes:
            if scope.site_id == site_id and scope.is_active and scope.can_view:
                return True

        return False

    def can_operate_at_site(self, site_id: int) -> bool:
        """Check if identity can perform operations at a specific site."""
        if self.has_global_business_access:
            return True

        for scope in self.scopes:
            if scope.site_id == site_id and scope.is_active and scope.can_view and scope.can_operate:
                return True

        return False

    def can_manage_catalog_at_site(self, site_id: int) -> bool:
        """Check if identity can manage catalog at a specific site."""
        if self.has_global_business_access:
            return True

        for scope in self.scopes:
            if (scope.site_id == site_id and scope.is_active and
                scope.can_view and scope.can_operate and scope.can_manage_catalog):
                return True

        return False

    def get_accessible_site_ids(self) -> list[int]:
        """Get list of site IDs accessible by this identity."""
        if self.has_global_business_access:
            return []

        return [scope.site_id for scope in self.scopes
                if scope.is_active and scope.can_view]
