import asyncio

from sqlalchemy import text

from app.core.db import engine


async def migrate() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE operations DROP CONSTRAINT IF EXISTS ck_operations_type"))
        await conn.execute(
            text(
                """
                ALTER TABLE operations
                ADD CONSTRAINT ck_operations_type CHECK (
                    operation_type IN (
                        'RECEIVE',
                        'EXPENSE',
                        'WRITE_OFF',
                        'MOVE',
                        'ADJUSTMENT',
                        'ISSUE',
                        'ISSUE_RETURN'
                    )
                )
                """
            )
        )
        await conn.execute(text("ALTER TABLE operation_lines DROP CONSTRAINT IF EXISTS ck_operation_lines_qty_positive"))
        await conn.execute(text("ALTER TABLE operation_lines DROP CONSTRAINT IF EXISTS ck_operation_lines_qty_non_zero"))
        await conn.execute(
            text(
                """
                ALTER TABLE operation_lines
                ADD CONSTRAINT ck_operation_lines_qty_non_zero CHECK (qty <> 0)
                """
            )
        )

    print("Operation constraints migrated successfully.")


if __name__ == "__main__":
    asyncio.run(migrate())
