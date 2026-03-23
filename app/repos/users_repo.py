from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UsersRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_required(self, user_id: UUID) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError(f"user {user_id} not found")
        return user

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_token(self, user_token: UUID) -> User | None:
        stmt = select(User).where(User.user_token == user_token)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_root_user(self) -> User | None:
        stmt = select(User).where(User.is_root == True).where(User.is_active == True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    async def list_users(
        self,
        *,
        is_active: bool | None = None,
        is_root: bool | None = None,
        role: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[User]:
        stmt: Select[tuple[User]] = select(User).order_by(User.username)
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        if is_root is not None:
            stmt = stmt.where(User.is_root == is_root)

        if role is not None:
            stmt = stmt.where(User.role == role)

        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_user(
        self,
        *,
        username: str,
        email: str | None = None,
        full_name: str | None = None,
        is_active: bool = True,
        is_root: bool = False,
        role: str = "observer",
        default_site_id: int | None = None,
    ) -> User:
        user = User(
                username=username,
                email=email,
                full_name=full_name,
                is_active=is_active,
            is_root=is_root,
            role=role,
            default_site_id=default_site_id,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def update_user(
        self,
        user_id: UUID,
        *,
        username: str | None = None,
        email: str | None = None,
        full_name: str | None = None,
        is_active: bool | None = None,
        is_root: bool | None = None,
        role: str | None = None,
        default_site_id: int | None = None,
    ) -> User:
        user = await self.get_required(user_id)

        if username is not None:
            user.username = username

        if email is not None:
            user.email = email

        if full_name is not None:
            user.full_name = full_name

        if is_active is not None:
            user.is_active = is_active

        if is_root is not None:
            user.is_root = is_root

        if role is not None:
            user.role = role

        if default_site_id is not None:
            user.default_site_id = default_site_id

        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def soft_delete_user(self, user_id: UUID) -> User:
        """Soft delete user by setting is_active=False."""
        user = await self.get_required(user_id)
        user.is_active = False
        await self.session.flush()
        await self.session.refresh(user)
        return user

