import asyncio
import sys

sys.path.append('.')
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


async def main():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.connect() as conn:
        # Проверяем текущую версию в alembic_version
        result = await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        version = result.scalar()
        print(f"Текущая версия в БД: {version}")
        print(f"Длина версии: {len(version)} символов")

        # Проверяем структуру столбца version_num
        result = await conn.execute(
            sa.text("""
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'alembic_version' AND column_name = 'version_num'
            """)
        )
        max_len = result.scalar()
        print(f"Максимальная длина столбца version_num: {max_len}")

        # Проверяем наличие таблиц из миграции 0004
        tables = ['recipients', 'recipient_aliases']
        for table in tables:
            result = await conn.execute(
                sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"),
                {"table": table}
            )
            exists = result.scalar()
            print(f"Таблица {table} существует: {exists}")

        # Проверяем наличие столбцов в operations
        columns = ['recipient_id', 'recipient_name_snapshot', 'acceptance_required', 'acceptance_state', 'acceptance_resolved_at']
        for col in columns:
            result = await conn.execute(
                sa.text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'operations' AND column_name = :col
                    )
                """),
                {"col": col}
            )
            exists = result.scalar()
            print(f"Столбец {col} в operations существует: {exists}")

        # Проверяем наличие индексов
        result = await conn.execute(
            sa.text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename IN ('recipients', 'recipient_aliases')
            """)
        )
        indexes = result.scalars().all()
        print(f"Индексы для таблиц recipients/aliases: {indexes}")

        # Проверяем, что ограничения добавлены
        result = await conn.execute(
            sa.text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'recipients' AND constraint_type = 'CHECK'
            """)
        )
        constraints = result.scalars().all()
        print(f"CHECK ограничения в recipients: {constraints}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
