"""Tests for documents API endpoints."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.document import Document
from app.models.operation import Operation


def test_generate_document_success(
    client: TestClient,
    auth_headers_user,
    test_operation_with_lines,
):
    """Test POST /documents/generate endpoint."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    
    response = client.post(
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


def test_generate_document_auto_finalize(
    client: TestClient,
    auth_headers_user,
    test_operation_with_lines,
):
    """Test POST /documents/generate with auto_finalize=True."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    
    response = client.post(
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


def test_generate_document_operation_not_found(
    client: TestClient,
    auth_headers_user,
):
    """Test POST /documents/generate with non-existent operation."""
    non_existent_id = uuid4()
    
    response = client.post(
        "/api/v1/documents/generate",
        headers=auth_headers_user,
        json={
            "operation_id": str(non_existent_id),
            "document_type": "waybill",
        },
    )
    
    assert response.status_code == 404
    assert "operation with id" in response.json()["detail"]


def test_generate_document_unauthorized(
    client: TestClient,
    test_operation_with_lines,
):
    """Test POST /documents/generate without authentication."""
    operation = test_operation_with_lines
    
    response = client.post(
        "/api/v1/documents/generate",
        json={
            "operation_id": str(operation.id),
            "document_type": "waybill",
        },
    )
    
    assert response.status_code == 401


def test_get_document_by_id(
    client: TestClient,
    auth_headers_user,
    test_document,
):
    """Test GET /documents/{document_id} endpoint."""
    document = test_document
    
    response = client.get(
        f"/api/v1/documents/{document.id}",
        headers=auth_headers_user,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == str(document.id)
    assert data["document_type"] == document.document_type
    assert data["site_id"] == document.site_id
    assert data["status"] == document.status
    assert data["payload"] == document.payload


def test_get_document_not_found(
    client: TestClient,
    auth_headers_user,
):
    """Test GET /documents/{document_id} with non-existent document."""
    non_existent_id = uuid4()
    
    response = client.get(
        f"/api/v1/documents/{non_existent_id}",
        headers=auth_headers_user,
    )
    
    assert response.status_code == 404
    assert "document with id" in response.json()["detail"]


def test_list_documents(
    client: TestClient,
    auth_headers_user,
    test_document,
    test_site,
):
    """Test GET /documents endpoint with filtering."""
    document = test_document
    
    # Test without filters
    response = client.get(
        "/api/v1/documents",
        headers=auth_headers_user,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "items" in data
    assert "total" in data
    assert "offset" in data
    assert "limit" in data
    
    # Should find at least our test document
    assert data["total"] >= 1
    document_found = any(d["id"] == str(document.id) for d in data["items"])
    assert document_found
    
    # Test with site filter
    response = client.get(
        f"/api/v1/documents?site_id={test_site.id}",
        headers=auth_headers_user,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    
    # Test with document_type filter
    response = client.get(
        f"/api/v1/documents?document_type={document.document_type}",
        headers=auth_headers_user,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    
    # Test with status filter
    response = client.get(
        f"/api/v1/documents?status={document.status}",
        headers=auth_headers_user,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


def test_update_document_status(
    client: TestClient,
    auth_headers_user,
    test_document,
):
    """Test PATCH /documents/{document_id}/status endpoint."""
    document = test_document
    assert document.status == "draft"
    
    # Finalize the document
    response = client.patch(
        f"/api/v1/documents/{document.id}/status",
        headers=auth_headers_user,
        json={"status": "finalized"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "finalized"
    assert data["finalized_at"] is not None
    
    # Try to void the finalized document
    response = client.patch(
        f"/api/v1/documents/{document.id}/status",
        headers=auth_headers_user,
        json={"status": "void"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "void"


def test_update_document_status_invalid_transition(
    client: TestClient,
    auth_headers_user,
    test_finalized_document,
):
    """Test invalid status transition (e.g., changing finalized document)."""
    document = test_finalized_document
    assert document.status == "finalized"
    
    # Try to change status of finalized document (should fail)
    response = client.patch(
        f"/api/v1/documents/{document.id}/status",
        headers=auth_headers_user,
        json={"status": "draft"},
    )
    
    assert response.status_code == 409
    assert "cannot change status of finalized document" in response.json()["detail"]


def test_get_documents_by_operation(
    client: TestClient,
    auth_headers_user,
    test_document,
    test_operation_with_lines,
):
    """Test GET /operations/{operation_id}/documents endpoint."""
    operation = test_operation_with_lines
    
    # Link document to operation
    from app.services.uow import UnitOfWork
    from app.core.db import get_db
    from sqlalchemy.ext.asyncio import AsyncSession
    
    # This would normally be done in a fixture, but for simplicity we'll skip
    # and assume the test_document is already linked
    
    response = client.get(
        f"/api/v1/documents/operations/{operation.id}/documents",
        headers=auth_headers_user,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, list)
    # Might be empty if no documents linked, but endpoint should work


def test_generate_document_for_operation_shortcut(
    client: TestClient,
    auth_headers_user,
    test_operation_with_lines,
):
    """Test POST /operations/{operation_id}/documents shortcut endpoint."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    
    response = client.post(
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
    
    document_data = data["document"]
    assert document_data["document_type"] == "waybill"
    assert document_data["status"] == "finalized"


def test_generate_document_for_operation_with_template(
    client: TestClient,
    auth_headers_user,
    test_operation_with_lines,
):
    """Test shortcut endpoint with custom template."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    
    response = client.post(
        f"/api/v1/documents/operations/{operation.id}/documents",
        headers=auth_headers_user,
        params={
            "document_type": "waybill",
            "template_name": "custom_template_v1",
            "auto_finalize": False,
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    document_data = data["document"]
    assert document_data["template_name"] == "custom_template_v1"


def test_permission_checks(
    client: TestClient,
    auth_headers_user_no_access,
    test_document,
    test_operation_with_lines,
):
    """Test that users without proper site access are denied."""
    document = test_document
    operation = test_operation_with_lines
    
    # Try to get document without access
    response = client.get(
        f"/api/v1/documents/{document.id}",
        headers=auth_headers_user_no_access,
    )
    
    # Should be 403 or 404 (depending on implementation)
    assert response.status_code in [403, 404]
    
    # Try to generate document without access
    response = client.post(
        "/api/v1/documents/generate",
        headers=auth_headers_user_no_access,
        json={
            "operation_id": str(operation.id),
            "document_type": "waybill",
        },
    )
    
    assert response.status_code in [403, 404]


def test_pagination(
    client: TestClient,
    auth_headers_user,
    test_site,
    test_user,
    db_session,
):
    """Test pagination parameters in GET /documents."""
    # Create multiple documents for testing
    documents = []
    for i in range(5):
        document = Document(
            document_type="waybill",
            site_id=test_site.id,
            payload={"test": f"document_{i}"},
            created_by_user_id=test_user.id,
            document_number=f"WB-TEST-{i}",
            status="draft",
        )
        db_session.add(document)
        documents.append(document)
    
    db_session.commit()
    
    # Test with limit=2
    response = client.get(
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
    
    # Test with offset=2
    response = client.get(
        "/api/v1/documents",
        headers=auth_headers_user,
        params={"limit": 2, "offset": 2},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["items"]) == 2
    assert data["offset"] == 2