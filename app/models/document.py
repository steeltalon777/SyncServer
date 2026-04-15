from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=False,
    )

    template_name: Mapped[str | None] = mapped_column(String(100))
    template_version: Mapped[str | None] = mapped_column(String(32))
    payload_schema_version: Mapped[str | None] = mapped_column(String(32))

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64))

    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    supersedes_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id"),
    )

    # Relationships
    site: Mapped["Site"] = relationship("Site", back_populates="documents")
    created_by_user: Mapped["User"] = relationship("User", back_populates="documents")
    supersedes: Mapped["Document | None"] = relationship(
        "Document",
        remote_side=[id],
        back_populates="superseded_by",
        foreign_keys=[supersedes_document_id],
    )
    superseded_by: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="supersedes",
        foreign_keys="Document.supersedes_document_id",
    )
    operations: Mapped[list["Operation"]] = relationship(
        "Operation",
        secondary="document_operations",
        back_populates="documents",
    )
    document_operations_assoc: Mapped[list["DocumentOperation"]] = relationship(
        "DocumentOperation",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    sources: Mapped[list["DocumentSource"]] = relationship(
        "DocumentSource",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'finalized', 'void', 'superseded')",
            name="ck_documents_status",
        ),
    )


class DocumentOperation(Base):
    __tablename__ = "document_operations"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="document_operations_assoc")
    operation: Mapped["Operation"] = relationship("Operation", back_populates="document_operations_assoc")


class DocumentSource(Base):
    __tablename__ = "document_sources"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped["Document"] = relationship("Document", back_populates="sources")

    __table_args__ = (
        CheckConstraint("btrim(source_type) <> ''", name="ck_document_sources_source_type_non_empty"),
        CheckConstraint("btrim(source_id) <> ''", name="ck_document_sources_source_id_non_empty"),
    )
