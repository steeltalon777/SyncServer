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


def test_storekeeper_can_read_operation_on_any_site() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    OperationsPolicy.require_read_site(identity, 999)


@pytest.mark.asyncio
async def test_operation_read_site_ids_include_all_sites_regardless_of_scope() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    class SitesRepo:
        async def list_sites(self, **kwargs):
            return [SimpleNamespace(id=10), SimpleNamespace(id=999)], 2

    uow = SimpleNamespace(sites=SitesRepo())

    site_ids = await OperationsPolicy.resolve_readable_site_ids(uow, identity)

    assert site_ids == [10, 999]


@pytest.mark.asyncio
async def test_asset_visible_site_ids_include_all_sites_regardless_of_scope() -> None:
    identity = _identity(role="storekeeper", scopes=[_scope(10)])

    class SitesRepo:
        async def list_sites(self, **kwargs):
            return [SimpleNamespace(id=10), SimpleNamespace(id=999)], 2

    uow = SimpleNamespace(sites=SitesRepo())

    site_ids = await OperationsPolicy.resolve_visible_site_ids(uow, identity)

    assert site_ids == [10, 999]


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

    with pytest.raises(HTTPException) as exc:
        OperationsPolicy.require_operation_cancel_permission(identity, own_submitted)

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


@pytest.mark.asyncio
async def test_acceptance_site_ids_use_operate_scopes_only() -> None:
    identity = _identity(
        role="storekeeper",
        scopes=[
            _scope(10, can_view=True, can_operate=True),
            _scope(20, can_view=True, can_operate=False),
        ],
    )

    class ScopesRepo:
        async def list_user_scopes(self, user_id):
            return identity.scopes

    uow = SimpleNamespace(user_access_scopes=ScopesRepo())

    site_ids = await OperationsPolicy.resolve_acceptance_site_ids(uow, identity)

    assert site_ids == [10]


@pytest.mark.asyncio
async def test_chief_acceptance_site_ids_include_all_sites() -> None:
    identity = _identity(role="chief_storekeeper")

    class SitesRepo:
        async def list_sites(self, **kwargs):
            return [SimpleNamespace(id=10), SimpleNamespace(id=20)], 2

    uow = SimpleNamespace(sites=SitesRepo())

    site_ids = await OperationsPolicy.resolve_acceptance_site_ids(uow, identity)

    assert site_ids == [10, 20]


def test_root_can_accept_without_site_scope() -> None:
    identity = _identity(role="storekeeper", is_root=True)

    OperationsPolicy.require_acceptance_site(identity, 999)
