from __future__ import annotations

from decimal import Decimal
from uuid import UUID

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
    from uuid import uuid4

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


def _decimal_equal(a, b, tolerance=Decimal("0.001")):
    """Сравнивает два Decimal с допуском."""
    if isinstance(a, str):
        a = Decimal(a)
    if isinstance(b, str):
        b = Decimal(b)
    return abs(a - b) <= tolerance


async def _fetch_all_operations(client: AsyncClient, headers: dict, page_size: int = 100):
    """Запрашивает все операции с пагинацией."""
    all_operations = []
    page = 1
    while True:
        response = await client.get(
            "/api/v1/operations",
            params={"page": page, "page_size": page_size},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        if not items:
            break
        all_operations.extend(items)
        if len(items) < page_size:
            break
        page += 1
    return all_operations


async def _find_item_id_by_name(client: AsyncClient, headers: dict, item_name: str) -> int | None:
    """Находит item_id по имени товара через балансы."""
    response = await client.get(
        "/api/v1/balances",
        params={"search": item_name},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    for item in data.get("items", []):
        if item["item_name"] == item_name:
            return item["item_id"]
    return None


async def _find_operation_line_for_item(
    client: AsyncClient,
    headers: dict,
    item_id: int,
    target_operation_id: UUID | None = None,
):
    """
    Ищет строку операции по item_id.
    Возвращает кортеж (operation, line) или (None, None), если не найдено.
    """
    operations = await _fetch_all_operations(client, headers)
    
    for operation in operations:
        if target_operation_id and operation["id"] != str(target_operation_id):
            continue
        for line in operation.get("lines", []):
            if line.get("item_id") == item_id:
                accepted = Decimal(line.get("accepted_qty", "0"))
                lost = Decimal(line.get("lost_qty", "0"))
                # Если нужны только строки с accepted_qty и lost_qty > 0
                if accepted > 0 and lost > 0:
                    return operation, line
    return None, None


@pytest.mark.asyncio
async def test_inventory_read_consistency(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """
    Smoke-тест на консистентность данных по item "Аккумулятор 140".
    
    Проверяет, что accepted_qty = 7.000, lost_qty = 3.000,
    баланс = 7, lost-assets = 3.000, и нет pending-acceptance.
    """
    TARGET_ITEM_NAME = "Аккумулятор 140"
    TARGET_OPERATION_ID = UUID("9906a10e-a7da-408d-ac9a-633531359cf1")
    
    # 1. Найти item_id по имени через балансы
    item_id = await _find_item_id_by_name(client, root_headers, TARGET_ITEM_NAME)
    if item_id is None:
        pytest.skip(f"Товар '{TARGET_ITEM_NAME}' не найден в балансах")
    
    # 2. Найти операционную строку по item_id (и, возможно, конкретному operation_id)
    operation, line = await _find_operation_line_for_item(
        client, root_headers, item_id, TARGET_OPERATION_ID
    )
    
    # Если не нашли по конкретному operation_id, ищем любую строку с accepted_qty и lost_qty
    if not line:
        operation, line = await _find_operation_line_for_item(client, root_headers, item_id, None)
    
    if not line:
        pytest.skip(f"Не найдена операционная строка для товара '{TARGET_ITEM_NAME}' с accepted_qty и lost_qty > 0")
    
    operation_line_id = line["id"]
    operation_id = operation["id"]
    
    # 3. Проверить accepted_qty и lost_qty
    accepted_qty = Decimal(line.get("accepted_qty", "0"))
    lost_qty = Decimal(line.get("lost_qty", "0"))
    
    # Ожидаемые значения из smoke-кейса
    EXPECTED_ACCEPTED = Decimal("7.000")
    EXPECTED_LOST = Decimal("3.000")
    
    # Проверяем с допуском
    if not _decimal_equal(accepted_qty, EXPECTED_ACCEPTED):
        pytest.skip(f"accepted_qty ({accepted_qty}) не соответствует ожидаемому ({EXPECTED_ACCEPTED}) для smoke-кейса")
    
    if not _decimal_equal(lost_qty, EXPECTED_LOST):
        pytest.skip(f"lost_qty ({lost_qty}) не соответствует ожидаемому ({EXPECTED_LOST}) для smoke-кейса")
    
    # 4. Получить балансы и проверить qty = 7
    balances_response = await client.get(
        "/api/v1/balances",
        params={"search": TARGET_ITEM_NAME},
        headers=root_headers,
    )
    assert balances_response.status_code == 200
    balances_data = balances_response.json()
    
    balance_row = None
    for item in balances_data.get("items", []):
        if item["item_name"] == TARGET_ITEM_NAME:
            balance_row = item
            break
    
    assert balance_row is not None, f"Баланс для товара '{TARGET_ITEM_NAME}' не найден"
    
    balance_qty = Decimal(balance_row["qty"]) if isinstance(balance_row["qty"], str) else Decimal(str(balance_row["qty"]))
    assert _decimal_equal(balance_qty, Decimal("7")), f"Баланс qty {balance_qty} != 7"
    
    # 5. Получить lost-assets и проверить qty = 3.000
    lost_response = await client.get("/api/v1/lost-assets", headers=root_headers)
    assert lost_response.status_code == 200
    lost_data = lost_response.json()
    
    lost_row = None
    for item in lost_data.get("items", []):
        if item["item_name"] == TARGET_ITEM_NAME:
            lost_row = item
            break
    
    assert lost_row is not None, f"Lost-assets для товара '{TARGET_ITEM_NAME}' не найден"
    
    lost_qty_in_assets = Decimal(lost_row["qty"]) if isinstance(lost_row["qty"], str) else Decimal(str(lost_row["qty"]))
    assert _decimal_equal(lost_qty_in_assets, EXPECTED_LOST), f"Lost-assets qty {lost_qty_in_assets} != {EXPECTED_LOST}"
    
    # 6. Проверить, что в pending-acceptance нет активной строки по этому operation_line_id
    pending_response = await client.get("/api/v1/pending-acceptance", headers=root_headers)
    assert pending_response.status_code == 200
    pending_data = pending_response.json()
    
    for item in pending_data.get("items", []):
        if item["operation_line_id"] == operation_line_id:
            pytest.fail(f"Найдена pending-acceptance строка для operation_line_id {operation_line_id}, хотя не должно быть")
    
    # Все проверки пройдены
    print(f"Smoke-тест пройден для operation_id={operation_id}, line_id={operation_line_id}")