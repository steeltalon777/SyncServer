from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.operations_workflow_policy import OperationsWorkflowPolicy


def _operation(*, status: str = "draft", acceptance_required: bool = False, acceptance_state: str = "pending"):
    return SimpleNamespace(
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


def test_cancel_rejects_already_cancelled_operation() -> None:
    operation = _operation(status="cancelled")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_not_cancelled_for_cancel(operation)

    assert exc.value.status_code == 409
    assert exc.value.detail == "operation is already cancelled"


def test_effective_at_change_rejects_cancelled_operation() -> None:
    operation = _operation(status="cancelled")

    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_not_cancelled_for_effective_at_change(operation)

    assert exc.value.status_code == 409
    assert exc.value.detail == "cannot change effective_at for cancelled operation"


def test_exists_guard_rejects_missing_operation() -> None:
    with pytest.raises(HTTPException) as exc:
        OperationsWorkflowPolicy.require_exists(None)

    assert exc.value.status_code == 404
    assert exc.value.detail == "operation not found"
