from __future__ import annotations

import logging
import sys

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Apply one logging policy for app, Uvicorn, Alembic and SQLAlchemy."""

    formatter = logging.Formatter(settings.LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(_level(settings.LOG_LEVEL, logging.WARNING))

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(formatter)

    _configure_logger("app", enabled=settings.LOG_APP_ENABLED, level=settings.LOG_LEVEL)
    _configure_logger("main", enabled=settings.LOG_APP_ENABLED, level=settings.LOG_LEVEL)
    _configure_logger("uvicorn", enabled=True, level=settings.LOG_UVICORN_LEVEL)
    _configure_logger("uvicorn.error", enabled=True, level=settings.LOG_UVICORN_LEVEL)
    _configure_logger(
        "uvicorn.access",
        enabled=settings.LOG_HTTP_ACCESS_ENABLED,
        level=settings.LOG_HTTP_ACCESS_LEVEL,
    )
    _configure_logger("alembic", enabled=settings.LOG_ALEMBIC_ENABLED, level=settings.LOG_ALEMBIC_LEVEL)
    _configure_logger("sqlalchemy", enabled=True, level=settings.LOG_SQLALCHEMY_LEVEL)
    _configure_logger("sqlalchemy.engine", enabled=True, level=settings.LOG_SQLALCHEMY_LEVEL)
    _configure_logger("sqlalchemy.engine.Engine", enabled=True, level=settings.LOG_SQLALCHEMY_LEVEL)
    _configure_logger("sqlalchemy.pool", enabled=True, level=settings.LOG_SQLALCHEMY_LEVEL)


def _configure_logger(name: str, *, enabled: bool, level: str) -> None:
    logger = logging.getLogger(name)
    logger.disabled = not enabled
    logger.setLevel(_level(level, logging.INFO))


def _level(value: str, default: int) -> int:
    level = logging.getLevelName(value.upper())
    return level if isinstance(level, int) else default
