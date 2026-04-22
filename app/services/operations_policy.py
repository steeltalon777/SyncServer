from __future__ import annotations

from fastapi import HTTPException, status

from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.services.uow import UnitOfWork


class OperationsPolicy:
    """Centralized access rules for operations and acceptance workflows."""

    READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}
    WRITE_ROLES = {"chief_storekeeper", "storekeeper"}
    TEMPORARY_ITEM_CREATE_ROLES = {"chief_storekeeper", "storekeeper"}

    @staticmethod
    def require_read_site(identity: Identity, site_id: int) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in OperationsPolicy.READ_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read operations permission required")
        if not identity.has_site_access(site_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user has no view access to site")

    @staticmethod
    def require_operate_site(identity: Identity, site_id: int) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in OperationsPolicy.WRITE_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="operate permission required")
        if not identity.can_operate_at_site(site_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user has no operate access to site")

    @staticmethod
    def require_move_access(identity: Identity, source_site_id: int | None, destination_site_id: int | None) -> None:
        if source_site_id is None or destination_site_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="MOVE operation requires source_site_id and destination_site_id",
            )
        OperationsPolicy.require_operate_site(identity, source_site_id)

    @staticmethod
    def require_acceptance_site(identity: Identity, destination_site_id: int) -> None:
        if identity.has_global_business_access:
            return
        if not identity.can_accept_at_site(destination_site_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="acceptance permission required for destination site",
            )

    @staticmethod
    def require_operation_owner_or_supervisor(identity: Identity, operation) -> None:
        if identity.has_global_business_access:
            return
        if operation.created_by_user_id != identity.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="only the operation creator, chief_storekeeper, or root may modify this draft",
            )

    @staticmethod
    def require_operation_submit_permission(identity: Identity) -> None:
        if identity.has_global_business_access:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only chief_storekeeper or root may submit operations",
        )

    @staticmethod
    def require_operation_cancel_permission(identity: Identity, operation) -> None:
        if identity.has_global_business_access:
            return
        if operation.status == "draft" and operation.created_by_user_id == identity.user_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only chief_storekeeper or root may cancel submitted or other users operations",
        )

    @staticmethod
    def require_operation_effective_at_permission(identity: Identity) -> None:
        if identity.has_global_business_access:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only chief_storekeeper or root may change operation effective_at",
        )

    @staticmethod
    def require_temporary_item_create(identity: Identity) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in OperationsPolicy.TEMPORARY_ITEM_CREATE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="temporary item creation is forbidden for current role",
            )

    @staticmethod
    def require_temporary_item_moderation(identity: Identity, site_id: int | None = None) -> None:
        if identity.has_global_business_access:
            return
        if identity.role != "chief_storekeeper":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="temporary item moderation requires chief_storekeeper or root",
            )
        if site_id is not None and not identity.can_manage_catalog_at_site(site_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="temporary item moderation requires catalog management access",
            )

    @staticmethod
    def require_assets_read_access(identity: Identity) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in OperationsPolicy.READ_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read assets permission required")

    @staticmethod
    def require_lost_resolve_access(identity: Identity) -> None:
        if identity.has_global_business_access:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only chief_storekeeper or root may resolve lost assets",
        )

    @staticmethod
    async def resolve_readable_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
        if identity.has_global_business_access:
            sites, _ = await uow.sites.list_sites(
                filter=SiteFilter(is_active=None),
                user_site_ids=None,
                page=1,
                page_size=1000,
            )
            return [site.id for site in sites]
        if identity.role not in OperationsPolicy.READ_ROLES:
            return []
        return identity.get_accessible_site_ids()

    @staticmethod
    async def resolve_visible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
        if identity.has_global_business_access:
            sites, _ = await uow.sites.list_sites(
                filter=SiteFilter(is_active=None),
                user_site_ids=None,
                page=1,
                page_size=1000,
            )
            return [site.id for site in sites]

        scopes = list(await uow.user_access_scopes.list_user_scopes(identity.user_id))
        return [scope.site_id for scope in scopes if scope.is_active and scope.can_view]
