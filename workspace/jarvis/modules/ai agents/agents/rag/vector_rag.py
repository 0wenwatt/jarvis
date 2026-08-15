"""VectorRAG — similarity search over embedded text chunks in pgvector.

LlamaIndex is used here for two things only:
  - ``PGVectorStore``: manages the pgvector table and executes ANN queries
  - ``VectorStoreIndex``: wraps the store with a query engine

Everything else — models, chunking, embedding, result parsing — lives in
Pydantic types and is orchestrated by plain async Python.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .db import get_pool
from .models import RAGQuery, VectorChunkResult, VectorContext

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-ada-002")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


async def _embed_query(text: str) -> list[float]:
    """Embed a single query string using OpenAI."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    response = await client.embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL,
    )
    return response.data[0].embedding


# ---------------------------------------------------------------------------
# LlamaIndex VectorStoreIndex (used for the "correct" llamaindex integration)
# ---------------------------------------------------------------------------


def _get_llama_vector_store() -> Any:
    """Return a llama_index PGVectorStore connected to the same database.

    This is the ONE place where llamaindex is used for VectorRAG —
    it manages the pgvector table and provides an ANN query interface.
    """
    from llama_index.vector_stores.postgres import PGVectorStore  # type: ignore[import]

    host = os.environ.get("POSTGRES_HOST", "postgres-age")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    db = os.environ.get("POSTGRES_DB", "jarvis")
    user = os.environ.get("POSTGRES_USER", "postgres")
    pw = os.environ.get("POSTGRES_PASSWORD", "")

    conn_string = f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"
    return PGVectorStore.from_params(
        connection_string=conn_string,
        table_name="knowledge_chunks",
        embed_dim=EMBEDDING_DIM,
        hybrid_search=False,
    )


# ---------------------------------------------------------------------------
# Direct pgvector retrieval (used when llamaindex is unavailable or for
# the mixed-RAG path where we need raw asyncpg access)
# ---------------------------------------------------------------------------


async def _direct_vector_search(
    query_embedding: list[float],
    top_k: int,
    source_url_filter: str | None = None,
) -> list[VectorChunkResult]:
    """ANN search via raw asyncpg + pgvector <-> operator."""
    pool = await get_pool()

    # Format embedding as postgres vector literal
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    if source_url_filter:
        sql = """
            SELECT id, source_url, text,
                   1 - (embedding <-> $1::vector) AS score,
                   metadata
            FROM knowledge_chunks
            WHERE source_url = $2
            ORDER BY embedding <-> $1::vector
            LIMIT $3
        """
        params = (embedding_str, source_url_filter, top_k)
    else:
        sql = """
            SELECT id, source_url, text,
                   1 - (embedding <-> $1::vector) AS score,
                   metadata
            FROM knowledge_chunks
            ORDER BY embedding <-> $1::vector
            LIMIT $2
        """
        params = (embedding_str, top_k)

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    results: list[VectorChunkResult] = []
    for row in rows:
        meta = row["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        results.append(
            VectorChunkResult(
                chunk_id=str(row["id"]),
                source_url=row["source_url"],
                text=row["text"],
                score=float(row["score"]),
                metadata=meta or {},
            )
        )
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def retrieve(query: RAGQuery) -> VectorContext:
    """Run vectorRAG retrieval for *query*, returning a VectorContext."""
    query_embedding = await _embed_query(query.query)

    # Attempt llamaindex PGVectorStore path first (demonstrates the integration);
    # fall back to the direct asyncpg path on any import/connection error.
    chunks: list[VectorChunkResult] = []

    try:
        from llama_index.core import VectorStoreIndex  # type: ignore[import]
        from llama_index.core.vector_stores.types import (  # type: ignore[import]
            VectorStoreQuery,
        )
        from llama_index.embeddings.openai import (  # type: ignore[import]
            OpenAIEmbedding,
        )

        vs = _get_llama_vector_store()
        embed_model = OpenAIEmbedding(model=EMBEDDING_MODEL)

        # Use llamaindex VectorStoreIndex for the standard retrieval pattern
        index = VectorStoreIndex.from_vector_store(
            vector_store=vs,
            embed_model=embed_model,
        )
        retriever = index.as_retriever(similarity_top_k=query.top_k)
        nodes = await retriever.aretrieve(query.query)

        for node in nodes:
            chunks.append(
                VectorChunkResult(
                    chunk_id=node.id_ or "",
                    source_url=node.metadata.get("source_url", ""),
                    text=node.get_content(),
                    score=node.score or 0.0,
                    metadata=node.metadata,
                )
            )
        logger.debug("VectorRAG via LlamaIndex PGVectorStore: %d chunks", len(chunks))

    except Exception as exc:
        logger.info("LlamaIndex VectorRAG unavailable (%s), using direct pgvector", exc)
        chunks = await _direct_vector_search(query_embedding, query.top_k)
        logger.debug("VectorRAG via direct pgvector: %d chunks", len(chunks))

    return VectorContext(chunks=chunks)
