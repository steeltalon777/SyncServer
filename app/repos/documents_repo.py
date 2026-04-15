from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentOperation, DocumentSource
from app.schemas.document import DocumentFilter


class DocumentsRepo:
    """Repository for documents."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _normalize_source_id(source_id: UUID | int | str) -> str:
        return str(source_id)

    async def create_document(
        self,
        document_type: str,
        site_id: int,
        payload: dict,
        created_by_user_id: UUID | None = None,
        document_number: str | None = None,
        revision: int = 0,
        status: Literal["draft", "finalized", "void", "superseded"] = "draft",
        template_name: str | None = None,
        template_version: str | None = None,
        payload_schema_version: str | None = None,
        payload_hash: str | None = None,
        finalized_at: datetime | None = None,
        supersedes_document_id: UUID | None = None,
    ) -> Document:
        """Create a new document."""
        document = Document(
            document_type=document_type,
            document_number=document_number,
            revision=revision,
            status=status,
            site_id=site_id,
            template_name=template_name,
            template_version=template_version,
            payload_schema_version=payload_schema_version,
            payload=payload,
            payload_hash=payload_hash,
            created_by_user_id=created_by_user_id,
            finalized_at=finalized_at,
            supersedes_document_id=supersedes_document_id,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def get_document_by_id(
        self,
        document_id: UUID,
        *,
        include_operations: bool = False,
    ) -> Document | None:
        """Retrieve a document by its ID."""
        stmt = select(Document).where(Document.id == document_id)
        if include_operations:
            stmt = stmt.options(selectinload(Document.operations))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_documents_by_source(
        self,
        source_type: str,
        source_id: UUID | int | str,
        document_type: str | None = None,
    ) -> list[Document]:
        """Retrieve documents linked to a generic source."""
        normalized_source_type = source_type.strip()
        normalized_source_id = self._normalize_source_id(source_id)

        stmt = (
            select(Document)
            .join(DocumentSource, Document.id == DocumentSource.document_id)
            .where(DocumentSource.source_type == normalized_source_type)
            .where(DocumentSource.source_id == normalized_source_id)
        )
        if document_type:
            stmt = stmt.where(Document.document_type == document_type)
        stmt = stmt.order_by(Document.created_at.desc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_sources_by_document(self, document_id: UUID) -> list[DocumentSource]:
        """Retrieve all generic sources linked to a document."""
        stmt = (
            select(DocumentSource)
            .where(DocumentSource.document_id == document_id)
            .order_by(DocumentSource.source_type.asc(), DocumentSource.source_id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_documents_by_operation(
        self,
        operation_id: UUID,
        document_type: str | None = None,
    ) -> list[Document]:
        """Retrieve all documents linked to a specific operation."""
        documents_by_id = {
            document.id: document
            for document in await self.get_documents_by_source(
                source_type="operation",
                source_id=operation_id,
                document_type=document_type,
            )
        }

        stmt = (
            select(Document)
            .join(DocumentOperation, Document.id == DocumentOperation.document_id)
            .where(DocumentOperation.operation_id == operation_id)
        )
        if document_type:
            stmt = stmt.where(Document.document_type == document_type)
        stmt = stmt.order_by(Document.created_at.desc())
        result = await self.session.execute(stmt)

        for document in result.scalars().all():
            documents_by_id.setdefault(document.id, document)

        return sorted(
            documents_by_id.values(),
            key=lambda document: document.created_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

    async def update_document_status(
        self,
        document_id: UUID,
        status: Literal["draft", "finalized", "void", "superseded"],
        finalized_at: datetime | None = None,
    ) -> bool:
        """Update a document's status (and optionally finalized_at)."""
        stmt = (
            select(Document)
            .where(Document.id == document_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()
        if not document:
            return False
        document.status = status
        if finalized_at is not None:
            document.finalized_at = finalized_at
        elif status == "finalized" and document.finalized_at is None:
            document.finalized_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def update_document(
        self,
        document_id: UUID,
        *,
        status: Literal["draft", "finalized", "void", "superseded"] | None = None,
        finalized_at: datetime | None = None,
        payload: dict | None = None,
        payload_hash: str | None = None,
    ) -> Document | None:
        """Update mutable document fields used by the documents API."""
        stmt = (
            select(Document)
            .where(Document.id == document_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()
        if not document:
            return None

        if status is not None:
            document.status = status
            if status == "finalized" and finalized_at is None and document.finalized_at is None:
                document.finalized_at = datetime.now(UTC)

        if finalized_at is not None:
            document.finalized_at = finalized_at
        if payload is not None:
            document.payload = payload
        if payload_hash is not None:
            document.payload_hash = payload_hash

        await self.session.flush()
        return document

    async def link_document_to_source(
        self,
        document_id: UUID,
        source_type: str,
        source_id: UUID | int | str,
    ) -> DocumentSource:
        """Create a generic link between a document and any source entity."""
        normalized_source_type = source_type.strip()
        normalized_source_id = self._normalize_source_id(source_id)

        stmt = (
            select(DocumentSource)
            .where(DocumentSource.document_id == document_id)
            .where(DocumentSource.source_type == normalized_source_type)
            .where(DocumentSource.source_id == normalized_source_id)
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        link = DocumentSource(
            document_id=document_id,
            source_type=normalized_source_type,
            source_id=normalized_source_id,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def link_document_to_operation(
        self,
        document_id: UUID,
        operation_id: UUID,
    ) -> DocumentOperation:
        """Create a link between a document and an operation.

        The legacy `document_operations` table is kept for backward compatibility,
        while `document_sources` becomes the canonical generic source registry.
        """
        await self.link_document_to_source(
            document_id=document_id,
            source_type="operation",
            source_id=operation_id,
        )

        stmt = (
            select(DocumentOperation)
            .where(DocumentOperation.document_id == document_id)
            .where(DocumentOperation.operation_id == operation_id)
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        link = DocumentOperation(
            document_id=document_id,
            operation_id=operation_id,
        )
        self.session.add(link)
        await self.session.flush()
        return link

    async def list_documents(
        self,
        filter: DocumentFilter,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[Document], int]:
        """List documents with filtering and pagination."""
        stmt = select(Document)
        count_stmt = select(func.count()).select_from(Document)

        # Apply filters
        if filter.site_id is not None:
            stmt = stmt.where(Document.site_id == filter.site_id)
            count_stmt = count_stmt.where(Document.site_id == filter.site_id)
        if filter.document_type is not None:
            stmt = stmt.where(Document.document_type == filter.document_type)
            count_stmt = count_stmt.where(Document.document_type == filter.document_type)
        if filter.status is not None:
            stmt = stmt.where(Document.status == filter.status)
            count_stmt = count_stmt.where(Document.status == filter.status)
        if filter.created_by_user_id is not None:
            stmt = stmt.where(Document.created_by_user_id == filter.created_by_user_id)
            count_stmt = count_stmt.where(Document.created_by_user_id == filter.created_by_user_id)
        if filter.date_from is not None:
            stmt = stmt.where(Document.created_at >= filter.date_from)
            count_stmt = count_stmt.where(Document.created_at >= filter.date_from)
        if filter.date_to is not None:
            stmt = stmt.where(Document.created_at <= filter.date_to)
            count_stmt = count_stmt.where(Document.created_at <= filter.date_to)

        # Ordering
        stmt = stmt.order_by(desc(Document.created_at))

        # Pagination
        stmt = stmt.offset(offset).limit(limit)

        # Execute
        result = await self.session.execute(stmt)
        documents = list(result.scalars().all())

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        return documents, total
