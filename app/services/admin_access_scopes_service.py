from __future__ import annotations

from fastapi import HTTPException, status

from app.services.admin_users_service import AdminUsersService, require_target_user_not_root
from app.services.uow import UnitOfWork


class AdminAccessScopesService:
    @staticmethod
    async def list_scopes(
        uow: UnitOfWork,
        *,
        user_id,
        site_id: int | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> list:
        return list(
            await uow.user_access_scopes.list_all_scopes(
                user_id=user_id,
                site_id=site_id,
                is_active=is_active,
                limit=limit,
                offset=offset,
            )
        )

    @staticmethod
    async def create_scope(uow: UnitOfWork, *, payload):
        user = await AdminUsersService.get_user_required(uow, payload.user_id)
        require_target_user_not_root(user, detail="cannot create scopes for root users")

        site = await uow.sites.get_by_id(payload.site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

        existing = await uow.user_access_scopes.get_any_by_user_and_site(payload.user_id, payload.site_id)
        if existing:
            existing.can_view = payload.can_view
            existing.can_operate = payload.can_operate
            existing.can_manage_catalog = payload.can_manage_catalog
            existing.is_active = payload.is_active
            await uow.session.flush()
            await uow.session.refresh(existing)
            return existing

        return await uow.user_access_scopes.create_scope(
            user_id=payload.user_id,
            site_id=payload.site_id,
            can_view=payload.can_view,
            can_operate=payload.can_operate,
            can_manage_catalog=payload.can_manage_catalog,
            is_active=payload.is_active,
        )

    @staticmethod
    async def update_scope(uow: UnitOfWork, *, scope_id: int, payload):
        scope = await uow.user_access_scopes.update_scope(
            scope_id=scope_id,
            can_view=payload.can_view,
            can_operate=payload.can_operate,
            can_manage_catalog=payload.can_manage_catalog,
            is_active=payload.is_active,
        )
        if not scope:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scope not found")
        return scope
