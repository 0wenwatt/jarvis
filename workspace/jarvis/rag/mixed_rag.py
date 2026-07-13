"""Mixed (graph + vector) RAG — combines GraphRAG and VectorRAG.

The retrieval strategy:
  1. Run GraphRAG to get structured entity/relationship context.
  2. Run VectorRAG to get semantically-similar text chunks.
  3. Merge results, deduplicate, and assemble a single ``RAGResult``.
  4. A pydantic-ai synthesis agent reads the combined context and answers the
     original question.

This module also provides the ``synthesise`` helper used by all three modes.
"""

from __future__ import annotations

import asyncio
import logging
import os

from pydantic_ai import Agent

from . import graph_rag, vector_rag
from .models import GraphContext, RAGMode, RAGQuery, RAGResult, VectorContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthesis agent — reads RAG context and produces a final answer
# ---------------------------------------------------------------------------

_SYNTHESIS_SYSTEM = """\
You are a knowledgeable assistant.  You have been given context retrieved from a
knowledge graph and/or a vector store.  Use ONLY the provided context to answer
the user's question.

Rules:
- Cite the source URL when referencing specific facts.
- If the context is insufficient, say so explicitly rather than guessing.
- Be concise: answer in ≤ 3 paragraphs unless the question demands more detail.
"""

_synthesis_agent: Agent[None, str] = Agent(
    model=os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6"),
    system_prompt=_SYNTHESIS_SYSTEM,
    result_type=str,
)


async def synthesise(query: str, context: str) -> str:
    """Ask the synthesis agent to answer *query* given *context*."""
    prompt = f"Context:\n{context}\n\nQuestion: {query}"
    result = await _synthesis_agent.run(prompt)
    return result.output


# ---------------------------------------------------------------------------
# Public API — retrieve + synthesise for each RAG mode
# ---------------------------------------------------------------------------


async def query_graph(q: RAGQuery) -> RAGResult:
    """GraphRAG: retrieve from PostgresAGE graph and synthesise an answer."""
    graph_ctx = await graph_rag.retrieve(q)
    answer = await synthesise(q.query, graph_ctx.to_text())

    sources = list({n.properties.get("source_url", "") for n in graph_ctx.nodes if n.properties.get("source_url")})

    return RAGResult(
        query=q.query,
        mode=RAGMode.GRAPH,
        graph_context=graph_ctx,
        answer=answer,
        sources=sources,
    )


async def query_vector(q: RAGQuery) -> RAGResult:
    """VectorRAG: retrieve from pgvector store (via LlamaIndex) and synthesise."""
    vector_ctx = await vector_rag.retrieve(q)
    answer = await synthesise(q.query, vector_ctx.to_text())

    sources = list({c.source_url for c in vector_ctx.chunks})

    return RAGResult(
        query=q.query,
        mode=RAGMode.VECTOR,
        vector_context=vector_ctx,
        answer=answer,
        sources=sources,
    )


async def query_mixed(q: RAGQuery) -> RAGResult:
    """Mixed RAG: run GraphRAG and VectorRAG in parallel, merge contexts."""
    # Run both retrievals concurrently
    graph_task = asyncio.create_task(graph_rag.retrieve(q))
    vector_task = asyncio.create_task(vector_rag.retrieve(q))

    graph_ctx, vector_ctx = await asyncio.gather(graph_task, vector_task)

    # Build a unified result with both context types
    result = RAGResult(
        query=q.query,
        mode=RAGMode.MIXED,
        graph_context=graph_ctx,
        vector_context=vector_ctx,
        answer="",  # filled below
        sources=[],
    )

    # Synthesise answer from the combined context
    combined = result.combined_context
    result.answer = await synthesise(q.query, combined)

    # Deduplicate sources
    graph_sources = {n.properties.get("source_url", "") for n in graph_ctx.nodes}
    vector_sources = {c.source_url for c in vector_ctx.chunks}
    result.sources = sorted(s for s in graph_sources | vector_sources if s)

    return result
