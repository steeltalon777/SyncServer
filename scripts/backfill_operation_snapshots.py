import asyncio
import sys
from pathlib import Path
from typing import List, Tuple

from sqlalchemy import join, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import get_settings
from app.core.db import engine

settings = get_settings()


async def backfill_operation_snapshots(batch_size: int = 1000) -> None:
    """
    Заполняет snapshot поля в существующих записях operation_lines.

    Обновляет:
    - item_name_snapshot из items.name
    - item_sku_snapshot из items.sku
    - unit_name_snapshot из units.name
    - unit_symbol_snapshot из units.symbol
    - category_name_snapshot из categories.name

    Выполняется пакетно для больших таблиц.
    """
    print("Начинаем backfill snapshot полей в operation_lines...")

    async with engine.begin() as conn:
        # Сначала проверим, есть ли записи для обновления
        result = await conn.execute(
            text("""
                SELECT COUNT(*)
                FROM operation_lines ol
                LEFT JOIN items i ON ol.item_id = i.id
                LEFT JOIN units u ON i.unit_id = u.id
                LEFT JOIN categories c ON i.category_id = c.id
                WHERE ol.item_name_snapshot IS NULL
                   OR ol.item_sku_snapshot IS NULL
                   OR ol.unit_name_snapshot IS NULL
                   OR ol.unit_symbol_snapshot IS NULL
                   OR ol.category_name_snapshot IS NULL
            """)
        )
        total_to_update = result.scalar()
        print(f"Всего записей для обновления: {total_to_update}")

        if total_to_update == 0:
            print("Все snapshot поля уже заполнены. Backfill не требуется.")
            return

    # Выполняем обновление пакетами
    offset = 0
    updated_count = 0

    while True:
        async with engine.begin() as conn:
            # Получаем batch записей для обновления
            result = await conn.execute(
                text("""
                    SELECT ol.id, i.name, i.sku, u.name, u.symbol, c.name
                    FROM operation_lines ol
                    LEFT JOIN items i ON ol.item_id = i.id
                    LEFT JOIN units u ON i.unit_id = u.id
                    LEFT JOIN categories c ON i.category_id = c.id
                    WHERE (ol.item_name_snapshot IS NULL
                           OR ol.item_sku_snapshot IS NULL
                           OR ol.unit_name_snapshot IS NULL
                           OR ol.unit_symbol_snapshot IS NULL
                           OR ol.category_name_snapshot IS NULL)
                    ORDER BY ol.id
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": batch_size, "offset": offset}
            )

            batch = result.fetchall()
            if not batch:
                break

            # Подготавливаем массовое обновление
            update_values = []
            for line_id, item_name, item_sku, unit_name, unit_symbol, category_name in batch:
                update_values.append({
                    "line_id": line_id,
                    "item_name": item_name or "",
                    "item_sku": item_sku or "",
                    "unit_name": unit_name or "",
                    "unit_symbol": unit_symbol or "",
                    "category_name": category_name or ""
                })

            # Выполняем массовое обновление
            if update_values:
                # Для каждой записи выполняем отдельный UPDATE (простой подход)
                for v in update_values:
                    await conn.execute(
                        text("""
                            UPDATE operation_lines
                            SET
                                item_name_snapshot = :item_name,
                                item_sku_snapshot = :item_sku,
                                unit_name_snapshot = :unit_name,
                                unit_symbol_snapshot = :unit_symbol,
                                category_name_snapshot = :category_name
                            WHERE id = :line_id
                        """),
                        {
                            "line_id": v["line_id"],
                            "item_name": v["item_name"],
                            "item_sku": v["item_sku"],
                            "unit_name": v["unit_name"],
                            "unit_symbol": v["unit_symbol"],
                            "category_name": v["category_name"]
                        }
                    )

            batch_updated = len(batch)
            updated_count += batch_updated
            offset += batch_size

            print(f"Обновлено {batch_updated} записей. Всего обновлено: {updated_count}/{total_to_update}")

    print(f"Backfill завершен. Всего обновлено {updated_count} записей.")

    # Проверяем результат
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT
                    COUNT(*) as total_lines,
                    COUNT(CASE WHEN item_name_snapshot IS NULL THEN 1 END) as missing_item_name,
                    COUNT(CASE WHEN item_sku_snapshot IS NULL THEN 1 END) as missing_item_sku,
                    COUNT(CASE WHEN unit_name_snapshot IS NULL THEN 1 END) as missing_unit_name,
                    COUNT(CASE WHEN unit_symbol_snapshot IS NULL THEN 1 END) as missing_unit_symbol,
                    COUNT(CASE WHEN category_name_snapshot IS NULL THEN 1 END) as missing_category_name
                FROM operation_lines
            """)
        )
        row = result.fetchone()
        if row is None:
            print("Ошибка: не удалось получить статистику.")
            return

        total_lines = row[0] or 0
        missing_item_name = row[1] or 0
        missing_item_sku = row[2] or 0
        missing_unit_name = row[3] or 0
        missing_unit_symbol = row[4] or 0
        missing_category_name = row[5] or 0

        print("\nСтатистика после backfill:")
        print(f"  Всего записей в operation_lines: {total_lines}")
        print(f"  Записей без item_name_snapshot: {missing_item_name}")
        print(f"  Записей без item_sku_snapshot: {missing_item_sku}")
        print(f"  Записей без unit_name_snapshot: {missing_unit_name}")
        print(f"  Записей без unit_symbol_snapshot: {missing_unit_symbol}")
        print(f"  Записей без category_name_snapshot: {missing_category_name}")

        if (missing_item_name > 0 or missing_item_sku > 0 or
            missing_unit_name > 0 or missing_unit_symbol > 0 or
            missing_category_name > 0):
            print("\nВНИМАНИЕ: Некоторые snapshot поля остались незаполненными.")
            print("Возможно, некоторые items/units/categories были удалены.")
        else:
            print("\n[OK] Все snapshot поля успешно заполнены.")


async def main() -> None:
    """Основная функция для запуска backfill."""
    try:
        await backfill_operation_snapshots(batch_size=1000)
    except Exception as e:
        print(f"Ошибка при выполнении backfill: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
