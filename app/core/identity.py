from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.models.device import Device
    from app.models.user import User
    from app.models.user_access_scope import UserAccessScope


@dataclass
class Identity:
    """
    Represents the authenticated identity of a request.
    Contains user, device, and access information.
    """
    user: User
    device: Device | None
    is_root: bool
    role: str
    default_site_id: int | None
    _scopes: list[UserAccessScope] | None = None
    
    @property
    def user_id(self) -> UUID:
        """Get user UUID."""
        return self.user.id
    
    @property
    def username(self) -> str:
        """Get username."""
        return self.user.username
    
    @property
    def user_token(self) -> UUID:
        """Get user token."""
        return self.user.user_token
    
    @property
    def device_id(self) -> UUID | None:
        """Get device UUID if available."""
        return self.device.id if self.device else None
    
    @property
    def site_id(self) -> int | None:
        """Get current site ID from device if available."""
        return self.device.site_id if self.device else None

    @property
    def has_global_business_access(self) -> bool:
        """Business-supervisor access across all sites."""
        return self.is_root or self.role == "chief_storekeeper"
    
    def has_site_access(self, site_id: int) -> bool:
        """Check if identity has access to a specific site."""
        if self.has_global_business_access:
            return True
        
        if not self._scopes:
            return False
        
        for scope in self._scopes:
            if scope.site_id == site_id and scope.is_active and scope.can_view:
                return True
        
        return False
    
    def can_operate_at_site(self, site_id: int) -> bool:
        """Check if identity can perform operations at a specific site."""
        if self.has_global_business_access:
            return True
        
        if not self._scopes:
            return False
        
        for scope in self._scopes:
            if scope.site_id == site_id and scope.is_active and scope.can_view and scope.can_operate:
                return True
        
        return False
    
    def can_manage_catalog_at_site(self, site_id: int) -> bool:
        """Check if identity can manage catalog at a specific site."""
        if self.has_global_business_access:
            return True
        
        if not self._scopes:
            return False
        
        for scope in self._scopes:
            if (scope.site_id == site_id and scope.is_active and 
                scope.can_view and scope.can_operate and scope.can_manage_catalog):
                return True
        
        return False
    
    def get_accessible_site_ids(self) -> list[int]:
        """Get list of site IDs accessible by this identity."""
        if self.has_global_business_access:
            # Global business users have access to all sites.
            # This should be resolved lazily when needed
            return []
        
        if not self._scopes:
            return []
        
        return [scope.site_id for scope in self._scopes 
                if scope.is_active and scope.can_view]
    
    @classmethod
    def from_user_and_device(
        cls,
        user: User,
        device: Device | None,
        scopes: list[UserAccessScope] | None = None,
    ) -> Identity:
        """Create Identity from user and device."""
        return cls(
            user=user,
            device=device,
            is_root=user.is_root,
            role=user.role,
            default_site_id=user.default_site_id,
            _scopes=scopes,
        )
