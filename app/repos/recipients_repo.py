from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recipient import Recipient, RecipientAlias

_NON_WORD_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_SPACES_RE = re.compile(r"\s+", flags=re.UNICODE)


def normalize_recipient_name(value: str) -> str:
    text = (value or "").strip().lower().replace("ё", "е")
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text


class RecipientsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, recipient_id: int) -> Recipient | None:
        return await self.session.get(Recipient, recipient_id)

    async def get_active_by_normalized_key(self, normalized_key: str) -> Recipient | None:
        stmt = select(Recipient).where(
            and_(
                Recipient.normalized_key == normalized_key,
                Recipient.merged_into_id.is_(None),
                Recipient.is_active.is_(True),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_alias_normalized_key(self, normalized_key: str) -> Recipient | None:
        stmt = (
            select(Recipient)
            .join(RecipientAlias, RecipientAlias.recipient_id == Recipient.id)
            .where(
                and_(
                    RecipientAlias.normalized_key == normalized_key,
                    Recipient.is_active.is_(True),
                    Recipient.merged_into_id.is_(None),
                )
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_create_by_name(
        self,
        *,
        display_name: str,
        recipient_type: str = "person",
        personnel_no: str | None = None,
    ) -> Recipient:
        normalized_key = normalize_recipient_name(display_name)
        if not normalized_key:
            raise ValueError("recipient display_name is empty after normalization")

        existing = await self.get_active_by_normalized_key(normalized_key)
        if existing is not None:
            return existing

        alias_match = await self.get_by_alias_normalized_key(normalized_key)
        if alias_match is not None:
            return alias_match

        recipient = Recipient(
            recipient_type=recipient_type,
            display_name=display_name.strip(),
            normalized_key=normalized_key,
            personnel_no=personnel_no,
            is_active=True,
        )
        self.session.add(recipient)
        await self.session.flush()
        return recipient

    async def create_recipient(
        self,
        *,
        display_name: str,
        recipient_type: str = "person",
        personnel_no: str | None = None,
    ) -> Recipient:
        normalized_key = normalize_recipient_name(display_name)
        if not normalized_key:
            raise ValueError("recipient display_name is empty after normalization")

        existing = await self.get_active_by_normalized_key(normalized_key)
        if existing is not None:
            return existing

        recipient = Recipient(
            recipient_type=recipient_type,
            display_name=display_name.strip(),
            normalized_key=normalized_key,
            personnel_no=personnel_no,
            is_active=True,
        )
        self.session.add(recipient)
        await self.session.flush()
        return recipient

    async def list_recipients(
        self,
        *,
        search: str | None,
        recipient_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Recipient], int]:
        stmt = select(Recipient).where(Recipient.merged_into_id.is_(None))
        count_stmt = select(func.count()).select_from(Recipient).where(Recipient.merged_into_id.is_(None))

        if recipient_type:
            stmt = stmt.where(Recipient.recipient_type == recipient_type)
            count_stmt = count_stmt.where(Recipient.recipient_type == recipient_type)

        if search:
            normalized = normalize_recipient_name(search)
            term = f"%{search.strip()}%"
            normalized_term = f"%{normalized}%"
            stmt = stmt.where(
                or_(
                    Recipient.display_name.ilike(term),
                    Recipient.personnel_no.ilike(term),
                    Recipient.normalized_key.ilike(normalized_term),
                )
            )
            count_stmt = count_stmt.where(
                or_(
                    Recipient.display_name.ilike(term),
                    Recipient.personnel_no.ilike(term),
                    Recipient.normalized_key.ilike(normalized_term),
                )
            )

        total_count = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(Recipient.display_name, Recipient.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        recipients = list((await self.session.execute(stmt)).scalars().all())
        return recipients, int(total_count)

    async def find_similar(
        self,
        *,
        display_name: str,
        limit: int = 5,
    ) -> list[Recipient]:
        normalized = normalize_recipient_name(display_name)
        if not normalized:
            return []

        term = f"%{normalized}%"
        stmt = (
            select(Recipient)
            .where(
                and_(
                    Recipient.merged_into_id.is_(None),
                    Recipient.is_active.is_(True),
                    Recipient.normalized_key.ilike(term),
                )
            )
            .order_by(Recipient.display_name, Recipient.id)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def merge_recipients(self, *, source_id: int, target_id: int) -> Recipient:
        if source_id == target_id:
            raise ValueError("cannot merge recipient into itself")

        source = await self.get_by_id(source_id)
        target = await self.get_by_id(target_id)
        if source is None or target is None:
            raise ValueError("recipient not found")

        source.is_active = False
        source.merged_into_id = target.id

        alias_exists_stmt = select(RecipientAlias).where(RecipientAlias.normalized_key == source.normalized_key)
        alias_exists = (await self.session.execute(alias_exists_stmt)).scalar_one_or_none()
        if alias_exists is None:
            alias = RecipientAlias(
                recipient_id=target.id,
                alias=source.display_name,
                normalized_key=source.normalized_key,
            )
            self.session.add(alias)

        await self.session.flush()
        return target

    async def update_recipient(
        self,
        recipient_id: int,
        *,
        display_name: str | None = None,
        recipient_type: str | None = None,
        personnel_no: str | None = None,
        is_active: bool | None = None,
    ) -> Recipient:
        recipient = await self.get_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient {recipient_id} not found")
        if recipient.deleted_at is not None:
            raise ValueError(f"Recipient {recipient_id} is deleted")
        if display_name is not None:
            recipient.display_name = display_name.strip()
            recipient.normalized_key = normalize_recipient_name(display_name)
        if recipient_type is not None:
            recipient.recipient_type = recipient_type
        if personnel_no is not None:
            recipient.personnel_no = personnel_no
        if is_active is not None:
            recipient.is_active = is_active
        await self.session.flush()
        return recipient

    async def soft_delete_recipient(self, recipient_id: int, user_id: UUID) -> None:
        recipient = await self.get_by_id(recipient_id)
        if not recipient:
            raise ValueError(f"Recipient {recipient_id} not found")
        if recipient.deleted_at is not None:
            raise ValueError(f"Recipient {recipient_id} already deleted")
        if recipient.is_active:
            raise ValueError(f"Cannot delete active recipient {recipient_id}")
        # Check for issued assets (simplified - need to integrate with asset registers)
        # For now, we'll assume no issued assets
        recipient.deleted_at = datetime.now()
        recipient.deleted_by_user_id = user_id
        await self.session.flush()

    async def list_recipients_with_filters(
        self,
        *,
        search: str | None = None,
        recipient_type: str | None = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Recipient], int]:
        stmt = select(Recipient).where(Recipient.merged_into_id.is_(None))

        if not include_deleted:
            stmt = stmt.where(Recipient.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(Recipient.is_active.is_(True))

        if search:
            search_term = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    Recipient.display_name.ilike(search_term),
                    Recipient.normalized_key.ilike(search_term),
                    Recipient.personnel_no.ilike(search_term) if Recipient.personnel_no is not None else false(),
                )
            )

        if recipient_type:
            stmt = stmt.where(Recipient.recipient_type == recipient_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Recipient.display_name).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total_count)
