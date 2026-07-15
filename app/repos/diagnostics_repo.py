from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagnostics import DiagnosticEvent


class DiagnosticsRepo:
    """Repository for diagnostic UI events (append-only)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def bulk_insert(self, events: list[dict]) -> int:
        """Insert events with INSERT ... ON CONFLICT (event_id) DO NOTHING.

        Returns the number of actually inserted rows.
        """
        if not events:
            return 0

        stmt = (
            pg_insert(DiagnosticEvent)
            .values(events)
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        # pg_insert returns result.rowcount (number of inserted rows)
        return result.rowcount or 0

    async def count_for_session(self, session_id: UUID) -> int:
        """Count events for a given session (used for rate limiting)."""
        stmt = (
            select(func.count())
            .select_from(DiagnosticEvent)
            .where(DiagnosticEvent.session_id == session_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
