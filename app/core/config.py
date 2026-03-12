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
    SYNC_SERVER_SERVICE_TOKEN: str = Field(default="", description="Service token for trusted service authentication")
    DEFAULT_OPERATIONS_PAGE_SIZE: int = Field(default=50, ge=1, le=100, description="Default page size for operations")
    DEFAULT_BALANCES_PAGE_SIZE: int = Field(default=100, ge=1, le=200, description="Default page size for balances")
    DEFAULT_ADMIN_PAGE_SIZE: int = Field(default=50, ge=1, le=100, description="Default page size for admin endpoints")
    MAX_OPERATION_LINES: int = Field(default=100, ge=1, le=500, description="Maximum lines per operation")


@lru_cache
def get_settings() -> Settings:
    return Settings()
