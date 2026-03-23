from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE, UNCATEGORIZED_CATEGORY_NAME
from app.core.db import SessionFactory
from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit


ITEM_NAME_HEADER_ALIASES = {
    "наименование тмц",
    "наименование",
    "тмц",
    "item name",
    "name",
}
SKU_HEADER_ALIASES = {
    "sku тмц",
    "sku",
    "артикул",
    "код",
}
UNIT_HEADER_ALIASES = {
    "единица измерения тмц",
    "единица измерения",
    "ед изм",
    "ед. изм.",
    "unit",
    "unit symbol",
}


@dataclass(frozen=True)
class CatalogCsvRow:
    item_name: str
    sku: str
    unit_value: str
    row_number: int

    @property
    def sku_key(self) -> str:
        return normalize_key(self.sku)

    @property
    def unit_key(self) -> str:
        return normalize_key(self.unit_value)

    @property
    def signature(self) -> tuple[str, str, str]:
        return (
            normalize_key(self.item_name),
            self.sku_key,
            self.unit_key,
        )


@dataclass(frozen=True)
class ParsedCatalogCsv:
    rows: list[CatalogCsvRow]
    duplicate_rows_skipped: int = 0


@dataclass
class ImportSummary:
    parsed_rows: int
    duplicate_rows_skipped: int = 0
    uncategorized_created: bool = False
    units_created: int = 0
    units_reused: int = 0
    items_created: int = 0
    items_skipped_existing: int = 0
    dry_run: bool = False


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\ufeff", "").strip().split())


def normalize_key(value: str) -> str:
    return normalize_text(value).replace("ё", "е").casefold()


def _sniff_dialect(handle) -> csv.Dialect:
    sample = handle.read(4096)
    handle.seek(0)
    if not sample.strip():
        raise ValueError("CSV file is empty")

    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _detect_header_indexes(row: list[str]) -> tuple[int, int, int] | None:
    normalized = [normalize_key(value) for value in row]

    def find_index(aliases: set[str]) -> int | None:
        for index, value in enumerate(normalized):
            if value in aliases:
                return index
        return None

    item_name_index = find_index(ITEM_NAME_HEADER_ALIASES)
    sku_index = find_index(SKU_HEADER_ALIASES)
    unit_index = find_index(UNIT_HEADER_ALIASES)

    if item_name_index is None or sku_index is None or unit_index is None:
        return None
    return (item_name_index, sku_index, unit_index)


def _row_value(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return normalize_text(row[index])


def parse_catalog_csv(csv_path: str | Path) -> ParsedCatalogCsv:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        dialect = _sniff_dialect(handle)
        reader = csv.reader(handle, dialect)
        raw_rows = [
            [normalize_text(value) for value in row]
            for row in reader
            if any(normalize_text(value) for value in row)
        ]

    if not raw_rows:
        raise ValueError("CSV file does not contain data rows")

    header_indexes = _detect_header_indexes(raw_rows[0])
    data_start = 1 if header_indexes is not None else 0
    item_name_index, sku_index, unit_index = header_indexes or (0, 1, 2)

    parsed_rows: list[CatalogCsvRow] = []
    duplicate_rows_skipped = 0
    rows_by_sku: dict[str, CatalogCsvRow] = {}

    for row_number, row in enumerate(raw_rows[data_start:], start=data_start + 1):
        item_name = _row_value(row, item_name_index)
        sku = _row_value(row, sku_index)
        unit_value = _row_value(row, unit_index)

        if not item_name or not sku or not unit_value:
            raise ValueError(
                f"Row {row_number}: expected non-empty item name, SKU, and unit value"
            )

        if len(item_name) > 255:
            raise ValueError(f"Row {row_number}: item name is longer than 255 characters")
        if len(sku) > 100:
            raise ValueError(f"Row {row_number}: SKU is longer than 100 characters")
        if len(unit_value) > 100:
            raise ValueError(f"Row {row_number}: unit value is longer than 100 characters")

        catalog_row = CatalogCsvRow(
            item_name=item_name,
            sku=sku,
            unit_value=unit_value,
            row_number=row_number,
        )

        existing_row = rows_by_sku.get(catalog_row.sku_key)
        if existing_row is not None:
            if existing_row.signature != catalog_row.signature:
                raise ValueError(
                    f"Row {catalog_row.row_number}: conflicting duplicate SKU '{catalog_row.sku}' in CSV"
                )
            duplicate_rows_skipped += 1
            continue

        rows_by_sku[catalog_row.sku_key] = catalog_row
        parsed_rows.append(catalog_row)

    if not parsed_rows:
        raise ValueError("CSV file does not contain importable rows")

    return ParsedCatalogCsv(
        rows=parsed_rows,
        duplicate_rows_skipped=duplicate_rows_skipped,
    )


async def ensure_uncategorized_category(session: AsyncSession) -> tuple[Category, bool]:
    result = await session.execute(
        select(Category).where(Category.code == UNCATEGORIZED_CATEGORY_CODE)
    )
    categories = list(result.scalars().all())

    if len(categories) > 1:
        raise RuntimeError("multiple uncategorized categories configured")

    if categories:
        category = categories[0]
        if not category.is_active:
            category.is_active = True
            await session.flush()
        return category, False

    category = Category(
        name=UNCATEGORIZED_CATEGORY_NAME,
        code=UNCATEGORIZED_CATEGORY_CODE,
        parent_id=None,
        is_active=True,
    )
    session.add(category)
    await session.flush()
    return category, True


async def import_catalog_rows(
    session: AsyncSession,
    rows: Iterable[CatalogCsvRow],
    *,
    duplicate_rows_skipped: int = 0,
    dry_run: bool = False,
) -> ImportSummary:
    row_list = list(rows)
    summary = ImportSummary(
        parsed_rows=len(row_list),
        duplicate_rows_skipped=duplicate_rows_skipped,
        dry_run=dry_run,
    )

    if not row_list:
        return summary

    uncategorized_category, uncategorized_created = await ensure_uncategorized_category(session)
    summary.uncategorized_created = uncategorized_created

    unit_keys = sorted({row.unit_key for row in row_list})
    sku_keys = sorted({row.sku_key for row in row_list})

    existing_units = list(
        (
            await session.execute(
                select(Unit).where(
                    (func.lower(Unit.symbol).in_(unit_keys))
                    | (func.lower(Unit.name).in_(unit_keys))
                )
            )
        ).scalars()
    )
    units_by_symbol = {normalize_key(unit.symbol): unit for unit in existing_units}
    units_by_name = {normalize_key(unit.name): unit for unit in existing_units}
    resolved_units: dict[str, Unit] = {}

    existing_items = list(
        (
            await session.execute(
                select(Item).where(
                    Item.sku.is_not(None),
                    func.lower(Item.sku).in_(sku_keys),
                )
            )
        ).scalars()
    )
    items_by_sku = {normalize_key(item.sku or ""): item for item in existing_items}

    for row in row_list:
        unit = resolved_units.get(row.unit_key)
        if unit is None:
            unit = units_by_symbol.get(row.unit_key) or units_by_name.get(row.unit_key)
            if unit is None:
                if len(row.unit_value) > 20:
                    raise ValueError(
                        f"Row {row.row_number}: new unit value '{row.unit_value}' is longer than 20 characters "
                        "and cannot be used as unit symbol"
                    )
                unit = Unit(
                    name=row.unit_value,
                    symbol=row.unit_value,
                    is_active=True,
                )
                session.add(unit)
                await session.flush()
                summary.units_created += 1
            else:
                summary.units_reused += 1
                if not unit.is_active:
                    unit.is_active = True
                    await session.flush()

            resolved_units[row.unit_key] = unit
            units_by_symbol[normalize_key(unit.symbol)] = unit
            units_by_name[normalize_key(unit.name)] = unit

        existing_item = items_by_sku.get(row.sku_key)
        if existing_item is not None:
            summary.items_skipped_existing += 1
            continue

        item = Item(
            sku=row.sku,
            name=row.item_name,
            category_id=uncategorized_category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.flush()

        items_by_sku[row.sku_key] = item
        summary.items_created += 1

    return summary


async def import_catalog_csv(
    csv_path: str | Path,
    *,
    dry_run: bool = False,
) -> ImportSummary:
    parsed = parse_catalog_csv(csv_path)

    async with SessionFactory() as session:
        summary = await import_catalog_rows(
            session,
            parsed.rows,
            duplicate_rows_skipped=parsed.duplicate_rows_skipped,
            dry_run=dry_run,
        )
        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return summary


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import items and measurement units from CSV with columns: "
            "item name, SKU, unit"
        )
    )
    parser.add_argument("csv_path", help="Path to CSV file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate CSV, but rollback all DB changes",
    )
    return parser


def print_summary(summary: ImportSummary) -> None:
    print("Catalog CSV import complete.")
    print(f"  parsed rows:            {summary.parsed_rows}")
    print(f"  duplicate rows skipped: {summary.duplicate_rows_skipped}")
    print(f"  uncategorized created:  {'yes' if summary.uncategorized_created else 'no'}")
    print(f"  units created:          {summary.units_created}")
    print(f"  units reused:           {summary.units_reused}")
    print(f"  items created:          {summary.items_created}")
    print(f"  items skipped existing: {summary.items_skipped_existing}")
    print(f"  dry run:                {'yes' if summary.dry_run else 'no'}")


async def main_async() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    summary = await import_catalog_csv(args.csv_path, dry_run=args.dry_run)
    print_summary(summary)


if __name__ == "__main__":
    asyncio.run(main_async())
