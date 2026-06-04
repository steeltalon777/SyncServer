from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory
from app.repos.issue_object_categories_repo import normalize_category_name
from app.schemas.issue_object import IssueObjectCreate, IssueObjectUpdate
from app.schemas.issue_object_category import TreeResponse
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
        category = await uow.issue_object_categories.get_by_id(payload.category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"category_id {payload.category_id} not found",
            )

        issue_object = await uow.issue_objects.create_issue_object(
            display_name=payload.display_name,
            object_type=payload.object_type,
            code=payload.code,
            comment=payload.comment,
            category_id=payload.category_id,
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

        if payload.category_id is not None:
            category = await uow.issue_object_categories.get_by_id(payload.category_id)
            if category is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"category_id {payload.category_id} not found",
                )

        updated = await uow.issue_objects.update_issue_object(
            issue_object_id=issue_object_id,
            display_name=payload.display_name,
            object_type=payload.object_type,
            code=payload.code,
            is_active=payload.is_active,
        )
        if payload.comment is not None:
            updated.comment = payload.comment
        if payload.category_id is not None:
            updated.category_id = payload.category_id
        await uow.session.flush()
        await uow.session.refresh(updated)
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
        category_id: int | None = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueObject], int]:
        """Список объектов выдачи с фильтрами."""
        return await uow.issue_objects.list_issue_objects_with_filters(
            search=search,
            object_type=object_type,
            category_id=category_id,
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


class IssueObjectCategoriesService:
    """Сервис для управления категориями объектов выдачи."""

    async def get_category(self, uow: UnitOfWork, category_id: int) -> IssueObjectCategory:
        category = await uow.issue_object_categories.get_by_id(category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
        return category

    async def create_category(
        self,
        uow: UnitOfWork,
        *,
        name: str,
        parent_id: int | None = None,
        sort_order: int = 0,
        is_active: bool = True,
    ) -> IssueObjectCategory:
        normalized_key = normalize_category_name(name)
        if not normalized_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="category name is empty after normalization",
            )

        existing_list, _ = await uow.issue_object_categories.list_categories(
            search=name, parent_id=parent_id, is_active=None, include_deleted=False, page=1, page_size=1
        )
        for cat in existing_list:
            if cat.normalized_key == normalized_key and cat.parent_id == parent_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"category with name '{name}' already exists under this parent",
                )

        if parent_id is not None:
            parent = await uow.issue_object_categories.get_by_id(parent_id)
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"parent_id {parent_id} not found",
                )

        category = await uow.issue_object_categories.create_category(
            name=name,
            normalized_key=normalized_key,
            parent_id=parent_id,
            sort_order=sort_order,
            is_active=is_active,
        )
        return category

    async def update_category(
        self,
        uow: UnitOfWork,
        category_id: int,
        *,
        name: str | None = None,
        parent_id: int | None = None,
        sort_order: int | None = None,
        is_active: bool | None = None,
    ) -> IssueObjectCategory:
        category = await self.get_category(uow, category_id)

        if category.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot update deleted category",
            )

        if parent_id is not None:
            if parent_id == category_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="category cannot be its own parent",
                )
            await self._check_cycle(uow, category_id, parent_id)
            parent = await uow.issue_object_categories.get_by_id(parent_id)
            if parent is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"parent_id {parent_id} not found",
                )

        if name is not None:
            new_normalized = normalize_category_name(name)
            effective_parent = parent_id if parent_id is not None else category.parent_id
            existing = await uow.issue_object_categories.get_by_parent_and_normalized_key(
                effective_parent, new_normalized,
            )
            if existing is not None and existing.id != category_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"category with name '{name}' already exists under this parent",
                )

        try:
            updated = await uow.issue_object_categories.update_category(
                category_id=category_id,
                name=name,
                normalized_key=normalize_category_name(name) if name else None,
                parent_id=parent_id,
                sort_order=sort_order,
                is_active=is_active,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
        return updated

    async def delete_category(
        self,
        uow: UnitOfWork,
        category_id: int,
        user_id: UUID,
    ) -> None:
        category = await self.get_category(uow, category_id)

        if category.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="category already deleted",
            )

        if await uow.issue_object_categories.has_active_children(category_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot delete category with active children",
            )

        if await uow.issue_object_categories.has_active_objects(category_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot delete category with active objects",
            )

        try:
            await uow.issue_object_categories.soft_delete_category(category_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    async def build_tree(
        self,
        uow: UnitOfWork,
        *,
        search: str | None = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
    ) -> list[TreeResponse]:
        """Build tree of categories and their objects with optional filters."""
        categories, _ = await uow.issue_object_categories.list_categories(
            parent_id=None,
            is_active=None if (include_inactive or include_deleted) else True,
            include_deleted=include_deleted,
            page=1,
            page_size=1000,
        )
        result: list[TreeResponse] = []
        for cat in categories:
            node = await self._build_category_node(
                uow, cat,
                search=search,
                include_inactive=include_inactive,
                include_deleted=include_deleted,
            )
            if node is not None:
                result.append(node)
        return result

    async def _build_category_node(
        self,
        uow: UnitOfWork,
        category: IssueObjectCategory,
        *,
        search: str | None = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
    ) -> TreeResponse | None:
        children: list[TreeResponse] = []

        sub_categories = await uow.issue_object_categories.get_children_filtered(
            category.id,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
        )
        for sub_cat in sub_categories:
            node = await self._build_category_node(
                uow, sub_cat,
                search=search,
                include_inactive=include_inactive,
                include_deleted=include_deleted,
            )
            if node is not None:
                children.append(node)

        cat_objects = await uow.issue_objects.search_objects_for_tree(
            category.id,
            search=search,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
        )
        for obj in cat_objects:
            children.append(TreeResponse(
                id=obj.id,
                type="object",
                name=obj.display_name,
                comment=obj.comment,
                category_id=obj.category_id,
                parent_id=None,
                is_active=obj.is_active,
                children=[],
            ))

        if search:
            term = search.strip().lower()
            category_matches = term in (category.name or "").lower() or term in (category.normalized_key or "")
            if not category_matches and not children:
                return None

        return TreeResponse(
            id=category.id,
            type="category",
            name=category.name,
            comment=None,
            category_id=None,
            parent_id=category.parent_id,
            is_active=category.is_active,
            children=children,
        )

    @staticmethod
    async def _check_cycle(uow: UnitOfWork, category_id: int, proposed_parent_id: int) -> None:
        """Check that proposed_parent_id does not create a cycle."""
        current = proposed_parent_id
        visited = {category_id}
        while current is not None:
            if current in visited:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="cycle detected in category hierarchy",
                )
            visited.add(current)
            parent = await uow.issue_object_categories.get_by_id(current)
            if parent is None:
                break
            current = parent.parent_id

    async def list_categories(
        self,
        uow: UnitOfWork,
        *,
        search: str | None = None,
        parent_id: int | None = None,
        is_active: bool | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueObjectCategory], int]:
        return await uow.issue_object_categories.list_categories(
            search=search,
            parent_id=parent_id,
            is_active=is_active,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )
