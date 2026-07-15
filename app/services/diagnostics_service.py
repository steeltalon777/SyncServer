from __future__ import annotations

from app.services.uow import UnitOfWork


class DiagnosticsService:
    """Service for diagnostic UI events.

    Append-only log: events are inserted in bulk and never updated.
    """

    @staticmethod
    async def bulk_insert(uow: UnitOfWork, events: list[dict]) -> int:
        """Bulk-insert events with idempotency on event_id.

        Returns the number of newly inserted rows.
        """
        if not events:
            return 0
        return await uow.diagnostics.bulk_insert(events)

    @staticmethod
    async def count_for_session(uow: UnitOfWork, session_id) -> int:
        """Count events for a given session (used for rate limiting)."""
        return await uow.diagnostics.count_for_session(session_id)
