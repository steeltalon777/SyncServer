from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.operations_service import OperationsService


def _operation(*, status: str = "cancelled") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        operation_type="RECEIVE",
        site_id=1,
        source_site_id=None,
        destination_site_id=None,
        acceptance_required=False,
    )


@pytest.mark.asyncio
async def test_delete_operation_succeeds_for_cancelled() -> None:
    operation = _operation(status="cancelled")
    uow = SimpleNamespace(
        operations=SimpleNamespace(
            get_operation_by_id=AsyncMock(return_value=operation),
            soft_delete_operation=AsyncMock(),
        ),
    )

    user_id = uuid4()
    await OperationsService.delete_operation(uow=uow, operation_id=operation.id, user_id=user_id)

    uow.operations.soft_delete_operation.assert_awaited_once_with(
        operation_id=operation.id,
        deleted_by_user_id=user_id,
    )


@pytest.mark.asyncio
async def test_delete_operation_rejects_draft() -> None:
    operation = _operation(status="draft")
    uow = SimpleNamespace(
        operations=SimpleNamespace(
            get_operation_by_id=AsyncMock(return_value=operation),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await OperationsService.delete_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_operation_rejects_submitted() -> None:
    operation = _operation(status="submitted")
    uow = SimpleNamespace(
        operations=SimpleNamespace(
            get_operation_by_id=AsyncMock(return_value=operation),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await OperationsService.delete_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_operation_rejects_missing() -> None:
    uow = SimpleNamespace(
        operations=SimpleNamespace(
            get_operation_by_id=AsyncMock(return_value=None),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await OperationsService.delete_operation(uow=uow, operation_id=uuid4(), user_id=uuid4())

    assert exc.value.status_code == 404
