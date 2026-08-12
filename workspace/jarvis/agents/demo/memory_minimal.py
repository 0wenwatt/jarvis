"""Memory minimal demo — shows persistent conversation history with PydanticAI.

Connection rule: *Direct* — memory is implemented as a native ``AbstractCapability``
(no MCP, no extra process).  History is kept in a JSON file on disk so it
survives container restarts, matching the pattern used by the main app.

What this demo shows
────────────────────
- ``AbstractCapability`` subclass (``ConversationMemoryCapability``) that:
    * counts turns (``before_tool_execute`` / ``after_tool_execute``)
    * exposes a ``turn_count`` property for health checks
- Per-session JSON history persistence (same pattern as app.py)
- Logfire tracing via ``instrument_pydantic_ai()``

Run:
    cd workspace/jarvis
    python agents/demo/memory_minimal.py          # interactive REPL
    # Or as ASGI (via uvicorn):
    uvicorn agents.demo.memory_minimal:app --host 0.0.0.0 --port 7933
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelMessage

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
        logger.info("Logfire configured — tracing active (memory_minimal)")
    else:
        logfire.configure(send_to_logfire=False)
        logger.info("LOGFIRE_TOKEN not set — Logfire disabled in memory_minimal")
except ImportError:
    logger.warning("logfire not installed — skipping observability setup")

# ---------------------------------------------------------------------------
# ConversationMemoryCapability — AbstractCapability subclass
# Tracks per-turn tool stats; attach to any Agent via middleware=[...].
# ---------------------------------------------------------------------------

_ta_messages: TypeAdapter[list[ModelMessage]] = TypeAdapter(list[ModelMessage])


@dataclass
class ConversationMemoryCapability(AbstractCapability):
    """Counts tool calls per conversation turn and surfaces them as stats.

    This is intentionally minimal: it demonstrates the ``AbstractCapability``
    interface without pulling in external storage.  For a production memory
    system (semantic search over past turns, etc.) extend this class with
    pgvector queries.
    """

    _turn_tool_counts: dict[str, int] = field(default_factory=dict, repr=False)
    turn_count: int = 0

    async def before_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
    ) -> None:
        name = tool_def.name
        self._turn_tool_counts[name] = self._turn_tool_counts.get(name, 0) + 1

    async def after_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
        result: Any,
    ) -> Any:
        self.turn_count += 1
        logger.debug(
            "Memory: turn=%d tool=%s total_calls=%s",
            self.turn_count,
            tool_def.name,
            self._turn_tool_counts,
        )
        return result

    def reset_turn(self) -> None:
        self._turn_tool_counts.clear()


# ---------------------------------------------------------------------------
# History helpers — JSON persistence (same pattern as app.py)
# ---------------------------------------------------------------------------

_HISTORY_DIR = Path(
    os.environ.get("MEMORY_HISTORY_DIR", "/workspace/jarvis/workspaces/memory_demo")
)
_HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _history_path(session_id: str) -> Path:
    import hashlib

    name = hashlib.sha256(session_id.encode()).hexdigest()
    return _HISTORY_DIR / f"{name}.json"


def load_history(session_id: str) -> list[ModelMessage]:
    path = _history_path(session_id)
    if not path.exists():
        return []
    try:
        return _ta_messages.validate_json(path.read_text())
    except Exception as exc:
        logger.warning("Could not load history for %s: %s", session_id, exc)
        return []


def save_history(session_id: str, messages: list[ModelMessage]) -> None:
    path = _history_path(session_id)
    path.write_text(_ta_messages.dump_json(messages, indent=2).decode())


# ---------------------------------------------------------------------------
# Agent with memory capability attached
# ---------------------------------------------------------------------------

_MODEL = os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6")

memory_cap = ConversationMemoryCapability()

agent = Agent(
    _MODEL,
    instructions=(
        "You are Jarvis, a helpful assistant with persistent memory across turns. "
        "The user's previous messages are included automatically. "
        "Refer to earlier context when it is relevant."
    ),
    middleware=[memory_cap],
)


# ---------------------------------------------------------------------------
# Interactive REPL — for quick local testing
# ---------------------------------------------------------------------------


async def _repl(session_id: str = "default") -> None:
    """Simple interactive loop to test multi-turn memory."""
    history: list[ModelMessage] = load_history(session_id)
    print(f"Jarvis Memory Demo  (session={session_id}, history={len(history)} msgs)")
    print("Type 'exit' or Ctrl-C to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        memory_cap.reset_turn()
        result = await agent.run(user_input, message_history=history)
        history = list(result.all_messages())
        save_history(session_id, history)

        print(f"Jarvis: {result.output}")
        print(f"  [turns={memory_cap.turn_count}  tools={memory_cap._turn_tool_counts}]\n")


# ---------------------------------------------------------------------------
# Minimal FastAPI wrapper — for uvicorn use
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Jarvis Memory Demo",
    description="Minimal demo: persistent conversation history via AbstractCapability.",
)

try:
    import logfire as _lf

    _lf.instrument_fastapi(app)
except (ImportError, Exception):
    pass


class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str


class ChatResponse(BaseModel):
    reply: str
    turn_count: int


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    history = load_history(req.session_id)
    memory_cap.reset_turn()
    result = await agent.run(req.message, message_history=history)
    save_history(req.session_id, list(result.all_messages()))
    return ChatResponse(reply=result.output, turn_count=memory_cap.turn_count)


@app.get("/stats")
async def stats() -> JSONResponse:
    return JSONResponse(
        {
            "turn_count": memory_cap.turn_count,
            "tool_counts": dict(memory_cap._turn_tool_counts),
        }
    )


if __name__ == "__main__":
    asyncio.run(_repl())
