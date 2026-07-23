"""Tests for source document repository methods.

TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING §11.1 (Gate A1)
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.operation import Operation, OperationLine
from app.repos.operations_repo import OperationsRepo


class TestGetBySourceRef:
    """Tests for OperationsRepo.get_by_source_ref."""

    def test_method_exists(self):
        """get_by_source_ref method exists on OperationsRepo."""
        assert hasattr(OperationsRepo, "get_by_source_ref")

    def test_method_signature(self):
        """get_by_source_ref has expected parameters."""
        import inspect
        sig = inspect.signature(OperationsRepo.get_by_source_ref)
        params = sig.parameters
        assert "source_ref" in params
        assert "creation_source" in params
        assert "created_by_user_id" in params


class TestModelFields:
    """Model field existence tests."""

    def test_operation_has_creation_source(self):
        """Operation model has creation_source column."""
        assert hasattr(Operation, "creation_source")
        col = Operation.__table__.columns.get("creation_source")
        assert col is not None
        assert col.server_default is not None  # has server_default='legacy'

    def test_operation_has_source_ref(self):
        """Operation model has source_ref column."""
        assert hasattr(Operation, "source_ref")
        col = Operation.__table__.columns.get("source_ref")
        assert col is not None
        assert col.nullable is True

    def test_operation_line_has_source_item_name(self):
        """OperationLine model has source_item_name column."""
        assert hasattr(OperationLine, "source_item_name")
        col = OperationLine.__table__.columns.get("source_item_name")
        assert col is not None

    def test_operation_line_has_source_item_sku(self):
        """OperationLine model has source_item_sku column."""
        assert hasattr(OperationLine, "source_item_sku")

    def test_operation_line_has_source_unit_name(self):
        """OperationLine model has source_unit_name column."""
        assert hasattr(OperationLine, "source_unit_name")

    def test_operation_line_has_source_category_name(self):
        """OperationLine model has source_category_name column."""
        assert hasattr(OperationLine, "source_category_name")

    def test_operation_line_has_resolution_mode(self):
        """OperationLine has resolution_mode property."""
        assert hasattr(OperationLine, "resolution_mode")
        line = OperationLine()
        line.temporary_draft_payload = None
        assert line.resolution_mode == "existing_item"
        line.temporary_draft_payload = {"name": "test"}
        assert line.resolution_mode == "inline_item"

    def test_creation_source_has_server_default(self):
        """creation_source column has server_default='legacy'."""
        col = Operation.__table__.columns.get("creation_source")
        assert col is not None
        assert col.server_default is not None
        # Check that server_default text contains 'legacy'
        assert "legacy" in str(col.server_default.arg)
