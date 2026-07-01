from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

# В тестовом режиме отключаем пул соединений, чтобы избежать конфликтов
# asyncpg Future'ов между разными event loop'ами TestClient'ов.
# В проде используем пул с pool_pre_ping для проверки жизнеспособности коннектов.
engine_kwargs: dict[str, object] = {
    "echo": settings.LOG_SQL,
}

if settings.TESTING:
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 3600

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async SQLAlchemy session."""

    async with SessionFactory() as session:
        yield session
