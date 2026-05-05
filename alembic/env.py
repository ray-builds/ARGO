"""Alembic environment — async SQLAlchemy migrations for ARGO."""
import asyncio
import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Load .env so DATABASE_URL is available when running alembic CLI directly
from dotenv import load_dotenv
load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Resolve DATABASE_URL ──────────────────────────────────────────────────────
_raw_url: str = os.getenv("DATABASE_URL", "") or config.get_main_option("sqlalchemy.url") or ""

# Alembic's synchronous URL-comparison logic cannot handle async driver schemes
# (e.g. postgresql+asyncpg:// or sqlite+aiosqlite://). Strip the async suffix so
# Alembic can introspect the schema while the actual engine still runs async below.
_sync_url = re.sub(r"\+(asyncpg|aiosqlite)", "", _raw_url)
config.set_main_option("sqlalchemy.url", _sync_url)

# ── Import ALL models so Alembic sees every table in metadata ─────────────────
from app.models.base import Base  # noqa: E402
from app.models import (  # noqa: E402, F401
    user, email, summary, meeting, document,
    portfolio, client, research, economic, chat,
)

target_metadata = Base.metadata


# ─────────────────────────────────────────────────────────────────────────────
# Offline mode — generate SQL script without a live DB connection
# ─────────────────────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script output)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# Online mode — async engine, synchronous migration callback
# ─────────────────────────────────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    """Synchronous callback executed inside an async connection context."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a synchronous bridge."""
    # Use the raw URL (with async driver) for the actual engine so the async
    # pool works correctly at runtime; Alembic's schema comparison uses _sync_url.
    engine_url = _raw_url or _sync_url
    connectable = async_engine_from_config(
        {**config.get_section(config.config_ini_section, {}),
         "sqlalchemy.url": engine_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (live DB) migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
