from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from dataclasses import dataclass, field
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


CSV_CANDIDATE_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "cp1251",
    "cp866",
)

DEFAULT_FALLBACK_UNIT_NAME = "Штука"
DEFAULT_FALLBACK_UNIT_SYMBOL = "шт"
DEFAULT_FALLBACK_UNIT_ALIASES = {
    "шт",
    "шт.",
    "штука",
    "штуки",
    "piece",
    "pc",
    "pcs",
}

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
PARENT_CATEGORY_HEADER_ALIASES = {
    "родительская категория",
    "родительская категория тмц",
    "родительская группа",
    "parent category",
    "parent category name",
    "parent_category_name",
}
CATEGORY_HEADER_ALIASES = {
    "категория",
    "категория тмц",
    "группа",
    "category",
    "category name",
    "category_name",
}
SUBCATEGORY_HEADER_ALIASES = {
    "подкатегория",
    "подкатегория тмц",
    "sub category",
    "subcategory",
    "subcategory name",
    "subcategory_name",
}


@dataclass(frozen=True)
class ImportIssue:
    row_number: int
    item_name: str
    message: str


@dataclass(frozen=True)
class CatalogCsvRow:
    item_name: str
    sku: str | None
    unit_value: str
    row_number: int
    category_path: tuple[str, ...] = ()

    @property
    def sku_key(self) -> str:
        return normalize_key(self.sku)

    @property
    def unit_key(self) -> str:
        return normalize_key(self.unit_value)

    @property
    def category_path_key(self) -> tuple[str, ...]:
        return tuple(normalize_key(value) for value in self.category_path)

    @property
    def identity_key(self) -> tuple[str, ...]:
        if self.sku_key:
            return ("sku", self.sku_key)
        return (
            "no-sku",
            normalize_key(self.item_name),
            self.unit_key,
            *self.category_path_key,
        )

    @property
    def signature(self) -> tuple[str, ...]:
        return (
            normalize_key(self.item_name),
            self.sku_key,
            self.unit_key,
            *self.category_path_key,
        )


@dataclass(frozen=True)
class PreparedCatalogRow:
    source: CatalogCsvRow
    category: Category
    unit: Unit


@dataclass(frozen=True)
class ParsedCatalogCsv:
    rows: list[CatalogCsvRow]
    duplicate_rows_skipped: int = 0
    invalid_rows_skipped: int = 0
    issues: list[ImportIssue] = field(default_factory=list)


@dataclass
class ImportSummary:
    parsed_rows: int
    duplicate_rows_skipped: int = 0
    invalid_rows_skipped: int = 0
    uncategorized_created: bool = False
    units_created: int = 0
    units_reused: int = 0
    unit_fallbacks: int = 0
    category_fallbacks: int = 0
    items_created: int = 0
    items_skipped_existing: int = 0
    dry_run: bool = False
    issues: list[ImportIssue] = field(default_factory=list)


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\ufeff", "").strip().split())


def normalize_key(value: str | None) -> str:
    return normalize_text(value).replace("ё", "е").casefold()


def format_category_path(path: Iterable[str]) -> str:
    parts = [normalize_text(part) for part in path if normalize_text(part)]
    return " > ".join(parts)


def _sniff_dialect(handle) -> csv.Dialect:
    sample = handle.read(4096)
    handle.seek(0)
    if not sample.strip():
        raise ValueError("CSV file is empty")

    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _read_raw_csv_rows(path: Path) -> list[list[str]]:
    last_rows: list[list[str]] | None = None

    for encoding in CSV_CANDIDATE_ENCODINGS:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                dialect = _sniff_dialect(handle)
                reader = csv.reader(handle, dialect)
                rows = [
                    [normalize_text(value) for value in row]
                    for row in reader
                    if any(normalize_text(value) for value in row)
                ]
        except UnicodeDecodeError:
            continue

        if not rows:
            continue
        if _detect_header_indexes(rows[0]) is not None:
            return rows
        if last_rows is None:
            last_rows = rows

    if last_rows is not None:
        return last_rows
    raise ValueError("CSV file does not contain data rows")


def _detect_header_indexes(row: list[str]) -> dict[str, int] | None:
    normalized = [normalize_key(value) for value in row]

    def find_index(aliases: set[str]) -> int | None:
        for index, value in enumerate(normalized):
            if value in aliases:
                return index
        return None

    item_name_index = find_index(ITEM_NAME_HEADER_ALIASES)
    if item_name_index is None:
        return None

    indexes: dict[str, int] = {
        "item_name": item_name_index,
    }
    optional_indexes = {
        "sku": find_index(SKU_HEADER_ALIASES),
        "unit": find_index(UNIT_HEADER_ALIASES),
        "parent_category_name": find_index(PARENT_CATEGORY_HEADER_ALIASES),
        "category_name": find_index(CATEGORY_HEADER_ALIASES),
        "subcategory_name": find_index(SUBCATEGORY_HEADER_ALIASES),
    }
    indexes.update({key: value for key, value in optional_indexes.items() if value is not None})
    return indexes


def _default_header_indexes() -> dict[str, int]:
    return {
        "item_name": 0,
        "sku": 1,
        "unit": 2,
        "parent_category_name": 3,
        "category_name": 4,
        "subcategory_name": 5,
    }


def _row_value(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return normalize_text(row[index])


def _coerce_row_shape(row: list[str], expected_columns: int) -> list[str]:
    if expected_columns <= 0:
        return row
    if len(row) == expected_columns:
        return row
    if len(row) < expected_columns:
        return row + [""] * (expected_columns - len(row))

    overflow = len(row) - expected_columns
    merged_first_column = ",".join(row[: overflow + 1])
    return [merged_first_column, *row[overflow + 1 :]]


def parse_catalog_csv(csv_path: str | Path) -> ParsedCatalogCsv:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    raw_rows = _read_raw_csv_rows(path)
    if not raw_rows:
        raise ValueError("CSV file does not contain data rows")

    detected_indexes = _detect_header_indexes(raw_rows[0])
    data_start = 1 if detected_indexes is not None else 0
    expected_columns = len(raw_rows[0]) if detected_indexes is not None else max(len(raw_rows[0]), 3)
    header_indexes = _default_header_indexes()
    if detected_indexes is not None:
        header_indexes.update(detected_indexes)

    parsed_rows: list[CatalogCsvRow] = []
    duplicate_rows_skipped = 0
    invalid_rows_skipped = 0
    issues: list[ImportIssue] = []
    rows_by_identity: dict[tuple[str, ...], CatalogCsvRow] = {}

    for row_number, row in enumerate(raw_rows[data_start:], start=data_start + 1):
        row = _coerce_row_shape(row, expected_columns)
        item_name = _row_value(row, header_indexes.get("item_name"))
        sku = _row_value(row, header_indexes.get("sku")) or None
        unit_value = _row_value(row, header_indexes.get("unit"))
        category_path = tuple(
            value
            for value in (
                _row_value(row, header_indexes.get("parent_category_name")),
                _row_value(row, header_indexes.get("category_name")),
                _row_value(row, header_indexes.get("subcategory_name")),
            )
            if value
        )

        row_errors: list[str] = []
        if not item_name:
            row_errors.append("empty item name")
        if len(item_name) > 255:
            row_errors.append("item name is longer than 255 characters")
        if sku is not None and len(sku) > 100:
            row_errors.append("SKU is longer than 100 characters")
        if len(unit_value) > 100:
            row_errors.append("unit value is longer than 100 characters")

        if row_errors:
            invalid_rows_skipped += 1
            issues.append(
                ImportIssue(
                    row_number=row_number,
                    item_name=item_name or "<empty>",
                    message="; ".join(row_errors),
                )
            )
            continue

        catalog_row = CatalogCsvRow(
            item_name=item_name,
            sku=sku,
            unit_value=unit_value,
            row_number=row_number,
            category_path=category_path,
        )

        existing_row = rows_by_identity.get(catalog_row.identity_key)
        if existing_row is not None:
            if existing_row.signature != catalog_row.signature:
                invalid_rows_skipped += 1
                issues.append(
                    ImportIssue(
                        row_number=catalog_row.row_number,
                        item_name=catalog_row.item_name,
                        message=(
                            f"conflicting duplicate SKU or row signature; "
                            f"already seen on row {existing_row.row_number}"
                        ),
                    )
                )
                continue
            duplicate_rows_skipped += 1
            continue

        rows_by_identity[catalog_row.identity_key] = catalog_row
        parsed_rows.append(catalog_row)

    if not parsed_rows:
        raise ValueError("CSV file does not contain importable rows")

    return ParsedCatalogCsv(
        rows=parsed_rows,
        duplicate_rows_skipped=duplicate_rows_skipped,
        invalid_rows_skipped=invalid_rows_skipped,
        issues=issues,
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


def build_category_path_lookup(categories: Iterable[Category]) -> dict[tuple[str, ...], Category]:
    category_list = list(categories)
    category_by_id = {category.id: category for category in category_list}
    path_cache: dict[int, tuple[str, ...]] = {}
    active_path_cache: dict[int, bool] = {}

    def build_path(category: Category) -> tuple[str, ...]:
        cached = path_cache.get(category.id)
        if cached is not None:
            return cached

        if category.parent_id is None:
            path = (normalize_key(category.name),)
        else:
            parent = category_by_id.get(category.parent_id)
            if parent is None:
                path = (normalize_key(category.name),)
            else:
                path = build_path(parent) + (normalize_key(category.name),)

        path_cache[category.id] = path
        return path

    def has_active_path(category: Category) -> bool:
        cached = active_path_cache.get(category.id)
        if cached is not None:
            return cached

        if not category.is_active:
            active_path_cache[category.id] = False
            return False
        if category.parent_id is None:
            active_path_cache[category.id] = True
            return True

        parent = category_by_id.get(category.parent_id)
        if parent is None:
            active_path_cache[category.id] = True
            return True

        result = has_active_path(parent)
        active_path_cache[category.id] = result
        return result

    lookup: dict[tuple[str, ...], Category] = {}
    for category in category_list:
        if has_active_path(category):
            lookup[build_path(category)] = category
    return lookup


async def ensure_fallback_unit(
    session: AsyncSession,
    *,
    units_by_symbol: dict[str, Unit],
    units_by_name: dict[str, Unit],
) -> tuple[Unit, bool]:
    for alias in DEFAULT_FALLBACK_UNIT_ALIASES:
        unit = units_by_symbol.get(alias) or units_by_name.get(alias)
        if unit is not None:
            if not unit.is_active:
                unit.is_active = True
                await session.flush()
            return unit, False

    unit = Unit(
        name=DEFAULT_FALLBACK_UNIT_NAME,
        symbol=DEFAULT_FALLBACK_UNIT_SYMBOL,
        is_active=True,
    )
    session.add(unit)
    await session.flush()
    units_by_symbol[normalize_key(unit.symbol)] = unit
    units_by_name[normalize_key(unit.name)] = unit
    return unit, True


async def import_catalog_rows(
    session: AsyncSession,
    rows: Iterable[CatalogCsvRow],
    *,
    duplicate_rows_skipped: int = 0,
    invalid_rows_skipped: int = 0,
    issues: Iterable[ImportIssue] = (),
    dry_run: bool = False,
) -> ImportSummary:
    row_list = list(rows)
    summary = ImportSummary(
        parsed_rows=len(row_list),
        duplicate_rows_skipped=duplicate_rows_skipped,
        invalid_rows_skipped=invalid_rows_skipped,
        dry_run=dry_run,
        issues=list(issues),
    )

    if not row_list:
        return summary

    uncategorized_category, uncategorized_created = await ensure_uncategorized_category(session)
    summary.uncategorized_created = uncategorized_created

    categories = list((await session.execute(select(Category))).scalars().all())
    category_lookup = build_category_path_lookup(categories)

    existing_units = list((await session.execute(select(Unit))).scalars().all())
    units_by_symbol = {normalize_key(unit.symbol): unit for unit in existing_units}
    units_by_name = {normalize_key(unit.name): unit for unit in existing_units}
    resolved_units: dict[str, Unit] = {}
    exact_unit_keys: set[str] = set()
    fallback_unit_keys: set[str] = set()
    fallback_unit: Unit | None = None

    prepared_rows: list[PreparedCatalogRow] = []

    for row in row_list:
        row_messages: list[str] = []

        category = uncategorized_category
        if row.category_path_key:
            resolved_category = category_lookup.get(row.category_path_key)
            if resolved_category is None:
                summary.category_fallbacks += 1
                row_messages.append(
                    f"category path '{format_category_path(row.category_path)}' not found; imported into '{UNCATEGORIZED_CATEGORY_NAME}'"
                )
            else:
                category = resolved_category

        unit = resolved_units.get(row.unit_key)
        if unit is None:
            exact_unit = units_by_symbol.get(row.unit_key) or units_by_name.get(row.unit_key)
            if exact_unit is not None:
                if not exact_unit.is_active:
                    exact_unit.is_active = True
                    await session.flush()
                unit = exact_unit
                resolved_units[row.unit_key] = unit
                if row.unit_key not in exact_unit_keys:
                    exact_unit_keys.add(row.unit_key)
                    summary.units_reused += 1
            else:
                if fallback_unit is None:
                    fallback_unit, created = await ensure_fallback_unit(
                        session,
                        units_by_symbol=units_by_symbol,
                        units_by_name=units_by_name,
                    )
                    if created:
                        summary.units_created += 1
                unit = fallback_unit
                resolved_units[row.unit_key] = unit
                fallback_unit_keys.add(row.unit_key)

        if row.unit_key in fallback_unit_keys:
            summary.unit_fallbacks += 1
            if row.unit_value:
                row_messages.append(
                    f"unknown unit '{row.unit_value}'; fallback to '{DEFAULT_FALLBACK_UNIT_NAME}'"
                )
            else:
                row_messages.append(
                    f"empty unit value; fallback to '{DEFAULT_FALLBACK_UNIT_NAME}'"
                )

        if row_messages:
            summary.issues.append(
                ImportIssue(
                    row_number=row.row_number,
                    item_name=row.item_name,
                    message="; ".join(row_messages),
                )
            )

        prepared_rows.append(
            PreparedCatalogRow(
                source=row,
                category=category,
                unit=unit,
            )
        )

    sku_keys = sorted({row.source.sku_key for row in prepared_rows if row.source.sku_key})
    items_by_sku: dict[str, Item] = {}
    if sku_keys:
        existing_items_by_sku = list(
            (
                await session.execute(
                    select(Item).where(
                        Item.sku.is_not(None),
                        func.lower(Item.sku).in_(sku_keys),
                    )
                )
            ).scalars().all()
        )
        items_by_sku = {normalize_key(item.sku): item for item in existing_items_by_sku}

    items_by_name_category_unit: dict[tuple[str, int, int], Item] = {}
    blank_sku_rows = [row for row in prepared_rows if not row.source.sku_key]
    if blank_sku_rows:
        category_ids = sorted({row.category.id for row in blank_sku_rows})
        existing_blank_sku_items = list(
            (
                await session.execute(
                    select(Item).where(Item.category_id.in_(category_ids))
                )
            ).scalars().all()
        )
        items_by_name_category_unit = {
            (normalize_key(item.name), item.category_id, item.unit_id): item
            for item in existing_blank_sku_items
        }

    for prepared_row in prepared_rows:
        row = prepared_row.source

        if row.sku_key:
            existing_item = items_by_sku.get(row.sku_key)
            if existing_item is not None:
                summary.items_skipped_existing += 1
                continue
        else:
            blank_sku_key = (
                normalize_key(row.item_name),
                prepared_row.category.id,
                prepared_row.unit.id,
            )
            existing_item = items_by_name_category_unit.get(blank_sku_key)
            if existing_item is not None:
                summary.items_skipped_existing += 1
                continue

        item = Item(
            sku=row.sku,
            name=row.item_name,
            category_id=prepared_row.category.id,
            unit_id=prepared_row.unit.id,
            is_active=True,
        )
        session.add(item)
        await session.flush()

        if row.sku_key:
            items_by_sku[row.sku_key] = item
        else:
            items_by_name_category_unit[
                (
                    normalize_key(row.item_name),
                    prepared_row.category.id,
                    prepared_row.unit.id,
                )
            ] = item
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
            invalid_rows_skipped=parsed.invalid_rows_skipped,
            issues=parsed.issues,
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
            "Import items from CSV with category fallback to 'Без категории' "
            "and unit fallback to 'Штука'"
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
    print(f"  invalid rows skipped:   {summary.invalid_rows_skipped}")
    print(f"  duplicate rows skipped: {summary.duplicate_rows_skipped}")
    print(f"  uncategorized created:  {'yes' if summary.uncategorized_created else 'no'}")
    print(f"  units created:          {summary.units_created}")
    print(f"  units reused:           {summary.units_reused}")
    print(f"  unit fallbacks:         {summary.unit_fallbacks}")
    print(f"  category fallbacks:     {summary.category_fallbacks}")
    print(f"  items created:          {summary.items_created}")
    print(f"  items skipped existing: {summary.items_skipped_existing}")
    print(f"  dry run:                {'yes' if summary.dry_run else 'no'}")

    if summary.issues:
        print("\nWarnings / issues:")
        for issue in summary.issues:
            print(f"  - row {issue.row_number} [{issue.item_name}]: {issue.message}")


async def main_async() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    summary = await import_catalog_csv(args.csv_path, dry_run=args.dry_run)
    print_summary(summary)


if __name__ == "__main__":
    asyncio.run(main_async())
