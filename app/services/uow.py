from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.asset_registers_repo import AssetRegistersRepo
from app.repos.audit_events_repo import AuditEventsRepo
from app.repos.balances_repo import BalancesRepo
from app.repos.catalog_repo import CatalogRepo
from app.repos.devices_repo import DevicesRepo
from app.repos.documents_repo import DocumentsRepo
from app.repos.events_repo import EventsRepo
from app.repos.inventory_subjects_repo import InventorySubjectsRepo
from app.repos.machine_repo import MachineRepo
from app.repos.operations_repo import OperationsRepo
from app.repos.issue_object_categories_repo import IssueObjectCategoriesRepo
from app.repos.issue_objects_repo import IssueObjectsRepo
from app.repos.reports_repo import ReportsRepo
from app.repos.sites_repo import SitesRepo
from app.repos.sync_state_repo import SyncStateRepo
from app.repos.temporary_items_repo import TemporaryItemsRepo
from app.repos.user_access_scopes_repo import UserAccessScopesRepo
from app.repos.users_repo import UsersRepo


class UnitOfWork:
    """Unit of work wrapper for a single database transaction."""

    def __init__(self, session: AsyncSession):
        self.session = session

        # batch_correlation_id is an audit-scoped context slot set by
        # catalog batch apply before processing individual changes. Every
        # audit event recorded inside this UoW inherits this id unless the
        # caller passes an explicit correlation_id. This is a lightweight
        # alternative to threading the id through every helper signature.
        self.batch_correlation_id: str | None = None

        # Audit context slots for system-generated flows (item.merge,
        # temporary item resolution, review merge). When set, every audit
        # event written by submit_operation/cancel_operation/record_audit_event
        # inherits these values. This lets merge orchestration attach itself as
        # the parent event for the system ADJUSTMENT events it triggers without
        # changing every helper signature.
        self.audit_parent_event_id: "UUID | None" = None
        self.audit_caused_by_event_id: int | None = None
        self.audit_effect_type_override: str | None = None

        self.sites = SitesRepo(session)
        self.devices = DevicesRepo(session)
        self.audit_events = AuditEventsRepo(session)
        self.events = EventsRepo(session)
        self.inventory_subjects = InventorySubjectsRepo(session)
        self.catalog = CatalogRepo(session)
        self.balances = BalancesRepo(session)
        self.asset_registers = AssetRegistersRepo(session)
        self.user_access_scopes = UserAccessScopesRepo(session)
        self.operations = OperationsRepo(session)
        self.issue_objects = IssueObjectsRepo(session)
        self.issue_object_categories = IssueObjectCategoriesRepo(session)
        self.reports = ReportsRepo(session)
        self.machine = MachineRepo(session)
        self.users = UsersRepo(session)
        self.documents = DocumentsRepo(session)
        self.temporary_items = TemporaryItemsRepo(session)
        self.sync_state = SyncStateRepo(session)

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            await self.session.commit()
        else:
            await self.session.rollback()

    async def commit(self) -> None:
        if self.session.in_transaction():
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session.in_transaction():
            await self.session.rollback()
