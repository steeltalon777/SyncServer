import os
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

# Добавляем корень проекта в sys.path для корректного импорта app при прямом запуске pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.core.db import get_db
from app.models import Base
from app.models.document import Document
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from app.services.uow import UnitOfWork
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from main import create_app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

load_dotenv()

app = create_app(enable_startup_migrations=False)


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


@pytest.fixture
async def uow(db_session: AsyncSession) -> AsyncIterator[UnitOfWork]:
    """Общий UnitOfWork для интеграционных тестов сервисного слоя."""
    yield UnitOfWork(db_session)


@pytest.fixture
async def site(db_session: AsyncSession) -> Site:
    """Тестовый активный сайт для сценариев, требующих site_id."""
    site_obj = Site(code=f"SITE-{uuid4().hex[:8]}", name=f"Test Site {uuid4().hex[:4]}", is_active=True)
    db_session.add(site_obj)
    await db_session.flush()
    return site_obj


@pytest.fixture
async def user(db_session: AsyncSession, site: Site) -> User:
    """Тестовый пользователь storekeeper."""
    user_obj = User(
        username=f"storekeeper-{uuid4().hex[:8]}",
        email=f"storekeeper-{uuid4().hex[:8]}@example.com",
        full_name="Storekeeper Test",
        is_active=True,
        is_root=False,
        role="storekeeper",
        default_site_id=site.id,
    )
    db_session.add(user_obj)
    await db_session.flush()
    return user_obj


@pytest.fixture
async def admin_user(db_session: AsyncSession, site: Site) -> User:
    """Тестовый admin/root пользователь для действий каталога с archive/delete."""
    admin_obj = User(
        username=f"admin-{uuid4().hex[:8]}",
        email=f"admin-{uuid4().hex[:8]}@example.com",
        full_name="Admin Test",
        is_active=True,
        is_root=True,
        role="root",
        default_site_id=site.id,
    )
    db_session.add(admin_obj)
    await db_session.flush()
    return admin_obj


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Общий ASGI-клиент для API тестов, использующий ту же test session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def test_site(site: Site, db_session: AsyncSession) -> Site:
    """Совместимый алиас для старых document-тестов."""
    if site.description is None:
        site.description = "Test warehouse site"
        await db_session.flush()
    return site


@pytest.fixture
async def secondary_site(db_session: AsyncSession) -> Site:
    """Дополнительная площадка для MOVE сценариев."""
    site_obj = Site(
        code=f"SITE-{uuid4().hex[:8]}",
        name=f"Secondary Site {uuid4().hex[:4]}",
        description="Secondary warehouse site",
        is_active=True,
    )
    db_session.add(site_obj)
    await db_session.flush()
    return site_obj


@pytest.fixture
async def test_user(db_session: AsyncSession, test_site: Site) -> User:
    """Пользователь с глобальным business-access для route и service тестов документов."""
    user_obj = User(
        username=f"chief-{uuid4().hex[:8]}",
        email=f"chief-{uuid4().hex[:8]}@example.com",
        full_name="Chief Storekeeper Test",
        is_active=True,
        is_root=False,
        role="chief_storekeeper",
        default_site_id=test_site.id,
    )
    db_session.add(user_obj)
    await db_session.flush()
    return user_obj


@pytest.fixture
async def test_user_no_access(db_session: AsyncSession) -> User:
    """Пользователь без прав доступа к test_site."""
    user_obj = User(
        username=f"observer-{uuid4().hex[:8]}",
        email=f"observer-{uuid4().hex[:8]}@example.com",
        full_name="Observer Without Access",
        is_active=True,
        is_root=False,
        role="observer",
        default_site_id=None,
    )
    db_session.add(user_obj)
    await db_session.flush()
    return user_obj


@pytest.fixture
async def auth_headers_user(test_user: User) -> dict[str, str]:
    return {"X-User-Token": str(test_user.user_token)}


@pytest.fixture
async def auth_headers_user_no_access(test_user_no_access: User) -> dict[str, str]:
    return {"X-User-Token": str(test_user_no_access.user_token)}


@pytest.fixture
async def storekeeper_scope(db_session: AsyncSession, user: User, test_site: Site) -> UserAccessScope:
    """Явный scope для локального storekeeper пользователя из базовой фикстуры."""
    scope = UserAccessScope(
        user_id=user.id,
        site_id=test_site.id,
        can_view=True,
        can_operate=True,
        can_manage_catalog=False,
        is_active=True,
    )
    db_session.add(scope)
    await db_session.flush()
    return scope


@pytest.fixture
async def create_operation(db_session: AsyncSession, test_site: Site, test_user: User):
    """Фабрика операций для document tests."""

    async def _create_operation(
        *,
        operation_type: str = "RECEIVE",
        site_obj: Site | None = None,
        created_by: User | None = None,
        destination_site: Site | None = None,
        status: str = "draft",
        notes: str | None = "document test operation",
        recipient_name_snapshot: str | None = None,
        issued_to_name: str | None = None,
        acceptance_required: bool = False,
        acceptance_state: str | None = None,
        line_snapshots: list[dict[str, object]] | None = None,
    ) -> Operation:
        site_obj = site_obj or test_site
        created_by = created_by or test_user
        effective_acceptance_state = acceptance_state or ("pending" if acceptance_required else "not_required")
        submitted_at = datetime.now(UTC) if status == "submitted" else None

        operation = Operation(
            site_id=site_obj.id,
            operation_type=operation_type,
            status=status,
            created_by_user_id=created_by.id,
            source_site_id=site_obj.id if operation_type == "MOVE" else None,
            destination_site_id=destination_site.id if destination_site is not None else None,
            recipient_name_snapshot=recipient_name_snapshot,
            issued_to_name=issued_to_name,
            acceptance_required=acceptance_required,
            acceptance_state=effective_acceptance_state,
            submitted_by_user_id=created_by.id if submitted_at else None,
            submitted_at=submitted_at,
            effective_at=datetime.now(UTC),
            notes=notes,
        )

        default_lines = line_snapshots or [
            {
                "qty": "3.000",
                "item_name_snapshot": "Test Item",
                "item_sku_snapshot": "ITEM-001",
                "unit_name_snapshot": "Pieces",
                "unit_symbol_snapshot": "pcs",
                "category_name_snapshot": "Default Category",
                "batch": "BATCH-001",
                "comment": "first line",
            },
            {
                "qty": "1.500",
                "item_name_snapshot": "Test Item 2",
                "item_sku_snapshot": "ITEM-002",
                "unit_name_snapshot": "Boxes",
                "unit_symbol_snapshot": "box",
                "category_name_snapshot": "Default Category",
                "batch": "BATCH-002",
                "comment": "second line",
            },
        ]

        operation.lines = [
            OperationLine(
                line_number=index,
                item_id=line.get("item_id"),
                qty=Decimal(str(line.get("qty", "1.000"))),
                accepted_qty=Decimal(str(line.get("accepted_qty", "0.000"))),
                lost_qty=Decimal(str(line.get("lost_qty", "0.000"))),
                batch=line.get("batch"),
                comment=line.get("comment"),
                item_name_snapshot=str(line.get("item_name_snapshot", f"Item {index}")),
                item_sku_snapshot=str(line.get("item_sku_snapshot", f"SKU-{index:03d}")),
                unit_name_snapshot=str(line.get("unit_name_snapshot", "Pieces")),
                unit_symbol_snapshot=str(line.get("unit_symbol_snapshot", "pcs")),
                category_name_snapshot=str(line.get("category_name_snapshot", "Default Category")),
            )
            for index, line in enumerate(default_lines, start=1)
        ]

        db_session.add(operation)
        await db_session.flush()
        return operation

    return _create_operation


@pytest.fixture
async def test_operation_with_lines(create_operation) -> Operation:
    return await create_operation()


@pytest.fixture
async def test_move_operation_with_lines(create_operation, secondary_site: Site) -> Operation:
    return await create_operation(
        operation_type="MOVE",
        destination_site=secondary_site,
    )


@pytest.fixture
async def test_issue_operation_with_lines(create_operation) -> Operation:
    return await create_operation(
        operation_type="ISSUE",
        recipient_name_snapshot="Recipient Employee",
        issued_to_name="Issued Employee",
    )


@pytest.fixture
async def test_operation_with_snapshot_lines(create_operation) -> Operation:
    return await create_operation(
        line_snapshots=[
            {
                "qty": "2.000",
                "item_name_snapshot": "Snapshot Item 1",
                "item_sku_snapshot": "SNAP-001",
                "unit_name_snapshot": "Kilogram",
                "unit_symbol_snapshot": "kg",
                "category_name_snapshot": "Food",
                "batch": "SNAP-BATCH-1",
            },
            {
                "qty": "5.000",
                "item_name_snapshot": "Snapshot Item 2",
                "item_sku_snapshot": "SNAP-002",
                "unit_name_snapshot": "Liter",
                "unit_symbol_snapshot": "l",
                "category_name_snapshot": "Liquids",
                "batch": "SNAP-BATCH-2",
            },
        ]
    )


@pytest.fixture
async def create_document(db_session: AsyncSession, test_site: Site, test_user: User):
    """Фабрика документов для route/document tests."""

    async def _create_document(
        *,
        document_type: str = "waybill",
        status: str = "draft",
        site_obj: Site | None = None,
        created_by: User | None = None,
        payload: dict | None = None,
        operation: Operation | None = None,
        template_name: str = "waybill_v1",
        document_number: str | None = None,
    ) -> Document:
        site_obj = site_obj or test_site
        created_by = created_by or test_user
        document = Document(
            document_type=document_type,
            site_id=site_obj.id,
            payload=payload or {"document_title": "Тестовый документ", "lines": []},
            created_by_user_id=created_by.id,
            document_number=document_number or f"DOC-{uuid4().hex[:8]}",
            status=status,
            template_name=template_name,
            template_version="1.0",
            payload_schema_version="1.0.0",
            payload_hash="f" * 64,
            finalized_at=datetime.now(UTC) if status == "finalized" else None,
        )
        db_session.add(document)
        await db_session.flush()

        if operation is not None:
            documents_uow = UnitOfWork(db_session)
            await documents_uow.documents.link_document_to_operation(document.id, operation.id)

        await db_session.flush()
        return document

    return _create_document


@pytest.fixture
async def test_document(create_document, test_operation_with_lines: Operation) -> Document:
    return await create_document(
        operation=test_operation_with_lines,
        payload={
            "document_title": "Товарная накладная",
            "operation_id": str(test_operation_with_lines.id),
            "lines": [
                {"item_name": line.item_name_snapshot, "quantity": float(line.qty)}
                for line in test_operation_with_lines.lines
            ],
        },
    )


@pytest.fixture
async def test_finalized_document(create_document) -> Document:
    return await create_document(status="finalized")


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
                print(f"INFO: Deselected {len(deselected)} stand tests (use -m stand to run them)")


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
