from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UsersRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_required(self, user_id: int) -> User:
        user = await self.get(user_id)
        if user is None:
            raise ValueError(f"user {user_id} not found")
        return user

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        is_active: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[User]:
        stmt: Select[tuple[User]] = select(User).order_by(User.id)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)

        stmt = stmt.offset(offset).limit(limit)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(
        self,
        *,
        user_id: int,
        username: str,
        email: str | None = None,
        full_name: str | None = None,
        is_active: bool = True,
    ) -> User:
        user = User(
            id=user_id,
            username=username,
            email=email,
            full_name=full_name,
            is_active=is_active,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(
            self,
            user_id: int,
            *,
            username: str | None = None,
            email: str | None = None,
            full_name: str | None = None,
            is_active: bool | None = None,
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

        await self.session.flush()
        await self.session.refresh(user)  # ← ВОТ ЭТО ДОБАВИТЬ

        return user

    async def upsert(
        self,
        *,
        user_id: int,
        username: str,
        email: str | None = None,
        full_name: str | None = None,
        is_active: bool = True,
    ) -> User:
        existing = await self.get(user_id)
        if existing is None:
            return await self.create(
                user_id=user_id,
                username=username,
                email=email,
                full_name=full_name,
                is_active=is_active,
            )

        existing.username = username
        existing.email = email
        existing.full_name = full_name
        existing.is_active = is_active

        await self.session.flush()
        return existing