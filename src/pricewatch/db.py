from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .config import get_settings

_settings = get_settings()

# On serverless platforms every invocation may run in a fresh process, and idle pooled
# connections would be cut off between requests, so connections are opened per request.
engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=not _settings.serverless,
    **({"poolclass": NullPool} if _settings.serverless else {}),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A session that commits on success and rolls back on error."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
