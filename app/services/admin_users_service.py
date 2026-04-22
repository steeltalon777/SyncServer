from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.models.user import User
from app.schemas.admin import (
    UserAccessScopeReplaceRequest,
    UserCreate,
    UserUpdate,
)
from app.services.uow import UnitOfWork


def require_root(identity) -> None:
    if not identity.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="root permissions required",
        )


def require_target_user_not_root(user: User, *, detail: str) -> None:
    if user.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


def validate_user_role_payload(*, role: str, is_root: bool) -> None:
    if is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin api cannot create or update root users",
        )
    if role == "root":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="role 'root' requires is_root=true and is managed outside admin api",
        )


async def validate_default_site(uow: UnitOfWork, default_site_id: int | None) -> None:
    if default_site_id is None:
        return

    site = await uow.sites.get_by_id(default_site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="default site not found")


class AdminUsersService:
    @staticmethod
    def paginate(items: list, page: int, page_size: int) -> tuple[list, int]:
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    @staticmethod
    async def list_users(
        uow: UnitOfWork,
        *,
        is_active: bool | None,
        is_root: bool | None,
        role: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[User], int]:
        users = list(
            await uow.users.list_users(
                is_active=is_active,
                is_root=is_root,
                role=role,
                limit=10000,
                offset=0,
            )
        )

        if search:
            needle = search.lower()
            users = [
                user
                for user in users
                if needle in user.username.lower()
                or (user.email and needle in user.email.lower())
                or (user.full_name and needle in user.full_name.lower())
            ]

        return AdminUsersService.paginate(users, page, page_size)

    @staticmethod
    async def get_user_required(uow: UnitOfWork, user_id: UUID) -> User:
        user = await uow.users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        return user

    @staticmethod
    async def create_user(
        uow: UnitOfWork,
        *,
        payload: UserCreate,
    ) -> User:
        validate_user_role_payload(role=payload.role, is_root=payload.is_root)
        await validate_default_site(uow, payload.default_site_id)

        if payload.id is not None:
            exists_by_id = await uow.users.get_by_id(payload.id)
            if exists_by_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user id already exists")

        exists_by_username = await uow.users.get_by_username(payload.username)
        if exists_by_username:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

        user = User(
            id=payload.id or uuid4(),
            username=payload.username,
            email=payload.email,
            full_name=payload.full_name,
            is_active=payload.is_active,
            is_root=payload.is_root,
            role=payload.role,
            default_site_id=payload.default_site_id,
        )
        uow.session.add(user)
        await uow.session.flush()
        await uow.session.refresh(user)
        return user

    @staticmethod
    async def update_user(
        uow: UnitOfWork,
        *,
        user_id: UUID,
        payload: UserUpdate,
    ) -> User:
        user = await AdminUsersService.get_user_required(uow, user_id)
        require_target_user_not_root(user, detail="admin api cannot update root users")

        if payload.username is not None and payload.username != user.username:
            exists_by_username = await uow.users.get_by_username(payload.username)
            if exists_by_username and exists_by_username.id != user.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

        next_is_root = payload.is_root if payload.is_root is not None else user.is_root
        next_role = payload.role if payload.role is not None else user.role
        validate_user_role_payload(role=next_role, is_root=next_is_root)

        default_site_id = payload.default_site_id if "default_site_id" in payload.model_fields_set else user.default_site_id
        await validate_default_site(uow, default_site_id)

        if payload.username is not None:
            user.username = payload.username
        if payload.email is not None:
            user.email = payload.email
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.is_active is not None:
            user.is_active = payload.is_active
        if payload.is_root is not None:
            user.is_root = payload.is_root
        if payload.role is not None:
            user.role = payload.role
        if "default_site_id" in payload.model_fields_set:
            user.default_site_id = payload.default_site_id

        await uow.session.flush()
        await uow.session.refresh(user)
        return user

    @staticmethod
    async def delete_user(
        uow: UnitOfWork,
        *,
        user_id: UUID,
        actor_user_id: UUID | None,
    ) -> User:
        user = await AdminUsersService.get_user_required(uow, user_id)
        if user.is_root and user.id == actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot deactivate current root user",
            )
        require_target_user_not_root(user, detail="admin api cannot deactivate root users")

        user.is_active = False
        await uow.session.flush()
        await uow.session.refresh(user)
        return user

    @staticmethod
    async def get_user_sync_state(
        uow: UnitOfWork,
        *,
        user_id: UUID,
    ) -> tuple[User, list]:
        user = await AdminUsersService.get_user_required(uow, user_id)
        scopes = list(await uow.user_access_scopes.list_user_scopes(user.id))
        return user, scopes

    @staticmethod
    async def replace_user_scopes(
        uow: UnitOfWork,
        *,
        user_id: UUID,
        payload: UserAccessScopeReplaceRequest,
    ) -> list:
        user = await AdminUsersService.get_user_required(uow, user_id)
        require_target_user_not_root(user, detail="cannot replace scopes for root users")

        seen_site_ids: set[int] = set()
        scopes_payload = []
        for scope in payload.scopes:
            if scope.site_id in seen_site_ids:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="duplicate site_id in scopes payload",
                )
            seen_site_ids.add(scope.site_id)

            site = await uow.sites.get_by_id(scope.site_id)
            if not site:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

            scopes_payload.append(
                {
                    "site_id": scope.site_id,
                    "can_view": scope.can_view,
                    "can_operate": scope.can_operate,
                    "can_manage_catalog": scope.can_manage_catalog,
                }
            )

        return await uow.user_access_scopes.replace_user_scopes(user.id, scopes_payload)

    @staticmethod
    async def rotate_user_token(
        uow: UnitOfWork,
        *,
        user_id: UUID,
    ) -> tuple[User, datetime]:
        user = await AdminUsersService.get_user_required(uow, user_id)
        require_target_user_not_root(user, detail="root token rotation is not allowed via API")

        user.user_token = uuid4()
        await uow.session.flush()
        await uow.session.refresh(user)
        return user, datetime.now(UTC)
