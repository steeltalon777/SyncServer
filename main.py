import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import SyncServerException
from app.api.exceptions_handlers import operation_lines_invalid_handler, operation_submit_error_handler
from app.api.routes_admin import router as admin_router
from app.api.routes_assets import router as assets_router
from app.api.routes_auth import router as auth_router
from app.api.routes_balances import router as balances_router
from app.api.routes_catalog import router as catalog_router
from app.api.routes_catalog_admin import router as catalog_admin_router
from app.api.routes_diagnostics import router as diagnostics_router
from app.api.routes_documents import router as documents_router
from app.api.routes_health import router as health_router
from app.api.routes_operations import router as operations_router
from app.api.routes_corrections import router as corrections_router
from app.api.routes_issue_objects import router as issue_objects_router, router_categories as issue_object_categories_router
from app.api.routes_reports import router as reports_router
from app.api.routes_sync import router as sync_router
from app.api.routes_review_items import router as review_items_router
from app.api.routes_temporary_items import router as temporary_items_router
from app.core.config import get_settings
from app.core.db import get_db
from app.core.logging_config import configure_logging
from app.services.operation_line_errors import OperationLinesInvalidError
from app.services.operation_submit_errors import OperationSubmitError

settings = get_settings()
if "LOG_LEVEL" not in os.environ:
    os.environ["LOG_LEVEL"] = settings.LOG_LEVEL

configure_logging()
logger = structlog.get_logger()

def create_app(*, enable_startup_migrations: bool = True) -> FastAPI:
    # Backward-compatible argument for test bootstrap:
    # older tests call create_app(enable_startup_migrations=False).
    # Current app startup does not run migrations in lifespan,
    # so this flag is intentionally a no-op for now.
    _ = enable_startup_migrations

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(
        title="SyncServer API",
        description="Central backend for warehouse management system",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=round(duration_ms, 1),
                request_id=request_id,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "internal server error"},
                headers={"X-Request-Id": request_id},
            )

        duration_ms = (time.perf_counter() - start) * 1000
        status_code = response.status_code

        if status_code >= 500:
            logger.error("http_request", method=request.method, path=request.url.path, status_code=status_code, duration_ms=round(duration_ms, 1), request_id=request_id)
        elif status_code >= 400:
            logger.warning("http_request", method=request.method, path=request.url.path, status_code=status_code, duration_ms=round(duration_ms, 1), request_id=request_id)
        else:
            logger.info("http_request", method=request.method, path=request.url.path, status_code=status_code, duration_ms=round(duration_ms, 1), request_id=request_id)

        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(SyncServerException)
    async def sync_server_exception_handler(request: Request, exc: SyncServerException):
        """Handle SyncServer exceptions with standard error format."""
        status_code = exc.status_code

        if status_code >= 500:
            logger.error(
                "sync_server_exception",
                code=exc.error_code,
                status_code=status_code,
                detail=str(exc.detail)[:500],
                request_id=getattr(request.state, "request_id", ""),
                path=request.url.path,
                method=request.method,
                exc_info=True,
            )
        else:
            logger.warning(
                "sync_server_exception",
                code=exc.error_code,
                status_code=status_code,
                detail=str(exc.detail)[:500],
                request_id=getattr(request.state, "request_id", ""),
                path=request.url.path,
                method=request.method,
            )

        error_body = {
            "error": {
                "code": exc.error_code,
                "message": exc.detail,
            }
        }

        if exc.details:
            error_body["error"]["details"] = exc.details

        request_id = getattr(request.state, "request_id", "")
        if request_id:
            error_body["request_id"] = request_id

        return JSONResponse(
            status_code=exc.status_code,
            content=error_body,
        )

    app.add_exception_handler(OperationSubmitError, operation_submit_error_handler)
    app.add_exception_handler(OperationLinesInvalidError, operation_lines_invalid_handler)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "message": "SyncServer API is running",
            "status": "ok",
            "env": settings.APP_ENV,
            "version": "1.0.0",
        }

    @app.get("/db_check")
    async def db_check(db: AsyncSession = Depends(get_db)) -> dict[str, str | int]:
        result = await db.execute(text("SELECT 1"))
        return {"db_status": "connected", "result": result.scalar_one()}

    # API version 1 routes
    api_v1_prefix = "/api/v1"

    # Sync API (device auth only)
    app.include_router(sync_router, prefix=api_v1_prefix)

    # Catalog API (user token auth)
    app.include_router(catalog_router, prefix=api_v1_prefix)

    # Operations API (user token auth)
    app.include_router(operations_router, prefix=api_v1_prefix)
    app.include_router(corrections_router, prefix=api_v1_prefix)

    # Temporary items API (user token auth)
    app.include_router(temporary_items_router, prefix=api_v1_prefix)

    # Documents API (user token auth)
    app.include_router(documents_router, prefix=api_v1_prefix)

    # Issue Objects API (user token auth)
    app.include_router(issue_objects_router, prefix=api_v1_prefix)

    # Issue Object Categories API (user token auth)
    app.include_router(issue_object_categories_router, prefix=api_v1_prefix)

    # Asset registers API (user token auth)
    app.include_router(assets_router, prefix=api_v1_prefix)

    # Balances API (user token auth)
    app.include_router(balances_router, prefix=api_v1_prefix)

    # Reports API (user token auth)
    app.include_router(reports_router, prefix=api_v1_prefix)

    # Catalog Admin API (user token auth + role-based)
    app.include_router(catalog_admin_router, prefix=api_v1_prefix)

    # Admin API (root only)
    app.include_router(admin_router, prefix=api_v1_prefix)

    # Health endpoints
    app.include_router(health_router, prefix=api_v1_prefix)

    # Review Items API (user token auth)
    app.include_router(review_items_router, prefix=api_v1_prefix)

    # Diagnostics API (user token auth)
    app.include_router(diagnostics_router, prefix=api_v1_prefix)

    # Auth endpoints
    app.include_router(auth_router, prefix=api_v1_prefix)

    temporary_item_paths = sorted(
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith(f"{api_v1_prefix}/temporary-items")
    )
    logger.info("app_route_registration", temporary_items_registered=bool(temporary_item_paths), temporary_item_paths=temporary_item_paths, total_routes=len(app.routes))

    return app


app = create_app()
