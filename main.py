import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import SyncServerException
from app.api.routes_admin import router as admin_router
from app.api.routes_assets import router as assets_router
from app.api.routes_auth import router as auth_router
from app.api.routes_balances import router as balances_router
from app.api.routes_catalog import router as catalog_router
from app.api.routes_catalog_admin import router as catalog_admin_router
from app.api.routes_documents import router as documents_router
from app.api.routes_health import router as health_router
from app.api.routes_operations import router as operations_router
from app.api.routes_recipients import router as recipients_router
from app.api.routes_reports import router as reports_router
from app.api.routes_sync import router as sync_router
from app.core.config import get_settings
from app.core.db import get_db
from app.core.migrations import ensure_database_ready

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

def create_app(
    *,
    enable_startup_migrations: bool | None = None,
) -> FastAPI:
    if enable_startup_migrations is None:
        enable_startup_migrations = settings.AUTO_MIGRATE_ON_STARTUP

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if enable_startup_migrations:
            logger.info("startup migration check started")
            await ensure_database_ready()
            logger.info("startup migration check finished")
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
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_id=%s unhandled_error path=%s", request_id, request.url.path)
            return JSONResponse(status_code=500, content={"detail": "internal server error"})

        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(SyncServerException)
    async def sync_server_exception_handler(request: Request, exc: SyncServerException):
        """Handle SyncServer exceptions with standard error format."""
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

    # Documents API (user token auth)
    app.include_router(documents_router, prefix=api_v1_prefix)

    # Recipients API (user token auth)
    app.include_router(recipients_router, prefix=api_v1_prefix)

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

    # Auth endpoints
    app.include_router(auth_router, prefix=api_v1_prefix)

    return app


app = create_app()

