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
def test_stand_health(stand_client):
    """Проверяет доступность health endpoint стенда."""
    response = stand_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print(f"✓ Health check passed: {data}")


@pytest.mark.stand
@pytest.mark.smoke
def test_stand_readiness(stand_client):
    """Проверяет доступность readiness endpoint стенда."""
    response = stand_client.get("/api/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    print(f"✓ Readiness check passed: {data}")


@pytest.mark.stand
@pytest.mark.smoke
def test_stand_auth(stand_client):
    """Проверяет, что аутентификация через root token работает."""
    # Простой запрос к защищённому endpoint (например, список сайтов)
    response = stand_client.get("/api/admin/sites")
    # Ожидаем либо 200 (если есть сайты), либо 404 если endpoint не существует
    # Главное - не получить 401 Unauthorized
    assert response.status_code != 401, f"Authentication failed: {response.status_code} {response.text}"
    print(f"✓ Auth check passed: {response.status_code}")


@pytest.mark.stand
@pytest.mark.smoke
def test_stand_run_id(stand_run_id):
    """Проверяет, что run_id генерируется корректно."""
    assert stand_run_id is not None
    assert isinstance(stand_run_id, str)
    assert len(stand_run_id) > 0
    print(f"✓ Run ID: {stand_run_id}")