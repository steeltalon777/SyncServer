import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.catalog_defaults import (
    DEFAULT_UNIT_CODE,
    DEFAULT_UNIT_NAME,
    DEFAULT_UNIT_SYMBOL,
    UNCATEGORIZED_CATEGORY_CODE,
    UNCATEGORIZED_CATEGORY_NAME,
)
from app.core.db import SessionFactory
from app.core.migrations import ensure_database_ready
from app.models.category import Category
from app.models.device import Device
from app.models.unit import Unit
from app.models.user import User

ROOT_USERNAME = "root"
ROOT_EMAIL = "root@local"
ROOT_FULL_NAME = "System Root"
DJANGO_DEVICE_CODE = "DJANGO_WEB"
DJANGO_DEVICE_NAME = "Django Web Client"


async def bootstrap(
    *,
    rotate_root_token: bool = False,
    rotate_device_token: bool = False,
    create_default_unit: bool = False,
) -> None:
    """Выполняет базовую инициализацию системы.

    Аргументы:
        rotate_root_token: принудительно генерирует новый user_token для root.
        rotate_device_token: принудительно генерирует новый device_token для DJANGO_WEB.
        create_default_unit: создаёт единицу измерения «Штука», если её ещё нет.
    """
    print("Ensuring database schema is up to date...")
    await ensure_database_ready()

    root_token_rotated = False
    device_token_rotated = False
    unit_created = False
    unit_already_existed = False

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
            if rotate_root_token:
                root_user.user_token = uuid.uuid4()
                root_token_rotated = True
                print("  Root token rotated.")
            elif root_user.user_token is None:
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
            if rotate_device_token:
                django_device.device_token = uuid.uuid4()
                device_token_rotated = True
                print("  Device token rotated.")
            elif django_device.device_token is None:
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

        # ---- Default unit (Штука) ----
        if create_default_unit:
            result = await session.execute(
                select(Unit).where(Unit.code == DEFAULT_UNIT_CODE)
            )
            default_unit = result.scalar_one_or_none()

            if default_unit is None:
                print("Creating default unit 'Штука'...")
                default_unit = Unit(
                    code=DEFAULT_UNIT_CODE,
                    name=DEFAULT_UNIT_NAME,
                    symbol=DEFAULT_UNIT_SYMBOL,
                    is_active=True,
                    sort_order=1,
                )
                session.add(default_unit)
                unit_created = True
                await session.flush()
            else:
                print("Default unit 'Штука' already exists. Ensuring it is active...")
                if not default_unit.is_active:
                    default_unit.is_active = True
                    print("  Unit reactivated.")
                unit_already_existed = True
                await session.flush()

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
        print()
        if create_default_unit:
            print("Default unit:")
            if unit_created:
                print("  status:   CREATED")
            elif unit_already_existed:
                print("  status:   ALREADY EXISTS (active)")
            print(f"  code:     {DEFAULT_UNIT_CODE}")
            print(f"  name:     {DEFAULT_UNIT_NAME}")
            print(f"  symbol:   {DEFAULT_UNIT_SYMBOL}")
            print()
        print("=" * 60)

        # ---- Warnings ----
        warnings: list[str] = []
        if root_token_rotated:
            warnings.append(
                "Root user token was rotated. Update any configurations or clients that use it."
            )
        if device_token_rotated:
            warnings.append(
                "Django device token was rotated. Update the Django client configuration."
            )
        if warnings:
            print("\n⚠️  WARNINGS:")
            for warning in warnings:
                print(f"  - {warning}")
            print()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap root-пользователя, устройства DJANGO_WEB и системных данных."
    )
    parser.add_argument(
        "--rotate-root-token",
        action="store_true",
        help="Принудительно генерирует новый user_token для root-пользователя.",
    )
    parser.add_argument(
        "--rotate-device-token",
        action="store_true",
        help="Принудительно генерирует новый device_token для устройства DJANGO_WEB.",
    )
    parser.add_argument(
        "--create-default-unit",
        action="store_true",
        help='Создаёт единицу измерения "Штука", если её ещё нет.',
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Эквивалентно --rotate-root-token --rotate-device-token --create-default-unit.",
    )
    return parser


if __name__ == "__main__":
    parser = build_argument_parser()
    args = parser.parse_args()

    rotate_root = args.rotate_root_token or args.force
    rotate_device = args.rotate_device_token or args.force
    create_unit = args.create_default_unit or args.force

    asyncio.run(
        bootstrap(
            rotate_root_token=rotate_root,
            rotate_device_token=rotate_device,
            create_default_unit=create_unit,
        )
    )
