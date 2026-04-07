from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.health import (
    HealthCheckResponse,
    HealthStatus,
    ReadinessResponse,
    LivenessResponse,
)
from app.services.health_service import HealthService

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict[str, str | int]:
    """Readiness check with database connection test."""
    result = await db.execute(text("SELECT 1"))
    return {"status": "ready", "db": result.scalar_one()}


@router.get("/health/detailed", response_model=HealthCheckResponse)
async def detailed_health(db: AsyncSession = Depends(get_db)) -> HealthCheckResponse:
    """
    Detailed health check with all dependencies.

    Returns comprehensive status of all system components including:
    - Database connection
    - Configuration validation
    - Cache (if configured)
    - External services (if configured)
    """
    health_service = HealthService(db)
    checks = await health_service.check_health()
    overall_status = health_service.aggregate_status(checks)

    return HealthCheckResponse(
        status=overall_status,
        checks=checks,
    )


@router.get("/health/readiness", response_model=ReadinessResponse)
async def readiness_check(db: AsyncSession = Depends(get_db)) -> ReadinessResponse:
    """
    Readiness check for critical dependencies.

    Used by load balancers and orchestration systems to determine
    if the service is ready to accept traffic.
    """
    health_service = HealthService(db)
    readiness_details = await health_service.check_readiness()

    # Система готова, если все критические зависимости здоровы
    ready = all(readiness_details.values())

    return ReadinessResponse(
        ready=ready,
        details=readiness_details,
    )


@router.get("/health/liveness", response_model=LivenessResponse)
async def liveness_check() -> LivenessResponse:
    """
    Liveness check for basic application health.

    Used by Kubernetes and container orchestration to determine
    if the container should be restarted.
    """
    # Для liveness проверки не требуется подключение к БД
    # Проверяем только базовые вещи (конфигурация)
    from app.services.health_service import ConfigHealthChecker

    try:
        config_checker = ConfigHealthChecker()
        config_result = await config_checker.check()
        alive = config_result.status == HealthStatus.HEALTHY
    except Exception:
        alive = False

    return LivenessResponse(alive=alive)
