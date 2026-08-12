"""Web UI demo — exposes Jarvis via PydanticAI's built-in chat interface.

Connection rule: *Direct* — ``agent.to_web()`` is a native PydanticAI feature;
no MCP server or extra process is needed.

The server binds to ``0.0.0.0:7932`` so that when the Jarvis container is
running inside Docker (with or without Tailscale), the UI is directly
reachable at:

    http://<tailscale-ip>:7932       — from any Tailscale peer
    http://localhost:7932            — from the host machine

Observability: Logfire traces every agent run and tool call.

Run:
    cd workspace/jarvis
    uvicorn agents.demo.web_ui_demo:app --host 0.0.0.0 --port 7932

Or stand-alone:
    python -m agents.demo.web_ui_demo
"""

from __future__ import annotations

import logging
import os

from pydantic_ai import Agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logfire — configure before creating the agent so all runs are traced.
# ---------------------------------------------------------------------------
try:
    import logfire

    _token = os.environ.get("LOGFIRE_TOKEN", "").strip()
    if _token:
        logfire.configure(token=_token)
        logfire.instrument_pydantic_ai()
        logger.info("Logfire configured — tracing active (web_ui_demo)")
    else:
        logfire.configure(send_to_logfire=False)
        logger.info("LOGFIRE_TOKEN not set — Logfire disabled in web_ui_demo")
except ImportError:
    logger.warning("logfire not installed — skipping observability setup")

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_MODEL = os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6")

agent = Agent(
    _MODEL,
    instructions=(
        "You are Jarvis, a helpful AI assistant. "
        "Answer questions clearly and concisely. "
        "Use markdown formatting where appropriate."
    ),
)

# ---------------------------------------------------------------------------
# Web UI — agent.to_web() returns a standard ASGI app.
# Bind to 0.0.0.0 so it is reachable over Tailscale from any peer.
# Requires: pip install 'pydantic-ai[web]'
# ---------------------------------------------------------------------------
app = agent.to_web(
    # Expose all configured models so the user can switch in the browser.
    models=[_MODEL],
)

# Instrument the ASGI app with Logfire so HTTP requests appear in traces.
try:
    import logfire as _lf

    _lf.instrument_fastapi(app)  # type: ignore[arg-type]
except (ImportError, Exception):
    pass

# ---------------------------------------------------------------------------
# Entrypoint — allows `python -m agents.demo.web_ui_demo`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("WEB_UI_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_UI_PORT", "7932"))
    print(f"Starting Jarvis Web UI on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
