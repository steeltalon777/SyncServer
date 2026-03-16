from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.balances_repo import BalancesRepo
from app.repos.catalog_repo import CatalogRepo
from app.repos.devices_repo import DevicesRepo
from app.repos.events_repo import EventsRepo
from app.repos.operations_repo import OperationsRepo
from app.repos.sites_repo import SitesRepo
from app.repos.user_site_roles_repo import UserSiteRolesRepo
from app.repos.users_repo import UsersRepo


class UnitOfWork:
    """Unit of work wrapper for a single database transaction."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.sites = SitesRepo(session)
        self.devices = DevicesRepo(session)
        self.events = EventsRepo(session)
        self.catalog = CatalogRepo(session)
        self.balances = BalancesRepo(session)
        self.user_site_roles = UserSiteRolesRepo(session)
        self.operations = OperationsRepo(session)
        self.users = UsersRepo(session)
        self._owns_transaction = False

    async def __aenter__(self) -> "UnitOfWork":
        if not self.session.in_transaction():
            await self.session.begin()
            self._owns_transaction = True
        else:
            self._owns_transaction = False
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if not self._owns_transaction:
            return

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