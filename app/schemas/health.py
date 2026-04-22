from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(str, Enum):
    """Статус проверки здоровья."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    NOT_CONFIGURED = "not_configured"


class HealthCheckDetail(BaseModel):
    """Детали одной проверки здоровья."""

    status: HealthStatus = Field(..., description="Статус проверки")
    latency_ms: float | None = Field(None, description="Время выполнения в миллисекундах")
    details: str | None = Field(None, description="Дополнительная информация")
    error: str | None = Field(None, description="Сообщение об ошибке, если есть")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "latency_ms": 12.5,
                "details": "Connection successful",
                "error": None,
            }
        }
    )


class HealthCheckResponse(BaseModel):
    """Ответ на запрос проверки здоровья."""

    status: HealthStatus = Field(..., description="Общий статус системы")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время проверки")
    version: str = Field("1.0.0", description="Версия приложения")
    checks: dict[str, HealthCheckDetail] = Field(..., description="Результаты отдельных проверок")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "degraded",
                "timestamp": "2026-04-06T06:42:52Z",
                "version": "1.0.0",
                "checks": {
                    "database": {
                        "status": "healthy",
                        "latency_ms": 8.2,
                        "details": "Connection successful",
                        "error": None,
                    },
                    "cache": {
                        "status": "unhealthy",
                        "latency_ms": None,
                        "details": "Connection timeout",
                        "error": "Redis connection failed",
                    },
                    "config": {
                        "status": "healthy",
                        "latency_ms": None,
                        "details": "All required configs present",
                        "error": None,
                    },
                },
            }
        }
    )


class ReadinessResponse(BaseModel):
    """Ответ на запрос готовности системы."""

    ready: bool = Field(..., description="Готова ли система к работе")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время проверки")
    details: dict[str, bool] = Field(..., description="Статус критических зависимостей")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ready": True,
                "timestamp": "2026-04-06T06:42:52Z",
                "details": {
                    "database": True,
                    "config": True,
                },
            }
        }
    )


class LivenessResponse(BaseModel):
    """Ответ на запрос живучести системы."""

    alive: bool = Field(..., description="Жива ли система")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Время проверки")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "alive": True,
                "timestamp": "2026-04-06T06:42:52Z",
            }
        }
    )
