from uuid import uuid4

from app.core.identity import Identity
from app.models.user import User


def _identity(*, role: str, is_root: bool = False) -> Identity:
    user = User(
        username=f"{role}-{uuid4().hex[:6]}",
        email=f"{role}@example.com",
        full_name=role,
        is_active=True,
        is_root=is_root,
        role=role,
        default_site_id=None,
    )
    return Identity.from_user_and_device(user=user, device=None, scopes=[])


def test_chief_storekeeper_has_global_business_access() -> None:
    identity = _identity(role="chief_storekeeper")

    assert identity.has_global_business_access is True
    assert identity.has_site_access(100) is True
    assert identity.can_operate_at_site(100) is True
    assert identity.can_manage_catalog_at_site(100) is True
    assert identity.get_accessible_site_ids() == []


def test_storekeeper_remains_site_scoped() -> None:
    identity = _identity(role="storekeeper")

    assert identity.has_global_business_access is False
    assert identity.has_site_access(100) is False
    assert identity.can_operate_at_site(100) is False
    assert identity.can_manage_catalog_at_site(100) is False
