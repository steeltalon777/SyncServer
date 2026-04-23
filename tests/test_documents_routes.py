"""Tests for documents API endpoints."""

from uuid import uuid4

import pytest
from app.models.document import Document
from app.models.operation import Operation
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _mark_submitted(operation: Operation, db_session: AsyncSession) -> None:
    operation.status = "submitted"
    await db_session.flush()


@pytest.mark.asyncio
async def test_generate_document_success(
    client: AsyncClient,
    auth_headers_user,
    test_operation_with_lines: Operation,
    db_session: AsyncSession,
):
    """Test POST /documents/generate endpoint."""
    operation = test_operation_with_lines
    await _mark_submitted(operation, db_session)

    response = await client.post(
        "/api/v1/documents/generate",
        headers=auth_headers_user,
        json={
            "operation_id": str(operation.id),
            "document_type": "waybill",
            "auto_finalize": False,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert "document" in data
    assert "operation_id" in data
    assert "generated_at" in data

    document_data = data["document"]
    assert document_data["document_type"] == "waybill"
    assert document_data["site_id"] == operation.site_id
    assert document_data["status"] == "draft"
    assert document_data["document_number"] is not None
    assert document_data["payload"] is not None


@pytest.mark.asyncio
async def test_generate_document_auto_finalize(
    client: AsyncClient,
    auth_headers_user,
    test_operation_with_lines: Operation,
    db_session: AsyncSession,
):
    """Test POST /documents/generate with auto_finalize=True."""
    operation = test_operation_with_lines
    await _mark_submitted(operation, db_session)

    response = await client.post(
        "/api/v1/documents/generate",
        headers=auth_headers_user,
        json={
            "operation_id": str(operation.id),
            "document_type": "waybill",
            "auto_finalize": True,
        },
    )

    assert response.status_code == 200
    data = response.json()

    document_data = data["document"]
    assert document_data["status"] == "finalized"
    assert document_data["finalized_at"] is not None


@pytest.mark.asyncio
async def test_generate_document_operation_not_found(
    client: AsyncClient,
    auth_headers_user,
):
    """Test POST /documents/generate with non-existent operation."""
    non_existent_id = uuid4()

    response = await client.post(
        "/api/v1/documents/generate",
        headers=auth_headers_user,
        json={
            "operation_id": str(non_existent_id),
            "document_type": "waybill",
        },
    )

    assert response.status_code == 404
    assert "operation with id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_document_unauthorized(
    client: AsyncClient,
    test_operation_with_lines: Operation,
):
    """Test POST /documents/generate without authentication."""
    response = await client.post(
        "/api/v1/documents/generate",
        json={
            "operation_id": str(test_operation_with_lines.id),
            "document_type": "waybill",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_document_by_id(
    client: AsyncClient,
    auth_headers_user,
    test_document: Document,
):
    """Test GET /documents/{document_id} endpoint."""
    response = await client.get(
        f"/api/v1/documents/{test_document.id}",
        headers=auth_headers_user,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(test_document.id)
    assert data["document_type"] == test_document.document_type
    assert data["site_id"] == test_document.site_id
    assert data["status"] == test_document.status
    assert data["payload"] == test_document.payload


@pytest.mark.asyncio
async def test_get_document_not_found(
    client: AsyncClient,
    auth_headers_user,
):
    """Test GET /documents/{document_id} with non-existent document."""
    non_existent_id = uuid4()

    response = await client.get(
        f"/api/v1/documents/{non_existent_id}",
        headers=auth_headers_user,
    )

    assert response.status_code == 404
    assert "document with id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_documents(
    client: AsyncClient,
    auth_headers_user,
    test_document: Document,
    test_site,
):
    """Test GET /documents endpoint with filtering."""
    response = await client.get(
        "/api/v1/documents",
        headers=auth_headers_user,
    )

    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "total" in data
    assert "offset" in data
    assert "limit" in data
    assert data["total"] >= 1
    assert any(doc["id"] == str(test_document.id) for doc in data["items"])

    response = await client.get(
        f"/api/v1/documents?site_id={test_site.id}",
        headers=auth_headers_user,
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    response = await client.get(
        f"/api/v1/documents?document_type={test_document.document_type}",
        headers=auth_headers_user,
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    response = await client.get(
        f"/api/v1/documents?status={test_document.status}",
        headers=auth_headers_user,
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 1


@pytest.mark.asyncio
async def test_update_document_status(
    client: AsyncClient,
    auth_headers_user,
    test_document: Document,
):
    """Test PATCH /documents/{document_id}/status endpoint."""
    assert test_document.status == "draft"

    response = await client.patch(
        f"/api/v1/documents/{test_document.id}/status",
        headers=auth_headers_user,
        json={"status": "finalized"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "finalized"
    assert data["finalized_at"] is not None

    response = await client.patch(
        f"/api/v1/documents/{test_document.id}/status",
        headers=auth_headers_user,
        json={"status": "void"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "void"


@pytest.mark.asyncio
async def test_update_document_status_invalid_transition(
    client: AsyncClient,
    auth_headers_user,
    test_finalized_document: Document,
):
    """Test invalid status transition for finalized document."""
    assert test_finalized_document.status == "finalized"

    response = await client.patch(
        f"/api/v1/documents/{test_finalized_document.id}/status",
        headers=auth_headers_user,
        json={"status": "draft"},
    )

    assert response.status_code == 409
    assert "cannot change status of finalized document" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_documents_by_operation(
    client: AsyncClient,
    auth_headers_user,
    test_document: Document,
    test_operation_with_lines: Operation,
):
    """Test GET /documents/operations/{operation_id}/documents endpoint."""
    response = await client.get(
        f"/api/v1/documents/operations/{test_operation_with_lines.id}/documents",
        headers=auth_headers_user,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(doc["id"] == str(test_document.id) for doc in data)


@pytest.mark.asyncio
async def test_generate_document_for_operation_shortcut(
    client: AsyncClient,
    auth_headers_user,
    test_operation_with_lines: Operation,
    db_session: AsyncSession,
):
    """Test POST /documents/operations/{operation_id}/documents shortcut endpoint."""
    operation = test_operation_with_lines
    await _mark_submitted(operation, db_session)

    response = await client.post(
        f"/api/v1/documents/operations/{operation.id}/documents",
        headers=auth_headers_user,
        params={
            "document_type": "waybill",
            "auto_finalize": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "document" in data
    assert "operation_id" in data
    assert "generated_at" in data
    assert data["document"]["document_type"] == "waybill"
    assert data["document"]["status"] == "finalized"


@pytest.mark.asyncio
async def test_generate_document_for_operation_with_template(
    client: AsyncClient,
    auth_headers_user,
    test_operation_with_lines: Operation,
    db_session: AsyncSession,
):
    """Test shortcut endpoint with custom template."""
    operation = test_operation_with_lines
    await _mark_submitted(operation, db_session)

    response = await client.post(
        f"/api/v1/documents/operations/{operation.id}/documents",
        headers=auth_headers_user,
        params={
            "document_type": "waybill",
            "template_name": "custom_template_v1",
            "auto_finalize": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["document"]["template_name"] == "custom_template_v1"


@pytest.mark.asyncio
async def test_permission_checks(
    client: AsyncClient,
    auth_headers_user_no_access,
    test_document: Document,
    test_operation_with_lines: Operation,
):
    """Test that users without proper site access are denied."""
    response = await client.get(
        f"/api/v1/documents/{test_document.id}",
        headers=auth_headers_user_no_access,
    )
    assert response.status_code in [403, 404]

    response = await client.post(
        "/api/v1/documents/generate",
        headers=auth_headers_user_no_access,
        json={
            "operation_id": str(test_operation_with_lines.id),
            "document_type": "waybill",
        },
    )
    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_pagination(
    client: AsyncClient,
    auth_headers_user,
    test_site,
    test_user,
    db_session: AsyncSession,
):
    """Test pagination parameters in GET /documents."""
    for index in range(5):
        db_session.add(
            Document(
                document_type="waybill",
                site_id=test_site.id,
                payload={"test": f"document_{index}"},
                created_by_user_id=test_user.id,
                document_number=f"WB-TEST-{index}",
                status="draft",
            )
        )
    await db_session.flush()

    response = await client.get(
        "/api/v1/documents",
        headers=auth_headers_user,
        params={"limit": 2, "offset": 0},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert data["total"] >= 5

    response = await client.get(
        "/api/v1/documents",
        headers=auth_headers_user,
        params={"limit": 2, "offset": 2},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["offset"] == 2
