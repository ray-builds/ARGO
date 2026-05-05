"""Async SQLAlchemy database engine, session factory, and dependency."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

# Module-level singletons — populated by init_db()
engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

# Internal alias used by get_session_factory() guard
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine(url: str) -> AsyncEngine:
    """Create the async SQLAlchemy engine appropriate for the given URL."""
    if url.startswith("sqlite"):
        return create_async_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
    # PostgreSQL (asyncpg)
    return create_async_engine(
        url,
        echo=False,
        pool_size=10,
        max_overflow=20,
    )


async def init_db() -> None:
    """Initialize database: create engine, session factory, and all tables.

    For SQLite (dev): creates tables via SQLAlchemy metadata.
    For PostgreSQL (prod): creates pgvector extension then creates tables.
    """
    global engine, AsyncSessionLocal, _session_factory

    from app.config import get_settings
    settings = get_settings()
    url = settings.database_url

    engine = _build_engine(url)
    _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    AsyncSessionLocal = _session_factory

    logger.info(f"Database engine created: {url.split('://')[0]}")

    async with engine.begin() as conn:
        # Enable pgvector on PostgreSQL
        if not url.startswith("sqlite"):
            await conn.execute(
                __import__("sqlalchemy").text(
                    "CREATE EXTENSION IF NOT EXISTS vector"
                )
            )
            logger.info("pgvector extension ensured")

        # Create all tables (idempotent in dev; in prod use alembic migrations)
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables verified/created")


async def close_db() -> None:
    """Dispose database connections on application shutdown."""
    global engine
    if engine is not None:
        await engine.dispose()
        logger.info("Database connections closed")
        engine = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory (raises RuntimeError if not yet initialized)."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager: yields an AsyncSession, commits on success, rolls back on error."""
    factory = get_session_factory()
    session: AsyncSession = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session via get_db_session()."""
    async with get_db_session() as session:
        yield session
