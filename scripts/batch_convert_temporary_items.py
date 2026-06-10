"""
Batch conversion: convert all active legacy temporary items to permanent catalog items.

Usage:
    python scripts/batch_convert_temporary_items.py [--dry-run]

Each active temporary item becomes a permanent Item with:
- category_id=1 ("Без категории") if missing
- unit_id=1 ("Штука"/"шт") if missing
- requires_review=true, review_status="needs_review"
- Balances transferred via service operations
- Temporary item marked as resolved (approved_as_item)
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select

from app.core.db import SessionFactory
from app.models.item import Item
from app.models.temporary_item import TemporaryItem
from app.models.user import User
from app.services.temporary_items_resolution_service import TemporaryItemsResolutionService
from app.services.uow import UnitOfWork


async def convert_all(dry_run: bool = False) -> None:
    async with SessionFactory() as session:
        root_result = await session.execute(
            select(User).where(User.is_root == True).order_by(User.created_at).limit(1)
        )
        root_user = root_result.scalar_one_or_none()
        if root_user is None:
            print("ERROR: no root user found")
            return

        temp_result = await session.execute(
            select(TemporaryItem).where(TemporaryItem.status == "active")
        )
        temp_items = temp_result.scalars().all()

    if not temp_items:
        print("No active temporary items found.")
        return

    print(f"Found {len(temp_items)} active temporary items.")
    print(f"Root user: {root_user.username} ({root_user.id})")

    if dry_run:
        print("\n--- DRY RUN ---")
        for ti in temp_items:
            has_backing = "YES" if ti.item_id else "NO"
            cat = ti.category_id or "default(1)"
            unit = ti.unit_id or "default(1)"
            print(f"  id={ti.id} name=\"{ti.name}\" backing_item={has_backing} cat={cat} unit={unit}")
        print(f"\nWould convert {len(temp_items)} items.")
        return

    converted = 0
    failed = 0

    for ti in temp_items:
        try:
            async with SessionFactory() as session:
                uow = UnitOfWork(session)
                async with uow:
                    # Fix up defaults before resolution
                    temp = await uow.temporary_items.get_by_id(ti.id)
                    if temp is None:
                        print(f"  [{ti.id}] SKIP: not found")
                        continue

                    if temp.category_id is None:
                        temp.category_id = 1  # "Без категории"
                    if temp.unit_id is None:
                        temp.unit_id = 1  # "Штука" / "шт"

                    # Create backing item if missing
                    if temp.item_id is None:
                        new_backing = Item(
                            sku=temp.sku,
                            name=temp.name,
                            normalized_name=temp.normalized_name or temp.name.lower().strip(),
                            category_id=temp.category_id,
                            unit_id=temp.unit_id,
                            description=temp.description,
                            hashtags=temp.hashtags,
                            is_active=True,
                            source_system="batch_temp_convert",
                            source_ref=f"backing_for_temp:{temp.id}",
                            requires_review=True,
                            review_status="needs_review",
                        )
                        new_backing = await uow.catalog.create_item(new_backing)
                        await uow.session.flush()
                        temp.item_id = new_backing.id
                        print(f"  [{ti.id}] Created backing item {new_backing.id}")

                    await TemporaryItemsResolutionService.approve_as_item(
                        uow,
                        temporary_item_id=temp.id,
                        resolved_by_user_id=root_user.id,
                    )

                converted += 1
                print(f"  [{ti.id}] ✓ \"{ti.name}\"")

        except Exception as exc:
            failed += 1
            print(f"  [{ti.id}] ✗ \"{ti.name}\": {exc}")

    print(f"\nDone: {converted} converted, {failed} failed")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert active legacy temporary items to permanent catalog items"
    )
    parser.add_argument("--dry-run", action="store_true", help="List items without making changes")
    args = parser.parse_args()
    asyncio.run(convert_all(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
