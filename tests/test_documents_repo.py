"""Tests for DocumentsRepo."""
from datetime import datetime, UTC
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.operation import Operation
from app.models.site import Site
from app.models.user import User
from app.repos.documents_repo import DocumentsRepo
from app.schemas.document import DocumentFilter


@pytest.mark.asyncio
async def test_create_document(db_session: AsyncSession):
    """Test creating a document via repository."""
    site = Site(code="REPO", name="Repo Site")
    db_session.add(site)
    await db_session.flush()

    repo = DocumentsRepo(db_session)
    document = await repo.create_document(
        document_type="waybill",
        site_id=site.id,
        payload={"test": "data"},
        document_number="DOC-001",
        revision=1,
        status="draft",
    )
    assert document.id is not None
    assert document.document_type == "waybill"
    assert document.site_id == site.id
    assert document.document_number == "DOC-001"
    assert document.revision == 1
    assert document.status == "draft"
    assert document.payload == {"test": "data"}


@pytest.mark.asyncio
async def test_get_document_by_id(db_session: AsyncSession):
    """Test retrieving a document by ID."""
    site = Site(code="REPO2", name="Repo Site 2")
    db_session.add(site)
    await db_session.flush()

    repo = DocumentsRepo(db_session)
    created = await repo.create_document(
        document_type="acceptance_certificate",
        site_id=site.id,
        payload={},
    )
    await db_session.commit()

    fetched = await repo.get_document_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.document_type == "acceptance_certificate"

    # Non-existent ID
    non_existent = await repo.get_document_by_id(uuid4())
    assert non_existent is None


@pytest.mark.asyncio
async def test_get_documents_by_operation(db_session: AsyncSession):
    """Test retrieving documents linked to an operation."""
    site = Site(code="REPO3", name="Repo Site 3")
    db_session.add(site)
    await db_session.flush()

    user = User(username="repo_user", email="repo@example.com", role="storekeeper")
    db_session.add(user)
    await db_session.flush()

    operation = Operation(
        site_id=site.id,
        operation_type="RECEIVE",
        created_by_user_id=user.id,
    )
    db_session.add(operation)
    await db_session.flush()

    repo = DocumentsRepo(db_session)
    doc1 = await repo.create_document(
        document_type="waybill",
        site_id=site.id,
        payload={},
    )
    doc2 = await repo.create_document(
        document_type="act",
        site_id=site.id,
        payload={},
    )
    await repo.link_document_to_operation(doc1.id, operation.id)
    await repo.link_document_to_operation(doc2.id, operation.id)
    await db_session.commit()

    documents = await repo.get_documents_by_operation(operation.id)
    assert len(documents) == 2
    doc_types = {d.document_type for d in documents}
    assert doc_types == {"waybill", "act"}

    # Filter by document_type
    waybills = await repo.get_documents_by_operation(operation.id, document_type="waybill")
    assert len(waybills) == 1
    assert waybills[0].document_type == "waybill"

    sources = await repo.get_sources_by_document(doc1.id)
    assert len(sources) == 1
    assert sources[0].source_type == "operation"
    assert sources[0].source_id == str(operation.id)


@pytest.mark.asyncio
async def test_get_documents_by_generic_source(db_session: AsyncSession):
    """Test retrieving documents linked to a universal document source."""
    site = Site(code="REPO_SRC", name="Repo Generic Source")
    db_session.add(site)
    await db_session.flush()

    repo = DocumentsRepo(db_session)
    doc = await repo.create_document(
        document_type="invoice",
        site_id=site.id,
        payload={"kind": "generic-source"},
    )
    await repo.link_document_to_source(doc.id, "report", "stock-summary:2026-04-15")
    await db_session.commit()

    documents = await repo.get_documents_by_source("report", "stock-summary:2026-04-15")
    assert len(documents) == 1
    assert documents[0].id == doc.id

    sources = await repo.get_sources_by_document(doc.id)
    assert len(sources) == 1
    assert sources[0].source_type == "report"
    assert sources[0].source_id == "stock-summary:2026-04-15"


@pytest.mark.asyncio
async def test_update_document_status(db_session: AsyncSession):
    """Test updating document status."""
    site = Site(code="REPO4", name="Repo Site 4")
    db_session.add(site)
    await db_session.flush()

    repo = DocumentsRepo(db_session)
    doc = await repo.create_document(
        document_type="waybill",
        site_id=site.id,
        payload={},
    )
    await db_session.commit()

    success = await repo.update_document_status(doc.id, "finalized")
    assert success is True
    await db_session.refresh(doc)
    assert doc.status == "finalized"
    assert doc.finalized_at is not None  # auto-set because status changed to finalized

    # Update with explicit finalized_at
    new_time = datetime(2025, 1, 1, tzinfo=UTC)
    success = await repo.update_document_status(doc.id, "void", finalized_at=new_time)
    assert success is True
    await db_session.refresh(doc)
    assert doc.status == "void"
    assert doc.finalized_at == new_time

    # Non-existent document
    success = await repo.update_document_status(uuid4(), "draft")
    assert success is False


@pytest.mark.asyncio
async def test_list_documents(db_session: AsyncSession):
    """Test listing documents with filters."""
    site1 = Site(code="SITE_A", name="Site A")
    site2 = Site(code="SITE_B", name="Site B")
    db_session.add_all([site1, site2])
    await db_session.flush()

    user = User(username="list_user", email="list@example.com", role="storekeeper")
    db_session.add(user)
    await db_session.flush()

    repo = DocumentsRepo(db_session)
    # Create documents
    doc1 = await repo.create_document(
        document_type="waybill",
        site_id=site1.id,
        payload={},
        created_by_user_id=user.id,
        status="draft",
    )
    doc2 = await repo.create_document(
        document_type="waybill",
        site_id=site1.id,
        payload={},
        created_by_user_id=user.id,
        status="finalized",
    )
    doc3 = await repo.create_document(
        document_type="act",
        site_id=site2.id,
        payload={},
        status="draft",
    )
    await db_session.commit()

    # Filter by site
    filter = DocumentFilter(site_id=site1.id)
    items, total = await repo.list_documents(filter)
    assert total == 2
    assert {d.id for d in items} == {doc1.id, doc2.id}

    # Filter by document_type
    filter = DocumentFilter(document_type="act")
    items, total = await repo.list_documents(filter)
    assert total == 1
    assert items[0].id == doc3.id

    # Filter by status
    filter = DocumentFilter(status="finalized")
    items, total = await repo.list_documents(filter)
    assert total == 1
    assert items[0].id == doc2.id

    # Filter by created_by_user_id
    filter = DocumentFilter(created_by_user_id=user.id)
    items, total = await repo.list_documents(filter)
    assert total == 2
    assert {d.id for d in items} == {doc1.id, doc2.id}

    # Pagination
    filter = DocumentFilter()
    items, total = await repo.list_documents(filter, offset=1, limit=2)
    assert total == 3
    assert len(items) == 2
