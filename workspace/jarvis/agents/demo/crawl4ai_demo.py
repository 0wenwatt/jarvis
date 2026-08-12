"""Crawl4AI MCP demo — Jarvis with web crawling capability.

Connection rule: *Local Stdio MCP* — the Crawl4AI built-in MCP server
(``python -m crawl4ai.mcp stdio``) manages Playwright browser sessions and
async crawl queues; it runs as an isolated child process over stdio.

What this demo shows
────────────────────
- ``pydantic_ai.mcp.MCPToolset`` wired to Crawl4AI's stdio MCP entry point
- Optional ``CRAWL4AI_API_TOKEN`` / ``CRAWL4AI_BASE_URL`` env vars for
  connecting to a remote self-hosted Crawl4AI instance instead of local
- Logfire tracing via ``instrument_pydantic_ai()``

Requirements:
    pip install 'crawl4ai>=0.9.0'
    playwright install chromium --with-deps   # already done in Dockerfile

Run:
    cd workspace/jarvis
    uvicorn agents.demo.crawl4ai_demo:app --host 0.0.0.0 --port 7935

Or directly:
    python agents/demo/crawl4ai_demo.py
"""

from __future__ import annotations

import asyncio
import logging
import os

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
        logger.info("Logfire configured — tracing active (crawl4ai_demo)")
    else:
        logfire.configure(send_to_logfire=False)
        logger.info("LOGFIRE_TOKEN not set — Logfire disabled in crawl4ai_demo")
except ImportError:
    logger.warning("logfire not installed — skipping observability setup")

# ---------------------------------------------------------------------------
# Crawl4AI MCP toolset (Local Stdio MCP)
# Runs `python -m crawl4ai.mcp stdio` as a child process.
# Set CRAWL4AI_API_TOKEN / CRAWL4AI_BASE_URL to point at a remote instance.
# ---------------------------------------------------------------------------


def _build_crawl4ai_mcp() -> MCPToolset:
    env: dict[str, str] = {}
    api_token = os.environ.get("CRAWL4AI_API_TOKEN", "").strip()
    if api_token:
        env["CRAWL4AI_API_TOKEN"] = api_token
    base_url = os.environ.get("CRAWL4AI_BASE_URL", "").strip()
    if base_url:
        env["CRAWL4AI_BASE_URL"] = base_url
    logger.info("Crawl4AI MCP server enabled (python -m crawl4ai.mcp stdio)")
    return MCPToolset(
        {
            "command": "python",
            "args": ["-m", "crawl4ai.mcp", "stdio"],
            **({"env": env} if env else {}),
        }
    )


_crawl4ai_toolset = _build_crawl4ai_mcp()

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_MODEL = os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6")

agent = Agent(
    _MODEL,
    instructions=(
        "You are Jarvis with web crawling capability powered by Crawl4AI. "
        "You can crawl URLs, extract structured content, take screenshots, "
        "and summarise web pages. "
        "When asked to crawl, use the available crawl4ai MCP tools. "
        "Always report the source URL alongside any extracted content."
    ),
    toolsets=[_crawl4ai_toolset],
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Jarvis Crawl4AI Demo",
    description="PydanticAI agent with Crawl4AI MCP server (stdio transport).",
)

try:
    import logfire as _lf

    _lf.instrument_fastapi(app)
except (ImportError, Exception):
    pass


class CrawlRequest(BaseModel):
    url: str
    instruction: str = "Summarise the main content of this page."


class CrawlResponse(BaseModel):
    url: str
    summary: str


@app.post("/crawl", response_model=CrawlResponse)
async def crawl(req: CrawlRequest) -> CrawlResponse:
    prompt = f"{req.instruction}\n\nURL: {req.url}"
    result = await agent.run(prompt)
    return CrawlResponse(url=req.url, summary=result.output)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "model": _MODEL})


# ---------------------------------------------------------------------------
# Quick interactive test
# ---------------------------------------------------------------------------


async def _repl() -> None:
    print("Jarvis Crawl4AI Demo")
    print("Type a URL to crawl, or 'exit' to quit.\n")
    while True:
        try:
            url = input("URL: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if url.lower() in {"exit", "quit"}:
            break
        if not url:
            continue
        result = await agent.run(f"Crawl this URL and summarise the main content: {url}")
        print(f"Jarvis: {result.output}\n")


if __name__ == "__main__":
    asyncio.run(_repl())
