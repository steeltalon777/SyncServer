import asyncio

import asyncpg

from app.core.config import get_settings


async def check_hashtags_column():
    settings = get_settings()
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        result = await conn.fetchrow("""
            SELECT data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'items' AND column_name = 'hashtags'
        """)
        if result:
            print(f'hashtags тип: {result["data_type"]}')
            print(f'hashtags nullable: {result["is_nullable"]}')
        else:
            print('Поле hashtags не найдено в таблице items')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_hashtags_column())
