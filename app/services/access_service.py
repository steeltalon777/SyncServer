from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.user_site_role import UserSiteRole
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
    """Domain access and permission service."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def validate_acting_user(self, acting_user_id: int) -> None:
        user = await self.uow.users.get(acting_user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acting user is not registered or inactive",
            )

    async def validate_root_permission(self, acting_user_id: int) -> None:
        await self.validate_acting_user(acting_user_id)

        accesses = await self.uow.user_site_roles.get_sites_for_user(acting_user_id)
        if not any(access.role == ROLE_ROOT for access in accesses):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Root permission required",
            )

    async def get_user_site_role(
        self,
        user_id: int,
        site_id: UUID,
    ) -> str | None:
        access = await self.uow.user_site_roles.get_by_user_and_site(user_id, site_id)
        if access is None:
            return None
        return access.role

    async def has_site_role(
        self,
        user_id: int,
        site_id: UUID,
        role: str,
    ) -> bool:
        current_role = await self.get_user_site_role(user_id, site_id)
        return current_role == role

    async def has_minimum_site_role(
        self,
        user_id: int,
        site_id: UUID,
        minimum_role: str,
    ) -> bool:
        current_role = await self.get_user_site_role(user_id, site_id)
        if current_role is None:
            return False

        current_priority = ROLE_PRIORITY.get(current_role, 0)
        minimum_priority = ROLE_PRIORITY.get(minimum_role, 0)
        return current_priority >= minimum_priority

    async def can_read_site(self, user_id: int, site_id: UUID) -> bool:
        role = await self.get_user_site_role(user_id, site_id)
        return role in {
            ROLE_ROOT,
            ROLE_CHIEF_STOREKEEPER,
            ROLE_STOREKEEPER,
            ROLE_OBSERVER,
        }

    async def can_create_operations(self, user_id: int, site_id: UUID) -> bool:
        role = await self.get_user_site_role(user_id, site_id)
        return role in {
            ROLE_ROOT,
            ROLE_CHIEF_STOREKEEPER,
            ROLE_STOREKEEPER,
        }

    async def can_manage_catalog(self, user_id: int, site_id: UUID | None = None) -> bool:
        accesses = await self.uow.user_site_roles.get_sites_for_user(user_id)

        if site_id is None:
            return any(
                access.role in {ROLE_ROOT, ROLE_CHIEF_STOREKEEPER}
                for access in accesses
            )

        return any(
            access.site_id == site_id
            and access.role in {ROLE_ROOT, ROLE_CHIEF_STOREKEEPER}
            for access in accesses
        )

    async def can_manage_root_admin(self, user_id: int) -> bool:
        accesses = await self.uow.user_site_roles.get_sites_for_user(user_id)
        return any(access.role == ROLE_ROOT for access in accesses)

    async def list_user_access_entries(self, acting_user_id: int) -> list[UserSiteRole]:
        await self.validate_root_permission(acting_user_id)
        return await self.uow.user_site_roles.list_access_entries()

    async def create_user_site_access(
        self,
        acting_user_id: int,
        payload: UserSiteAccessCreate,
    ) -> UserSiteRole:
        await self.validate_root_permission(acting_user_id)

        user = await self.uow.users.get(payload.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {payload.user_id} not found",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User {payload.user_id} is inactive",
            )

        site = await self.uow.sites.get_by_id(payload.site_id)
        if site is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )

        existing = await self.uow.user_site_roles.get_by_user_and_site(
            payload.user_id,
            payload.site_id,
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Access for this user and site already exists",
            )

        return await self.uow.user_site_roles.create(
            user_id=payload.user_id,
            site_id=payload.site_id,
            role=payload.role,
        )

    async def update_user_site_access(
        self,
        acting_user_id: int,
        access_id: int,
        payload: UserSiteAccessUpdate,
    ) -> UserSiteRole:
        await self.validate_root_permission(acting_user_id)

        access = await self.uow.user_site_roles.get_by_id(access_id)
        if access is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Access entry not found",
            )

        if payload.role is not None:
            access.role = payload.role

        if payload.is_active is not None:
            access.is_active = payload.is_active

        await self.uow.session.flush()
        return access

    async def get_user_permissions(
        self,
        user_id: int,
        site_id: UUID,
    ) -> dict[str, bool]:
        role = await self.get_user_site_role(user_id, site_id)

        if role is None:
            return {
                "can_read_operations": False,
                "can_create_operations": False,
                "can_read_balances": False,
                "can_manage_catalog": False,
                "can_manage_root_admin": False,
            }

        if role == ROLE_ROOT:
            return {
                "can_read_operations": True,
                "can_create_operations": True,
                "can_read_balances": True,
                "can_manage_catalog": True,
                "can_manage_root_admin": True,
            }

        if role == ROLE_CHIEF_STOREKEEPER:
            return {
                "can_read_operations": True,
                "can_create_operations": True,
                "can_read_balances": True,
                "can_manage_catalog": True,
                "can_manage_root_admin": False,
            }

        if role == ROLE_STOREKEEPER:
            return {
                "can_read_operations": True,
                "can_create_operations": True,
                "can_read_balances": True,
                "can_manage_catalog": False,
                "can_manage_root_admin": False,
            }

        if role == ROLE_OBSERVER:
            return {
                "can_read_operations": True,
                "can_create_operations": False,
                "can_read_balances": True,
                "can_manage_catalog": False,
                "can_manage_root_admin": False,
            }

        return {
            "can_read_operations": False,
            "can_create_operations": False,
            "can_read_balances": False,
            "can_manage_catalog": False,
            "can_manage_root_admin": False,
        }