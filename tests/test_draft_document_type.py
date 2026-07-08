"""TZ-V3.1I rev. 2 (Stage I5.2): guard tests for draft document type map.

After I3.1 narrowing DRAFT_DOCUMENT_TYPE_BY_OPERATION to {MOVE, ISSUE, ISSUE_RETURN},
EXPENSE/RECEIVE/WRITE_OFF/ADJUSTMENT must NOT generate draft documents at create or
update time. Submit EXPENSE must still produce a finalized "act" reflecting the
post-edit state.
"""
from decimal import Decimal

import pytest

from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit
from app.schemas.operation import OperationCreate, OperationLineCreate, OperationUpdate
from app.services.operations_service import OperationsService


async def _create_catalog_fixture(uow, *, unit_name: str, unit_symbol: str, category_name: str, item_name: str, item_sku: str, is_active: bool = True):
    """Создать минимальный набор (unit, category, item) для строк операций."""
    unit = await uow.catalog.create_unit(
        Unit(
            name=unit_name,
            symbol=unit_symbol,
            is_active=is_active,
        )
    )

    category = await uow.catalog.create_category(
        Category(
            name=category_name,
            normalized_name=category_name.lower(),
            is_active=is_active,
        )
    )

    item = await uow.catalog.create_item(
        Item(
            name=item_name,
            normalized_name=item_name.lower(),
            sku=item_sku,
            category_id=category.id,
            unit_id=unit.id,
            is_active=is_active,
        )
    )
    return unit, category, item


@pytest.mark.asyncio
async def test_create_draft_expense_has_no_waybill_draft(
    uow,
    site,
    user,
):
    """rev. 2 (blocker #1): EXPENSE draft не должен порождать draft-документ.

    Если бы порождал — на submit draft act был бы финализирован in-place
    без пересборки payload (потеря правок черновика). Плюс draft waybills
    от H1 не войдируются void-фильтром по типу.
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Draft Unit",
        unit_symbol="DU",
        category_name="Draft Category",
        item_name="Expense Item",
        item_sku="EXP-001",
    )

    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="EXPENSE",
            site_id=site.id,
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=Decimal("5"),
                ),
            ],
        ),
        user_id=user.id,
    )

    docs = await uow.documents.get_documents_by_operation(operation["operation"].id)
    assert len(docs) == 0, f"EXPENSE draft не должен иметь документов, got {len(docs)}"


@pytest.mark.asyncio
async def test_create_draft_receive_has_no_waybill_draft(
    uow,
    site,
    user,
):
    """RECEIVE не маппится в waybill на стадии draft; acceptance_certificate
    появится на submit.
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Receive Unit",
        unit_symbol="RU",
        category_name="Receive Category",
        item_name="Receive Item",
        item_sku="REC-001",
    )

    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="RECEIVE",
            site_id=site.id,
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=Decimal("5"),
                ),
            ],
        ),
        user_id=user.id,
    )

    docs = await uow.documents.get_documents_by_operation(operation["operation"].id)
    assert len(docs) == 0, f"RECEIVE draft не должен иметь документов, got {len(docs)}"


@pytest.mark.asyncio
async def test_update_draft_expense_does_not_create_waybill(
    uow,
    site,
    user,
):
    """rev. 2 (warning #2): H1 в update_operation тоже идёт через helper —
    EXPENSE не получает waybill при update.
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Expense Upd Unit",
        unit_symbol="EUU",
        category_name="Expense Upd Category",
        item_name="Expense Upd Item",
        item_sku="EXPU-001",
    )

    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="EXPENSE",
            site_id=site.id,
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=Decimal("5"),
                ),
            ],
        ),
        user_id=user.id,
    )

    # Подтверждаем 0 документов после create
    docs_after_create = await uow.documents.get_documents_by_operation(operation["operation"].id)
    assert len(docs_after_create) == 0

    # Update notes
    update_data = OperationUpdate(notes="updated")
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation["operation"].id,
        update_data=update_data,
    )

    docs_after_update = await uow.documents.get_documents_by_operation(
        operation["operation"].id, document_type="waybill"
    )
    assert len(docs_after_update) == 0, "EXPENSE update не должен создавать waybill"

    # Также проверяем, что других draft-документов не появилось
    all_docs = await uow.documents.get_documents_by_operation(operation["operation"].id)
    assert len(all_docs) == 0, f"EXPENSE update не должен создавать никаких документов, got {len(all_docs)}"


@pytest.mark.asyncio
async def test_submit_expense_act_reflects_post_edit_state(
    uow,
    site,
    user,
):
    """rev. 2 (note #13, regression): submit EXPENSE после правок черновика
    должен дать финальный act с состоянием ПОСЛЕ правок, а не на момент create.

    Guard от stale-reuse: если бы EXPENSE порождал draft "act" на create,
    на submit _find_reusable_document нашёл бы его и финализировал in-place
    без пересборки payload → финал отражал бы pre-edit состояние.
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Expense Submit Unit",
        unit_symbol="ESU",
        category_name="Expense Submit Category",
        item_name="Expense Submit Item",
        item_sku="EXPS-001",
    )

    # create EXPENSE с qty=5
    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="EXPENSE",
            site_id=site.id,
            lines=[
                OperationLineCreate(
                    line_number=1,
                    item_id=item.id,
                    qty=Decimal("5"),
                ),
            ],
        ),
        user_id=user.id,
    )

    # Подтверждаем 0 документов после create
    docs_after_create = await uow.documents.get_documents_by_operation(operation["operation"].id)
    assert len(docs_after_create) == 0

    # update qty 5 → 10
    update_data = OperationUpdate(
        lines=[
            OperationLineCreate(
                line_number=1,
                item_id=item.id,
                qty=Decimal("10"),
            ),
        ],
    )
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation["operation"].id,
        update_data=update_data,
    )

    # Чтобы EXPENSE submit прошёл, нужен достаточный баланс.
    # Получаем inventory_subject_id из линии операции и добавляем qty=10.
    submitted_op_before = await uow.operations.get_operation_by_id(operation["operation"].id)
    assert submitted_op_before is not None
    line = submitted_op_before.lines[0]
    inventory_subject_id = line.inventory_subject_id
    assert inventory_subject_id is not None
    await uow.balances.update_balance_quantity(
        site_id=site.id,
        inventory_subject_id=inventory_subject_id,
        quantity_delta=Decimal("20"),
    )

    # submit
    submit_result = await OperationsService.submit_operation(
        uow=uow,
        operation_id=operation["operation"].id,
        user_id=user.id,
    )
    assert submit_result is not None
    assert "operation" in submit_result
    submitted_op = submit_result["operation"]
    assert submitted_op.status == "submitted"

    # Проверяем act: должен существовать, быть finalized, и иметь qty=10
    act_docs = await uow.documents.get_documents_by_operation(
        operation["operation"].id, document_type="act"
    )
    assert len(act_docs) == 1, f"EXPENSE submit должен дать ровно 1 act, got {len(act_docs)}"
    act = act_docs[0]
    assert act.status == "finalized", f"act должен быть finalized, got {act.status}"

    # payload должен отражать ПОСТ-edit состояние (qty=10, не 5)
    assert act.payload is not None
    lines = act.payload.get("lines", [])
    assert len(lines) == 1
    payload_qty = lines[0].get("quantity")
    assert payload_qty == 10.0 or payload_qty == "10" or payload_qty == Decimal("10"), (
        f"act payload должен отражать post-edit qty=10, got {payload_qty}"
    )
