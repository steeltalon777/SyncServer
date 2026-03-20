import asyncio
import uuid

from sqlalchemy import select

from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE, UNCATEGORIZED_CATEGORY_NAME
from app.core.db import SessionFactory, engine
from app.models import Base
from app.models.category import Category
from app.models.user import User
from app.models.device import Device

ROOT_USERNAME = "root"
ROOT_EMAIL = "root@local"
ROOT_FULL_NAME = "System Root"
DJANGO_DEVICE_CODE = "DJANGO_WEB"
DJANGO_DEVICE_NAME = "Django Web Client"


async def bootstrap() -> None:
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionFactory() as session:
        # ---- Root user ----
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
                is_root=True,
                role="root",
                default_site_id=None,
            )
            session.add(root_user)
            await session.flush()
        else:
            print("Root user already exists. Updating if needed...")
            root_user.email = ROOT_EMAIL
            root_user.full_name = ROOT_FULL_NAME
            root_user.is_active = True
            root_user.is_root = True
            root_user.role = "root"
            if root_user.user_token is None:
                root_user.user_token = uuid.uuid4()
            await session.flush()

        # ---- Django device ----
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
                site_id=None,
                is_active=True,
            )
            session.add(django_device)
            await session.flush()
        else:
            print("Django device already exists. Updating...")
            django_device.device_name = DJANGO_DEVICE_NAME
            django_device.is_active = True
            if django_device.device_token is None:
                django_device.device_token = uuid.uuid4()
            await session.flush()

        # ---- Uncategorized category ----
        result = await session.execute(
            select(Category).where(Category.code == UNCATEGORIZED_CATEGORY_CODE)
        )
        uncategorized_categories = list(result.scalars().all())

        if not uncategorized_categories:
            print("Creating uncategorized category...")
            uncategorized_category = Category(
                name=UNCATEGORIZED_CATEGORY_NAME,
                code=UNCATEGORIZED_CATEGORY_CODE,
                parent_id=None,
                is_active=True,
            )
            session.add(uncategorized_category)
            await session.flush()
        elif len(uncategorized_categories) == 1:
            print("Uncategorized category already exists. Updating...")
            uncategorized_category = uncategorized_categories[0]
            uncategorized_category.name = UNCATEGORIZED_CATEGORY_NAME
            uncategorized_category.parent_id = None
            uncategorized_category.is_active = True
            await session.flush()
        else:
            raise RuntimeError("multiple uncategorized categories configured")

        await session.commit()

        # ---- Output ----
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
        print("System category:")
        print(f"  code:     {UNCATEGORIZED_CATEGORY_CODE}")
        print(f"  name:     {UNCATEGORIZED_CATEGORY_NAME}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(bootstrap())
