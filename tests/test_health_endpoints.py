from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas.health import HealthStatus
from main import create_app

app = create_app(enable_startup_migrations=False)


class TestHealthEndpoints:
    """Тесты для health endpoints."""

    @pytest.fixture
    def client(self):
        """Фикстура для тестового клиента."""
        return TestClient(app)

    def test_health_basic(self, client):
        """Тест базового health endpoint."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_ready_basic(self, client):
        """Тест базового ready endpoint."""
        response = client.get("/api/v1/ready")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ready"
        assert "db" in data
        assert data["db"] == 1

    def test_detailed_health_success(self, client):
        """Тест детализированного health endpoint."""
        response = client.get("/api/v1/health/detailed")

        assert response.status_code == 200
        data = response.json()

        # Проверяем структуру ответа
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "checks" in data

        # Проверяем статусы
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

        # Проверяем наличие проверок
        checks = data["checks"]
        assert "database" in checks
        assert "config" in checks
        assert "cache" in checks

        # Проверяем структуру каждой проверки
        for check_name, check_data in checks.items():
            assert "status" in check_data
            assert check_data["status"] in ["healthy", "degraded", "unhealthy", "not_configured"]

            if "latency_ms" in check_data and check_data["latency_ms"] is not None:
                assert isinstance(check_data["latency_ms"], (int, float))
                assert check_data["latency_ms"] >= 0

    def test_readiness_check_success(self, client):
        """Тест readiness endpoint."""
        response = client.get("/api/v1/health/readiness")

        assert response.status_code == 200
        data = response.json()

        # Проверяем структуру ответа
        assert "ready" in data
        assert isinstance(data["ready"], bool)
        assert "timestamp" in data
        assert "details" in data

        # Проверяем детали
        details = data["details"]
        assert "database" in details
        assert "config" in details
        assert isinstance(details["database"], bool)
        assert isinstance(details["config"], bool)

        # В нормальных условиях должно быть ready=True
        assert data["ready"] is True
        assert details["database"] is True
        assert details["config"] is True

    def test_liveness_check_success(self, client):
        """Тест liveness endpoint."""
        response = client.get("/api/v1/health/liveness")

        assert response.status_code == 200
        data = response.json()

        # Проверяем структуру ответа
        assert "alive" in data
        assert isinstance(data["alive"], bool)
        assert "timestamp" in data

        # В нормальных условиях должно быть alive=True
        assert data["alive"] is True

    @pytest.mark.asyncio
    async def test_detailed_health_with_mocked_failure(self, client):
        """Тест детализированного health с моком неудачи."""
        # Мокаем HealthService чтобы симулировать неудачу
        with patch('app.api.routes_health.HealthService') as MockHealthService:
            mock_service = MagicMock()
            mock_service.check_health = AsyncMock(return_value={
                "database": {
                    "status": HealthStatus.UNHEALTHY,
                    "latency_ms": None,
                    "details": "Database connection failed",
                    "error": "Connection refused",
                },
                "config": {
                    "status": HealthStatus.HEALTHY,
                    "latency_ms": None,
                    "details": "All required configurations are present and valid",
                    "error": None,
                },
                "cache": {
                    "status": HealthStatus.NOT_CONFIGURED,
                    "latency_ms": None,
                    "details": "Redis health check is disabled",
                    "error": None,
                },
            })
            mock_service.aggregate_status.return_value = HealthStatus.UNHEALTHY
            MockHealthService.return_value = mock_service

            response = client.get("/api/v1/health/detailed")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["checks"]["database"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_readiness_with_mocked_failure(self, client):
        """Тест readiness с моком неудачи."""
        with patch('app.api.routes_health.HealthService') as MockHealthService:
            mock_service = MagicMock()
            mock_service.check_readiness = AsyncMock(return_value={
                "database": False,
                "config": True,
            })
            MockHealthService.return_value = mock_service

            response = client.get("/api/v1/health/readiness")

            assert response.status_code == 200
            data = response.json()
            assert data["ready"] is False
            assert data["details"]["database"] is False
            assert data["details"]["config"] is True

    @pytest.mark.asyncio
    async def test_liveness_with_mocked_failure(self, client):
        """Тест liveness с моком неудачи."""
        with patch('app.services.health_service.ConfigHealthChecker') as MockChecker:
            mock_checker = MagicMock()
            mock_checker.check = AsyncMock(return_value=SimpleNamespace(status=HealthStatus.UNHEALTHY))
            MockChecker.return_value = mock_checker

            response = client.get("/api/v1/health/liveness")

            assert response.status_code == 200
            data = response.json()
            assert data["alive"] is False

    def test_endpoints_exist_in_openapi(self, client):
        """Проверка что endpoints зарегистрированы в OpenAPI."""
        # Получаем OpenAPI схему
        response = client.get("/api/openapi.json")
        assert response.status_code == 200

        openapi_schema = response.json()
        paths = openapi_schema.get("paths", {})

        # Проверяем что все endpoints существуют
        assert "/api/v1/health" in paths
        assert "/api/v1/ready" in paths
        assert "/api/v1/health/detailed" in paths
        assert "/api/v1/health/readiness" in paths
        assert "/api/v1/health/liveness" in paths
        assert all(not path.startswith("/api/v1/machine") for path in paths)

        # Проверяем методы
        assert "get" in paths["/api/v1/health"]
        assert "get" in paths["/api/v1/ready"]
        assert "get" in paths["/api/v1/health/detailed"]
        assert "get" in paths["/api/v1/health/readiness"]
        assert "get" in paths["/api/v1/health/liveness"]

    def test_response_schemas(self, client):
        """Проверка что ответы соответствуют схемам."""
        # Проверяем detailed health
        response = client.get("/api/v1/health/detailed")
        assert response.status_code == 200

        data = response.json()
        # Проверяем обязательные поля
        assert all(field in data for field in ["status", "timestamp", "version", "checks"])

        # Проверяем checks
        checks = data["checks"]
        for check_name, check_data in checks.items():
            assert "status" in check_data
            # status должен быть одним из допустимых значений
            assert check_data["status"] in [
                "healthy", "degraded", "unhealthy", "not_configured"
            ]
