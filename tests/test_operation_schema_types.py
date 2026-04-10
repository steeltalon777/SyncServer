from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.operation import OperationCreate


def _base_payload(operation_type: str, qty: int) -> dict:
    payload = {
        "operation_type": operation_type,
        "site_id": 1,
        "lines": [
            {
                "line_number": 1,
                "item_id": 10,
                "qty": qty,
            }
        ],
    }
    if operation_type == "MOVE":
        payload["source_site_id"] = 1
        payload["destination_site_id"] = 2
    if operation_type in {"ISSUE", "ISSUE_RETURN"}:
        payload["recipient_name"] = "Worker One"
    return payload


def test_operation_create_accepts_new_supported_types() -> None:
    for operation_type in ("RECEIVE", "EXPENSE", "WRITE_OFF", "MOVE", "ADJUSTMENT", "ISSUE", "ISSUE_RETURN"):
        qty = -3 if operation_type == "ADJUSTMENT" else 3
        model = OperationCreate.model_validate(_base_payload(operation_type, qty))
        assert model.operation_type == operation_type


def test_non_adjustment_operations_require_positive_qty() -> None:
    with pytest.raises(ValidationError):
        OperationCreate.model_validate(_base_payload("EXPENSE", -2))


def test_adjustment_allows_negative_qty() -> None:
    model = OperationCreate.model_validate(_base_payload("ADJUSTMENT", -5))
    assert model.lines[0].qty == -5


def test_all_operations_reject_zero_qty() -> None:
    with pytest.raises(ValidationError):
        OperationCreate.model_validate(_base_payload("ADJUSTMENT", 0))


def test_operation_create_accepts_optional_effective_at() -> None:
    effective_at = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)
    payload = _base_payload("RECEIVE", 3)
    payload["effective_at"] = effective_at.isoformat()

    model = OperationCreate.model_validate(payload)

    assert model.effective_at == effective_at
