from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.admin_common import CANONICAL_ROLES, require_admin_basic
from app.api.deps import get_uow, require_user_identity
from app.api.routes_admin_access import router as admin_access_router
from app.api.routes_admin_devices import router as admin_devices_router
from app.api.routes_admin_sites import router as admin_sites_router
from app.api.routes_admin_users import router as admin_users_router
from app.core.identity import Identity
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/roles", response_model=list[str])
async def list_roles(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> list[str]:
    async with uow:
        require_admin_basic(identity)
    return CANONICAL_ROLES


router.include_router(admin_sites_router)
router.include_router(admin_users_router)
router.include_router(admin_access_router)
router.include_router(admin_devices_router)
