from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db

settings = get_settings()
app = FastAPI(title="Server Sync API")


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
