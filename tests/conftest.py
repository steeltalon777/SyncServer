import os
import sys
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

# Добавляем корень проекта в sys.path для корректного импорта app при прямом запуске pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# Хуки для управления stand тестами
def pytest_collection_modifyitems(config: Any, items: list) -> None:
    """
    Автоматически убирает stand тесты из запуска по умолчанию.
    
    Этот хук дублирует логику из tests/stand/conftest.py для гарантии,
    что stand тесты не запустятся случайно даже если stand conftest не загружен.
    """
    # Проверяем, были ли stand тесты явно выбраны через маркер
    marker_expr = config.getoption("-m", "").lower()
    keyword_expr = config.getoption("-k", "").lower()
    
    has_explicit_stand_marker = (
        "stand" in marker_expr or
        "integration" in marker_expr or
        "e2e" in marker_expr or
        "smoke" in marker_expr or
        "stand" in keyword_expr
    )
    
    # Если stand тесты не были явно выбраны, убираем их
    if not has_explicit_stand_marker:
        selected = []
        deselected = []
        
        for item in items:
            # Проверяем маркеры stand, integration, e2e, smoke
            if any(
                item.get_closest_marker(marker)
                for marker in ["stand", "integration", "e2e", "smoke"]
            ):
                deselected.append(item)
            else:
                selected.append(item)
        
        if deselected:
            config.hook.pytest_deselected(items=deselected)
            items[:] = selected
            if config.option.verbose >= 1:
                print(f"ℹ️  Deselected {len(deselected)} stand tests (use -m stand to run them)")


def pytest_configure(config: Any) -> None:
    """Регистрирует маркеры для pytest."""
    config.addinivalue_line(
        "markers",
        "unit: быстрые локальные тесты без реального HTTP и БД"
    )
    config.addinivalue_line(
        "markers",
        "stand: тесты, требующие внешнего поднятого стенда"
    )
    config.addinivalue_line(
        "markers",
        "integration: stand-based API and repository integration"
    )
    config.addinivalue_line(
        "markers",
        "e2e: длинные пользовательские workflow"
    )
    config.addinivalue_line(
        "markers",
        "smoke: минимальная проверка доступности стенда"
    )
    config.addinivalue_line(
        "markers",
        "serial: нельзя параллелить"
    )
    config.addinivalue_line(
        "markers",
        "destructive: агрессивно изменяет состояние стенда"
    )
    config.addinivalue_line(
        "markers",
        "requires_reset: требует заранее сброшенного known baseline"
    )
    config.addinivalue_line(
        "markers",
        "stand_db: прямое обращение к stand database (отдельный guard)"
    )
