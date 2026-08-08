"""GitHub MCP demo — Jarvis with full GitHub API access via the official MCP server.

Connection rule: *Local Stdio MCP* — the GitHub MCP server is a compiled Go
binary that manages its own OAuth state and REST/GraphQL client pool; it runs
as an isolated child process communicating over stdio.  The binary is already
installed in the Docker image at ``/usr/local/bin/github-mcp-server`` (see
``Dockerfile``).

What this demo shows
────────────────────
- ``pydantic_ai.mcp.MCPToolset`` wired to the GitHub MCP stdio binary
- Graceful degradation: agent starts without MCP when ``GITHUB_TOKEN`` is absent
- Logfire tracing via ``instrument_pydantic_ai()``

Run:
    cd workspace/jarvis
    GITHUB_TOKEN=ghp_... uvicorn agents.demo.github_demo:app --host 0.0.0.0 --port 7934

Or directly:
    GITHUB_TOKEN=ghp_... python agents/demo/github_demo.py
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Logfire
# ---------------------------------------------------------------------------
try:
    import logfire

    _token = os.environ.get("LOGFIRE_TOKEN", "").strip()
    if _token:
        logfire.configure(token=_token)
        logfire.instrument_pydantic_ai()
        logger.info("Logfire configured — tracing active (github_demo)")
    else:
        logfire.configure(send_to_logfire=False)
        logger.info("LOGFIRE_TOKEN not set — Logfire disabled in github_demo")
except ImportError:
    logger.warning("logfire not installed — skipping observability setup")

# ---------------------------------------------------------------------------
# GitHub MCP toolset (Local Stdio MCP)
# Requires GITHUB_TOKEN and the github-mcp-server binary in PATH.
# ---------------------------------------------------------------------------

_GITHUB_MCP_BINARY = "/usr/local/bin/github-mcp-server"


def _build_github_mcp() -> MCPToolset | None:
    """Build the GitHub MCPToolset if prerequisites are present."""
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not gh_token:
        logger.warning("GITHUB_TOKEN not set — GitHub MCP server disabled")
        return None
    if not Path(_GITHUB_MCP_BINARY).exists():
        logger.warning(
            "%s not found — GitHub MCP disabled (rebuild the Docker image?)",
            _GITHUB_MCP_BINARY,
        )
        return None
    logger.info("GitHub MCP server enabled")
    return MCPToolset(
        {
            "command": _GITHUB_MCP_BINARY,
            "args": ["stdio"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": gh_token},
        }
    )


_github_toolset = _build_github_mcp()
_extra_toolsets = [_github_toolset] if _github_toolset is not None else []

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_MODEL = os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6")

agent = Agent(
    _MODEL,
    instructions=(
        "You are Jarvis with full GitHub access. "
        "You can search repositories, read issues and pull requests, "
        "list commits, view file contents, and explore code on GitHub. "
        "Always cite the repository and URL when referencing GitHub content."
    ),
    toolsets=_extra_toolsets,
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Jarvis GitHub Demo",
    description="PydanticAI agent with GitHub MCP server (stdio transport).",
)

try:
    import logfire as _lf

    _lf.instrument_fastapi(app)
except (ImportError, Exception):
    pass


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    github_mcp_enabled: bool


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    result = await agent.run(req.message)
    return ChatResponse(
        reply=result.output,
        github_mcp_enabled=_github_toolset is not None,
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "github_mcp": _github_toolset is not None,
            "model": _MODEL,
        }
    )


# ---------------------------------------------------------------------------
# Quick interactive test
# ---------------------------------------------------------------------------


async def _repl() -> None:
    print("Jarvis GitHub Demo")
    print(f"  MCP enabled: {_github_toolset is not None}")
    print("Type 'exit' to quit.\n")
    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit"}:
            break
        if not q:
            continue
        result = await agent.run(q)
        print(f"Jarvis: {result.output}\n")


if __name__ == "__main__":
    asyncio.run(_repl())
