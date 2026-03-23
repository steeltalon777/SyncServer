from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE
from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit
from scripts.import_catalog_csv import CatalogCsvRow, import_catalog_rows, parse_catalog_csv


def test_parse_catalog_csv_supports_russian_headers_and_skips_identical_duplicates(tmp_path: Path) -> None:
    csv_path = tmp_path / "catalog.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Наименование ТМЦ;SKU ТМЦ;Единица измерения ТМЦ",
                "Болт М8;BOLT-M8;шт",
                "Болт М8;BOLT-M8;шт",
                "Гайка М8;NUT-M8;шт",
            ]
        ),
        encoding="utf-8",
    )

    parsed = parse_catalog_csv(csv_path)

    assert parsed.duplicate_rows_skipped == 1
    assert [row.sku for row in parsed.rows] == ["BOLT-M8", "NUT-M8"]
    assert parsed.rows[0].item_name == "Болт М8"
    assert parsed.rows[0].unit_value == "шт"


@pytest.mark.asyncio
async def test_import_catalog_rows_creates_items_and_one_shared_unit(db_session: AsyncSession) -> None:
    rows = [
        CatalogCsvRow(item_name="Болт М8", sku="BOLT-M8", unit_value="шт", row_number=2),
        CatalogCsvRow(item_name="Гайка М8", sku="NUT-M8", unit_value="шт", row_number=3),
    ]

    summary = await import_catalog_rows(db_session, rows)

    assert summary.uncategorized_created is True
    assert summary.units_created == 1
    assert summary.units_reused == 0
    assert summary.items_created == 2
    assert summary.items_skipped_existing == 0

    uncategorized = (
        await db_session.execute(select(Category).where(Category.code == UNCATEGORIZED_CATEGORY_CODE))
    ).scalar_one()
    units = list((await db_session.execute(select(Unit))).scalars().all())
    items = list((await db_session.execute(select(Item).order_by(Item.sku))).scalars().all())

    assert len(units) == 1
    assert units[0].symbol == "шт"
    assert [item.sku for item in items] == ["BOLT-M8", "NUT-M8"]
    assert all(item.category_id == uncategorized.id for item in items)
    assert all(item.unit_id == units[0].id for item in items)


@pytest.mark.asyncio
async def test_import_catalog_rows_reuses_existing_unit_and_skips_existing_sku(db_session: AsyncSession) -> None:
    uncategorized = Category(
        name="Без категории",
        code=UNCATEGORIZED_CATEGORY_CODE,
        parent_id=None,
        is_active=True,
    )
    unit = Unit(name="Штука", symbol="шт", is_active=True)
    db_session.add_all([uncategorized, unit])
    await db_session.flush()

    existing_item = Item(
        sku="BOLT-M8",
        name="Болт М8",
        category_id=uncategorized.id,
        unit_id=unit.id,
        is_active=True,
    )
    db_session.add(existing_item)
    await db_session.flush()

    rows = [
        CatalogCsvRow(item_name="Болт М8", sku="BOLT-M8", unit_value="шт", row_number=2),
        CatalogCsvRow(item_name="Гайка М8", sku="NUT-M8", unit_value="шт", row_number=3),
    ]

    summary = await import_catalog_rows(db_session, rows)

    assert summary.uncategorized_created is False
    assert summary.units_created == 0
    assert summary.units_reused == 1
    assert summary.items_created == 1
    assert summary.items_skipped_existing == 1

    units = list((await db_session.execute(select(Unit))).scalars().all())
    items = list((await db_session.execute(select(Item).order_by(Item.sku))).scalars().all())

    assert len(units) == 1
    assert [item.sku for item in items] == ["BOLT-M8", "NUT-M8"]
