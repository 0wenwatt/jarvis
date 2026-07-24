"""Database schema setup for the Jarvis RAG system.

Idempotent — safe to call on every application startup.

Creates (if not already present):
  1. pgvector extension
  2. Apache AGE extension + the default knowledge graph
  3. ``knowledge_chunks`` table with vector column + indexes
"""

from __future__ import annotations

import logging
import os

import asyncpg

from .db import get_pool

logger = logging.getLogger(__name__)

DEFAULT_GRAPH = os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))


async def setup(graph_name: str = DEFAULT_GRAPH) -> None:
    """Run all setup steps against the shared pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _ensure_extensions(conn)
        await _ensure_graph(conn, graph_name)
        await _ensure_chunks_table(conn)
    logger.info("RAG schema setup complete (graph=%s, dim=%d)", graph_name, EMBEDDING_DIM)


async def _ensure_extensions(conn: asyncpg.Connection) -> None:
    """Enable age and vector extensions (idempotent)."""
    await conn.execute("CREATE EXTENSION IF NOT EXISTS age")
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await conn.execute("LOAD 'age'")
    await conn.execute("SET search_path = ag_catalog, \"$user\", public")
    logger.debug("Extensions ensured: age, vector")


async def _ensure_graph(conn: asyncpg.Connection, graph_name: str) -> None:
    """Create the AGE property graph if it does not exist."""
    exists = await conn.fetchval(
        "SELECT count(*) FROM ag_graph WHERE name = $1",
        graph_name,
    )
    if not exists:
        await conn.execute(f"SELECT create_graph('{graph_name}')")
        logger.info("Created AGE graph '%s'", graph_name)
    else:
        logger.debug("AGE graph '%s' already exists", graph_name)


async def _ensure_chunks_table(conn: asyncpg.Connection) -> None:
    """Create knowledge_chunks table and its indexes (idempotent)."""
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            source_url  TEXT        NOT NULL,
            chunk_index INTEGER     NOT NULL,
            text        TEXT        NOT NULL,
            embedding   vector({EMBEDDING_DIM}),
            metadata    JSONB       NOT NULL DEFAULT '{{}}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source_url, chunk_index)
        )
        """
    )

    # IVFFlat approximate nearest-neighbour index
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
            ON knowledge_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_url
            ON knowledge_chunks (source_url)
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_metadata
            ON knowledge_chunks USING gin (metadata)
        """
    )
    logger.debug("knowledge_chunks table and indexes ensured")
