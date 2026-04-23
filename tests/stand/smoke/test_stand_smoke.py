"""
Минимальный smoke тест для проверки работы stand инфраструктуры.

Этот тест проверяет:
1. Что guard-механизмы работают и тест запускается только при наличии стенда
2. Что stand_client корректно подключён к стенду
3. Что базовые health endpoints доступны
4. Что аутентификация через root token работает
"""

import pytest


@pytest.mark.stand
@pytest.mark.smoke
def test_stand_health(stand_client, stand_api_prefix):
    """Проверяет доступность health endpoint стенда."""
    response = stand_client.get(f"{stand_api_prefix}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    print(f"OK: Health check passed: {data}")


@pytest.mark.stand
@pytest.mark.smoke
def test_stand_readiness(stand_client, stand_api_prefix):
    """Проверяет доступность readiness endpoint стенда."""
    response = stand_client.get(f"{stand_api_prefix}/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    print(f"OK: Readiness check passed: {data}")


@pytest.mark.stand
@pytest.mark.smoke
def test_stand_auth(stand_client, stand_api_prefix):
    """Проверяет, что аутентификация через root token работает."""
    # Простой запрос к защищённому endpoint (например, список сайтов)
    response = stand_client.get(f"{stand_api_prefix}/admin/sites")
    assert response.status_code == 200, f"Authentication failed: {response.status_code} {response.text}"
    print(f"OK: Auth check passed: {response.status_code}")


@pytest.mark.stand
@pytest.mark.smoke
def test_stand_run_id(stand_run_id):
    """Проверяет, что run_id генерируется корректно."""
    assert stand_run_id is not None
    assert isinstance(stand_run_id, str)
    assert len(stand_run_id) > 0
    print(f"OK: Run ID: {stand_run_id}")
