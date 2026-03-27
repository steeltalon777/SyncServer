from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE
from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit
from scripts.import_catalog_csv import (
    CatalogCsvRow,
    build_category_path_lookup,
    import_catalog_rows,
    parse_catalog_csv,
)


def test_parse_catalog_csv_supports_category_headers_blank_sku_and_skips_invalid_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "catalog.csv"
    csv_path.write_text(
        "\n".join(
            [
                "name;sku;unit_symbol;parent_category_name;category_name;subcategory_name",
                "Кабель ВВГ 2*1,5;;Метр;Электротехника;Кабельно-проводниковая продукция;Кабели",
                "Кабель ВВГ 2*1,5;;Метр;Электротехника;Кабельно-проводниковая продукция;Кабели",
                ";BAD-SKU;шт;Прочее;Разное;",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_catalog_csv(csv_path)

    assert parsed.duplicate_rows_skipped == 1
    assert parsed.invalid_rows_skipped == 1
    assert len(parsed.issues) == 1
    assert len(parsed.rows) == 1
    assert parsed.rows[0].sku is None
    assert parsed.rows[0].item_name == "Кабель ВВГ 2*1,5"
    assert parsed.rows[0].unit_value == "Метр"
    assert parsed.rows[0].category_path == (
        "Электротехника",
        "Кабельно-проводниковая продукция",
        "Кабели",
    )


def test_build_category_path_lookup_uses_full_hierarchy() -> None:
    root = Category(id=1, name="Электротехника", parent_id=None, code=None, is_active=True)
    child = Category(id=2, name="Кабельно-проводниковая продукция", parent_id=1, code=None, is_active=True)
    leaf = Category(id=3, name="Кабели", parent_id=2, code=None, is_active=True)
    inactive = Category(id=4, name="Скрытая", parent_id=3, code=None, is_active=False)

    lookup = build_category_path_lookup([root, child, leaf, inactive])

    assert lookup[("электротехника",)] == root
    assert lookup[("электротехника", "кабельно-проводниковая продукция")] == child
    assert lookup[("электротехника", "кабельно-проводниковая продукция", "кабели")] == leaf
    assert ("электротехника", "кабельно-проводниковая продукция", "кабели", "скрытая") not in lookup


@pytest.mark.asyncio
async def test_import_catalog_rows_resolves_existing_category_and_falls_back_for_unknowns(
    db_session: AsyncSession,
) -> None:
    root = Category(name="Электротехника", code=None, parent_id=None, is_active=True)
    child = Category(name="Кабельно-проводниковая продукция", code=None, parent_id=None, is_active=True)
    db_session.add_all([root, child])
    await db_session.flush()

    child.parent_id = root.id
    await db_session.flush()

    leaf = Category(name="Кабели", code=None, parent_id=child.id, is_active=True)
    meter = Unit(name="Метр", symbol="м", is_active=True)
    piece = Unit(name="Штука", symbol="шт", is_active=True)
    db_session.add_all([leaf, meter, piece])
    await db_session.flush()

    rows = [
        CatalogCsvRow(
            item_name="Кабель ВВГ",
            sku=None,
            unit_value="Метр",
            row_number=2,
            category_path=("Электротехника", "Кабельно-проводниковая продукция", "Кабели"),
        ),
        CatalogCsvRow(
            item_name="Неизвестная позиция",
            sku=None,
            unit_value="Коробка",
            row_number=3,
            category_path=("Прочее", "Разное"),
        ),
    ]

    summary = await import_catalog_rows(db_session, rows)

    uncategorized = (
        await db_session.execute(select(Category).where(Category.code == UNCATEGORIZED_CATEGORY_CODE))
    ).scalar_one()
    items = list((await db_session.execute(select(Item).order_by(Item.name))).scalars().all())

    assert summary.uncategorized_created is True
    assert summary.units_created == 0
    assert summary.units_reused == 1
    assert summary.unit_fallbacks == 1
    assert summary.category_fallbacks == 1
    assert summary.items_created == 2
    assert summary.items_skipped_existing == 0
    assert len(summary.issues) == 1
    assert "unknown unit 'Коробка'" in summary.issues[0].message
    assert "category path 'Прочее > Разное' not found" in summary.issues[0].message

    assert [item.name for item in items] == ["Кабель ВВГ", "Неизвестная позиция"]
    assert items[0].category_id == leaf.id
    assert items[0].unit_id == meter.id
    assert items[1].category_id == uncategorized.id
    assert items[1].unit_id == piece.id


@pytest.mark.asyncio
async def test_import_catalog_rows_skips_existing_item_without_sku_by_name_category_and_unit(
    db_session: AsyncSession,
) -> None:
    uncategorized = Category(
        name="Без категории",
        code=UNCATEGORIZED_CATEGORY_CODE,
        parent_id=None,
        is_active=True,
    )
    piece = Unit(name="Штука", symbol="шт", is_active=True)
    db_session.add_all([uncategorized, piece])
    await db_session.flush()

    existing_item = Item(
        sku=None,
        name="Болт М8",
        category_id=uncategorized.id,
        unit_id=piece.id,
        is_active=True,
    )
    db_session.add(existing_item)
    await db_session.flush()

    rows = [
        CatalogCsvRow(item_name="Болт М8", sku=None, unit_value="шт", row_number=2),
        CatalogCsvRow(item_name="Гайка М8", sku=None, unit_value="шт", row_number=3),
    ]

    summary = await import_catalog_rows(db_session, rows)
    items = list((await db_session.execute(select(Item).order_by(Item.name))).scalars().all())

    assert summary.uncategorized_created is False
    assert summary.units_created == 0
    assert summary.items_created == 1
    assert summary.items_skipped_existing == 1
    assert [item.name for item in items] == ["Болт М8", "Гайка М8"]


@pytest.mark.asyncio
async def test_import_catalog_rows_creates_piece_unit_when_needed(db_session: AsyncSession) -> None:
    rows = [
        CatalogCsvRow(item_name="Болт М8", sku="BOLT-M8", unit_value="шт", row_number=2),
        CatalogCsvRow(item_name="Гайка М8", sku="NUT-M8", unit_value="шт", row_number=3),
    ]

    summary = await import_catalog_rows(db_session, rows)
    units = list((await db_session.execute(select(Unit))).scalars().all())

    assert summary.uncategorized_created is True
    assert summary.units_created == 1
    assert summary.units_reused == 0
    assert summary.unit_fallbacks == 2
    assert summary.items_created == 2
    assert len(units) == 1
    assert units[0].name == "Штука"
    assert units[0].symbol == "шт"
