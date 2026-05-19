"""
Tests for bootstrap_root.py and rotate_tokens.py scripts.

These are script-level integration tests using the standard test DB fixtures.
They verify idempotency, token creation, and explicit rotation behaviour.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE
from app.models.category import Category
from app.models.device import Device
from app.models.user import User
from scripts.bootstrap_root import (
    DJANGO_DEVICE_CODE,
    ROOT_USERNAME,
    bootstrap_data,
)
from scripts.rotate_tokens import (
    rotate_django_device_token_in_session,
    rotate_root_token_in_session,
)


async def _count_uncategorized(session: AsyncSession) -> int:
    result = await session.execute(
        select(Category).where(Category.code == UNCATEGORIZED_CATEGORY_CODE)
    )
    return len(list(result.scalars().all()))


async def _get_root(session: AsyncSession) -> User | None:
    result = await session.execute(
        select(User).where(User.username == ROOT_USERNAME)
    )
    return result.scalar_one_or_none()


async def _get_django_device(session: AsyncSession) -> Device | None:
    result = await session.execute(
        select(Device).where(Device.device_code == DJANGO_DEVICE_CODE)
    )
    return result.scalar_one_or_none()


async def _get_other_users(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User).where(User.username != ROOT_USERNAME)
    )
    return list(result.scalars().all())


async def _get_other_devices(session: AsyncSession) -> list[Device]:
    result = await session.execute(
        select(Device).where(Device.device_code != DJANGO_DEVICE_CODE)
    )
    return list(result.scalars().all())


class TestBootstrapFirstRun:
    """First bootstrap run should create root user, Django device, uncategorized category."""

    async def test_creates_root_user(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        root = await _get_root(db_session)
        assert root is not None
        assert root.username == ROOT_USERNAME
        assert root.is_root is True
        assert root.role == "root"
        assert root.is_active is True
        assert root.user_token is not None

    async def test_creates_django_device(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        device = await _get_django_device(db_session)
        assert device is not None
        assert device.device_code == DJANGO_DEVICE_CODE
        assert device.is_active is True
        assert device.device_token is not None

    async def test_creates_uncategorized_category(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        count = await _count_uncategorized(db_session)
        assert count == 1

    async def test_root_user_correct_role(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        root = await _get_root(db_session)
        assert root.role == "root"
        assert root.is_root is True

    async def test_django_device_no_site(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        device = await _get_django_device(db_session)
        assert device.site_id is None


class TestBootstrapIdempotent:
    """Second bootstrap run must not create duplicates or change tokens."""

    async def test_no_duplicate_root(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        await bootstrap_data(db_session)
        await db_session.commit()
        roots = list(
            (await db_session.execute(select(User).where(User.username == ROOT_USERNAME)))
            .scalars()
            .all()
        )
        assert len(roots) == 1

    async def test_no_duplicate_device(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        await bootstrap_data(db_session)
        await db_session.commit()
        devices = list(
            (await db_session.execute(select(Device).where(Device.device_code == DJANGO_DEVICE_CODE)))
            .scalars()
            .all()
        )
        assert len(devices) == 1

    async def test_no_duplicate_category(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        await bootstrap_data(db_session)
        await db_session.commit()
        count = await _count_uncategorized(db_session)
        assert count == 1

    async def test_root_token_unchanged(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        first_root = await _get_root(db_session)
        first_token = first_root.user_token
        await bootstrap_data(db_session)
        await db_session.commit()
        second_root = await _get_root(db_session)
        assert second_root.user_token == first_token

    async def test_device_token_unchanged(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        first_device = await _get_django_device(db_session)
        first_token = first_device.device_token
        await bootstrap_data(db_session)
        await db_session.commit()
        second_device = await _get_django_device(db_session)
        assert second_device.device_token == first_token


class TestRotation:
    """Explicit token rotation must change only the target token."""

    async def test_root_rotation_changes_token(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        root = await _get_root(db_session)
        old_token = root.user_token
        old_token_str = str(old_token)
        rotated_old, rotated_new = await rotate_root_token_in_session(db_session)
        await db_session.commit()
        assert str(rotated_old) == old_token_str
        assert str(rotated_new) != old_token_str
        fresh_root = await _get_root(db_session)
        assert str(fresh_root.user_token) == str(rotated_new)

    async def test_root_rotation_does_not_affect_device(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        device = await _get_django_device(db_session)
        device_token_before = device.device_token
        await rotate_root_token_in_session(db_session)
        await db_session.commit()
        device_after = await _get_django_device(db_session)
        assert device_after.device_token == device_token_before

    async def test_root_rotation_does_not_affect_other_users(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        other_before = await _get_other_users(db_session)
        await rotate_root_token_in_session(db_session)
        await db_session.commit()
        other_after = await _get_other_users(db_session)
        assert len(other_before) == len(other_after)

    async def test_device_rotation_changes_token(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        device = await _get_django_device(db_session)
        old_token = device.device_token
        rotated_old, rotated_new = await rotate_django_device_token_in_session(db_session)
        await db_session.commit()
        assert str(rotated_old) == str(old_token)
        assert str(rotated_new) != str(old_token)
        fresh_device = await _get_django_device(db_session)
        assert str(fresh_device.device_token) == str(rotated_new)

    async def test_device_rotation_does_not_affect_root(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        root = await _get_root(db_session)
        root_token_before = root.user_token
        await rotate_django_device_token_in_session(db_session)
        await db_session.commit()
        root_after = await _get_root(db_session)
        assert root_after.user_token == root_token_before

    async def test_device_rotation_does_not_affect_other_devices(self, db_session: AsyncSession) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        other_before = await _get_other_devices(db_session)
        await rotate_django_device_token_in_session(db_session)
        await db_session.commit()
        other_after = await _get_other_devices(db_session)
        assert len(other_before) == len(other_after)

    async def test_root_rotation_old_token_no_longer_authenticates(
        self, db_session: AsyncSession, client: AsyncClient
    ) -> None:
        await bootstrap_data(db_session)
        await db_session.commit()
        root = await _get_root(db_session)
        old_token = str(root.user_token)
        await rotate_root_token_in_session(db_session)
        await db_session.commit()
        new_root = await _get_root(db_session)
        new_token = str(new_root.user_token)

        old_headers = {"X-User-Token": old_token}
        old_resp = await client.get("/api/v1/admin/sites", headers=old_headers)
        assert old_resp.status_code == 401

        new_headers = {"X-User-Token": new_token}
        new_resp = await client.get("/api/v1/admin/sites", headers=new_headers)
        assert new_resp.status_code == 200
