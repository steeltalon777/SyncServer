from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_subject import InventorySubject


class InventorySubjectsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, inventory_subject_id: int) -> InventorySubject | None:
        stmt = select(InventorySubject).where(InventorySubject.id == inventory_subject_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_item_id(self, item_id: int) -> InventorySubject | None:
        stmt = select(InventorySubject).where(InventorySubject.item_id == item_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_temporary_item_id(self, temporary_item_id: int) -> InventorySubject | None:
        stmt = select(InventorySubject).where(InventorySubject.temporary_item_id == temporary_item_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_create_for_item(self, *, item_id: int) -> InventorySubject:
        existing = await self.get_by_item_id(item_id)
        if existing is not None:
            return existing

        try:
            async with self.session.begin_nested():
                subject = InventorySubject(subject_type="catalog_item", item_id=item_id)
                self.session.add(subject)
                await self.session.flush()
                return subject
        except IntegrityError:
            return (await self.session.execute(select(InventorySubject).where(InventorySubject.item_id == item_id))).scalar_one()

    async def get_or_create_for_temporary_item(self, *, temporary_item_id: int, item_id: int) -> InventorySubject:
        existing = await self.get_by_temporary_item_id(temporary_item_id)
        if existing is not None:
            return existing

        try:
            async with self.session.begin_nested():
                subject = InventorySubject(
                    subject_type="temporary_item",
                    temporary_item_id=temporary_item_id,
                    item_id=item_id,
                )
                self.session.add(subject)
                await self.session.flush()
                return subject
        except IntegrityError:
            return (
                await self.session.execute(
                    select(InventorySubject).where(InventorySubject.temporary_item_id == temporary_item_id)
                )
            ).scalar_one()

    async def create_for_item(self, *, item_id: int) -> InventorySubject:
        """Create a new catalog_item subject for a permanent item (used during approve)."""
        subject = InventorySubject(subject_type="catalog_item", item_id=item_id)
        self.session.add(subject)
        await self.session.flush()
        return subject

    async def archive(self, inventory_subject_id: int) -> None:
        """Mark an inventory subject as archived (used during merge)."""
        subject = await self.get_by_id(inventory_subject_id)
        if subject is not None:
            subject.archived_at = datetime.now(UTC)
            await self.session.flush()

