"""TZ-V3.1I rev. 3 (Stage I5.2): guard tests for draft document type map.

После расширения DRAFT_DOCUMENT_TYPE_BY_OPERATION до {MOVE, ISSUE, ISSUE_RETURN,
RECEIVE, EXPENSE, WRITE_OFF}, все операции движения ТМЦ получают draft waybill
на create и на каждом update. ADJUSTMENT — служебная операция
(Functional §II.5.5; OPERATIONS_SCREEN_SCENARIOS.md:530,1285-1286) — draft waybill
НЕ получает, draft-документ не создаётся ни на create, ни на update.

Stale in-place finalization (rev. 2 blocker #1) исключён:
- draft = waybill, final = acceptance_certificate / act — разные document_type;
- _find_reusable_document (document_service.py:356) фильтрует по document_type и
  никогда не находит draft waybill при поиске act / acceptance_certificate;
- I3.3 (operations_service.py:1094-1105) войдирует draft waybills перед submit
  для не-waybill финалов.
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
async def test_create_draft_move_has_waybill_draft(
    uow,
    site,
    secondary_site,
    user,
):
    """rev. 3 sanity-check: MOVE draft порождает ровно 1 draft waybill.

    Сохранён как явный sanity guard против регрессии в DRAFT_DOCUMENT_TYPE_BY_OPERATION.
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Move Unit",
        unit_symbol="MU",
        category_name="Move Category",
        item_name="Move Item",
        item_sku="MOV-001",
    )

    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="MOVE",
            site_id=site.id,
            source_site_id=site.id,
            destination_site_id=secondary_site.id,
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
    assert len(docs) == 1, f"MOVE draft должен иметь 1 документ, got {len(docs)}"
    assert docs[0].document_type == "waybill", f"ожидался waybill, got {docs[0].document_type}"
    assert docs[0].status == "draft", f"ожидался draft status, got {docs[0].status}"


@pytest.mark.asyncio
async def test_create_draft_receive_has_waybill_draft(
    uow,
    site,
    user,
):
    """rev. 3: RECEIVE draft порождает 1 draft waybill.

    Финальный acceptance_certificate появится на submit, при этом I3.3
    войдирует draft waybill. Stale in-place finalization исключён, т.к.
    _find_reusable_document ищет по document_type=acceptance_certificate
    и никогда не находит draft waybill.
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
    assert len(docs) == 1, f"RECEIVE draft должен иметь 1 документ, got {len(docs)}"
    assert docs[0].document_type == "waybill", f"ожидался waybill, got {docs[0].document_type}"
    assert docs[0].status == "draft", f"ожидался draft status, got {docs[0].status}"


@pytest.mark.asyncio
async def test_create_draft_expense_has_waybill_draft(
    uow,
    site,
    user,
):
    """rev. 3: EXPENSE draft порождает 1 draft waybill.

    Финальный act появится на submit; draft waybill будет войдирован (I3.3).
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Expense Unit",
        unit_symbol="EU",
        category_name="Expense Category",
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
    assert len(docs) == 1, f"EXPENSE draft должен иметь 1 документ, got {len(docs)}"
    assert docs[0].document_type == "waybill", f"ожидался waybill, got {docs[0].document_type}"
    assert docs[0].status == "draft", f"ожидался draft status, got {docs[0].status}"


@pytest.mark.asyncio
async def test_create_draft_write_off_has_waybill_draft(
    uow,
    site,
    user,
):
    """rev. 3: WRITE_OFF draft порождает 1 draft waybill.

    Финальный act появится на submit; draft waybill будет войдирован (I3.3).
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Write Off Unit",
        unit_symbol="WO",
        category_name="Write Off Category",
        item_name="Write Off Item",
        item_sku="WRO-001",
    )

    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="WRITE_OFF",
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
    assert len(docs) == 1, f"WRITE_OFF draft должен иметь 1 документ, got {len(docs)}"
    assert docs[0].document_type == "waybill", f"ожидался waybill, got {docs[0].document_type}"
    assert docs[0].status == "draft", f"ожидался draft status, got {docs[0].status}"


@pytest.mark.asyncio
async def test_create_draft_adjustment_has_no_documents(
    uow,
    site,
    user,
):
    """rev. 3: ADJUSTMENT — служебная операция, draft waybill НЕ создаётся.

    ADJUSTMENT (Functional §II.5.5: «корректировка - служебная операция которая
    позволит изменить количество или саму ТМЦ»;
    OPERATIONS_SCREEN_SCENARIOS.md:530,1285-1286: «submit корректировки только
    root/chief») не имеет накладной по определению — используется для transfer
    balances, review items, merge batches.
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Adjustment Unit",
        unit_symbol="AU",
        category_name="Adjustment Category",
        item_name="Adjustment Item",
        item_sku="ADJ-001",
    )

    operation = await OperationsService.create_operation(
        uow=uow,
        operation_data=OperationCreate(
            operation_type="ADJUSTMENT",
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
    assert len(docs) == 0, f"ADJUSTMENT draft не должен иметь документов, got {len(docs)}: {[d.document_type for d in docs]}"


@pytest.mark.asyncio
async def test_update_draft_expense_refreshes_waybill(
    uow,
    site,
    user,
):
    """rev. 3 (I3.3, closes warning #2): update EXPENSE draft освежает waybill.

    Create → 1 draft waybill. Update notes → старый waybill войдируется,
    создаётся новый draft waybill. Итог: ровно 1 активный (status=draft) waybill.
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

    # После create: 1 draft waybill
    docs_after_create = await uow.documents.get_documents_by_operation(
        operation["operation"].id, document_type="waybill"
    )
    assert len(docs_after_create) == 1, f"EXPENSE create должен создать 1 waybill, got {len(docs_after_create)}"
    assert docs_after_create[0].status == "draft"
    first_waybill_id = docs_after_create[0].id

    # Update notes
    update_data = OperationUpdate(notes="updated")
    await OperationsService.update_operation(
        uow=uow,
        operation_id=operation["operation"].id,
        update_data=update_data,
    )

    # После update: ровно 1 активный (draft) waybill — старый войдирован, новый создан
    all_waybills = await uow.documents.get_documents_by_operation(
        operation["operation"].id, document_type="waybill"
    )
    active_waybills = [d for d in all_waybills if d.status == "draft"]
    assert len(active_waybills) == 1, (
        f"EXPENSE update должен оставить ровно 1 активный draft waybill, got {len(active_waybills)} "
        f"(всего waybill: {len(all_waybills)}, статусы: {[d.status for d in all_waybills]})"
    )
    # Документ должен быть освежён (id изменился, т.к. старый войдирован и создан новый)
    assert active_waybills[0].id != first_waybill_id, (
        f"waybill id должен измениться после update (recreate), got тот же {active_waybills[0].id}"
    )

    # Других типов документов быть не должно
    all_docs = await uow.documents.get_documents_by_operation(operation["operation"].id)
    doc_types = {d.document_type for d in all_docs}
    assert doc_types == {"waybill"}, f"ожидались только waybill-документы, got {doc_types}"


@pytest.mark.asyncio
async def test_submit_expense_act_reflects_post_edit_state(
    uow,
    site,
    user,
):
    """rev. 2 (note #13, regression): submit EXPENSE после правок черновика
    должен дать финальный act с состоянием ПОСЛЕ правок, а не на момент create.

    Guard от stale-reuse: I3.3 (operations_service.py:1094-1105) войдирует
    draft waybills (document_type=waybill) перед генерацией финального act.
    _find_reusable_document ищет по document_type=act и никогда не находит
    draft waybill → финальный act всегда строится с актуальным payload.
    """
    _, _, item = await _create_catalog_fixture(
        uow,
        unit_name="Expense Submit Unit",
        unit_symbol="ESU",
        category_name="Expense Submit Category",
        item_name="Expense Submit Item",
        item_sku="EXPS-001",
    )

    # create EXPENSE с qty=5 — rev. 3 теперь порождает 1 draft waybill
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

    # Подтверждаем наличие 1 draft waybill после create
    docs_after_create = await uow.documents.get_documents_by_operation(
        operation["operation"].id, document_type="waybill"
    )
    assert len(docs_after_create) == 1
    assert docs_after_create[0].status == "draft"

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

    # Также: draft waybill должен быть войдирован (I3.3)
    waybill_docs = await uow.documents.get_documents_by_operation(
        operation["operation"].id, document_type="waybill"
    )
    waybill_statuses = {d.status for d in waybill_docs}
    assert waybill_statuses == {"void"}, (
        f"после submit все draft waybills должны быть войдированы, got {waybill_statuses}"
    )
