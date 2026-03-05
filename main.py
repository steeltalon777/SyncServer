import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_catalog import router as catalog_router
from app.api.routes_health import router as health_router
from app.api.routes_sync import router as sync_router
from app.core.config import get_settings
from app.core.db import get_db

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(title="Server Sync API")


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


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "Server Sync API is running",
        "status": "ok",
        "env": settings.APP_ENV,
    }


@app.get("/db_check")
async def db_check(db: AsyncSession = Depends(get_db)) -> dict[str, str | int]:
    result = await db.execute(text("SELECT 1"))
    return {"db_status": "connected", "result": result.scalar_one()}


app.include_router(sync_router)
app.include_router(catalog_router)
app.include_router(health_router)
