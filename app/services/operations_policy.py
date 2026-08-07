from __future__ import annotations

from fastapi import HTTPException, status

from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.services.uow import UnitOfWork


class OperationsPolicy:
    """Centralized access rules for operations and acceptance workflows."""

    # ADR-0030: agent has observer-level business read and draft creation,
    # but no site operate / submit / lifecycle authority.
    READ_ROLES = {"chief_storekeeper", "storekeeper", "observer", "agent"}
    WRITE_ROLES = {"chief_storekeeper", "storekeeper"}
    TEMPORARY_ITEM_CREATE_ROLES = {"chief_storekeeper", "storekeeper"}
    CREATE_DRAFT_ROLES = {"chief_storekeeper", "storekeeper", "observer", "agent"}

    @staticmethod
    def require_read_site(identity: Identity, site_id: int) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in OperationsPolicy.READ_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read operations permission required")

    @staticmethod
    def require_operate_site(identity: Identity, site_id: int) -> None:
        if identity.has_global_business_access:
            return
        if identity.role not in OperationsPolicy.WRITE_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="operate permission required")
        if not identity.can_operate_at_site(site_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user has no operate access to site")

    @staticmethod
    def require_create_draft(identity: Identity, site_id: int) -> None:
        """Allow any authenticated user to create a draft. No scope check."""
        if identity.has_global_business_access:
            return
        if identity.role not in OperationsPolicy.CREATE_DRAFT_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="create draft permission required",
            )

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
    def require_agent_own_draft(identity: Identity, operation) -> None:
        """ADR-0030 / TZ-AGENT-ROLE-SYNCSERVER §6.3, §6.6: agent may touch only
        its own draft operations.

        For non-agent identities this is a no-op (routes call it only inside
        the agent branch). For the agent role the operation must be a draft
        created by the same agent user, otherwise 403.
        """
        if identity.role != "agent":
            return
        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="agent may only modify its own draft operations",
            )
        if operation.created_by_user_id != identity.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="agent may only modify its own draft operations",
            )

    @staticmethod
    def require_operation_submit_permission(identity: Identity, operation) -> None:
        """
        Check submit permission for an operation.

        - root / chief_storekeeper: global submit access (any site, any type).
        - storekeeper: submit allowed when the operation involves a site
          where the storekeeper has operate scope:
            * MOVE: source_site_id OR destination_site_id must be in scope
            * RECEIVE, EXPENSE, WRITE_OFF, ADJUSTMENT, ISSUE, ISSUE_RETURN:
              site_id must be in scope
        - observer and others: forbidden.
        """
        if identity.has_global_business_access:
            return

        if identity.role != "storekeeper":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="only storekeeper, chief_storekeeper, or root may submit operations",
            )

        op_type = operation.operation_type
        site_id = operation.site_id

        if op_type == "MOVE":
            source_in_scope = (
                operation.source_site_id is not None
                and identity.can_operate_at_site(operation.source_site_id)
            )
            dest_in_scope = (
                operation.destination_site_id is not None
                and identity.can_operate_at_site(operation.destination_site_id)
            )
            if source_in_scope or dest_in_scope:
                return
        elif identity.can_operate_at_site(site_id):
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user has no submit permission for this operation site",
        )

    @staticmethod
    def can_view_cancelled_operations(identity: Identity) -> bool:
        """Root can see cancelled operations; non-root cannot."""
        return identity.is_root

    @staticmethod
    def require_cancelled_visibility(identity: Identity) -> None:
        """Raise 403 if identity is not root (for explicit cancelled queries)."""
        if not identity.is_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="only root may view cancelled operations",
            )

    @staticmethod
    def require_operation_delete_permission(identity: Identity, operation) -> None:
        if identity.is_root:
            return
        if identity.role == "chief_storekeeper":
            return
        if identity.role == "storekeeper" and operation.created_by_user_id == identity.user_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the operation creator, chief_storekeeper, or root may delete this cancelled operation",
        )

    @staticmethod
    def require_operation_cancel_permission(identity: Identity, operation) -> None:
        # Already cancelled — workflow policy should prevent this, but guard anyway
        if operation.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="operation is already cancelled",
            )
        # Submitted operations: only root may cancel
        if operation.status == "submitted":
            if identity.is_root:
                return
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="only root may cancel submitted operations",
            )
        # Draft operations: creator, chief_storekeeper, or root
        if identity.has_global_business_access:
            return
        if operation.created_by_user_id == identity.user_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the operation creator, chief_storekeeper, or root may cancel this operation",
        )

    @staticmethod
    def require_root_for_restore(identity: Identity) -> None:
        if identity.role != "root":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="only root can restore cancelled operations",
            )

    @staticmethod
    def require_operation_effective_at_permission(identity: Identity, operation=None) -> None:
        if identity.has_global_business_access:
            return
        if operation is not None and operation.status == "draft" and operation.created_by_user_id == identity.user_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only chief_storekeeper, root, or draft creator may change operation effective_at",
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
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=None),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        return [site.id for site in sites]

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
        if identity.role not in OperationsPolicy.READ_ROLES:
            return []
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=None),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        return [site.id for site in sites]
