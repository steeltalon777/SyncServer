import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.db import engine


async def migrate() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                ALTER TABLE operations
                ADD COLUMN IF NOT EXISTS effective_at TIMESTAMPTZ NULL
                """
            )
        )

    print("operations.effective_at migration applied successfully.")


if __name__ == "__main__":
    asyncio.run(migrate())
