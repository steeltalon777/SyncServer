"""Contract and integration tests for POST /api/v1/operations/from-source-document.

Gate A1: endpoint contract, idempotency, schema enforcement.
Full integration scenarios (canonical resolution, submit behaviour) are in Gate A2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.operation import (
    OperationLineResponse,
    OperationResponse,
    SourceDocumentOperationCreate,
    SourceDocumentOperationLineCreate,
)


class TestSchemaEnforcement:
    """Schema-level enforcement (no DB needed)."""

    def test_source_document_line_no_temporary_item(self):
        """SourceDocumentOperationLineCreate has NO temporary_item field."""
        field_names = set(SourceDocumentOperationLineCreate.model_fields.keys())
        assert "temporary_item" not in field_names

    def test_source_document_line_requires_item_id(self):
        """item_id is required (not Optional)."""
        field = SourceDocumentOperationLineCreate.model_fields["item_id"]
        assert field.is_required()

    def test_source_document_line_qty_positive(self):
        """qty must be > 0 (validated by schema)."""
        from pydantic import ValidationError
        # qty=0 should be rejected
        with pytest.raises(ValidationError):
            SourceDocumentOperationLineCreate(
                line_number=1, item_id=100, qty=Decimal("0")
            )
        # qty negative should be rejected
        with pytest.raises(ValidationError):
            SourceDocumentOperationLineCreate(
                line_number=1, item_id=100, qty=Decimal("-1")
            )
        # qty positive should pass
        line = SourceDocumentOperationLineCreate(
            line_number=1, item_id=100, qty=Decimal("0.001")
        )
        assert line.qty == Decimal("0.001")

    def test_source_document_line_extra_forbid(self):
        """Schema has extra='forbid'."""
        assert SourceDocumentOperationLineCreate.model_config.get("extra") == "forbid"

    def test_source_document_operation_extra_forbid(self):
        """Schema has extra='forbid'."""
        assert SourceDocumentOperationCreate.model_config.get("extra") == "forbid"

    def test_source_document_operation_no_temporary_item(self):
        """SourceDocumentOperationCreate has no temporary_item field."""
        field_names = set(SourceDocumentOperationCreate.model_fields.keys())
        assert "temporary_item" not in field_names
        assert "temporary_draft_payload" not in field_names

    def test_operation_response_has_creation_source(self):
        """OperationResponse includes creation_source."""
        assert "creation_source" in OperationResponse.model_fields
        field = OperationResponse.model_fields["creation_source"]
        assert field.default == "legacy"

    def test_operation_response_has_source_ref(self):
        """OperationResponse includes source_ref."""
        assert "source_ref" in OperationResponse.model_fields

    def test_operation_line_response_has_source_fields(self):
        """OperationLineResponse includes source_* fields."""
        for field_name in ["source_item_name", "source_item_sku", "source_unit_name", "source_category_name"]:
            assert field_name in OperationLineResponse.model_fields, f"{field_name} missing"

    def test_source_document_create_requires_source_ref(self):
        """source_ref is mandatory."""
        assert SourceDocumentOperationCreate.model_fields["source_ref"].is_required()

    def test_source_document_create_has_client_request_id(self):
        """client_request_id is supported for idempotency."""
        assert "client_request_id" in SourceDocumentOperationCreate.model_fields


class TestPayloadValidation:
    """Validation of example payloads."""

    def test_minimal_valid_payload(self):
        """Minimal valid payload works."""
        payload = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref="invoice-001",
            source_document_type="invoice",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=100, qty=Decimal("10")
                )
            ],
        )
        assert payload.source_ref == "invoice-001"
        assert len(payload.lines) == 1

    def test_full_payload_with_source_snapshot(self):
        """Full payload with all fields including source snapshot."""
        now = datetime.now(timezone.utc)
        payload = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref="invoice-001",
            source_document_type="invoice",
            source_document_date=now,
            effective_at=now,
            client_request_id="idem-key-001",
            notes="Test notes",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1,
                    item_id=100,
                    qty=Decimal("10"),
                    batch="LOT-001",
                    comment="Line comment",
                    source_item_name="Source Item",
                    source_item_sku="SRC-001",
                    source_unit_name="kg",
                    source_category_name="Metals",
                ),
            ],
        )
        assert payload.lines[0].source_item_name == "Source Item"
        assert payload.client_request_id == "idem-key-001"

    def test_type_alias(self):
        """operation_type accepts 'type' alias."""
        payload = SourceDocumentOperationCreate(
            type="RECEIVE",
            site_id=1,
            source_ref="test",
            source_document_type="invoice",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=100, qty=Decimal("10")
                )
            ],
        )
        assert payload.operation_type == "RECEIVE"

    def test_quantity_alias_in_line(self):
        """Line accepts 'quantity' alias for qty."""
        line = SourceDocumentOperationLineCreate(
            line_number=1, item_id=100, quantity=Decimal("10")
        )
        assert line.qty == Decimal("10")


class TestResponseSerialization:
    """Response schema serialization with new fields."""

    def test_serialize_with_creation_source(self):
        """OperationResponse serializes creation_source correctly."""
        resp = OperationResponse(
            id=uuid4(),
            site_id=1,
            operation_type="RECEIVE",
            status="draft",
            created_by_user_id=uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            creation_source="source_document",
            source_ref="test-ref",
        )
        data = resp.model_dump(mode="json")
        assert data["creation_source"] == "source_document"
        assert data["source_ref"] == "test-ref"

    def test_serialize_with_default_legacy(self):
        """Default creation_source is 'legacy'."""
        resp = OperationResponse(
            id=uuid4(),
            site_id=1,
            operation_type="RECEIVE",
            status="draft",
            created_by_user_id=uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        data = resp.model_dump(mode="json")
        assert data["creation_source"] == "legacy"

    def test_line_response_serializes_source_fields(self):
        """OperationLineResponse serializes source_* fields."""
        line = OperationLineResponse(
            id=1,
            line_number=1,
            qty=Decimal("10"),
            source_item_name="Test Item",
            source_item_sku="TST-001",
            source_unit_name="kg",
            source_category_name="Metals",
        )
        data = line.model_dump(mode="json")
        assert data["source_item_name"] == "Test Item"
        assert data["source_item_sku"] == "TST-001"
