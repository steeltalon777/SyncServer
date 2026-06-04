"""
Centralized structlog configuration for SyncServer.

Env vars:
  LOG_LEVEL   — logging level (DEBUG, INFO, WARNING, ERROR). Default: INFO.
  LOG_FORMAT  — "console" (colored, human-readable) or "json" (machine-readable).
                Default: "console".
"""

import logging
import os
import sys

import structlog


def configure_logging() -> None:
    """Wire structlog processors and stdlib logging for the entire app.

    Must be called once at startup, before any logger is created:

        from app.core.logging_config import configure_logging
        configure_logging()
        logger = structlog.get_logger()

    After this call, every ``structlog.get_logger()`` produces structured
    events and every ``logging.getLogger()`` call is also covered by the same
    handler (so third-party libraries like uvicorn emit structured lines too).
    """

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "console").strip().lower()

    # ---------------------------------------------------------------
    # Shared processors (applied before renderer)
    # ---------------------------------------------------------------
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,   # request_id, user_id, etc.
        structlog.stdlib.add_log_level,            # level=info, level=error
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # ---------------------------------------------------------------
    # Renderer: console (colored) or JSON
    # ---------------------------------------------------------------
    if log_format == "json":
        renderer_processor = structlog.processors.JSONRenderer()
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
        )
    else:
        renderer_processor = structlog.dev.ConsoleRenderer(
            colors=True,
            pad_event_to=40,
        )
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=renderer_processor,
        )

    # ---------------------------------------------------------------
    # stdlib logging configuration (handler + formatter)
    # ---------------------------------------------------------------
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Uvicorn loggers: clear their handlers so logs propagate to root
    # and go through our structlog ProcessorFormatter.
    for _uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _uv_logger = logging.getLogger(_uv_name)
        _uv_logger.handlers.clear()
        _uv_logger.propagate = True

    # Приглушаем шумные сторонние логгеры в dev-режиме
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # ---------------------------------------------------------------
    # structlog configuration
    # ---------------------------------------------------------------
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
