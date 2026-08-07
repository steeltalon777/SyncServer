from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.operation_submit_errors import OperationInWrongStateError, OperationNotFoundError
from app.services.operations_workflow_policy import OperationsWorkflowPolicy


def _operation(*, status: str = "draft", acceptance_required: bool = False, acceptance_state: str = "pending"):
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        acceptance_required=acceptance_required,
        acceptance_state=acceptance_state,
    )


def test_update_requires_draft_status() -> None:
    operation = _operation(status="submitted")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_draft_for_update(operation)

    assert exc.value.status_code == 409
    assert exc.value.detail == "cannot update operation with status submitted"


def test_submit_requires_draft_status() -> None:
    operation = _operation(status="cancelled")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_draft_for_submit(operation)

    assert exc.value.status_code == 409
    assert exc.value.detail == "operation is already cancelled"


def test_acceptance_requires_submitted_operation() -> None:
    operation = _operation(status="draft", acceptance_required=True)

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_submitted_for_acceptance(operation)

    assert exc.value.status_code == 409
    assert exc.value.detail == "only submitted operations can be accepted"


def test_acceptance_requires_acceptance_flag() -> None:
    operation = _operation(status="submitted", acceptance_required=False)

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_acceptance_required(operation)

    assert exc.value.status_code == 409
    assert exc.value.detail == "operation does not require acceptance"


def test_acceptance_requires_unresolved_state() -> None:
    operation = _operation(status="submitted", acceptance_required=True, acceptance_state="resolved")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_acceptance_not_resolved(operation)

    assert exc.value.status_code == 409
    assert exc.value.detail == "operation is already fully accepted"


def test_delete_requires_cancelled_status() -> None:
    operation = _operation(status="draft")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_cancelled_for_delete(operation)

    assert exc.value.status_code == 409
    assert "cancelled" in exc.value.detail


def test_delete_accepts_cancelled_status() -> None:
    operation = _operation(status="cancelled")

    OperationsWorkflowPolicy.require_cancelled_for_delete(operation)


def test_delete_rejects_submitted_operation() -> None:
    operation = _operation(status="submitted")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_cancelled_for_delete(operation)

    assert exc.value.status_code == 409


def test_cancel_rejects_already_cancelled_operation() -> None:
    operation = _operation(status="cancelled")

    with pytest.raises(OperationInWrongStateError) as exc:
        OperationsWorkflowPolicy.require_not_cancelled_for_cancel(operation)

    assert not isinstance(exc.value, HTTPException)
    assert exc.value.http_status == 409
    assert exc.value.current_state == "cancelled"
    assert exc.value.allowed_states == ["draft", "submitted"]
    assert exc.value.problem_class == "operation-cancel-rejected"
    envelope = exc.value.to_envelope()
    assert envelope.code == "operation_cancel_rejected"
    assert envelope.errors[0].code == "operation_in_wrong_state"
    assert envelope.errors[0].current_state == "cancelled"
    assert envelope.errors[0].allowed_states == ["draft", "submitted"]


def test_cancel_accepts_non_cancelled_operation() -> None:
    for status in ("draft", "submitted"):
        OperationsWorkflowPolicy.require_not_cancelled_for_cancel(_operation(status=status))


def test_effective_at_change_allows_draft() -> None:
    """ADR-0028 §2: effective_at change is allowed for draft operations."""

    operation = _operation(status="draft")

    OperationsWorkflowPolicy.require_draft_for_effective_at_change(operation)


def test_effective_at_change_rejects_submitted() -> None:
    """ADR-0028 §2: submitted operations are fail-closed for effective_at."""

    operation = _operation(status="submitted")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_draft_for_effective_at_change(operation)

    assert exc.value.status_code == 409
    assert "effective_at" in exc.value.detail
    assert "submitted" in exc.value.detail


def test_effective_at_change_rejects_cancelled() -> None:
    """ADR-0028 §2: cancelled operations are fail-closed for effective_at."""

    operation = _operation(status="cancelled")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_draft_for_effective_at_change(operation)

    assert exc.value.status_code == 409
    assert "effective_at" in exc.value.detail
    assert "cancelled" in exc.value.detail


def test_effective_at_change_rejects_unknown_status() -> None:
    """ADR-0028 §2: unknown/legacy status is fail-closed (defensive default)."""

    operation = _operation(status="legacy_unknown")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_draft_for_effective_at_change(operation)

    assert exc.value.status_code == 409
    assert "effective_at" in exc.value.detail
    assert "legacy_unknown" in exc.value.detail


def test_exists_guard_rejects_missing_operation() -> None:
    with pytest.raises(OperationNotFoundError) as exc:
        OperationsWorkflowPolicy.require_exists(None)

    assert not isinstance(exc.value, HTTPException)
    assert exc.value.http_status == 404
    assert exc.value.operation_id is None
    assert exc.value.problem_class == "operation-not-found"
    envelope = exc.value.to_envelope()
    assert envelope.type == "urn:warehouse:problem:operation-not-found"
    assert envelope.code == "operation_not_found"
    assert envelope.errors[0].code == "operation_not_found"


def test_exists_guard_accepts_existing_operation() -> None:
    operation = _operation(status="draft")
    OperationsWorkflowPolicy.require_exists(operation)
