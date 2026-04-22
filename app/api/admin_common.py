from __future__ import annotations

from fastapi import HTTPException, status

from app.core.identity import Identity
from app.models.user import User
from app.schemas.admin import UserWithTokenResponse


CANONICAL_ROLES = [
    "root",
    "chief_storekeeper",
    "storekeeper",
    "observer",
]


def require_admin_basic(identity: Identity) -> None:
    if identity.is_root:
        return
    if identity.role != "chief_storekeeper":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin access denied",
        )


def user_with_token_payload(user: User) -> UserWithTokenResponse:
    return UserWithTokenResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_root=user.is_root,
        role=user.role,
        default_site_id=user.default_site_id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        user_token=user.user_token,
    )
