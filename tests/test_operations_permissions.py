from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes_operations import (
    _require_operation_cancel_permission,
    _require_operation_effective_at_permission,
    _require_operation_owner_or_supervisor,
    _require_operation_submit_permission,
    _require_operate_site,
)
from app.core.identity import Identity
from app.models.user import User
from app.models.user_access_scope import UserAccessScope


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

    _require_operate_site(identity, 10)


def test_chief_storekeeper_has_global_operational_access() -> None:
    identity = _identity(role="chief_storekeeper")

    _require_operate_site(identity, 999)
    _require_operation_submit_permission(identity)


def test_storekeeper_cannot_submit_operations() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    with pytest.raises(HTTPException) as exc:
        _require_operation_submit_permission(identity)

    assert exc.value.status_code == 403


def test_storekeeper_cannot_change_operation_effective_at() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    with pytest.raises(HTTPException) as exc:
        _require_operation_effective_at_permission(identity)

    assert exc.value.status_code == 403


def test_chief_storekeeper_can_change_operation_effective_at() -> None:
    identity = _identity(role="chief_storekeeper")

    _require_operation_effective_at_permission(identity)


def test_storekeeper_may_update_only_own_draft() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])
    own_operation = _operation(identity.user_id, status="draft")
    other_operation = _operation(uuid4(), status="draft")

    _require_operation_owner_or_supervisor(identity, own_operation)

    with pytest.raises(HTTPException) as exc:
        _require_operation_owner_or_supervisor(identity, other_operation)

    assert exc.value.status_code == 403


def test_storekeeper_may_cancel_only_own_draft_not_submitted() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])
    own_draft = _operation(identity.user_id, status="draft")
    own_submitted = _operation(identity.user_id, status="submitted")

    _require_operation_cancel_permission(identity, own_draft)

    with pytest.raises(HTTPException) as exc:
        _require_operation_cancel_permission(identity, own_submitted)

    assert exc.value.status_code == 403
