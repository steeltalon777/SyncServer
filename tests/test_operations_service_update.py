"""Tests for OperationsService.update_operation — H1 waybill auto-generation."""

import pytest

from app.models.operation import Operation
from app.services.operations_service import OperationsService
from app.schemas.operation import OperationUpdate
from app.services.uow import UnitOfWork


@pytest.mark.asyncio
async def test_update_draft_operation_auto_generates_waybill(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines: Operation,
):
    """Updating a draft operation should auto-generate a waybill document (H1)."""
    operation = test_operation_with_lines
    assert operation.status == "draft"
    await uow.session.commit()

    # Before update: no waybill documents exist
    docs_before = await uow.documents.get_documents_by_operation(operation.id, document_type="waybill")
    assert len(docs_before) == 0

    # Update operation (just notes, no lines change)
    update_data = OperationUpdate(notes="Updated notes for waybill auto-generation test")
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation.id,
        update_data=update_data,
    )

    # After update: waybill should exist
    docs_after = await uow.documents.get_documents_by_operation(operation.id, document_type="waybill")
    assert len(docs_after) >= 1
    waybill = docs_after[0]
    assert waybill.status == "draft"  # Not finalized since auto_finalize=False for drafts
    assert waybill.payload is not None


@pytest.mark.asyncio
async def test_update_draft_operation_twice_recreates_waybill(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines: Operation,
):
    """Updating a draft operation twice should void old waybill and create new one."""
    operation = test_operation_with_lines
    assert operation.status == "draft"
    await uow.session.commit()

    # First update
    update_data = OperationUpdate(notes="First update")
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation.id,
        update_data=update_data,
    )

    docs_after_first = await uow.documents.get_documents_by_operation(operation.id, document_type="waybill")
    assert len(docs_after_first) == 1
    first_waybill_id = docs_after_first[0].id

    # Second update
    update_data = OperationUpdate(notes="Second update")
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation.id,
        update_data=update_data,
    )

    docs_after_second = await uow.documents.get_documents_by_operation(operation.id, document_type="waybill")
    assert len(docs_after_second) == 2
    statuses = {d.status for d in docs_after_second}
    assert statuses == {"void", "draft"}
    # The old document should be void
    old_doc = await uow.documents.get_document_by_id(first_waybill_id)
    assert old_doc is not None
    assert old_doc.status == "void"


@pytest.mark.asyncio
async def test_update_draft_operation_without_lines_still_generates_waybill(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines: Operation,
):
    """Updating draft metadata (notes only, no lines) should still generate waybill."""
    operation = test_operation_with_lines
    assert operation.status == "draft"
    await uow.session.commit()

    update_data = OperationUpdate(notes="Just notes update, no lines change")
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation.id,
        update_data=update_data,
    )

    # Waybill should still be generated even though lines weren't updated
    docs = await uow.documents.get_documents_by_operation(operation.id, document_type="waybill")
    assert len(docs) >= 1
    assert docs[0].status == "draft"


@pytest.mark.asyncio
async def test_update_draft_operation_waybill_error_does_not_abort(
    uow: UnitOfWork,
    test_site,
    test_user,
    test_operation_with_lines: Operation,
    monkeypatch: pytest.MonkeyPatch,
):
    """A waybill generation error should not abort the update_operation."""
    operation = test_operation_with_lines
    assert operation.status == "draft"
    await uow.session.commit()

    # Mock DocumentService.generate_from_operation to raise an exception
    async def _mock_generate_error(*args, **kwargs):
        raise RuntimeError("Simulated waybill generation error")

    monkeypatch.setattr(
        "app.services.operations_service.DocumentService.generate_from_operation",
        _mock_generate_error,
    )

    # Should not raise — the error is caught and logged
    update_data = OperationUpdate(notes="Even if waybill fails, update should succeed")
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation.id,
        update_data=update_data,
    )

    # Operation should still be updated
    updated = await uow.operations.get_operation_by_id(operation.id)
    assert updated is not None
    assert updated.notes == "Even if waybill fails, update should succeed"
