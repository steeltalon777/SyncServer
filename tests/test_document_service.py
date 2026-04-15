"""Tests for DocumentService."""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.document_service import DocumentService
from app.services.uow import UnitOfWork


@pytest.mark.asyncio
async def test_generate_from_operation_success(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines,
):
    """Test successful document generation from an operation."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    # Generate document
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation.id,
        document_type="waybill",
        created_by_user_id=test_user.id,
    )
    
    assert "document" in result
    assert "operation" in result
    
    document = result["document"]
    assert document.document_type == "waybill"
    assert document.site_id == operation.site_id
    assert document.status == "draft"  # По умолчанию draft, если не auto_finalize
    assert document.document_number is not None
    assert document.payload is not None
    
    # Проверяем payload
    payload = document.payload
    assert payload["document_title"] == "Товарная накладная"
    assert payload["operation_id"] == str(operation.id)
    assert "lines" in payload
    assert len(payload["lines"]) == len(operation.lines)
    
    # Проверяем связь с операцией
    linked_docs = await uow.documents.get_documents_by_operation(operation.id)
    assert len(linked_docs) == 1
    assert linked_docs[0].id == document.id

    generic_linked_docs = await uow.documents.get_documents_by_source("operation", operation.id)
    assert len(generic_linked_docs) == 1
    assert generic_linked_docs[0].id == document.id

    sources = await uow.documents.get_sources_by_document(document.id)
    assert len(sources) == 1
    assert sources[0].source_type == "operation"
    assert sources[0].source_id == str(operation.id)


@pytest.mark.asyncio
async def test_generate_from_operation_auto_finalize(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines,
):
    """Test document generation with auto_finalize=True."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation.id,
        document_type="waybill",
        auto_finalize=True,
        created_by_user_id=test_user.id,
    )
    
    document = result["document"]
    assert document.status == "finalized"
    assert document.finalized_at is not None


@pytest.mark.asyncio
async def test_generate_from_operation_not_found(uow: UnitOfWork):
    """Test document generation with non-existent operation."""
    non_existent_id = uuid4()
    
    with pytest.raises(HTTPException) as exc_info:
        await DocumentService.generate_from_operation(
            uow=uow,
            operation_id=non_existent_id,
            document_type="waybill",
        )
    
    assert exc_info.value.status_code == 404
    assert f"operation with id {non_existent_id} not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_generate_from_operation_wrong_status(
    uow: UnitOfWork,
    test_operation_with_lines,
):
    """Test document generation for operation with wrong status."""
    operation = test_operation_with_lines
    # Операция в статусе draft по умолчанию - должна пройти
    # Но проверим случай с отменённой операцией
    operation.status = "cancelled"
    await uow.session.commit()
    
    with pytest.raises(HTTPException) as exc_info:
        await DocumentService.generate_from_operation(
            uow=uow,
            operation_id=operation.id,
            document_type="waybill",
        )
    
    assert exc_info.value.status_code == 409
    assert "cannot generate document for operation with status 'cancelled'" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_generate_different_document_types(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines,
):
    """Test generation of different document types."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    document_types = ["waybill", "acceptance_certificate", "act", "invoice"]
    
    for doc_type in document_types:
        result = await DocumentService.generate_from_operation(
            uow=uow,
            operation_id=operation.id,
            document_type=doc_type,
            created_by_user_id=test_user.id,
        )
        
        document = result["document"]
        assert document.document_type == doc_type
        
        # Проверяем заголовок в payload
        payload = document.payload
        if doc_type == "waybill":
            assert payload["document_title"] == "Товарная накладная"
        elif doc_type == "acceptance_certificate":
            assert payload["document_title"] == "Акт приёмки"
        elif doc_type == "act":
            assert payload["document_title"] == "Акт"
        elif doc_type == "invoice":
            assert payload["document_title"] == "Счёт"


@pytest.mark.asyncio
async def test_generate_with_custom_template(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines,
):
    """Test document generation with custom template name."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    custom_template = "custom_waybill_v2"
    
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation.id,
        document_type="waybill",
        template_name=custom_template,
        created_by_user_id=test_user.id,
    )
    
    document = result["document"]
    assert document.template_name == custom_template


@pytest.mark.asyncio
async def test_payload_structure_for_move_operation(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_move_operation_with_lines,
):
    """Test payload structure for MOVE operation with destination site."""
    operation = test_move_operation_with_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation.id,
        document_type="waybill",
        created_by_user_id=test_user.id,
    )
    
    document = result["document"]
    payload = document.payload
    
    # Для MOVE операции должен быть receiver
    assert payload["operation_type"] == "MOVE"
    assert "receiver" in payload
    assert payload["receiver"] is not None
    assert payload["receiver"]["site_id"] == operation.destination_site_id
    
    # Должен быть sender
    assert "sender" in payload
    assert payload["sender"]["site_id"] == operation.site_id


@pytest.mark.asyncio
async def test_payload_structure_for_issue_operation(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_issue_operation_with_lines,
):
    """Test payload structure for ISSUE operation with recipient."""
    operation = test_issue_operation_with_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation.id,
        document_type="waybill",
        created_by_user_id=test_user.id,
    )
    
    document = result["document"]
    payload = document.payload
    
    # Для ISSUE операции должен быть recipient
    assert payload["operation_type"] == "ISSUE"
    assert "recipient" in payload
    assert payload["recipient"] is not None
    assert payload["recipient"]["recipient_name"] == operation.recipient_name_snapshot
    
    # Должен быть issued_to
    assert "issued_to" in payload
    assert payload["issued_to"]["name"] == operation.issued_to_name


@pytest.mark.asyncio
async def test_payload_includes_snapshots(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_snapshot_lines,
):
    """Test that payload includes item snapshots from operation lines."""
    operation = test_operation_with_snapshot_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation.id,
        document_type="waybill",
        created_by_user_id=test_user.id,
    )
    
    document = result["document"]
    payload = document.payload
    
    # Проверяем, что снапшоты включены в строки
    lines = payload["lines"]
    assert len(lines) == len(operation.lines)
    
    for i, line in enumerate(lines):
        operation_line = operation.lines[i]
        assert line["item_name"] == operation_line.item_name_snapshot
        assert line["item_sku"] == operation_line.item_sku_snapshot
        assert line["unit_name"] == operation_line.unit_name_snapshot
        assert line["category_name"] == operation_line.category_name_snapshot


@pytest.mark.asyncio
async def test_payload_hash_calculation(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines,
):
    """Test that payload hash is correctly calculated."""
    operation = test_operation_with_lines
    operation.status = "submitted"
    await uow.session.commit()
    
    result = await DocumentService.generate_from_operation(
        uow=uow,
        operation_id=operation.id,
        document_type="waybill",
        created_by_user_id=test_user.id,
    )
    
    document = result["document"]
    assert document.payload_hash is not None
    assert len(document.payload_hash) == 64  # SHA-256 hex digest length
    
    # Хэш должен быть одинаковым для одинакового payload
    import json
    import hashlib
    
    payload_bytes = json.dumps(document.payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    expected_hash = hashlib.sha256(payload_bytes).hexdigest()
    assert document.payload_hash == expected_hash
