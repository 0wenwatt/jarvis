"""Module 4: Unified Demo Agent & LangGraph Node Handler.

This module combines the Research and Coding capabilities into a single
pydantic-ai agent and wraps it in a LangGraph node function so it can be
scheduled by the parent orchestration graph reading state from PostgreSQL.

Pydantic AI Agent
─────────────────
``demo_agent`` is a full ``Agent[ResearchCodingDeps, str]`` instance that
exposes every tool from both the research pipeline and the coding tool set:
  - web_search_to_db
  - ingest_github_repo_to_db
  - query_graph_memory
  - ast_rename_symbol
  - ast_find_references
  - ast_apply_refactoring
  - legacy_read_file
  - legacy_replace_string
  - legacy_write_file

LangGraph Integration
─────────────────────
:func:`langgraph_node` is an async function with the standard LangGraph
``(state: dict) -> dict`` signature.  It reads task configuration from the
incoming state, constructs :class:`ResearchCodingDeps`, invokes the agent,
and returns an updated state dict.  The parent orchestration graph can wire
this function as a node::

    from langgraph.graph import StateGraph
    from demo.demo_agent import langgraph_node

    graph = StateGraph(dict)
    graph.add_node("jarvis_demo", langgraph_node)

Capability flags (env vars or state overrides)
──────────────────────────────────────────────
``AgentCapabilitiesConfig`` inherits the same flags from ``CapabilitiesConfig``
plus high-level research toggles, all readable from environment variables.
Override them per-invocation by passing them in the LangGraph state dict under
the ``"capabilities"`` key.

Run standalone (FastAPI)
────────────────────────
    cd workspace/jarvis
    uvicorn demo.demo_agent:app --host 0.0.0.0 --port 7936 --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logfire — optional observability
# ---------------------------------------------------------------------------
try:
    import logfire

    _token = os.environ.get("LOGFIRE_TOKEN", "").strip()
    if _token:
        logfire.configure(token=_token)
        logfire.instrument_pydantic_ai()
        logger.info("Logfire configured (demo_agent)")
    else:
        logfire.configure(send_to_logfire=False)
        logger.info("LOGFIRE_TOKEN not set — Logfire disabled (demo_agent)")
except ImportError:
    logger.warning("logfire not installed — skipping observability (demo_agent)")


# ---------------------------------------------------------------------------
# Helper to read boolean env vars
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool = True) -> bool:
    val = os.environ.get(name, "").strip().lower()
    return (val in {"1", "true", "yes", "on"}) if val else default


# ---------------------------------------------------------------------------
# Capability config (Pydantic BaseModel per spec)
# ---------------------------------------------------------------------------


class AgentCapabilitiesConfig(BaseModel):
    """Top-level feature-flag model for the unified demo agent.

    All fields are readable from environment variables so Docker deployments
    need only set env vars rather than modifying code.
    """

    enable_web_search: bool = Field(
        default_factory=lambda: _env_bool("USE_WEB_SEARCH"),
        description="Allow the agent to crawl URLs and store results in PostgreSQL",
    )
    enable_github_ingest: bool = Field(
        default_factory=lambda: _env_bool("USE_GITHUB_INGEST"),
        description="Allow the agent to clone and ingest GitHub repositories",
    )
    enable_codegen_ast: bool = Field(
        default_factory=lambda: _env_bool("ENABLE_CODEGEN_AST"),
        description="Enable AST-based coding tools (codegen / Tree-sitter)",
    )
    enable_legacy_tools: bool = Field(
        default_factory=lambda: _env_bool("ENABLE_LEGACY_TOOLS"),
        description="Enable direct file I/O legacy tools",
    )
    postgres_db_url: str = Field(
        default_factory=lambda: os.environ.get("DATABASE_URL", ""),
        description="PostgreSQL connection URL used by RAG and AST bridge subsystems",
    )


# ---------------------------------------------------------------------------
# Deps model (Pydantic BaseModel per spec)
# ---------------------------------------------------------------------------


class ResearchCodingDeps(BaseModel):
    """Runtime dependencies for the unified demo agent.

    Holds the capabilities config and references to the database / AST handles.
    The ``extra`` dict allows callers to pass additional context (e.g. an
    existing asyncpg pool) without breaking the schema.
    """

    config: AgentCapabilitiesConfig = Field(default_factory=AgentCapabilitiesConfig)
    graph_name: str = Field(
        default_factory=lambda: os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")
    )
    cognee_dataset: str = Field(
        default_factory=lambda: os.environ.get("COGNEE_DATASET", "jarvis_research")
    )
    workspace_root: str = Field(
        default_factory=lambda: os.environ.get("WORKSPACE_ROOT", ".")
    )
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are Jarvis — a unified research and coding assistant.

You combine:
  1. Research capabilities: web crawling, GitHub repository ingestion,
     and graph/vector knowledge base queries.
  2. Coding capabilities: AST-based symbol operations (rename, find references,
     apply refactoring) and direct file editing tools.

Workflow guidance
─────────────────
- For research tasks: ingest sources first, then query the knowledge base.
- For coding tasks: prefer AST tools for Python; use legacy tools for other
  languages or when AST is disabled.
- Always explain what you did and cite sources where applicable.

Capability status is governed by the AgentCapabilitiesConfig passed at runtime.
If a tool returns a "disabled" message, inform the user and suggest how to
enable it (environment variable or config flag).
"""

demo_agent: Agent[ResearchCodingDeps, str] = Agent(
    model=os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6"),
    system_prompt=_SYSTEM_PROMPT,
    deps_type=ResearchCodingDeps,
    output_type=str,
    defer_model_check=True,
)


# ===========================================================================
# Tools — Research
# ===========================================================================


@demo_agent.tool
async def web_search_to_db(
    ctx: RunContext[ResearchCodingDeps],
    query: Annotated[str, Field(description="URL or search query to crawl and ingest")],
) -> str:
    """Crawl a URL and store the extracted knowledge in PostgreSQL."""
    if not ctx.deps.config.enable_web_search:
        return "Web search is disabled (enable_web_search=False)."

    try:
        from rag import ingest_url
    except ImportError as exc:
        raise ModelRetry(f"rag module unavailable: {exc}") from exc

    url = query.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://duckduckgo.com/?q={url.replace(' ', '+')}"

    try:
        result = await ingest_url(url, graph_name=ctx.deps.graph_name)
    except Exception as exc:
        raise ModelRetry(f"Ingestion failed: {exc}") from exc

    return (
        f"Ingested '{result.source_url}' — {result.entities_stored} entities, "
        f"{result.relationships_stored} relationships, {result.chunks_stored} chunks."
    )


@demo_agent.tool
async def ingest_github_repo_to_db(
    ctx: RunContext[ResearchCodingDeps],
    repo_url: Annotated[str, Field(description="GitHub repo URL (https://github.com/owner/repo)")],
) -> str:
    """Clone a GitHub repo, extract its AST symbol graph, and persist to PostgreSQL."""
    if not ctx.deps.config.enable_github_ingest:
        return "GitHub ingestion is disabled (enable_github_ingest=False)."

    try:
        from research.pipeline import ResearchAgentDeps, ingest_github_repo_to_db as _ingest

        sub_deps = ResearchAgentDeps(
            graph_name=ctx.deps.graph_name,
            cognee_dataset=ctx.deps.cognee_dataset,
            github_ingest_enabled=True,
        )
    except ImportError as exc:
        raise ModelRetry(f"research.pipeline unavailable: {exc}") from exc

    # Build a mock RunContext-like wrapper and delegate
    # We call the inner logic directly to avoid nesting agent runs.
    import shutil
    import subprocess

    repo_url_clean = repo_url.strip().rstrip("/")
    if not repo_url_clean.startswith(("http://", "https://")):
        raise ModelRetry(f"Invalid repo URL: {repo_url_clean!r}")

    repo_slug = repo_url_clean.split("github.com/")[-1].replace("/", "__")
    cache_dir = sub_deps.github_cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    clone_target = os.path.join(cache_dir, repo_slug)

    if os.path.isdir(clone_target):
        shutil.rmtree(clone_target, ignore_errors=True)

    try:
        subprocess.run(
            ["git", "clone", "--depth=1", "--single-branch", repo_url_clean, clone_target],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ModelRetry(f"git clone failed: {exc}") from exc

    if not ctx.deps.config.enable_codegen_ast:
        shutil.rmtree(clone_target, ignore_errors=True)
        return (
            f"Cloned {repo_url_clean} but AST ingestion disabled (enable_codegen_ast=False). "
            "Enable ENABLE_CODEGEN_AST=true to extract symbol graphs."
        )

    try:
        from comprehension.bridge import CodebaseBridgeDeps, ingest_codebase
    except ImportError as exc:
        shutil.rmtree(clone_target, ignore_errors=True)
        raise ModelRetry(f"comprehension.bridge unavailable: {exc}") from exc

    bridge_deps = CodebaseBridgeDeps(
        codebase_root=clone_target,
        cognee_dataset=ctx.deps.cognee_dataset,
        ast_enabled=True,
    )
    try:
        result = await ingest_codebase(bridge_deps)
    except Exception as exc:
        raise ModelRetry(f"AST ingestion failed: {exc}") from exc
    finally:
        shutil.rmtree(clone_target, ignore_errors=True)

    return (
        f"Ingested {repo_url_clean} — {result.nodes_extracted} AST nodes, "
        f"{result.edges_extracted} edges in {result.elapsed_seconds:.1f}s."
    )


@demo_agent.tool
async def query_graph_memory(
    ctx: RunContext[ResearchCodingDeps],
    cypher_or_vector_query: Annotated[
        str,
        Field(description="Natural-language question or Cypher MATCH…RETURN body"),
    ],
) -> str:
    """Query the stored knowledge base (graph + vector) and return synthesised results."""
    try:
        from rag import RAGMode, RAGQuery, query_mixed
    except ImportError as exc:
        raise ModelRetry(f"rag module unavailable: {exc}") from exc

    q_text = cypher_or_vector_query.strip()
    q = RAGQuery(query=q_text, mode=RAGMode.MIXED, top_k=5, graph_name=ctx.deps.graph_name)
    try:
        result = await query_mixed(q)
    except Exception as exc:
        raise ModelRetry(f"Graph memory query failed: {exc}") from exc

    sources_str = ("\nSources: " + ", ".join(result.sources)) if result.sources else ""
    return f"{result.answer}{sources_str}"


# ===========================================================================
# Tools — Coding (delegating to coding.tools internals)
# ===========================================================================


def _coding_caps(ctx: RunContext[ResearchCodingDeps]):
    """Build a CapabilitiesConfig from the demo deps."""
    try:
        from coding.tools import CapabilitiesConfig
    except ImportError:
        return None

    return CapabilitiesConfig(
        enable_codegen_ast=ctx.deps.config.enable_codegen_ast,
        enable_legacy_tools=ctx.deps.config.enable_legacy_tools,
        workspace_root=ctx.deps.workspace_root,
    )


@demo_agent.tool
async def ast_rename_symbol(
    ctx: RunContext[ResearchCodingDeps],
    symbol_name: Annotated[str, Field(description="Symbol name to rename")],
    new_name: Annotated[str, Field(description="New symbol name")],
) -> str:
    """Rename a symbol across the workspace using AST-safe transformation."""
    if not ctx.deps.config.enable_codegen_ast:
        return "AST tools are disabled (enable_codegen_ast=False)."

    try:
        from coding.tools import CodingAgentDeps, ast_rename_symbol as _fn
    except ImportError as exc:
        raise ModelRetry(f"coding.tools unavailable: {exc}") from exc

    caps = _coding_caps(ctx)
    deps = CodingAgentDeps(capabilities=caps, workspace_root=ctx.deps.workspace_root)

    # Build a mock context and delegate
    from dataclasses import dataclass

    @dataclass
    class _MockCtx:
        deps: Any

    mock_ctx = _MockCtx(deps=deps)
    return await _fn(mock_ctx, symbol_name=symbol_name, new_name=new_name)  # type: ignore[arg-type]


@demo_agent.tool
async def ast_find_references(
    ctx: RunContext[ResearchCodingDeps],
    symbol_name: Annotated[str, Field(description="Symbol to find references for")],
) -> str:
    """Find all usages of *symbol_name* in the workspace."""
    if not ctx.deps.config.enable_codegen_ast:
        return "AST tools are disabled (enable_codegen_ast=False)."

    try:
        from coding.tools import CodingAgentDeps, ast_find_references as _fn
    except ImportError as exc:
        raise ModelRetry(f"coding.tools unavailable: {exc}") from exc

    from dataclasses import dataclass

    @dataclass
    class _MockCtx:
        deps: Any

    caps = _coding_caps(ctx)
    deps = CodingAgentDeps(capabilities=caps, workspace_root=ctx.deps.workspace_root)
    mock_ctx = _MockCtx(deps=deps)
    return await _fn(mock_ctx, symbol_name=symbol_name)  # type: ignore[arg-type]


@demo_agent.tool
async def ast_apply_refactoring(
    ctx: RunContext[ResearchCodingDeps],
    file_path: Annotated[str, Field(description="Relative path to the file")],
    refactor_spec: Annotated[str, Field(description="Refactoring description")],
) -> str:
    """Apply a targeted AST-scoped refactoring to *file_path*."""
    if not ctx.deps.config.enable_codegen_ast:
        return "AST tools are disabled (enable_codegen_ast=False)."

    try:
        from coding.tools import CodingAgentDeps, ast_apply_refactoring as _fn
    except ImportError as exc:
        raise ModelRetry(f"coding.tools unavailable: {exc}") from exc

    from dataclasses import dataclass

    @dataclass
    class _MockCtx:
        deps: Any

    caps = _coding_caps(ctx)
    deps = CodingAgentDeps(capabilities=caps, workspace_root=ctx.deps.workspace_root)
    mock_ctx = _MockCtx(deps=deps)
    return await _fn(mock_ctx, file_path=file_path, refactor_spec=refactor_spec)  # type: ignore[arg-type]


@demo_agent.tool
async def legacy_read_file(
    ctx: RunContext[ResearchCodingDeps],
    file_path: Annotated[str, Field(description="Relative path to read")],
) -> str:
    """Read a file from disk and return its contents."""
    if not ctx.deps.config.enable_legacy_tools:
        return "Legacy tools are disabled (enable_legacy_tools=False)."

    try:
        from coding.tools import CodingAgentDeps, legacy_read_file as _fn
    except ImportError as exc:
        raise ModelRetry(f"coding.tools unavailable: {exc}") from exc

    from dataclasses import dataclass

    @dataclass
    class _MockCtx:
        deps: Any

    caps = _coding_caps(ctx)
    deps = CodingAgentDeps(capabilities=caps, workspace_root=ctx.deps.workspace_root)
    mock_ctx = _MockCtx(deps=deps)
    return await _fn(mock_ctx, file_path=file_path)  # type: ignore[arg-type]


@demo_agent.tool
async def legacy_replace_string(
    ctx: RunContext[ResearchCodingDeps],
    file_path: Annotated[str, Field(description="Relative path to the file")],
    target: Annotated[str, Field(description="String to find")],
    replacement: Annotated[str, Field(description="Replacement string")],
) -> str:
    """Find and replace *target* with *replacement* in *file_path*."""
    if not ctx.deps.config.enable_legacy_tools:
        return "Legacy tools are disabled (enable_legacy_tools=False)."

    try:
        from coding.tools import CodingAgentDeps, legacy_replace_string as _fn
    except ImportError as exc:
        raise ModelRetry(f"coding.tools unavailable: {exc}") from exc

    from dataclasses import dataclass

    @dataclass
    class _MockCtx:
        deps: Any

    caps = _coding_caps(ctx)
    deps = CodingAgentDeps(capabilities=caps, workspace_root=ctx.deps.workspace_root)
    mock_ctx = _MockCtx(deps=deps)
    return await _fn(mock_ctx, file_path=file_path, target=target, replacement=replacement)  # type: ignore[arg-type]


@demo_agent.tool
async def legacy_write_file(
    ctx: RunContext[ResearchCodingDeps],
    file_path: Annotated[str, Field(description="Relative path to write")],
    content: Annotated[str, Field(description="Full file content")],
) -> str:
    """Write or overwrite *file_path* with *content*."""
    if not ctx.deps.config.enable_legacy_tools:
        return "Legacy tools are disabled (enable_legacy_tools=False)."

    try:
        from coding.tools import CodingAgentDeps, legacy_write_file as _fn
    except ImportError as exc:
        raise ModelRetry(f"coding.tools unavailable: {exc}") from exc

    from dataclasses import dataclass

    @dataclass
    class _MockCtx:
        deps: Any

    caps = _coding_caps(ctx)
    deps = CodingAgentDeps(capabilities=caps, workspace_root=ctx.deps.workspace_root)
    mock_ctx = _MockCtx(deps=deps)
    return await _fn(mock_ctx, file_path=file_path, content=content)  # type: ignore[arg-type]


# ===========================================================================
# LangGraph Node Handler
# ===========================================================================


async def langgraph_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node function that invokes the unified demo agent.

    The parent orchestration graph passes a state dict that may contain:
      - ``"message"``       (str)  — the task / user message to run
      - ``"capabilities"``  (dict) — optional capability overrides
      - ``"graph_name"``    (str)  — AGE graph name override
      - ``"workspace_root"``(str)  — workspace directory override

    Returns an updated state dict with:
      - ``"result"``        (str)  — agent output
      - ``"error"``         (str | None) — error message if the run failed
      - ``"agent_usage"``   (dict | None) — token usage stats

    Example LangGraph wiring::

        from langgraph.graph import StateGraph
        from demo.demo_agent import langgraph_node

        graph_builder = StateGraph(dict)
        graph_builder.add_node("jarvis", langgraph_node)
        graph_builder.set_entry_point("jarvis")
        graph_builder.set_finish_point("jarvis")
        graph = graph_builder.compile()

        final_state = await graph.ainvoke({"message": "Summarise Tree-sitter"})
    """
    message = state.get("message", "")
    if not message:
        return {**state, "result": "", "error": "No message provided", "agent_usage": None}

    caps_override = state.get("capabilities") or {}
    caps = AgentCapabilitiesConfig(**caps_override)

    deps = ResearchCodingDeps(
        config=caps,
        graph_name=state.get("graph_name", os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")),
        cognee_dataset=state.get("cognee_dataset", os.environ.get("COGNEE_DATASET", "jarvis_research")),
        workspace_root=state.get("workspace_root", os.environ.get("WORKSPACE_ROOT", ".")),
    )

    try:
        run_result = await demo_agent.run(message, deps=deps)
        usage = run_result.usage()
        return {
            **state,
            "result": run_result.output,
            "error": None,
            "agent_usage": usage.model_dump() if usage else None,
        }
    except Exception as exc:
        logger.error("langgraph_node error: %s", exc)
        return {**state, "result": "", "error": str(exc), "agent_usage": None}


# ===========================================================================
# FastAPI demo application
# ===========================================================================


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    capabilities: AgentCapabilitiesConfig | None = None
    graph_name: str = os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")
    workspace_root: str = os.environ.get("WORKSPACE_ROOT", ".")


class ChatResponse(BaseModel):
    reply: str
    usage: dict[str, Any] | None = None
    capabilities: dict[str, Any]


class NodeRequest(BaseModel):
    """Request body for the /langgraph/invoke endpoint."""

    message: str = Field(..., min_length=1)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    graph_name: str = os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")
    workspace_root: str = os.environ.get("WORKSPACE_ROOT", ".")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Jarvis Demo Agent starting up")
    yield
    logger.info("Jarvis Demo Agent shutting down")


app = FastAPI(
    title="Jarvis Demo Agent",
    description=(
        "Unified Research + Coding Pydantic AI agent with LangGraph node handler. "
        "Combines web ingestion, GitHub AST analysis, and dual-skill code editing."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

try:
    import logfire as _lf

    _lf.instrument_fastapi(app)
except (ImportError, Exception):
    pass


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Invoke the unified demo agent with a natural-language message."""
    caps = request.capabilities or AgentCapabilitiesConfig()
    deps = ResearchCodingDeps(
        config=caps,
        graph_name=request.graph_name,
        workspace_root=request.workspace_root,
    )
    try:
        run_result = await demo_agent.run(request.message, deps=deps)
        usage = run_result.usage()
        return ChatResponse(
            reply=run_result.output,
            usage=usage.model_dump() if usage else None,
            capabilities=caps.model_dump(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/langgraph/invoke", summary="Invoke via LangGraph node interface")
async def invoke_via_langgraph(request: NodeRequest) -> JSONResponse:
    """Invoke the agent through the LangGraph node handler.

    Mirrors the interface used by the parent orchestration graph.
    """
    state: dict[str, Any] = {
        "message": request.message,
        "capabilities": request.capabilities,
        "graph_name": request.graph_name,
        "workspace_root": request.workspace_root,
    }
    result_state = await langgraph_node(state)
    return JSONResponse(result_state)


@app.get("/capabilities", summary="Show current capability config")
async def get_capabilities() -> AgentCapabilitiesConfig:
    """Return the default capability configuration derived from environment variables."""
    return AgentCapabilitiesConfig()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("demo.demo_agent:app", host="0.0.0.0", port=7936, reload=True)
