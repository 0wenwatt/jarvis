"""Module 2: Multi-Source Research & Web Ingestion Pipeline.

Capabilities
────────────
1. **Web search → PostgreSQL** — Crawl a URL (via crawl4ai or httpx fallback)
   and persist the extracted knowledge graph + text chunks to PostgreSQL using
   the existing ``rag`` module infrastructure.

2. **GitHub repository ingestion** — Clone/fetch a remote GitHub repo to a
   local temp directory, run the AST bridge to extract the symbol graph, then
   push the payload into PostgreSQL via cognee.

3. **Graph memory query** — Query the stored knowledge using the AGE graph or
   pgvector similarity search.

All three capabilities are exposed as pydantic-ai ``@research_agent.tool``
decorated async functions so the agent can call them autonomously.

Feature flags
─────────────
- ``USE_WEB_SEARCH=true`` — enables :func:`web_search_to_db`
- ``USE_GITHUB_INGEST=true`` — enables :func:`ingest_github_repo_to_db`
- ``USE_GRAPH_MEMORY=true`` — enables :func:`query_graph_memory`

All flags default to **enabled** when absent; set to ``false`` / ``0`` to
disable.

Usage
─────
    import asyncio
    from research.pipeline import research_agent, ResearchAgentDeps

    deps = ResearchAgentDeps()
    result = asyncio.run(
        research_agent.run("What is Tree-sitter?", deps=deps)
    )
    print(result.output)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature-flag helpers
# ---------------------------------------------------------------------------


def _flag(name: str, default: bool = True) -> bool:
    """Read a boolean environment variable, defaulting to *default*."""
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in {"1", "true", "yes", "on"}


def _web_search_enabled() -> bool:
    return _flag("USE_WEB_SEARCH")


def _github_ingest_enabled() -> bool:
    return _flag("USE_GITHUB_INGEST")


def _graph_memory_enabled() -> bool:
    return _flag("USE_GRAPH_MEMORY")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ResearchResult(BaseModel):
    """Structured result returned by the ResearchAgent."""

    summary: str = Field(..., description="Synthesised research summary")
    sources: list[str] = Field(default_factory=list, description="URLs or repo paths referenced")
    actions_taken: list[str] = Field(default_factory=list, description="Tools invoked during the run")


# ---------------------------------------------------------------------------
# Deps
# ---------------------------------------------------------------------------


@dataclass
class ResearchAgentDeps:
    """Runtime dependencies injected into all research tools."""

    graph_name: str = field(default_factory=lambda: os.environ.get("RAG_GRAPH_NAME", "jarvis_kg"))
    cognee_dataset: str = field(default_factory=lambda: os.environ.get("COGNEE_DATASET", "jarvis_research"))
    github_cache_dir: str = field(default_factory=lambda: os.environ.get("GITHUB_CACHE_DIR", "/tmp/jarvis_github_cache"))
    use_crawl4ai: bool = True
    web_search_enabled: bool = field(default_factory=_web_search_enabled)
    github_ingest_enabled: bool = field(default_factory=_github_ingest_enabled)
    graph_memory_enabled: bool = field(default_factory=_graph_memory_enabled)
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ResearchAgent type alias (makes it importable without instantiating)
# ---------------------------------------------------------------------------

ResearchAgent = Agent  # type alias; the concrete instance is ``research_agent`` below

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a deep-research assistant with access to web search, GitHub repository
analysis, and a persistent PostgreSQL knowledge base.

Tools available
───────────────
- web_search_to_db(query): crawl the top result for *query* and store it in the
  knowledge graph + vector store.
- ingest_github_repo_to_db(repo_url): clone a GitHub repo, extract its symbol
  graph via AST analysis, and persist everything to PostgreSQL.
- query_graph_memory(query): retrieve relevant facts from the stored knowledge
  using graph traversal and/or semantic vector search.

Workflow
────────
1. Ingest relevant sources first (web or GitHub).
2. Query the knowledge base to synthesise your answer.
3. Always cite sources in your final response.
"""

research_agent: Agent[ResearchAgentDeps, ResearchResult] = Agent(  # type: ignore[type-arg]
    model=os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6"),
    system_prompt=_SYSTEM_PROMPT,
    deps_type=ResearchAgentDeps,
    output_type=ResearchResult,
    defer_model_check=True,
)


# ---------------------------------------------------------------------------
# Tool 1 — web_search_to_db
# ---------------------------------------------------------------------------


@research_agent.tool
async def web_search_to_db(
    ctx: RunContext[ResearchAgentDeps],
    query: Annotated[str, Field(description="Search query or URL to ingest into the knowledge base")],
) -> str:
    """Crawl the given URL (or search for a query) and store results in PostgreSQL.

    The ingested content is available for subsequent ``query_graph_memory`` calls.
    """
    if not ctx.deps.web_search_enabled:
        return "Web search ingestion is disabled (USE_WEB_SEARCH=false)."

    # Import lazily to avoid hard dependency when feature is disabled
    try:
        from rag import ingest_url, IngestResult  # noqa: F401
    except ImportError as exc:
        raise ModelRetry(f"rag module not available: {exc}") from exc

    # Normalise — if query is not a URL, construct a DuckDuckGo-style URL
    url = query.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://duckduckgo.com/?q={url.replace(' ', '+')}"

    try:
        result = await ingest_url(
            url,
            graph_name=ctx.deps.graph_name,
            use_crawl4ai=ctx.deps.use_crawl4ai,
        )
    except Exception as exc:
        raise ModelRetry(f"Web ingestion failed for '{url}': {exc}") from exc

    return (
        f"Ingested '{result.source_url}' in {result.elapsed_seconds:.1f}s — "
        f"{result.entities_stored} entities, {result.relationships_stored} relationships, "
        f"{result.chunks_stored} chunks stored."
    )


# ---------------------------------------------------------------------------
# Tool 2 — ingest_github_repo_to_db
# ---------------------------------------------------------------------------


def _clone_repo(repo_url: str, target_dir: str) -> tuple[bool, str]:
    """Git-clone *repo_url* into *target_dir*.

    Returns ``(success, message)``.  Uses ``git`` CLI.
    """
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", "--single-branch", repo_url, target_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return True, f"Cloned {repo_url} → {target_dir}"
    except subprocess.TimeoutExpired:
        return False, f"git clone timed out for {repo_url}"
    except subprocess.CalledProcessError as exc:
        return False, f"git clone failed: {exc.stderr.strip()}"
    except FileNotFoundError:
        return False, "git not found in PATH"


@research_agent.tool
async def ingest_github_repo_to_db(
    ctx: RunContext[ResearchAgentDeps],
    repo_url: Annotated[
        str,
        Field(description="Public GitHub repository URL, e.g. https://github.com/owner/repo"),
    ],
) -> str:
    """Clone a GitHub repository, extract its AST symbol graph, and persist to PostgreSQL.

    The symbol graph (functions, classes, imports, call edges, inheritance edges) is stored
    via the AST bridge and made available for subsequent ``query_graph_memory`` calls.
    """
    if not ctx.deps.github_ingest_enabled:
        return "GitHub ingestion is disabled (USE_GITHUB_INGEST=false)."

    repo_url = repo_url.strip().rstrip("/")
    if not repo_url.startswith(("http://", "https://")):
        raise ModelRetry(f"repo_url must be a full HTTPS URL, got: {repo_url!r}")

    # Derive a safe directory name from the repo URL
    repo_slug = repo_url.split("github.com/")[-1].replace("/", "__")
    cache_dir = ctx.deps.github_cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    clone_target = os.path.join(cache_dir, repo_slug)

    # Remove stale cache if present
    if os.path.isdir(clone_target):
        shutil.rmtree(clone_target, ignore_errors=True)

    success, msg = _clone_repo(repo_url, clone_target)
    if not success:
        raise ModelRetry(f"Could not clone repository: {msg}")

    # Import AST bridge lazily
    try:
        from comprehension.bridge import (
            CodebaseBridgeDeps,
            ingest_codebase,
            is_ast_bridge_enabled,
        )
    except ImportError as exc:
        raise ModelRetry(f"comprehension.bridge not available: {exc}") from exc

    if not is_ast_bridge_enabled():
        # AST disabled — still return the clone summary
        shutil.rmtree(clone_target, ignore_errors=True)
        return (
            f"Cloned {repo_url} but AST ingestion is disabled (USE_CODEGEN_AST=false). "
            "Set USE_CODEGEN_AST=true to extract symbol graphs."
        )

    deps = CodebaseBridgeDeps(
        codebase_root=clone_target,
        cognee_dataset=ctx.deps.cognee_dataset,
        ast_enabled=True,
    )
    try:
        result = await ingest_codebase(deps)
    except Exception as exc:
        raise ModelRetry(f"AST ingestion failed: {exc}") from exc
    finally:
        shutil.rmtree(clone_target, ignore_errors=True)

    warnings_str = (f" Warnings: {'; '.join(result.warnings)}") if result.warnings else ""
    return (
        f"Ingested {repo_url} in {result.elapsed_seconds:.1f}s — "
        f"{result.nodes_extracted} AST nodes, {result.edges_extracted} edges stored "
        f"in dataset '{result.cognee_dataset}'.{warnings_str}"
    )


# ---------------------------------------------------------------------------
# Tool 3 — query_graph_memory
# ---------------------------------------------------------------------------


@research_agent.tool
async def query_graph_memory(
    ctx: RunContext[ResearchAgentDeps],
    cypher_or_vector_query: Annotated[
        str,
        Field(
            description=(
                "A natural-language question OR an AGE Cypher query body "
                "(MATCH … RETURN …) to run against the knowledge graph."
            )
        ),
    ],
) -> str:
    """Query stored knowledge via graph traversal and/or semantic vector search.

    Pass a natural-language question to use mixed (graph + vector) retrieval.
    Pass a Cypher MATCH … RETURN … body for direct graph traversal.
    """
    if not ctx.deps.graph_memory_enabled:
        return "Graph memory queries are disabled (USE_GRAPH_MEMORY=false)."

    try:
        from rag import RAGMode, RAGQuery, query_mixed  # noqa: F401
    except ImportError as exc:
        raise ModelRetry(f"rag module not available: {exc}") from exc

    query_text = cypher_or_vector_query.strip()

    # Detect raw Cypher — starts with MATCH or WITH (common AGE patterns)
    is_cypher = query_text.upper().startswith(("MATCH ", "WITH "))

    if is_cypher:
        # Execute Cypher directly against AGE
        try:
            from rag.db import get_pool
            from rag.crawl4ai_ingest import _validate_graph_name
        except ImportError as exc:
            raise ModelRetry(f"rag.db or rag.crawl4ai_ingest not available: {exc}") from exc

        graph_name = _validate_graph_name(ctx.deps.graph_name)
        pool = await get_pool()
        try:
            async with pool.acquire() as conn:
                sql = (
                    f"SELECT * FROM cypher('{graph_name}', $$ {query_text} $$) "
                    f"AS result(c agtype)"
                )
                rows = await conn.fetch(sql)
            if not rows:
                return "Graph query returned no results."
            lines = [str(row[0]) for row in rows[:20]]
            return "Graph results:\n" + "\n".join(lines)
        except Exception as exc:
            raise ModelRetry(f"Cypher query failed: {exc}") from exc
    else:
        # Natural-language → mixed RAG
        q = RAGQuery(
            query=query_text,
            mode=RAGMode.MIXED,
            top_k=5,
            graph_name=ctx.deps.graph_name,
        )
        try:
            result = await query_mixed(q)
        except Exception as exc:
            raise ModelRetry(f"Mixed RAG query failed: {exc}") from exc

        sources_str = ("\nSources: " + ", ".join(result.sources)) if result.sources else ""
        return f"{result.answer}{sources_str}"
