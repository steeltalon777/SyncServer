from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_state import SyncState


class SyncStateRepo:
    """Data access for per-device sync state (ADR-0016).

    Tracks per-device sync progress: last consumed server_seq, last activity
    timestamps, status and last error. Used by /api/v1/ping, /push, /pull
    to keep device state observable, and exposed via /api/v1/sync/status.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_device_id(self, device_id: int) -> SyncState | None:
        result = await self.session.execute(
            select(SyncState).where(SyncState.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        device_id: int,
        last_sequence_number: int,
        status: str = "online",
        last_error: str | None = None,
        last_sync_at: datetime | None = None,
    ) -> SyncState:
        """INSERT … ON CONFLICT (device_id) DO UPDATE.

        Monotonic invariant: ``last_sequence_number`` is never decreased
        (it represents the highest server_seq the device has observed).
        Uses ``GREATEST(excluded, sync_state)`` to enforce monotonicity
        atomically inside a single SQL statement.
        """
        ts = last_sync_at or datetime.now(UTC)
        # Truncate last_error to keep the column small and prevent abuse.
        truncated_error = last_error[:1000] if last_error else None

        values: dict[str, Any] = {
            "device_id": device_id,
            "last_sequence_number": last_sequence_number,
            "last_sync_at": ts,
            "status": status,
            "last_error": truncated_error,
        }

        stmt = (
            pg_insert(SyncState)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[SyncState.device_id],
                set_={
                    "last_sequence_number": func.greatest(
                        SyncState.last_sequence_number,
                        pg_insert(SyncState).excluded.last_sequence_number,
                    ),
                    "last_sync_at": pg_insert(SyncState).excluded.last_sync_at,
                    "status": pg_insert(SyncState).excluded.status,
                    "last_error": pg_insert(SyncState).excluded.last_error,
                    "updated_at": func.now(),
                },
            )
            .returning(SyncState)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()
