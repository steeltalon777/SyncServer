import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Base

load_dotenv()


def _test_database_url() -> str:
    url = os.getenv("DATABASE_URL_TEST") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_TEST or DATABASE_URL is required for tests")
    return url


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return _test_database_url()


@pytest.fixture
async def session_factory(test_db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    schema = f"test_sync_{uuid4().hex[:8]}"
    admin_engine = create_async_engine(test_db_url, poolclass=NullPool)

    async with admin_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        test_db_url,
        connect_args={"server_settings": {"search_path": schema}},
        poolclass=NullPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.fixture
async def db_session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
