from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.health import HealthCheckDetail, HealthStatus

logger = logging.getLogger(__name__)


class HealthChecker(ABC):
    """Абстрактный базовый класс для проверки здоровья."""

    def __init__(self, name: str, critical: bool = True):
        self.name = name
        self.critical = critical
        self.settings = get_settings()

    @abstractmethod
    async def check(self) -> HealthCheckDetail:
        """Выполнить проверку и вернуть результат."""
        pass

    async def _measure_latency(self, check_func) -> tuple[float, Any]:
        """Измерить время выполнения функции проверки."""
        start_time = time.time()
        try:
            result = await check_func()
            latency_ms = (time.time() - start_time) * 1000
            return latency_ms, result
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return latency_ms, e


class DatabaseHealthChecker(HealthChecker):
    """Проверка подключения к базе данных PostgreSQL."""

    def __init__(self, session: AsyncSession):
        super().__init__("database", critical=True)
        self.session = session

    async def check(self) -> HealthCheckDetail:
        """Проверить подключение к базе данных."""
        try:
            latency_ms, result = await self._measure_latency(
                lambda: self.session.execute(text("SELECT 1"))
            )

            if isinstance(result, Exception):
                raise result

            # Проверяем, что запрос выполнился успешно
            scalar_result = result.scalar_one()
            if scalar_result == 1:
                return HealthCheckDetail(
                    status=HealthStatus.HEALTHY,
                    latency_ms=round(latency_ms, 2),
                    details="Database connection successful",
                    error=None,
                )
            else:
                return HealthCheckDetail(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=round(latency_ms, 2),
                    details="Database query returned unexpected result",
                    error=f"Unexpected result: {scalar_result}",
                )

        except asyncio.TimeoutError:
            return HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details="Database connection timeout",
                error="Connection timeout exceeded",
            )

        except Exception as e:
            logger.exception("Database health check failed")
            return HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details="Database connection failed",
                error=str(e),
            )


class ConfigHealthChecker(HealthChecker):
    """Проверка конфигурации приложения."""

    def __init__(self):
        super().__init__("config", critical=True)

    async def check(self) -> HealthCheckDetail:
        """Проверить наличие обязательных конфигурационных параметров."""
        try:
            # Проверяем обязательные параметры
            required_configs = [
                ("DATABASE_URL", self.settings.DATABASE_URL),
            ]

            missing_configs = []
            for name, value in required_configs:
                if not value:
                    missing_configs.append(name)

            if missing_configs:
                return HealthCheckDetail(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=None,
                    details="Missing required configuration",
                    error=f"Missing configs: {', '.join(missing_configs)}",
                )

            # Проверяем валидность URL базы данных
            db_url = self.settings.DATABASE_URL
            if not db_url.startswith(("postgresql://", "postgresql+asyncpg://")):
                return HealthCheckDetail(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=None,
                    details="Invalid database URL format",
                    error=f"Invalid DB URL format: {db_url[:50]}...",
                )

            return HealthCheckDetail(
                status=HealthStatus.HEALTHY,
                latency_ms=None,
                details="All required configurations are present and valid",
                error=None,
            )

        except Exception as e:
            logger.exception("Config health check failed")
            return HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details="Configuration check failed",
                error=str(e),
            )


class RedisHealthChecker(HealthChecker):
    """Проверка подключения к Redis (опционально)."""

    def __init__(self):
        super().__init__("cache", critical=False)

    async def check(self) -> HealthCheckDetail:
        """Проверить подключение к Redis, если настроено."""
        if not self.settings.HEALTH_CHECK_ENABLE_REDIS:
            return HealthCheckDetail(
                status=HealthStatus.NOT_CONFIGURED,
                latency_ms=None,
                details="Redis health check is disabled",
                error=None,
            )

        if not self.settings.HEALTH_CHECK_REDIS_URL:
            return HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details="Redis URL is not configured",
                error="HEALTH_CHECK_REDIS_URL is not set",
            )

        try:
            # Здесь должна быть реализация проверки Redis
            # Для простоты возвращаем not_configured, так как Redis пока не используется
            return HealthCheckDetail(
                status=HealthStatus.NOT_CONFIGURED,
                latency_ms=None,
                details="Redis is not yet implemented in the application",
                error=None,
            )

        except Exception as e:
            logger.exception("Redis health check failed")
            return HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details="Redis connection failed",
                error=str(e),
            )


class HealthService:
    """Сервис для проверки здоровья системы."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

        # Инициализируем проверки
        self.checkers: list[HealthChecker] = [
            DatabaseHealthChecker(session),
            ConfigHealthChecker(),
            RedisHealthChecker(),
        ]

    async def check_health(self) -> dict[str, HealthCheckDetail]:
        """Выполнить все проверки здоровья."""
        results = {}

        # Выполняем проверки параллельно с таймаутом
        tasks = []
        for checker in self.checkers:
            task = asyncio.create_task(self._run_check_with_timeout(checker))
            tasks.append((checker.name, task))

        for name, task in tasks:
            try:
                result = await task
                results[name] = result
            except Exception as e:
                logger.exception("Health check task failed: %s", name)
                results[name] = HealthCheckDetail(
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=None,
                    details=f"Health check failed: {name}",
                    error=str(e),
                )

        return results

    async def _run_check_with_timeout(self, checker: HealthChecker) -> HealthCheckDetail:
        """Выполнить проверку с таймаутом."""
        try:
            return await asyncio.wait_for(
                checker.check(),
                timeout=self.settings.HEALTH_CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details=f"Health check timeout: {checker.name}",
                error=f"Timeout after {self.settings.HEALTH_CHECK_TIMEOUT}s",
            )
        except Exception as e:
            logger.exception("Health check failed: %s", checker.name)
            return HealthCheckDetail(
                status=HealthStatus.UNHEALTHY,
                latency_ms=None,
                details=f"Health check failed: {checker.name}",
                error=str(e),
            )

    def aggregate_status(self, results: dict[str, HealthCheckDetail]) -> HealthStatus:
        """Агрегировать результаты проверок в общий статус."""
        if not results:
            return HealthStatus.UNHEALTHY

        # Считаем статусы
        status_counts = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 0,
            HealthStatus.UNHEALTHY: 0,
            HealthStatus.NOT_CONFIGURED: 0,
        }

        critical_unhealthy = False
        non_critical_unhealthy = False

        for checker in self.checkers:
            result = results.get(checker.name)
            if not result:
                continue

            status_counts[result.status] += 1

            # Проверяем критические проверки
            if checker.critical and result.status == HealthStatus.UNHEALTHY:
                critical_unhealthy = True
            elif not checker.critical and result.status == HealthStatus.UNHEALTHY:
                non_critical_unhealthy = True

        # Определяем общий статус
        if critical_unhealthy:
            return HealthStatus.UNHEALTHY
        elif non_critical_unhealthy:
            return HealthStatus.DEGRADED
        elif status_counts[HealthStatus.HEALTHY] > 0:
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.DEGRADED

    async def check_readiness(self) -> dict[str, bool]:
        """Проверить готовность системы (критические зависимости)."""
        results = await self.check_health()
        readiness = {}

        for checker in self.checkers:
            if checker.critical:
                result = results.get(checker.name)
                readiness[checker.name] = (
                    result is not None and result.status == HealthStatus.HEALTHY
                )

        return readiness

    async def check_liveness(self) -> bool:
        """Проверить живучесть системы (базовые проверки)."""
        # Для liveness проверяем только самые базовые вещи
        try:
            # Быстрая проверка конфигурации
            config_checker = ConfigHealthChecker()
            config_result = await config_checker.check()
            return config_result.status == HealthStatus.HEALTHY
        except Exception:
            return False
