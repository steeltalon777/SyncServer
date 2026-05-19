"""
SyncServer token rotation script — rotate root user and/or Django device tokens.

This is an explicit local ops tool for token recovery after compromise.
It must be intentionally invoked; default bootstrap never rotates tokens.

Usage:
    python scripts/rotate_tokens.py --root
    python scripts/rotate_tokens.py --django-device
    python scripts/rotate_tokens.py --root --django-device

Output uses Django env var names (SYNC_ROOT_USER_TOKEN, SYNC_DEVICE_TOKEN).
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.db import SessionFactory
from app.models.device import Device
from app.models.user import User

ROOT_USERNAME = "root"
DJANGO_DEVICE_CODE = "DJANGO_WEB"


async def rotate_root_token_in_session(session: AsyncSession) -> tuple:
    """
    Rotate root user token in the given session.

    Returns (old_token, new_token).
    Raises ValueError if root user not found.
    """
    result = await session.execute(
        select(User).where(User.username == ROOT_USERNAME)
    )
    root_user = result.scalar_one_or_none()
    if root_user is None:
        raise ValueError("Root user not found. Run bootstrap_root.py first.")

    old_token = root_user.user_token
    root_user.user_token = uuid.uuid4()
    await session.flush()
    return old_token, root_user.user_token


async def rotate_django_device_token_in_session(session: AsyncSession) -> tuple:
    """
    Rotate Django device token in the given session.

    Returns (old_token, new_token).
    Raises ValueError if Django device not found.
    """
    result = await session.execute(
        select(Device).where(Device.device_code == DJANGO_DEVICE_CODE)
    )
    django_device = result.scalar_one_or_none()
    if django_device is None:
        raise ValueError("Django device not found. Run bootstrap_root.py first.")

    old_token = django_device.device_token
    django_device.device_token = uuid.uuid4()
    await session.flush()
    return old_token, django_device.device_token


async def rotate_root_token() -> None:
    """CLI entry point: rotate root token with console output."""
    async with SessionFactory() as session:
        try:
            old_token, new_token = await rotate_root_token_in_session(session)
            await session.commit()
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        print("Root user token rotated.")
        print(f"  Previous: SYNC_ROOT_USER_TOKEN={old_token}")
        print(f"  New:      SYNC_ROOT_USER_TOKEN={new_token}")
        print()
        print("Update your Django .env with the new value.")


async def rotate_django_device_token() -> None:
    """CLI entry point: rotate Django device token with console output."""
    async with SessionFactory() as session:
        try:
            old_token, new_token = await rotate_django_device_token_in_session(session)
            await session.commit()
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        print("Django device token rotated.")
        print(f"  Previous: SYNC_DEVICE_TOKEN={old_token}")
        print(f"  New:      SYNC_DEVICE_TOKEN={new_token}")
        print()
        print("Update your Django .env with the new value.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rotate SyncServer tokens for root user and/or Django device."
    )
    parser.add_argument(
        "--root",
        action="store_true",
        help="Rotate root user token",
    )
    parser.add_argument(
        "--django-device",
        action="store_true",
        dest="django_device",
        help="Rotate Django device token",
    )
    args = parser.parse_args()

    if not args.root and not args.django_device:
        parser.print_help()
        print()
        print("ERROR: Specify at least one of --root or --django-device.")
        sys.exit(1)

    if args.root:
        asyncio.run(rotate_root_token())
    if args.django_device:
        if args.root:
            print()
        asyncio.run(rotate_django_device_token())
