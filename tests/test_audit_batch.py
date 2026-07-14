"""Tests for catalog batch audit (Phase 1 §10.6).

applies `uow.batch_correlation_id` so every audit event recorded by
child helpers (item.update, item.create, …) picks up the same id,
then emits one catalog.batch.apply event with outcome=success /
partial depending on per-change status.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.audit_helper import record_audit_event
from app.services.catalog_admin_service import CatalogAdminService
from app.schemas.catalog import (
    CatalogBatchRequest,
    BatchChangeUpdate,
    BatchChangeUpdatePayload,
)


pytestmark = pytest.mark.asyncio


def _make_update_payload(name: str = "Audit Category") -> BatchChangeUpdatePayload:
    return BatchChangeUpdatePayload(name=name)


async def _seed_category(uow, name: str, code: str) -> int:
    from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE
    from app.models.category import Category as CategoryModel
    from sqlalchemy import select

    cat = (
        await uow.session.execute(
            select(CategoryModel).where(CategoryModel.code == code)
        )
    ).scalar_one_or_none()
    if cat is None:
        cat = CategoryModel(name=name, code=code, parent_id=None, sort_order=0, is_active=True)
        uow.session.add(cat)
        await uow.session.flush()
    return cat.id


async def test_batch_correlation_id_picked_up_by_children(uow, test_user):
    """Children inherit uow.batch_correlation_id via record_audit_event."""
    cid = str(uuid4())
    uow.batch_correlation_id = cid
    event = await record_audit_event(
        uow,
        event_type="audit-test.child",
        event_version=2,
        actor_user_id=test_user.id,
        entity_type="test",
        entity_id="1",
        summary="child",
    )
    assert event.correlation_id == cid


async def test_batch_apply_success_outcome(uow, test_user):
    """All-applied batch: outcome=success, one summary event written."""
    cat_id = await _seed_category(uow, "Audit Batch OK", "AUDIT-BATCH-OK")
    service = CatalogAdminService()
    identity = SimpleNamespace(user_id=test_user.id)
    request = CatalogBatchRequest(
        client_batch_id=str(uuid4()),
        changes=[
            BatchChangeUpdate(
                local_id="ok-1",
                entity_id=cat_id,
                entity_type="category",
                action="update",
                payload=_make_update_payload(name=f"Audit Batch OK {uuid4().hex[:4]}"),
            )
        ],
    )
    results, summary = await service.apply_batch(uow, request, identity)
    assert results
    assert summary["error"] == 0
    summary_event = (
        await uow.session.execute(
            __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.__table__.select()
            .where(
                __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.event_type == "catalog.batch.apply"
            )
            .order_by(
                __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.id.desc()
            )
            .limit(1)
        )
    ).first()
    assert summary_event is not None
    assert summary_event[12] == "success"  # outcome column index
    # And the child update should share the same correlation_id
    child = (
        await uow.session.execute(
            __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.__table__.select()
            .where(
                (__import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.event_type == "category.update")
                & (__import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.entity_id == str(cat_id))
            )
            .order_by(
                __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.id.desc()
            )
            .limit(1)
        )
    ).first()
    assert child[13] == summary_event[13]  # correlation_id match
    assert child[13]  # not null


async def test_batch_apply_partial_outcome(uow, test_user):
    """When one change fails, summary event has outcome=partial."""
    service = CatalogAdminService()
    identity = SimpleNamespace(user_id=test_user.id)
    good_cat = await _seed_category(uow, "Audit Batch Mix", "AUDIT-BATCH-MIX")
    request = CatalogBatchRequest(
        client_batch_id=str(uuid4()),
        changes=[
            BatchChangeUpdate(
                local_id="ok-1",
                entity_id=good_cat,
                entity_type="category",
                action="update",
                payload=_make_update_payload(name=f"Audit Batch Mix {uuid4().hex[:4]}"),
            ),
            BatchChangeUpdate(
                local_id="fail-1",
                entity_id=999_999_999,
                entity_type="category",
                action="update",
                payload=_make_update_payload(name="ghost"),
            ),
        ],
    )
    results, summary = await service.apply_batch(uow, request, identity)
    assert summary["error"] == 1
    summary_row = (
        await uow.session.execute(
            __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.__table__.select()
            .where(
                __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.event_type
                == "catalog.batch.apply"
            )
            .order_by(
                __import__("app.models.audit_event", fromlist=["AuditEvent"]).AuditEvent.id.desc()
            )
            .limit(1)
        )
    ).first()
    assert summary_row is not None
    assert summary_row[12] == "partial"


async def test_batch_apply_writes_resource_link(uow, test_user):
    """The batch event has a primary resource edge pointing at the batch entity."""
    cat_id = await _seed_category(uow, "Audit Batch Link", "AUDIT-BATCH-LINK")
    service = CatalogAdminService()
    identity = SimpleNamespace(user_id=test_user.id)
    batch_id = str(uuid4())
    request = CatalogBatchRequest(
        client_batch_id=batch_id,
        changes=[
            BatchChangeUpdate(
                local_id="ok-1",
                entity_id=cat_id,
                entity_type="category",
                action="update",
                payload=_make_update_payload(name=f"Audit Batch Link {uuid4().hex[:4]}"),
            )
        ],
    )
    await service.apply_batch(uow, request, identity)

    from app.models.audit_event import AuditEvent as AuditEventModel
    from app.models.audit_event_resource import AuditEventResource

    batch_event_row = (
        await uow.session.execute(
            AuditEventModel.__table__.select()
            .where(AuditEventModel.event_type == "catalog.batch.apply")
            .order_by(AuditEventModel.id.desc())
            .limit(1)
        )
    ).first()
    batch_entity_id = batch_event_row[8]  # entity_id column

    res_row = (
        await uow.session.execute(
            AuditEventResource.__table__.select()
            .where(
                (AuditEventResource.resource_type == "batch")
                & (AuditEventResource.resource_id == batch_entity_id)
            )
        )
    ).first()
    assert res_row is not None
    assert res_row[4] == "primary"  # relation column
