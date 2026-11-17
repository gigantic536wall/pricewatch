from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
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
