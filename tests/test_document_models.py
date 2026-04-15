"""Basic tests for Document, DocumentOperation and DocumentSource models."""
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentOperation, DocumentSource
from app.models.operation import Operation
from app.models.site import Site
from app.models.user import User


@pytest.mark.asyncio
async def test_document_creation(db_session: AsyncSession):
    """Test that a Document can be created and persisted."""
    # Create a site and user first (they are required foreign keys)
    site = Site(code="TEST", name="Test Site")
    db_session.add(site)
    await db_session.flush()

    user = User(username="testuser", email="test@example.com", role="storekeeper")
    db_session.add(user)
    await db_session.flush()

    # Create a document
    document = Document(
        document_type="waybill",
        site_id=site.id,
        payload={"title": "Test document", "items": []},
        created_by_user_id=user.id,
        document_number="WB-001",
    )
    db_session.add(document)
    await db_session.flush()
    await db_session.refresh(document)

    assert document.id is not None
    assert document.document_type == "waybill"
    assert document.site_id == site.id
    assert document.status == "draft"
    assert document.document_number == "WB-001"
    assert document.created_by_user_id == user.id
    assert document.payload == {"title": "Test document", "items": []}


@pytest.mark.asyncio
async def test_document_operation_link(db_session: AsyncSession):
    """Test linking a document to an operation via DocumentOperation."""
    site = Site(code="TEST2", name="Test Site 2")
    db_session.add(site)
    await db_session.flush()

    user = User(username="testuser2", email="test2@example.com", role="storekeeper")
    db_session.add(user)
    await db_session.flush()

    operation = Operation(
        site_id=site.id,
        operation_type="RECEIVE",
        created_by_user_id=user.id,
    )
    db_session.add(operation)
    await db_session.flush()

    document = Document(
        document_type="waybill",
        site_id=site.id,
        payload={},
        created_by_user_id=user.id,
    )
    db_session.add(document)
    await db_session.flush()

    link = DocumentOperation(
        document_id=document.id,
        operation_id=operation.id,
    )
    db_session.add(link)
    await db_session.flush()

    # Verify the link
    assert link.document_id == document.id
    assert link.operation_id == operation.id

    # Verify relationships
    await db_session.refresh(document, ["operations"])
    await db_session.refresh(operation, ["documents"])

    assert len(document.operations) == 1
    assert document.operations[0].id == operation.id
    assert len(operation.documents) == 1
    assert operation.documents[0].id == document.id


@pytest.mark.asyncio
async def test_document_source_link(db_session: AsyncSession):
    """Test linking a document to a generic source via DocumentSource."""
    site = Site(code="TESTSRC", name="Test Site Source")
    db_session.add(site)
    await db_session.flush()

    document = Document(
        document_type="waybill",
        site_id=site.id,
        payload={"title": "Generic source document"},
    )
    db_session.add(document)
    await db_session.flush()

    source = DocumentSource(
        document_id=document.id,
        source_type="report",
        source_id="inventory-summary-2026-04-15",
    )
    db_session.add(source)
    await db_session.flush()

    await db_session.refresh(document, ["sources"])

    assert len(document.sources) == 1
    assert document.sources[0].document_id == document.id
    assert document.sources[0].source_type == "report"
    assert document.sources[0].source_id == "inventory-summary-2026-04-15"


@pytest.mark.asyncio
async def test_document_status_transition(db_session: AsyncSession):
    """Test updating document status."""
    site = Site(code="TEST3", name="Test Site 3")
    db_session.add(site)
    await db_session.flush()

    document = Document(
        document_type="acceptance_certificate",
        site_id=site.id,
        payload={},
    )
    db_session.add(document)
    await db_session.flush()

    # Update status
    document.status = "finalized"
    await db_session.flush()
    await db_session.refresh(document)

    assert document.status == "finalized"
    assert document.finalized_at is None  # not auto-set

    # Set finalized_at
    from datetime import datetime, UTC
    now = datetime.now(UTC)
    document.finalized_at = now
    await db_session.flush()
    await db_session.refresh(document)
    assert document.finalized_at == now
