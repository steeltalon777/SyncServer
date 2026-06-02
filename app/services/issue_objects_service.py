from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.issue_object import IssueObject
from app.schemas.issue_object import IssueObjectCreate, IssueObjectUpdate
from app.services.uow import UnitOfWork


class IssueObjectsService:
    """Сервис для управления объектами выдачи с поддержкой архивного удаления."""

    async def get_issue_object(self, uow: UnitOfWork, issue_object_id: int) -> IssueObject:
        """Получить объект выдачи по ID."""
        issue_object = await uow.issue_objects.get_by_id(issue_object_id)
        if issue_object is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="issue_object not found")
        return issue_object

    async def create_issue_object(
        self,
        uow: UnitOfWork,
        payload: IssueObjectCreate,
    ) -> IssueObject:
        """Создать новый объект выдачи."""
        normalized_name = payload.display_name.strip().lower()
        existing = await uow.issue_objects.get_active_by_normalized_key(normalized_name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"issue_object with name '{payload.display_name}' already exists",
            )

        issue_object = await uow.issue_objects.create_issue_object(
            display_name=payload.display_name,
            object_type=payload.object_type,
            code=payload.code,
        )
        return issue_object

    async def update_issue_object(
        self,
        uow: UnitOfWork,
        issue_object_id: int,
        payload: IssueObjectUpdate,
    ) -> IssueObject:
        """Обновить данные объекта выдачи."""
        issue_object = await self.get_issue_object(uow, issue_object_id)

        if issue_object.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot update deleted issue_object",
            )

        if payload.display_name is not None:
            new_name = payload.display_name.strip()
            if new_name.lower() != issue_object.display_name.lower():
                normalized_name = new_name.lower()
                existing = await uow.issue_objects.get_active_by_normalized_key(normalized_name)
                if existing is not None and existing.id != issue_object_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"issue_object with name '{new_name}' already exists",
                    )

        updated = await uow.issue_objects.update_issue_object(
            issue_object_id=issue_object_id,
            display_name=payload.display_name,
            object_type=payload.object_type,
            code=payload.code,
            is_active=payload.is_active,
        )
        return updated

    async def delete_issue_object(
        self,
        uow: UnitOfWork,
        issue_object_id: int,
        user_id: UUID,
    ) -> None:
        """Архивное удаление объекта выдачи."""
        issue_object = await self.get_issue_object(uow, issue_object_id)

        if issue_object.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="issue_object already deleted",
            )

        if issue_object.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot delete active issue_object",
            )

        try:
            await uow.issue_objects.soft_delete_issue_object(issue_object_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    async def list_issue_objects(
        self,
        uow: UnitOfWork,
        *,
        search: str | None = None,
        object_type: str | None = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueObject], int]:
        """Список объектов выдачи с фильтрами."""
        return await uow.issue_objects.list_issue_objects_with_filters(
            search=search,
            object_type=object_type,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    async def merge_issue_objects(
        self,
        uow: UnitOfWork,
        source_id: int,
        target_id: int,
    ) -> IssueObject:
        """Объединить два объекта выдачи."""
        try:
            merged = await uow.issue_objects.merge_issue_objects(
                source_id=source_id,
                target_id=target_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        return merged
