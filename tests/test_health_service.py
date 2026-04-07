from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.health import HealthCheckDetail
from app.services.health_service import (
    ConfigHealthChecker,
    DatabaseHealthChecker,
    HealthService,
    HealthStatus,
    RedisHealthChecker,
)


class TestDatabaseHealthChecker:
    """Тесты для DatabaseHealthChecker."""

    @pytest.mark.asyncio
    async def test_check_success(self, session_factory):
        """Успешная проверка базы данных."""
        async with session_factory() as session:
            checker = DatabaseHealthChecker(session)
            result = await checker.check()

            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None
            assert result.latency_ms >= 0
            assert result.details is not None
            assert "successful" in result.details.lower()
            assert result.error is None

    @pytest.mark.asyncio
    async def test_check_timeout(self, session_factory):
        """Проверка таймаута базы данных."""
        async with session_factory() as session:
            checker = DatabaseHealthChecker(session)

            # Мокаем execute чтобы вызвать таймаут
            with patch.object(session, 'execute', side_effect=TimeoutError):
                result = await checker.check()

                assert result.status == HealthStatus.UNHEALTHY
                assert result.details is not None
                assert "timeout" in result.details.lower()
                assert result.error is not None

    @pytest.mark.asyncio
    async def test_check_exception(self, session_factory):
        """Проверка исключения при подключении к БД."""
        async with session_factory() as session:
            checker = DatabaseHealthChecker(session)

            # Мокаем execute чтобы вызвать исключение
            with patch.object(session, 'execute', side_effect=Exception("DB error")):
                result = await checker.check()

                assert result.status == HealthStatus.UNHEALTHY
                assert result.details is not None
                assert "failed" in result.details.lower()
                assert result.error is not None
                assert "DB error" in result.error


class TestConfigHealthChecker:
    """Тесты для ConfigHealthChecker."""

    @pytest.mark.asyncio
    async def test_check_success(self):
        """Успешная проверка конфигурации."""
        with patch('app.services.health_service.get_settings') as mock_settings:
            mock_settings.return_value.DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/db"

            checker = ConfigHealthChecker()
            result = await checker.check()

            assert result.status == HealthStatus.HEALTHY
            assert result.details is not None
            assert "present" in result.details.lower()
            assert result.error is None

    @pytest.mark.asyncio
    async def test_check_missing_config(self):
        """Проверка отсутствия обязательной конфигурации."""
        with patch('app.services.health_service.get_settings') as mock_settings:
            mock_settings.return_value.DATABASE_URL = ""

            checker = ConfigHealthChecker()
            result = await checker.check()

            assert result.status == HealthStatus.UNHEALTHY
            assert result.details is not None
            assert "missing" in result.details.lower()
            assert result.error is not None
            assert "DATABASE_URL" in result.error

    @pytest.mark.asyncio
    async def test_check_invalid_db_url(self):
        """Проверка невалидного URL базы данных."""
        with patch('app.services.health_service.get_settings') as mock_settings:
            mock_settings.return_value.DATABASE_URL = "invalid://url"

            checker = ConfigHealthChecker()
            result = await checker.check()

            assert result.status == HealthStatus.UNHEALTHY
            assert result.details is not None
            assert "invalid" in result.details.lower()
            assert result.error is not None
            assert "Invalid DB URL" in result.error


class TestRedisHealthChecker:
    """Тесты для RedisHealthChecker."""

    @pytest.mark.asyncio
    async def test_check_disabled(self):
        """Проверка когда Redis отключен."""
        with patch('app.services.health_service.get_settings') as mock_settings:
            mock_settings.return_value.HEALTH_CHECK_ENABLE_REDIS = False
            mock_settings.return_value.HEALTH_CHECK_REDIS_URL = None

            checker = RedisHealthChecker()
            result = await checker.check()

            assert result.status == HealthStatus.NOT_CONFIGURED
            assert result.details is not None
            assert "disabled" in result.details.lower()
            assert result.error is None

    @pytest.mark.asyncio
    async def test_check_enabled_no_url(self):
        """Проверка когда Redis включен, но URL не настроен."""
        with patch('app.services.health_service.get_settings') as mock_settings:
            mock_settings.return_value.HEALTH_CHECK_ENABLE_REDIS = True
            mock_settings.return_value.HEALTH_CHECK_REDIS_URL = None

            checker = RedisHealthChecker()
            result = await checker.check()

            assert result.status == HealthStatus.UNHEALTHY
            assert result.details is not None
            assert "not configured" in result.details.lower()
            assert result.error is not None
            assert "HEALTH_CHECK_REDIS_URL" in result.error

    @pytest.mark.asyncio
    async def test_check_not_implemented(self):
        """Проверка когда Redis включен, но не реализован."""
        with patch('app.services.health_service.get_settings') as mock_settings:
            mock_settings.return_value.HEALTH_CHECK_ENABLE_REDIS = True
            mock_settings.return_value.HEALTH_CHECK_REDIS_URL = "redis://localhost"

            checker = RedisHealthChecker()
            result = await checker.check()

            assert result.status == HealthStatus.NOT_CONFIGURED
            assert result.details is not None
            assert "not yet implemented" in result.details.lower()
            assert result.error is None


class TestHealthService:
    """Тесты для HealthService."""

    @pytest.mark.asyncio
    async def test_check_health_success(self, session_factory):
        """Успешная проверка всех компонентов."""
        async with session_factory() as session:
            health_service = HealthService(session)
            results = await health_service.check_health()

            assert "database" in results
            assert "config" in results
            assert "cache" in results

            # Проверяем что база данных и конфигурация здоровы
            assert results["database"].status == HealthStatus.HEALTHY
            assert results["config"].status == HealthStatus.HEALTHY
            # Redis должен быть not_configured (по умолчанию отключен)
            assert results["cache"].status == HealthStatus.NOT_CONFIGURED

    @pytest.mark.asyncio
    async def test_aggregate_status_all_healthy(self):
        """Агрегация статусов когда все здоровы."""
        session = AsyncMock()
        health_service = HealthService(session)

        results = {
            "database": HealthCheckDetail(
                status=HealthStatus.HEALTHY,
                latency_ms=10,
                details="OK",
                error=None
            ),
            "config": HealthCheckDetail(
                status=HealthStatus.HEALTHY,
                latency_ms=None,
                details="OK",
                error=None
            ),
        }

        status = health_service.aggregate_status(results)
        assert status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_aggregate_status_critical_unhealthy(self):
        """Агрегация статусов когда критический компонент нездоров."""
        session = AsyncMock()
        health_service = HealthService(session)

        results = {
            "database": HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details="Failed",
                error="Error"
            ),
            "config": HealthCheckDetail(
                status=HealthStatus.HEALTHY,
                latency_ms=None,
                details="OK",
                error=None
            ),
        }

        status = health_service.aggregate_status(results)
        assert status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_aggregate_status_non_critical_unhealthy(self):
        """Агрегация статусов когда не критический компонент нездоров."""
        session = AsyncMock()
        health_service = HealthService(session)

        results = {
            "database": HealthCheckDetail(
                status=HealthStatus.HEALTHY,
                latency_ms=10,
                details="OK",
                error=None
            ),
            "config": HealthCheckDetail(
                status=HealthStatus.HEALTHY,
                latency_ms=None,
                details="OK",
                error=None
            ),
            "cache": HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details="Failed",
                error="Error"
            ),
        }

        status = health_service.aggregate_status(results)
        assert status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_check_readiness(self, session_factory):
        """Проверка готовности системы."""
        async with session_factory() as session:
            health_service = HealthService(session)
            readiness = await health_service.check_readiness()

            # Критические зависимости: database и config
            assert "database" in readiness
            assert "config" in readiness
            assert "cache" not in readiness  # cache не критический

            # Должны быть готовы
            assert readiness["database"] is True
            assert readiness["config"] is True

    @pytest.mark.asyncio
    async def test_check_liveness(self, session_factory):
        """Проверка живучести системы."""
        async with session_factory() as session:
            health_service = HealthService(session)
            alive = await health_service.check_liveness()

            # В нормальных условиях должна быть жива
            assert alive is True

    @pytest.mark.asyncio
    async def test_check_with_timeout(self, session_factory):
        """Проверка с таймаутом."""
        async with session_factory() as session:
            health_service = HealthService(session)

            # Мокаем checker чтобы вызвать таймаут
            with patch.object(DatabaseHealthChecker, 'check', side_effect=TimeoutError):
                results = await health_service.check_health()

                # Должен быть статус unhealthy для database
                assert results["database"].status == HealthStatus.UNHEALTHY
                assert results["database"].details is not None
                assert "timeout" in results["database"].details.lower()
