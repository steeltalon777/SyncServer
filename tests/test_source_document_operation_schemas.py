"""Tests for SourceDocumentOperationCreate / SourceDocumentOperationLineCreate schemas.

TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING §11.1 (Gate A1)
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.operation import (
    SourceDocumentOperationCreate,
    SourceDocumentOperationLineCreate,
    SourceDocumentType,
)


class TestSourceDocumentLineSchema:
    """SourceDocumentOperationLineCreate schema tests."""

    def test_requires_item_id(self):
        """item_id is required (NOT optional unlike OperationLineCreate)."""
        with pytest.raises(ValidationError) as exc:
            SourceDocumentOperationLineCreate(
                line_number=1,
                qty=10,
                # item_id missing
            )
        errors = exc.value.errors()
        assert any(e["loc"] == ("item_id",) for e in errors)

    def test_valid_minimal_line(self):
        """Minimal valid line."""
        line = SourceDocumentOperationLineCreate(
            line_number=1,
            item_id=100,
            qty=Decimal("10"),
        )
        assert line.line_number == 1
        assert line.item_id == 100
        assert line.qty == Decimal("10")
        assert line.source_item_name is None
        assert line.source_item_sku is None

    def test_valid_full_line(self):
        """Full line with all optional fields."""
        line = SourceDocumentOperationLineCreate(
            line_number=2,
            item_id=200,
            qty=Decimal("5.5"),
            batch="LOT-001",
            comment="test comment",
            source_item_name="Source Item Name",
            source_item_sku="SRC-001",
            source_unit_name="kg",
            source_category_name="Metals",
        )
        assert line.source_item_name == "Source Item Name"
        assert line.source_item_sku == "SRC-001"
        assert line.source_unit_name == "kg"
        assert line.source_category_name == "Metals"

    def test_qty_must_be_positive(self):
        """qty must be > 0."""
        with pytest.raises(ValidationError) as exc:
            SourceDocumentOperationLineCreate(
                line_number=1,
                item_id=100,
                qty=Decimal("0"),
            )
        assert exc.value.errors()

        with pytest.raises(ValidationError) as exc:
            SourceDocumentOperationLineCreate(
                line_number=1,
                item_id=100,
                qty=Decimal("-1"),
            )
        assert exc.value.errors()

    def test_qty_accepts_alias_quantity(self):
        """qty can be provided as 'quantity' alias."""
        line = SourceDocumentOperationLineCreate(
            line_number=1,
            item_id=100,
            quantity=Decimal("10"),
        )
        assert line.qty == Decimal("10")

    def test_no_temporary_item_field(self):
        """Schema has NO temporary_item field."""
        field_names = set(SourceDocumentOperationLineCreate.model_fields.keys())
        assert "temporary_item" not in field_names

    def test_extra_forbid(self):
        """extra='forbid' rejects unknown fields."""
        with pytest.raises(ValidationError) as exc:
            SourceDocumentOperationLineCreate(
                line_number=1,
                item_id=100,
                qty=Decimal("10"),
                temporary_item={"name": "test"},  # unknown field
            )
        errors = exc.value.errors()
        # Pydantic v2 extra=forbid raises on unexpected field
        assert any("temporary_item" in str(e["loc"]) or "temporary_item" in str(e.get("input", {})) for e in errors) or any(
            e["type"] == "extra_forbidden" for e in errors
        )

    def test_extra_forbid_any_unknown(self):
        """Any unknown field is rejected."""
        with pytest.raises(ValidationError) as exc:
            SourceDocumentOperationLineCreate(
                line_number=1,
                item_id=100,
                qty=Decimal("10"),
                unknown_field="test",
            )
        errors = exc.value.errors()
        assert any(e["type"] == "extra_forbidden" for e in errors)


class TestSourceDocumentOperationSchema:
    """SourceDocumentOperationCreate schema tests."""

    def test_requires_source_ref(self):
        """source_ref is required."""
        with pytest.raises(ValidationError) as exc:
            SourceDocumentOperationCreate(
                operation_type="RECEIVE",
                site_id=1,
                source_document_type="invoice",
                lines=[
                    SourceDocumentOperationLineCreate(
                        line_number=1, item_id=100, qty=Decimal("10")
                    )
                ],
            )
        errors = exc.value.errors()
        assert any("source_ref" in str(e["loc"]) for e in errors)

    def test_source_ref_min_length(self):
        """source_ref must have min_length=1."""
        with pytest.raises(ValidationError):
            SourceDocumentOperationCreate(
                operation_type="RECEIVE",
                site_id=1,
                source_ref="",
                source_document_type="invoice",
                lines=[
                    SourceDocumentOperationLineCreate(
                        line_number=1, item_id=100, qty=Decimal("10")
                    )
                ],
            )

    def test_valid_source_document_type_values(self):
        """Valid source_document_type values."""
        for doc_type in SourceDocumentType.__args__:
            payload = SourceDocumentOperationCreate(
                operation_type="RECEIVE",
                site_id=1,
                source_ref="test-ref",
                source_document_type=doc_type,
                lines=[
                    SourceDocumentOperationLineCreate(
                        line_number=1, item_id=100, qty=Decimal("10")
                    )
                ],
            )
            assert payload.source_document_type == doc_type

    def test_invalid_source_document_type(self):
        """Invalid source_document_type raises error."""
        with pytest.raises(ValidationError):
            SourceDocumentOperationCreate(
                operation_type="RECEIVE",
                site_id=1,
                source_ref="test-ref",
                source_document_type="invalid_type",
                lines=[
                    SourceDocumentOperationLineCreate(
                        line_number=1, item_id=100, qty=Decimal("10")
                    )
                ],
            )

    def test_requires_at_least_one_line(self):
        """lines must have at least 1 item."""
        with pytest.raises(ValidationError):
            SourceDocumentOperationCreate(
                operation_type="RECEIVE",
                site_id=1,
                source_ref="test-ref",
                source_document_type="invoice",
                lines=[],
            )

    def test_minimal_valid_payload(self):
        """Minimal valid payload."""
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
        assert payload.operation_type == "RECEIVE"
        assert payload.site_id == 1
        assert payload.source_ref == "invoice-001"
        assert payload.source_document_type == "invoice"
        assert len(payload.lines) == 1

    def test_full_valid_payload(self):
        """Full valid payload with all fields."""
        now = datetime.now(timezone.utc)
        payload = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref="invoice-001",
            source_document_type="invoice",
            source_document_date=now,
            effective_at=now,
            destination_site_id=None,
            notes="Test notes",
            client_request_id="client-req-001",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1,
                    item_id=100,
                    qty=Decimal("10"),
                    batch="LOT-001",
                    source_item_name="Source Name",
                ),
                SourceDocumentOperationLineCreate(
                    line_number=2,
                    item_id=200,
                    qty=Decimal("5"),
                ),
            ],
        )
        assert len(payload.lines) == 2
        assert payload.client_request_id == "client-req-001"

    def test_type_alias(self):
        """operation_type can be provided as 'type' alias."""
        payload = SourceDocumentOperationCreate(
            type="RECEIVE",
            site_id=1,
            source_ref="test-ref",
            source_document_type="invoice",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=100, qty=Decimal("10")
                )
            ],
        )
        assert payload.operation_type == "RECEIVE"

    def test_destination_site_id_alias(self):
        """destination_site_id can be provided as 'target_site_id' alias."""
        payload = SourceDocumentOperationCreate(
            operation_type="MOVE",
            site_id=1,
            source_ref="test-ref",
            source_document_type="invoice",
            source_site_id=1,
            target_site_id=2,
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=100, qty=Decimal("10")
                )
            ],
        )
        assert payload.destination_site_id == 2

    def test_extra_forbid_top_level(self):
        """extra='forbid' rejects unknown fields at top level."""
        with pytest.raises(ValidationError) as exc:
            SourceDocumentOperationCreate(
                operation_type="RECEIVE",
                site_id=1,
                source_ref="test-ref",
                source_document_type="invoice",
                lines=[
                    SourceDocumentOperationLineCreate(
                        line_number=1, item_id=100, qty=Decimal("10")
                    )
                ],
                temporary_item={"name": "test"},
            )
        errors = exc.value.errors()
        assert any(e["type"] == "extra_forbidden" for e in errors)

    def test_no_temporary_item_at_top_level(self):
        """SourceDocumentOperationCreate has NO temporary_item field."""
        field_names = set(SourceDocumentOperationCreate.model_fields.keys())
        assert "temporary_item" not in field_names
        assert "temporary_draft_payload" not in field_names


class TestOperationResponseNewFields:
    """Test that OperationResponse includes new fields."""

    def test_operation_response_has_creation_source(self):
        from app.schemas.operation import OperationResponse
        assert "creation_source" in OperationResponse.model_fields
        field = OperationResponse.model_fields["creation_source"]
        assert field.default == "legacy"

    def test_operation_response_has_source_ref(self):
        from app.schemas.operation import OperationResponse
        assert "source_ref" in OperationResponse.model_fields

    def test_operation_line_response_has_source_fields(self):
        from app.schemas.operation import OperationLineResponse
        source_fields = ["source_item_name", "source_item_sku", "source_unit_name", "source_category_name"]
        for field_name in source_fields:
            assert field_name in OperationLineResponse.model_fields, f"{field_name} missing from OperationLineResponse"
