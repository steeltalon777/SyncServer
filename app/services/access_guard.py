from fastapi import HTTPException, status

from app.services.access_service import AccessService


class AccessGuard:

    @staticmethod
    async def require_role(access_service, user_id, site_id, allowed_roles: list[str]):
        role = await access_service.get_user_role(user_id, site_id)

        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"required roles: {allowed_roles}",
            )

    @staticmethod
    async def require_storekeeper(access_service, user_id, site_id):
        await AccessGuard.require_role(
            access_service,
            user_id,
            site_id,
            ["root", "chief_storekeeper", "storekeeper"],
        )

    @staticmethod
    async def require_catalog_admin(access_service, user_id, site_id):
        await AccessGuard.require_role(
            access_service,
            user_id,
            site_id,
            ["root", "chief_storekeeper"],
        )

    @staticmethod
    async def require_root(access_service, user_id):
        allowed = await access_service.can_manage_root_admin(user_id)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="root permission required",
            )