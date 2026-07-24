"""Async PostgreSQL connection-pool management for the RAG module.

A single module-level pool is shared across the entire process.
Call ``initialise()`` once at application startup and ``close()`` at shutdown.
All RAG components import ``get_pool()`` to obtain a connection.
"""

from __future__ import annotations

import logging
import os

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "postgres-age")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "jarvis")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


async def _setup_connection(conn: asyncpg.Connection) -> None:
    """Run once per new pool connection: load AGE and set search path."""
    await conn.execute("LOAD 'age'")
    await conn.execute("SET search_path = ag_catalog, \"$user\", public")


async def initialise(min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    """Create (or return) the shared connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    dsn = _dsn()
    logger.info("Creating asyncpg pool (min=%d, max=%d)", min_size, max_size)
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        setup=_setup_connection,
        command_timeout=60,
    )
    logger.info("asyncpg pool ready")
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Return the shared pool, creating it lazily if needed."""
    if _pool is None:
        return await initialise()
    return _pool


async def close() -> None:
    """Gracefully close the pool (call at application shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("asyncpg pool closed")
