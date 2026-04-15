from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


DocumentType = Literal["waybill", "acceptance_certificate", "act", "invoice"]
DocumentStatus = Literal["draft", "finalized", "void", "superseded"]


class DocumentFilter(BaseModel):
    """Filter for listing documents."""
    site_id: int | None = None
    document_type: DocumentType | None = None
    status: DocumentStatus | None = None
    created_by_user_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class DocumentCreate(BaseModel):
    """Input for creating a new document."""
    document_type: DocumentType
    site_id: int
    payload: dict[str, Any]
    created_by_user_id: UUID | None = None
    document_number: str | None = None
    revision: int = 0
    status: DocumentStatus = "draft"
    template_name: str | None = None
    template_version: str | None = None
    payload_schema_version: str | None = None
    payload_hash: str | None = None
    finalized_at: datetime | None = None
    supersedes_document_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentUpdate(BaseModel):
    """Input for updating a document (partial)."""
    status: DocumentStatus | None = None
    finalized_at: datetime | None = None
    payload: dict[str, Any] | None = None
    payload_hash: str | None = None


class DocumentResponse(ORMBaseModel):
    """Full document response."""
    id: UUID
    document_type: DocumentType
    document_number: str | None
    revision: int
    status: DocumentStatus
    site_id: int
    template_name: str | None
    template_version: str | None
    payload_schema_version: str | None
    payload: dict[str, Any]
    payload_hash: str | None
    created_by_user_id: UUID | None
    created_at: datetime
    finalized_at: datetime | None
    supersedes_document_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""
    items: list[DocumentResponse]
    total: int
    offset: int
    limit: int


class DocumentLinkOperation(BaseModel):
    """Link a document to an operation."""
    operation_id: UUID


class DocumentGenerateRequest(BaseModel):
    """Request to generate a document from an operation."""
    operation_id: UUID
    document_type: DocumentType = "waybill"
    template_name: str | None = None
    auto_finalize: bool = False
    language: str = Field(default="ru", description="Язык документа (например: ru, en)")
    basis_type: str | None = Field(default=None, description="Тип основания документа (договор, заявка, приказ)")
    basis_number: str | None = Field(default=None, description="Номер основания документа")
    basis_date: datetime | None = Field(default=None, description="Дата основания документа")
