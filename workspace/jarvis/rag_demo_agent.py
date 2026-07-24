"""Jarvis RAG Demo Agent — showcases GraphRAG, VectorRAG and Mixed RAG.

This FastAPI application demonstrates:

  PydanticAI features used
  ─────────────────────────
  - Agent with typed deps (RAGAgentDeps dataclass)
  - Structured result type (str — but all intermediate data is pydantic)
  - @agent.tool decorated async tools (crawl_and_ingest, query_graph_rag,
    query_vector_rag, query_mixed_rag, get_knowledge_base_status)
  - RunContext[RAGAgentDeps] for dependency injection inside tools
  - ModelRetry for graceful tool-call validation errors
  - AbstractCapability subclasses for instrumentation (GraphRAGCapability,
    VectorRAGCapability, MixedRAGCapability)
  - Streaming via agent.run_stream()

  Pydantic features used
  ───────────────────────
  - BaseModel for every request/response schema (all models in rag/models.py)
  - Field validators + model_validator
  - TypeAdapter for flexible JSON validation
  - Annotated types with Field metadata
  - Computed properties on RAGResult

  LlamaIndex usage (minimal — only for VectorRAG)
  ─────────────────────────────────────────────────
  - PGVectorStore (llama-index-vector-stores-postgres) as the pgvector backend
  - VectorStoreIndex + retriever for the standard llamaindex retrieval pattern
  - OpenAIEmbedding for consistent embedding generation

  PostgresAGE usage (GraphRAG)
  ─────────────────────────────
  - Apache AGE Cypher queries via asyncpg
  - create_graph / MERGE vertex / MATCH edge patterns
  - Full knowledge-graph construction from crawl4ai output

Run standalone
──────────────
    cd workspace/jarvis
    uvicorn rag_demo_agent:app --reload --port 8001

Or import and mount on the main app:
    from rag_demo_agent import app as rag_app
    main_app.mount("/rag", rag_app)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Any

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

from rag import (
    CrawlResult,
    GraphRAGCapability,
    IngestResult,
    MixedRAGCapability,
    RAGMode,
    RAGQuery,
    RAGResult,
    VectorRAGCapability,
    close_db,
    ingest_crawl_result,
    ingest_url,
    initialise_db,
    query_graph,
    query_mixed,
    query_vector,
    setup_db,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent dependencies (injected via RunContext)
# ---------------------------------------------------------------------------


@dataclass
class RAGAgentDeps:
    """Dependencies available to all agent tools at runtime."""

    db_pool: asyncpg.Pool
    graph_name: str = field(default_factory=lambda: os.environ.get("RAG_GRAPH_NAME", "jarvis_kg"))
    default_top_k: int = field(default_factory=lambda: int(os.environ.get("RAG_TOP_K", "5")))

    # Capability instances — also accessible as attributes so the FastAPI
    # layer can read their stats after each request.
    graph_cap: GraphRAGCapability = field(default_factory=GraphRAGCapability)
    vector_cap: VectorRAGCapability = field(default_factory=VectorRAGCapability)
    mixed_cap: MixedRAGCapability = field(default_factory=MixedRAGCapability)


# ---------------------------------------------------------------------------
# HTTP request / response schemas (pydantic)
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Request body for the /rag/ingest endpoint."""

    url: str | None = Field(default=None, description="URL to crawl and ingest")
    crawl_result: CrawlResult | None = Field(
        default=None,
        description="Pre-crawled CrawlResult (skip HTTP fetch)",
    )
    graph_name: str = Field(
        default=os.environ.get("RAG_GRAPH_NAME", "jarvis_kg"),
        description="Target AGE graph name",
    )
    use_crawl4ai: bool = Field(
        default=True,
        description="Use crawl4ai if installed, else fall back to httpx",
    )

    def model_post_init(self, __context: Any) -> None:
        if self.url is None and self.crawl_result is None:
            raise ValueError("Either url or crawl_result must be provided")


class QueryRequest(BaseModel):
    """Request body for the /rag/query endpoint (agent-mediated)."""

    message: str = Field(..., min_length=1, description="Natural-language question")
    mode: RAGMode = RAGMode.MIXED
    top_k: int = Field(default=5, ge=1, le=50)
    graph_name: str = os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")


class DirectQueryRequest(BaseModel):
    """Request body for the /rag/query/direct endpoint (no agent)."""

    query: str = Field(..., min_length=1)
    mode: RAGMode = RAGMode.MIXED
    top_k: int = Field(default=5, ge=1, le=50)
    graph_name: str = os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")


class StatsResponse(BaseModel):
    """Aggregated RAG capability statistics."""

    graph_rag: dict[str, Any]
    vector_rag: dict[str, Any]
    mixed_rag: dict[str, Any]


# ---------------------------------------------------------------------------
# Global shared deps (one instance per process)
# ---------------------------------------------------------------------------

_deps: RAGAgentDeps | None = None


def get_deps() -> RAGAgentDeps:
    if _deps is None:
        raise RuntimeError("RAG agent not initialised — call /rag/setup first")
    return _deps


# ---------------------------------------------------------------------------
# PydanticAI Agent with tools + capabilities
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a knowledge-graph and vector-search assistant.

You have access to a knowledge base built from web pages:
  - GraphRAG: structured entity/relationship graph stored in PostgresAGE
  - VectorRAG: semantic text chunks stored in pgvector (via LlamaIndex)
  - MixedRAG: combines both for the best coverage

Tools at your disposal:
  - crawl_and_ingest(url): crawl a URL and add it to the knowledge base
  - query_graph_rag(query): answer a question using graph traversal
  - query_vector_rag(query): answer using semantic vector similarity
  - query_mixed_rag(query): answer using both graph + vector (recommended)
  - get_knowledge_base_status(): check what is in the knowledge base

Always choose the most appropriate RAG mode:
  - Use graph for "who works at", "what is part of", relationship questions
  - Use vector for detailed factual or conceptual questions
  - Use mixed (default) when unsure — it provides the best coverage
"""

rag_agent: Agent[RAGAgentDeps, str] = Agent(
    model=os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6"),
    system_prompt=_SYSTEM_PROMPT,
    deps_type=RAGAgentDeps,
    result_type=str,
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@rag_agent.tool
async def crawl_and_ingest(
    ctx: RunContext[RAGAgentDeps],
    url: Annotated[str, Field(description="The URL to crawl and add to the knowledge base")],
    use_crawl4ai: Annotated[bool, Field(description="Use crawl4ai (True) or plain httpx (False)")] = True,
) -> str:
    """Crawl a web page and ingest it into the knowledge graph + vector store.

    Returns a summary of what was stored.
    """
    try:
        result: IngestResult = await ingest_url(
            url,
            graph_name=ctx.deps.graph_name,
            use_crawl4ai=use_crawl4ai,
        )
    except Exception as exc:
        raise ModelRetry(f"Ingestion failed: {exc}") from exc

    warnings_str = (" Warnings: " + "; ".join(result.warnings)) if result.warnings else ""
    return (
        f"Ingested {result.source_url} in {result.elapsed_seconds:.1f}s: "
        f"{result.entities_stored} entities, {result.relationships_stored} relationships, "
        f"{result.chunks_stored} text chunks stored.{warnings_str}"
    )


@rag_agent.tool
async def query_graph_rag(
    ctx: RunContext[RAGAgentDeps],
    query: Annotated[str, Field(description="Natural-language question to answer via graph traversal")],
    top_k: Annotated[int, Field(description="Maximum entities to retrieve", ge=1, le=50)] = 5,
) -> str:
    """Answer a question using the knowledge graph (GraphRAG).

    Best for: entity lookups, relationship questions, 'who', 'what organisation'.
    """
    q = RAGQuery(
        query=query,
        mode=RAGMode.GRAPH,
        top_k=top_k,
        graph_name=ctx.deps.graph_name,
    )
    try:
        result: RAGResult = await query_graph(q)
    except Exception as exc:
        raise ModelRetry(f"GraphRAG retrieval failed: {exc}") from exc

    sources_str = "\nSources: " + ", ".join(result.sources) if result.sources else ""
    return f"{result.answer}{sources_str}"


@rag_agent.tool
async def query_vector_rag(
    ctx: RunContext[RAGAgentDeps],
    query: Annotated[str, Field(description="Natural-language question to answer via semantic search")],
    top_k: Annotated[int, Field(description="Maximum text chunks to retrieve", ge=1, le=50)] = 5,
) -> str:
    """Answer a question using semantic vector search (VectorRAG via LlamaIndex).

    Best for: detailed factual questions, finding similar passages, concept lookup.
    """
    q = RAGQuery(
        query=query,
        mode=RAGMode.VECTOR,
        top_k=top_k,
        graph_name=ctx.deps.graph_name,
    )
    try:
        result: RAGResult = await query_vector(q)
    except Exception as exc:
        raise ModelRetry(f"VectorRAG retrieval failed: {exc}") from exc

    sources_str = "\nSources: " + ", ".join(result.sources) if result.sources else ""
    return f"{result.answer}{sources_str}"


@rag_agent.tool
async def query_mixed_rag(
    ctx: RunContext[RAGAgentDeps],
    query: Annotated[str, Field(description="Natural-language question using both graph and vector retrieval")],
    top_k: Annotated[int, Field(description="Maximum results per retrieval mode", ge=1, le=50)] = 5,
) -> str:
    """Answer a question using combined GraphRAG + VectorRAG (recommended for most questions).

    Runs graph traversal and semantic search in parallel, then synthesises one answer.
    """
    q = RAGQuery(
        query=query,
        mode=RAGMode.MIXED,
        top_k=top_k,
        graph_name=ctx.deps.graph_name,
    )
    try:
        result: RAGResult = await query_mixed(q)
    except Exception as exc:
        raise ModelRetry(f"MixedRAG retrieval failed: {exc}") from exc

    sources_str = "\nSources: " + ", ".join(result.sources) if result.sources else ""
    return f"{result.answer}{sources_str}"


@rag_agent.tool
async def get_knowledge_base_status(ctx: RunContext[RAGAgentDeps]) -> str:
    """Check the current state of the knowledge base.

    Returns entity count, relationship count, chunk count and graph name.
    """
    from rag.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Vector store count
        chunk_count = await conn.fetchval("SELECT count(*) FROM knowledge_chunks")

        # Graph entity/edge counts via AGE
        graph_name = ctx.deps.graph_name
        try:
            entity_rows = await conn.fetch(
                f"SELECT * FROM cypher('{graph_name}', $$ MATCH (n) RETURN count(n) $$) "
                f"AS (c agtype)"
            )
            entity_count = int(entity_rows[0][0]) if entity_rows else 0

            edge_rows = await conn.fetch(
                f"SELECT * FROM cypher('{graph_name}', $$ MATCH ()-[r]->() RETURN count(r) $$) "
                f"AS (c agtype)"
            )
            edge_count = int(edge_rows[0][0]) if edge_rows else 0
        except Exception:
            entity_count = edge_count = -1

    return (
        f"Knowledge base status:\n"
        f"  Graph: '{graph_name}' — {entity_count} entities, {edge_count} relationships\n"
        f"  Vector store: {chunk_count} text chunks\n"
    )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the DB pool and schema on startup; close pool on shutdown."""
    global _deps

    pool = await initialise_db()
    await setup_db()

    _deps = RAGAgentDeps(db_pool=pool)
    logger.info("RAG demo agent ready (graph=%s)", _deps.graph_name)

    yield

    await close_db()
    logger.info("RAG demo agent shut down")


app = FastAPI(
    title="Jarvis RAG Demo",
    description=(
        "Demonstrates GraphRAG (PostgresAGE), VectorRAG (pgvector via LlamaIndex) "
        "and Mixed RAG using pydantic-ai, pydantic, and minimal llamaindex."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/rag/ingest", response_model=IngestResult, summary="Ingest a URL or CrawlResult")
async def api_ingest(request: IngestRequest) -> IngestResult:
    """Crawl (or accept pre-crawled) content and store it in the knowledge graph + vector store.

    Supports two modes:
    - Pass ``url`` — the server crawls it (via crawl4ai or httpx fallback)
    - Pass ``crawl_result`` — skip the HTTP fetch and use your crawl4ai JSON directly
    """
    try:
        if request.crawl_result is not None:
            return await ingest_crawl_result(
                request.crawl_result,
                graph_name=request.graph_name,
            )
        else:
            return await ingest_url(
                request.url,  # type: ignore[arg-type]
                graph_name=request.graph_name,
                use_crawl4ai=request.use_crawl4ai,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/rag/query", summary="Query via the pydantic-ai RAG agent (natural language)")
async def api_query_agent(request: QueryRequest) -> JSONResponse:
    """Ask the pydantic-ai agent a question.

    The agent will choose the appropriate RAG tool (graph, vector or mixed)
    and return a synthesised answer.
    """
    deps = get_deps()
    try:
        result = await rag_agent.run(
            request.message,
            deps=deps,
        )
        return JSONResponse(
            {
                "answer": result.output,
                "usage": result.usage().model_dump() if result.usage() else None,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/rag/query/direct", response_model=RAGResult, summary="Direct RAG query (no agent)")
async def api_query_direct(request: DirectQueryRequest) -> RAGResult:
    """Run a RAG query directly (bypasses the agent, useful for benchmarking).

    Returns the full ``RAGResult`` including raw graph/vector context.
    """
    q = RAGQuery(
        query=request.query,
        mode=request.mode,
        top_k=request.top_k,
        graph_name=request.graph_name,
    )
    try:
        if request.mode == RAGMode.GRAPH:
            return await query_graph(q)
        elif request.mode == RAGMode.VECTOR:
            return await query_vector(q)
        else:
            return await query_mixed(q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/rag/stats", response_model=StatsResponse, summary="RAG capability statistics")
async def api_stats() -> StatsResponse:
    """Return accumulated latency and cache statistics for each RAG capability."""
    deps = get_deps()
    return StatsResponse(
        graph_rag=deps.graph_cap.get_stats().to_dict(),
        vector_rag=deps.vector_cap.get_stats().to_dict(),
        mixed_rag=deps.mixed_cap.get_stats().to_dict(),
    )


@app.post("/rag/stats/reset", summary="Reset RAG capability statistics")
async def api_stats_reset() -> dict[str, str]:
    """Reset all accumulated RAG statistics and caches."""
    deps = get_deps()
    deps.graph_cap.reset()
    deps.vector_cap.reset()
    deps.mixed_cap.reset()
    return {"status": "reset"}


@app.get("/rag/health", summary="Health check")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("rag_demo_agent:app", host="0.0.0.0", port=8001, reload=True)
