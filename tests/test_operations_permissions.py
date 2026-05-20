from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.identity import Identity
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from app.services.operations_policy import OperationsPolicy


def _identity(
    *,
    role: str,
    is_root: bool = False,
    scopes: list[UserAccessScope] | None = None,
) -> Identity:
    user = User(
        username=f"{role}-{uuid4().hex[:6]}",
        email=f"{role}-{uuid4().hex[:6]}@example.com",
        full_name=role,
        is_active=True,
        is_root=is_root,
        role=role,
        default_site_id=None,
    )
    return Identity.from_user_and_device(user=user, device=None, scopes=scopes or [])


def _scope(site_id: int, *, can_view: bool = True, can_operate: bool = True) -> UserAccessScope:
    return UserAccessScope(
        user_id=uuid4(),
        site_id=site_id,
        can_view=can_view,
        can_operate=can_operate,
        can_manage_catalog=False,
        is_active=True,
    )


def _operation(created_by_user_id, *, status: str = "draft"):
    return SimpleNamespace(
        created_by_user_id=created_by_user_id,
        status=status,
    )


def test_storekeeper_can_create_operation_on_scoped_site() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    OperationsPolicy.require_operate_site(identity, 10)


def test_chief_storekeeper_has_global_operational_access() -> None:
    identity = _identity(role="chief_storekeeper")

    OperationsPolicy.require_operate_site(identity, 999)
    OperationsPolicy.require_operation_submit_permission(identity)


def test_storekeeper_cannot_submit_operations() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_submit_permission(identity)

    assert exc.value.status_code == 403


def test_storekeeper_cannot_change_operation_effective_at() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_effective_at_permission(identity)

    assert exc.value.status_code == 403


def test_chief_storekeeper_can_change_operation_effective_at() -> None:
    identity = _identity(role="chief_storekeeper")

    OperationsPolicy.require_operation_effective_at_permission(identity)


def test_storekeeper_may_update_only_own_draft() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])
    own_operation = _operation(identity.user_id, status="draft")
    other_operation = _operation(uuid4(), status="draft")

    OperationsPolicy.require_operation_owner_or_supervisor(identity, own_operation)

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_owner_or_supervisor(identity, other_operation)

    assert exc.value.status_code == 403


def test_storekeeper_may_cancel_only_own_draft_not_submitted() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])
    own_draft = _operation(identity.user_id, status="draft")
    own_submitted = _operation(identity.user_id, status="submitted")

    OperationsPolicy.require_operation_cancel_permission(identity, own_draft)

    # storekeeper cannot cancel own submitted — root-only
    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_cancel_permission(identity, own_submitted)

    assert exc.value.status_code == 403
    assert "only root" in exc.value.detail.lower()


def test_chief_storekeeper_can_cancel_own_draft_but_not_submitted() -> None:
    identity = _identity(role="chief_storekeeper")
    own_draft = _operation(identity.user_id, status="draft")
    own_submitted = _operation(identity.user_id, status="submitted")

    # chief can cancel own draft (has_global_business_access)
    OperationsPolicy.require_operation_cancel_permission(identity, own_draft)

    # chief cannot cancel submitted — root-only
    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_cancel_permission(identity, own_submitted)

    assert exc.value.status_code == 403
    assert "only root" in exc.value.detail.lower()


def test_root_can_cancel_submitted_draft_and_own_draft() -> None:
    identity = _identity(role="storekeeper", is_root=True)

    submitted_op = _operation(uuid4(), status="submitted")
    draft_op = _operation(uuid4(), status="draft")
    own_draft = _operation(identity.user_id, status="draft")

    # root can cancel submitted
    OperationsPolicy.require_operation_cancel_permission(identity, submitted_op)
    # root can cancel any draft
    OperationsPolicy.require_operation_cancel_permission(identity, draft_op)
    # root can cancel own draft
    OperationsPolicy.require_operation_cancel_permission(identity, own_draft)


def test_creator_can_cancel_own_draft() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])
    own_draft = _operation(identity.user_id, status="draft")

    OperationsPolicy.require_operation_cancel_permission(identity, own_draft)


def test_storekeeper_cannot_cancel_other_draft() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])
    other_draft = _operation(uuid4(), status="draft")

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_cancel_permission(identity, other_draft)

    assert exc.value.status_code == 403


def test_storekeeper_can_accept_only_at_target_site_with_operate_scope() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(20)])

    OperationsPolicy.require_acceptance_site(identity, 20)

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_acceptance_site(identity, 21)

    assert exc.value.status_code == 403


def test_observer_cannot_accept_even_with_view_scope() -> None:
    identity = _identity(role="observer", scopes=[_scope(20, can_operate=False)])

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_acceptance_site(identity, 20)

    assert exc.value.status_code == 403


def test_root_can_accept_without_site_scope() -> None:
    identity = _identity(role="storekeeper", is_root=True)

    OperationsPolicy.require_acceptance_site(identity, 999)


def test_root_can_delete_any_cancelled_operation() -> None:
    identity = _identity(role="storekeeper", is_root=True)
    op = _operation(uuid4(), status="cancelled")

    OperationsPolicy.require_operation_delete_permission(identity, op)


def test_chief_storekeeper_cannot_delete_cancelled_operation() -> None:
    identity = _identity(role="chief_storekeeper")
    op = _operation(uuid4(), status="cancelled")

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_delete_permission(identity, op)

    assert exc.value.status_code == 403


def test_storekeeper_cannot_delete_cancelled_operation() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])
    op = _operation(identity.user_id, status="cancelled")

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_delete_permission(identity, op)

    assert exc.value.status_code == 403


def test_cancel_on_already_cancelled_operation_raises_conflict() -> None:
    identity = _identity(role="root", is_root=True)
    cancelled_op = _operation(uuid4(), status="cancelled")

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_cancel_permission(identity, cancelled_op)

    assert exc.value.status_code == 409


# New: cancelled visibility helpers

def test_can_view_cancelled_root() -> None:
    identity = _identity(role="root", is_root=True)
    assert OperationsPolicy.can_view_cancelled_operations(identity) is True


def test_can_view_cancelled_non_root() -> None:
    identity = _identity(role="chief_storekeeper")
    assert OperationsPolicy.can_view_cancelled_operations(identity) is False

    identity = _identity(role="storekeeper")
    assert OperationsPolicy.can_view_cancelled_operations(identity) is False

    identity = _identity(role="observer")
    assert OperationsPolicy.can_view_cancelled_operations(identity) is False


def test_require_cancelled_visibility_root_passes() -> None:
    identity = _identity(role="root", is_root=True)
    OperationsPolicy.require_cancelled_visibility(identity)


def test_require_cancelled_visibility_non_root_raises() -> None:
    for role in ("chief_storekeeper", "storekeeper", "observer"):
        identity = _identity(role=role)
        with pytest.raises(HTTPException) as exc:
            OperationsPolicy.require_cancelled_visibility(identity)
        assert exc.value.status_code == 403
