"""Check database schema configuration."""
import asyncio
import os
import sys

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["APP_ENV"] = "dev"

from sqlalchemy import text
from app.core.db import engine


async def check():
    async with engine.connect() as conn:
        # Check current schema search path
        result = await conn.execute(text("SHOW search_path"))
        print("search_path:", result.scalar())

        # Check if public schema exists
        result = await conn.execute(
            text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = 'public')"
            )
        )
        print("public schema exists:", result.scalar())

        # Check current user and its default schema
        result = await conn.execute(text("SELECT current_user"))
        print("current_user:", result.scalar())

        # Check all schemas
        result = await conn.execute(
            text("SELECT schema_name FROM information_schema.schemata")
        )
        schemas = [row[0] for row in result]
        print("all schemas:", schemas)

        # Check if any tables exist
        result = await conn.execute(
            text(
                "SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'categories'"
            )
        )
        tables = [(row[0], row[1]) for row in result]
        print("categories table exists in:", tables)

        # Check user schema privileges
        result = await conn.execute(
            text(
                "SELECT has_schema_privilege('public', 'USAGE')"
            )
        )
        print("has public schema usage:", result.scalar())

        result = await conn.execute(
            text(
                "SELECT has_schema_privilege('public', 'CREATE')"
            )
        )
        print("has public schema create:", result.scalar())


asyncio.run(check())
