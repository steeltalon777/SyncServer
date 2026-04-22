from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    DATABASE_URL_TEST: str | None = None
    APP_ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    DEFAULT_PAGE_SIZE: int = Field(default=100, ge=1, le=5000)
    ALLOWED_ORIGINS: str = ""
    MAX_PUSH_EVENTS: int = Field(default=500, ge=1, le=5000)
    DEFAULT_PULL_LIMIT: int = Field(default=200, ge=1, le=1000)
    DEFAULT_OPERATIONS_PAGE_SIZE: int = Field(default=50, ge=1, le=100, description="Default page size for operations")
    DEFAULT_BALANCES_PAGE_SIZE: int = Field(default=100, ge=1, le=200, description="Default page size for balances")
    DEFAULT_ADMIN_PAGE_SIZE: int = Field(default=50, ge=1, le=100, description="Default page size for admin endpoints")
    MAX_OPERATION_LINES: int = Field(default=100, ge=1, le=500, description="Maximum lines per operation")

    # Health check settings
    HEALTH_CHECK_TIMEOUT: float = Field(default=5.0, ge=0.5, le=30.0, description="Timeout for health checks in seconds")
    HEALTH_CHECK_ENABLE_REDIS: bool = Field(default=False, description="Enable Redis health check")
    HEALTH_CHECK_REDIS_URL: str | None = Field(default=None, description="Redis URL for health check")
    HEALTH_CHECK_ENABLE_EXTERNAL_SERVICES: bool = Field(
        default=False, description="Enable external services health checks"
    )
    HEALTH_CHECK_EXTERNAL_SERVICES: list[str] = Field(
        default_factory=list, description="List of external service URLs to check"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
