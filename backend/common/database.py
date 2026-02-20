"""Async database engine and session factory.

Uses SQLAlchemy 2.0+ async with asyncpg for PostgreSQL
and aiosqlite for testing.

Usage in FastAPI:
    from backend.common.database import get_db

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(User))
        ...

Usage in Celery tasks:
    from backend.common.database import get_task_session

    async def my_task():
        async with get_task_session() as db:
            result = await db.execute(select(Trade))
            ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.common.config import get_settings

# Create engine lazily on first use
_engine = None
_session_factory = None


def _get_engine():
    """Get or create the async engine (lazy singleton)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=(settings.environment == "development"),
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
    return _engine


def _get_session_factory():
    """Get or create the session factory (lazy singleton)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session.

    The session is automatically closed when the request finishes.
    Transactions must be committed explicitly by the caller.
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_task_session() -> AsyncSession:
    """Create a new session for use in Celery tasks (not a generator).

    Caller is responsible for closing the session:
        async with get_task_session() as db:
            ...
    """
    factory = _get_session_factory()
    return factory()


def reset_engine() -> None:
    """Reset the engine and session factory. Used in tests."""
    global _engine, _session_factory
    if _engine is not None:
        # Engine disposal should be awaited in async context
        _engine = None
    _session_factory = None
