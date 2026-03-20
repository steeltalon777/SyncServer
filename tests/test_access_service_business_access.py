from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.access_service import AccessService


@pytest.mark.asyncio
async def test_access_service_grants_global_business_permissions_to_chief_storekeeper() -> None:
    user_id = uuid4()
    chief_user = SimpleNamespace(
        id=user_id,
        is_active=True,
        is_root=False,
        role="chief_storekeeper",
    )
    site = SimpleNamespace(id=10)
    uow = SimpleNamespace(
        users=SimpleNamespace(get_by_id=AsyncMock(return_value=chief_user)),
        user_access_scopes=SimpleNamespace(
            get_by_user_and_site=AsyncMock(return_value=None),
            list_accessible_site_ids=AsyncMock(return_value=[]),
        ),
        sites=SimpleNamespace(list_sites=AsyncMock(return_value=([site], 1))),
    )
    service = AccessService(uow)

    assert await service.can_view_site(user_id, 10) is True
    assert await service.can_operate_site(user_id, 10) is True
    assert await service.can_manage_catalog(user_id, 10) is True

    permissions = await service.get_user_permissions_uuid(user_id, 10)
    assert permissions == {
        "can_read_operations": True,
        "can_create_operations": True,
        "can_read_balances": True,
        "can_manage_catalog": True,
        "can_manage_root_admin": False,
        "is_root": False,
    }

    accessible_site_ids = await service.list_accessible_site_ids(user_id)
    assert accessible_site_ids == [10]
