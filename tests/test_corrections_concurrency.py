from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.repos.corrections_repo import CorrectionsRepo
from app.repos.operation_revisions_repo import OperationRevisionsRepo
from app.services.corrections_service import CorrectionsService
from fastapi import HTTPException


class MockSession:
    def __init__(self):
        self._flushed = False

    async def flush(self):
        self._flushed = True

    async def commit(self):
        pass

    async def rollback(self):
        pass

    def add(self, obj):
        pass

    async def delete(self, obj):
        pass


class TestCorrectionsRepoConcurrency:
    """Tests for corrections repo concurrency features."""

    @pytest.mark.asyncio
    async def test_correction_version_conflict(self):
        """expected_version mismatch → 409."""
        session = MockSession()
        repo = CorrectionsRepo(session)

        correction = MagicMock()
        correction.id = uuid4()
        correction.operation_id = uuid4()
        correction.status = "draft"
        correction.version = 1

        repo.get_correction_by_id_for_update = AsyncMock(return_value=correction)

        with pytest.raises(HTTPException) as exc:
            await repo.update_correction_status(
                correction_id=correction.id,
                status="applied",
                expected_version=2,  # wrong version
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_correction_version_match_succeeds(self):
        """expected_version matches → status updated."""
        session = MockSession()
        repo = CorrectionsRepo(session)

        correction = MagicMock()
        correction.id = uuid4()
        correction.operation_id = uuid4()
        correction.status = "draft"
        correction.version = 1

        repo.get_correction_by_id_for_update = AsyncMock(return_value=correction)

        result = await repo.update_correction_status(
            correction_id=correction.id,
            status="applied",
            expected_version=1,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_abandoned_correction_cannot_be_submitted(self):
        """Submitting an already applied/abandoned correction → 422."""
        session = MockSession()
        repo = CorrectionsRepo(session)
        uow = MagicMock()
        uow.corrections = repo

        correction = MagicMock()
        correction.id = uuid4()
        correction.operation_id = uuid4()
        correction.status = "abandoned"
        correction.version = 1
        correction.base_operation_revision_id = uuid4()
        correction.idempotency_key = None
        correction.lines = []

        uow.corrections.get_correction_by_id_for_update = AsyncMock(
            return_value=correction,
        )
        uow.corrections.get_correction_by_id = AsyncMock(return_value=correction)
        uow.operations = MagicMock()
        uow.operation_revisions = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await CorrectionsService.submit_correction(
                uow=uow,
                correction_id=correction.id,
                user_id=uuid4(),
                expected_version=1,
            )
        assert exc.value.status_code == 422
        assert "already" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_version_bumps_on_each_update(self):
        """Correction version increments on status change."""
        session = MockSession()
        repo = CorrectionsRepo(session)

        correction = MagicMock()
        correction.id = uuid4()
        correction.operation_id = uuid4()
        correction.status = "draft"
        correction.version = 1

        repo.get_correction_by_id_for_update = AsyncMock(return_value=correction)

        await repo.update_correction_status(
            correction_id=correction.id,
            status="draft",
            expected_version=1,
        )
        assert int(correction.version) == 2
