#!/usr/bin/env python3
"""
Bootstrap script for SyncServer.

Creates:
- Database tables (if not exist)
- Root user (username='root') with UUID id and user_token
- Django device (device_code='DJANGO_WEB') with device_token
- Technical internal site (code='SYSTEM') for root access assignment (temporary workaround)
- Root access record (UserSiteRole) linking root user to internal site with role='root'

Idempotent: safe to run multiple times.
"""

import asyncio
import uuid
from uuid import UUID

from sqlalchemy import select

from app.core.db import SessionFactory, engine
from app.models import Base
from app.models.user import User
from app.models.device import Device
from app.models.site import Site
from app.models.user_site_role import UserSiteRole

# Constants
ROOT_USERNAME = "root"
ROOT_EMAIL = "root@local"
ROOT_FULL_NAME = "System Root"

DJANGO_DEVICE_CODE = "DJANGO_WEB"
DJANGO_DEVICE_NAME = "Django Web Client"

INTERNAL_SITE_CODE = "SYSTEM"
INTERNAL_SITE_NAME = "System Internal (technical)"


async def bootstrap() -> None:
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionFactory() as session:
        # ---- 1. Technical internal site (workaround for root access) ----
        result = await session.execute(
            select(Site).where(Site.code == INTERNAL_SITE_CODE)
        )
        internal_site = result.scalar_one_or_none()
        if internal_site is None:
            print(f"Creating internal technical site '{INTERNAL_SITE_CODE}'...")
            internal_site = Site(
                code=INTERNAL_SITE_CODE,
                name=INTERNAL_SITE_NAME,
                is_active=True,
            )
            session.add(internal_site)
            await session.flush()
        else:
            print(f"Internal site '{INTERNAL_SITE_CODE}' already exists.")
            # Обновим имя на случай изменения
            if internal_site.name != INTERNAL_SITE_NAME:
                internal_site.name = INTERNAL_SITE_NAME
            if not internal_site.is_active:
                internal_site.is_active = True
            await session.flush()

        # ---- 2. Root user ----
        result = await session.execute(
            select(User).where(User.username == ROOT_USERNAME)
        )
        root_user = result.scalar_one_or_none()

        if root_user is None:
            print("Creating root user...")
            root_user = User(
                id=uuid.uuid4(),
                username=ROOT_USERNAME,
                email=ROOT_EMAIL,
                full_name=ROOT_FULL_NAME,
                user_token=uuid.uuid4(),
                is_active=True,
            )
            session.add(root_user)
            await session.flush()
        else:
            print("Root user already exists. Updating if needed...")
            # Обновляем стандартные поля
            root_user.email = ROOT_EMAIL
            root_user.full_name = ROOT_FULL_NAME
            if not root_user.is_active:
                root_user.is_active = True
            # Если у пользователя нет токена (старая запись) – генерируем
            if root_user.user_token is None:
                print("  Generating missing user_token...")
                root_user.user_token = uuid.uuid4()
            await session.flush()

        # ---- 3. Django device ----
        result = await session.execute(
            select(Device).where(Device.device_code == DJANGO_DEVICE_CODE)
        )
        django_device = result.scalar_one_or_none()

        if django_device is None:
            print("Creating Django device...")
            django_device = Device(
                device_code=DJANGO_DEVICE_CODE,
                device_name=DJANGO_DEVICE_NAME,
                device_token=uuid.uuid4(),
                site_id=None,          # не привязан к складу
                is_active=True,
            )
            session.add(django_device)
            await session.flush()
        else:
            print("Django device already exists. Updating if needed...")
            django_device.device_name = DJANGO_DEVICE_NAME
            if not django_device.is_active:
                django_device.is_active = True
            if django_device.device_token is None:
                print("  Generating missing device_token...")
                django_device.device_token = uuid.uuid4()
            # Если site_id был установлен, можно сбросить в None (опционально)
            # Но оставим как есть, чтобы не ломать возможные привязки.
            await session.flush()

        # ---- 4. Root access (UserSiteRole) ----
        # Привязываем root пользователя к внутреннему сайту с ролью 'root'
        result = await session.execute(
            select(UserSiteRole).where(
                UserSiteRole.user_id == root_user.id,
                UserSiteRole.site_id == internal_site.id,
            )
        )
        root_access = result.scalar_one_or_none()

        if root_access is None:
            print("Creating root access record...")
            root_access = UserSiteRole(
                user_id=root_user.id,
                site_id=internal_site.id,
                role="root",
                is_active=True,
            )
            session.add(root_access)
            await session.flush()
        else:
            print("Root access already exists. Updating if needed...")
            if root_access.role != "root":
                root_access.role = "root"
            if not root_access.is_active:
                root_access.is_active = True
            await session.flush()

        await session.commit()

        # ---- 5. Output ----
        print("\n" + "=" * 60)
        print("BOOTSTRAP COMPLETE")
        print("=" * 60)
        print("Root user:")
        print(f"  id:       {root_user.id}")
        print(f"  username: {root_user.username}")
        print(f"  token:    {root_user.user_token}")
        print()
        print("Django device:")
        print(f"  id:       {django_device.id}")
        print(f"  code:     {django_device.device_code}")
        print(f"  token:    {django_device.device_token}")
        print()
        print("Recommended Django .env entries:")
        print(f"SYNC_USER_TOKEN={root_user.user_token}")
        print(f"SYNC_DEVICE_TOKEN={django_device.device_token}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(bootstrap())