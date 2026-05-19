"""
SyncServer bootstrap script — creates/repairs root user, Django device,
and system uncategorized category.

Usage:
    python scripts/bootstrap_root.py [--run-migrations]

The preferred DB lifecycle is:
    1. python -m alembic upgrade head
    2. python scripts/bootstrap_root.py

If --run-migrations is passed, alembic is run inline before data bootstrap.

This script is idempotent: re-running does not change existing tokens
unless an explicit rotation script is used (see rotate_tokens.py).
"""

import argparse
import asyncio
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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


def run_alembic_migrations() -> None:
    """Run Alembic migrations using the same config as the project."""
    alembic_ini = ROOT_DIR / "alembic.ini"
    if not alembic_ini.exists():
        print("WARNING: alembic.ini not found, skipping migrations.")
        return
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("ERROR: Alembic migrations failed:")
        print(result.stderr)
        sys.exit(result.returncode)
    for line in result.stdout.splitlines():
        if line.strip():
            print(f"  [alembic] {line}")


async def create_all_tables() -> None:
    """Ensure all tables exist (safe fallback when Alembic was not run)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def bootstrap_data(session: AsyncSession) -> dict:
    """
    Core bootstrap logic — creates or repairs seed data in the given session.

    Returns a dict with keys: root_user, django_device, uncategorized_category.
    This function is used by the CLI script and by tests.
    """
    result = await session.execute(
        select(User).where(User.username == ROOT_USERNAME)
    )
    root_user = result.scalar_one_or_none()

    if root_user is None:
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
        uncategorized_category = Category(
            name=UNCATEGORIZED_CATEGORY_NAME,
            code=UNCATEGORIZED_CATEGORY_CODE,
            parent_id=None,
            is_active=True,
        )
        session.add(uncategorized_category)
        await session.flush()
    elif len(uncategorized_categories) == 1:
        uncategorized_category = uncategorized_categories[0]
        uncategorized_category.name = UNCATEGORIZED_CATEGORY_NAME
        uncategorized_category.parent_id = None
        uncategorized_category.is_active = True
        await session.flush()
    else:
        raise RuntimeError(
            f"Multiple uncategorized categories found (code={UNCATEGORIZED_CATEGORY_CODE}). "
            "Database is in an invalid state — manual cleanup required."
        )

    return {
        "root_user": root_user,
        "django_device": django_device,
        "uncategorized_category": uncategorized_category,
    }


async def bootstrap(*, run_migrations: bool = False) -> None:
    """Full bootstrap workflow: tables + seed data + console output."""
    if run_migrations:
        print("Running Alembic migrations...")
        run_alembic_migrations()

    print("Ensuring database tables...")
    await create_all_tables()

    print("Bootstrapping seed data...")
    async with SessionFactory() as session:
        entities = await bootstrap_data(session)
        await session.commit()

        root_user = entities["root_user"]
        django_device = entities["django_device"]

        print()
        print("=" * 60)
        print("BOOTSTRAP COMPLETE")
        print("=" * 60)
        print()
        print("Root user:")
        print(f"  SYNC_ROOT_USER_TOKEN={root_user.user_token}")
        print(f"  username={root_user.username}")
        print(f"  id={root_user.id}")
        print()
        print("Django device:")
        print(f"  SYNC_DEVICE_TOKEN={django_device.device_token}")
        print(f"  code={django_device.device_code}")
        print(f"  id={django_device.id}")
        print()
        print("System category:")
        print(f"  code={UNCATEGORIZED_CATEGORY_CODE}")
        print(f"  name={UNCATEGORIZED_CATEGORY_NAME}")
        print("=" * 60)
        print()
        print("Copy these values into your Django .env:")
        print(f"  SYNC_ROOT_USER_TOKEN={root_user.user_token}")
        print(f"  SYNC_DEVICE_TOKEN={django_device.device_token}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SyncServer bootstrap — create/repair root user, Django device, system category."
    )
    parser.add_argument(
        "--run-migrations",
        action="store_true",
        help="Run Alembic migrations before bootstrapping data",
    )
    args = parser.parse_args()
    asyncio.run(bootstrap(run_migrations=args.run_migrations))
