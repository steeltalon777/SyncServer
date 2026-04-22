"""
Stand-тесты: фикстуры и guard-механизмы для работы с поднятым стендом.

Этот модуль содержит инфраструктуру для тестов, которые требуют внешнего поднятого стенда.
Все stand-тесты должны быть помечены маркером `@pytest.mark.stand`.

Guard-цепочка:
1. Если stand-тесты не были явно выбраны, они автоматически убираются из запуска через deselect.
2. Если stand-тесты были явно выбраны, но guard env не заданы, pytest завершается с ошибкой.
3. Если guard env заданы, выполняется preflight probe стенда.
4. Если probe не прошёл, pytest завершается до старта тестов.
5. Если probe прошёл, создаются фикстуры для работы со стендом.
"""

import os
import sys
from typing import Any, Dict, Optional
from uuid import uuid4

import pytest
import httpx
from pydantic import ValidationError
from pydantic_settings import BaseSettings


class StandSettings(BaseSettings):
    """Настройки тестового стенда, загружаемые из переменных окружения."""
    
    # Обязательные переменные
    SYNC_TEST_MODE: str = ""
    SYNC_TEST_ALLOW_STAND: str = ""
    SYNC_TEST_BASE_URL: str = ""
    SYNC_TEST_ROOT_TOKEN: str = ""
    
    # Опциональные переменные
    SYNC_TEST_DB_URL: Optional[str] = None
    SYNC_TEST_ALLOW_DIRECT_DB: str = ""
    SYNC_TEST_RUN_ID: str = ""
    
    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False


def _validate_stand_settings(settings: StandSettings) -> None:
    """Проверяет, что guard env корректно заданы для запуска stand тестов."""
    errors = []
    
    if settings.SYNC_TEST_MODE.lower() != "stand":
        errors.append("SYNC_TEST_MODE must be 'stand'")
    
    if settings.SYNC_TEST_ALLOW_STAND != "1":
        errors.append("SYNC_TEST_ALLOW_STAND must be '1'")
    
    if not settings.SYNC_TEST_BASE_URL:
        errors.append("SYNC_TEST_BASE_URL is required")
    elif not settings.SYNC_TEST_BASE_URL.startswith(("http://", "https://")):
        errors.append("SYNC_TEST_BASE_URL must start with http:// or https://")
    
    if not settings.SYNC_TEST_ROOT_TOKEN:
        errors.append("SYNC_TEST_ROOT_TOKEN is required")
    
    if errors:
        error_msg = "\n".join([f"  - {error}" for error in errors])
        raise RuntimeError(
            f"Stand guard validation failed:\n{error_msg}\n\n"
            f"Please set required environment variables:\n"
            f"  SYNC_TEST_MODE=stand\n"
            f"  SYNC_TEST_ALLOW_STAND=1\n"
            f"  SYNC_TEST_BASE_URL=http://host:port\n"
            f"  SYNC_TEST_ROOT_TOKEN=<token>\n"
        )


def _probe_stand_health(base_url: str, root_token: str) -> bool:
    """Выполняет preflight probe стенда через health endpoint."""
    try:
        client = httpx.Client(timeout=5.0)
        headers = {"Authorization": f"Bearer {root_token}"}
        
        # Проверяем health endpoint
        health_response = client.get(f"{base_url}/api/health", headers=headers)
        if health_response.status_code != 200:
            print(f"Health check failed: {health_response.status_code} {health_response.text}")
            return False
        
        # Проверяем readiness endpoint
        ready_response = client.get(f"{base_url}/api/health/ready", headers=headers)
        if ready_response.status_code != 200:
            print(f"Readiness check failed: {ready_response.status_code} {ready_response.text}")
            return False
        
        # TODO: В будущем можно добавить проверку test stand identity
        # через специальный endpoint или заголовки
        
        return True
    except Exception as e:
        print(f"Stand probe failed with exception: {e}")
        return False


@pytest.fixture(scope="session")
def stand_settings() -> StandSettings:
    """Фикстура настроек стенда с валидацией guard env."""
    try:
        settings = StandSettings()
    except ValidationError as e:
        raise RuntimeError(f"Failed to load stand settings: {e}")
    
    # Если мы в этом контексте, значит stand тесты были явно выбраны
    # Проверяем guard env
    _validate_stand_settings(settings)
    
    # Выполняем preflight probe
    if not _probe_stand_health(settings.SYNC_TEST_BASE_URL, settings.SYNC_TEST_ROOT_TOKEN):
        raise RuntimeError(
            f"Stand preflight probe failed for {settings.SYNC_TEST_BASE_URL}\n"
            f"Make sure the stand is running and accessible with the provided token."
        )
    
    print(f"✓ Stand guard passed: {settings.SYNC_TEST_BASE_URL}")
    return settings


@pytest.fixture(scope="session")
def stand_run_id(stand_settings: StandSettings) -> str:
    """Уникальный идентификатор запуска для namespacing тестовых данных."""
    if stand_settings.SYNC_TEST_RUN_ID:
        return stand_settings.SYNC_TEST_RUN_ID
    return f"run_{uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def stand_client(stand_settings: StandSettings) -> httpx.Client:
    """HTTP клиент для работы со стендом."""
    client = httpx.Client(
        base_url=stand_settings.SYNC_TEST_BASE_URL.rstrip("/"),
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {stand_settings.SYNC_TEST_ROOT_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    
    # Добавляем run_id в заголовки для трассировки
    # (если стенд поддерживает такой заголовок)
    client.headers["X-Test-Run-ID"] = stand_settings.SYNC_TEST_RUN_ID or "unknown"
    
    yield client
    client.close()


@pytest.fixture(scope="session")
def stand_async_client(stand_settings: StandSettings) -> httpx.AsyncClient:
    """Асинхронный HTTP клиент для работы со стендом."""
    client = httpx.AsyncClient(
        base_url=stand_settings.SYNC_TEST_BASE_URL.rstrip("/"),
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {stand_settings.SYNC_TEST_ROOT_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    
    client.headers["X-Test-Run-ID"] = stand_settings.SYNC_TEST_RUN_ID or "unknown"
    
    yield client
    # Закрытие будет в finally блоках тестов или через async context manager


# Хук для автоматического deselect stand тестов по умолчанию
def pytest_collection_modifyitems(config: Any, items: list) -> None:
    """Автоматически убирает stand тесты из запуска, если они не были явно выбраны."""
    # Проверяем, были ли stand тесты явно выбраны через маркер
    marker_expr = config.getoption("-m", "").lower()
    keyword_expr = config.getoption("-k", "").lower()
    
    has_explicit_stand_marker = (
        marker_expr in ["stand", "integration", "e2e", "smoke"] or
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


# Хук для fail-fast при явном выборе stand тестов без guard env
def pytest_sessionstart(session: Any) -> None:
    """Проверяет guard env при явном выборе stand тестов."""
    # Проверяем, есть ли stand тесты в сессии
    has_stand_tests = any(
        item.get_closest_marker("stand") for item in session.items
    )
    
    if not has_stand_tests:
        return
    
    # Если есть stand тесты, проверяем guard env
    try:
        settings = StandSettings()
        _validate_stand_settings(settings)
        
        # Проверяем preflight probe
        if not _probe_stand_health(settings.SYNC_TEST_BASE_URL, settings.SYNC_TEST_ROOT_TOKEN):
            session.shouldstop = "Stand preflight probe failed"
            raise RuntimeError("Stand preflight probe failed")
            
    except Exception as e:
        # Прерываем сессию с понятным сообщением
        session.shouldstop = str(e)
        raise