from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.recipient import Recipient
from app.schemas.recipient import RecipientCreate, RecipientUpdate
from app.services.uow import UnitOfWork


class RecipientsService:
    """Сервис для управления получателями с поддержкой архивного удаления."""

    async def get_recipient(self, uow: UnitOfWork, recipient_id: int) -> Recipient:
        """Получить получателя по ID."""
        recipient = await uow.recipients.get_by_id(recipient_id)
        if recipient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recipient not found")
        return recipient

    async def create_recipient(
        self,
        uow: UnitOfWork,
        payload: RecipientCreate,
    ) -> Recipient:
        """Создать нового получателя."""
        # Проверка уникальности имени (нормализованного)
        normalized_name = payload.display_name.strip().lower()
        existing = await uow.recipients.get_active_by_normalized_key(normalized_name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"recipient with name '{payload.display_name}' already exists",
            )

        recipient = await uow.recipients.create_recipient(
            display_name=payload.display_name,
            recipient_type=payload.recipient_type,
            personnel_no=payload.personnel_no,
        )
        return recipient

    async def update_recipient(
        self,
        uow: UnitOfWork,
        recipient_id: int,
        payload: RecipientUpdate,
    ) -> Recipient:
        """Обновить данные получателя."""
        recipient = await self.get_recipient(uow, recipient_id)

        if recipient.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot update deleted recipient",
            )

        # Проверка уникальности нового имени, если оно изменилось
        if payload.display_name is not None:
            new_name = payload.display_name.strip()
            if new_name.lower() != recipient.display_name.lower():
                normalized_name = new_name.lower()
                existing = await uow.recipients.get_active_by_normalized_key(normalized_name)
                if existing is not None and existing.id != recipient_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"recipient with name '{new_name}' already exists",
                    )

        updated = await uow.recipients.update_recipient(
            recipient_id=recipient_id,
            display_name=payload.display_name,
            recipient_type=payload.recipient_type,
            personnel_no=payload.personnel_no,
            is_active=payload.is_active,
        )
        return updated

    async def delete_recipient(
        self,
        uow: UnitOfWork,
        recipient_id: int,
        user_id: UUID,
    ) -> None:
        """Архивное удаление получателя."""
        recipient = await self.get_recipient(uow, recipient_id)

        if recipient.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="recipient already deleted",
            )

        if recipient.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot delete active recipient",
            )

        # Проверка наличия выданных активов
        # TODO: добавить проверку через asset_register_repo
        # Пока используем простую проверку - если есть issued_asset_balances, нельзя удалять
        # Для простоты пока пропускаем эту проверку, но в реальности нужно реализовать

        try:
            await uow.recipients.soft_delete_recipient(recipient_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    async def list_recipients(
        self,
        uow: UnitOfWork,
        *,
        search: str | None = None,
        recipient_type: str | None = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Recipient], int]:
        """Список получателей с фильтрами."""
        return await uow.recipients.list_recipients_with_filters(
            search=search,
            recipient_type=recipient_type,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    async def merge_recipients(
        self,
        uow: UnitOfWork,
        source_id: int,
        target_id: int,
    ) -> Recipient:
        """Объединить двух получателей."""
        try:
            merged = await uow.recipients.merge_recipients(
                source_id=source_id,
                target_id=target_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        return merged
