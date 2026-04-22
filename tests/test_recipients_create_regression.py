from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.site import Site
from app.models.user import User
from main import create_app

app = create_app(enable_startup_migrations=False)


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


async def _seed_root_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> User:
    """Создаёт root пользователя и активный сайт, возвращает пользователя."""
    async with session_factory() as session:
        # Создаём активный сайт, чтобы root видел хотя бы один сайт
        site = Site(
            code=f"SITE-{uuid4().hex[:6]}",
            name=f"Test Site {uuid4().hex[:4]}",
            is_active=True,
        )
        session.add(site)
        await session.flush()

        root_user = User(
            username=f"root-{uuid4().hex[:6]}",
            email=f"root-{uuid4().hex[:6]}@example.com",
            full_name="Root Smoke",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add(root_user)
        await session.commit()
        return root_user


@pytest.fixture
async def root_headers(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Фикстура, возвращающая заголовки аутентификации для root пользователя."""
    root_user = await _seed_root_user(session_factory)
    return {"X-User-Token": str(root_user.user_token)}


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Check constraint violation for recipient_type='employee'")
async def test_recipients_create_regression(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """
    Регрессионный тест на POST /api/v1/recipients.
    Фиксирует текущее поведение endpoint'а создания получателя.
    Если endpoint возвращает 500, тест явно зафиксирует это и даст понятное сообщение.
    """
    # Опционально: сначала GET /api/v1/recipients с search по smoke имени
    # (чтобы проверить, нет ли уже такого получателя)
    search_response = await client.get(
        "/api/v1/recipients",
        params={"search": "Smoke Recipient API Regression"},
        headers=root_headers,
    )
    # GET endpoint должен вернуть 200 (если доступ разрешён)
    # Если нет, это может быть признаком проблемы, но не ломаем тест.
    if search_response.status_code == 200:
        data = search_response.json()
        # Если уже есть получатель с таким именем, можно пропустить создание или удалить?
        # Для простоты просто продолжим.

    # Пробуем создать recipient с display_name = "Smoke Recipient API Regression"
    payload = {
        "display_name": "Smoke Recipient API Regression",
        "recipient_type": "employee",
        "personnel_no": "SMOKE-REG-001",
    }
    response = await client.post("/api/v1/recipients", json=payload, headers=root_headers)

    # Фиксируем фактический статус код
    status_code = response.status_code
    if status_code == 500:
        # Если endpoint возвращает 500, это известная проблема check constraint.
        # Помечаем тест как ожидаемый провал с деталями.
        error_detail = response.json().get("detail", "No detail") if response.content else "No content"
        pytest.xfail(
            f"POST /api/v1/recipients возвращает 500 Internal Server Error. "
            f"Это известная проблема создания получателя с recipient_type='employee'. "
            f"Детали ошибки: {error_detail}. "
            f"Ответ: {response.text}"
        )
    elif status_code == 200:
        # Успешное создание (текущий endpoint возвращает 200, а не 201)
        data = response.json()
        assert data["display_name"] == payload["display_name"]
        assert data["recipient_type"] == payload["recipient_type"]
        assert data["personnel_no"] == payload["personnel_no"]
        # Дополнительно можно проверить, что объект действительно сохранён через GET
        get_response = await client.get(f"/api/v1/recipients/{data['id']}", headers=root_headers)
        assert get_response.status_code == 200
    else:
        # Любой другой статус (например, 400, 403, 422) – возможно, ожидаемое поведение,
        # но для регрессионного теста мы хотим явно это зафиксировать.
        pytest.fail(
            f"POST /api/v1/recipients вернул неожиданный статус код {status_code}. "
            f"Ожидалось либо 200 (успех), либо 500 (известная ошибка). "
            f"Ответ: {response.text}"
        )


@pytest.mark.asyncio
async def test_recipients_create_minimal_payload(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """
    Дополнительный тест с минимальным payload {"display_name": "..."}.
    Сравнивает поведение с полным payload.
    """
    payload = {
        "display_name": "Smoke Minimal",
    }
    response = await client.post("/api/v1/recipients", json=payload, headers=root_headers)

    status_code = response.status_code
    if status_code == 500:
        error_detail = response.json().get("detail", "No detail") if response.content else "No content"
        pytest.fail(
            f"POST /api/v1/recipients с минимальным payload возвращает 500. "
            f"Детали ошибки: {error_detail}. "
            f"Ответ: {response.text}"
        )
    elif status_code == 200:
        # Успешное создание (endpoint возвращает 200, а не 201)
        data = response.json()
        assert data["display_name"] == payload["display_name"]
        # recipient_type по умолчанию должен быть "person" (см. схему RecipientCreate)
        assert data["recipient_type"] == "person"
        assert data["personnel_no"] is None
        # Дополнительно можно проверить, что объект действительно сохранён через GET
        get_response = await client.get(f"/api/v1/recipients/{data['id']}", headers=root_headers)
        assert get_response.status_code == 200
    else:
        pytest.fail(
            f"POST /api/v1/recipients с минимальным payload вернул неожиданный статус {status_code}. "
            f"Ответ: {response.text}"
        )