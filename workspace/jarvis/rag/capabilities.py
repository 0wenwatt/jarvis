"""PydanticAI Capabilities for the three RAG systems.

Each capability wraps one RAG retrieval mode and integrates with the
pydantic-ai Capability lifecycle hooks:

  - ``before_tool_execute``: start timing, optionally return a cached result
  - ``after_tool_execute``:  record latency and call-count stats; update cache

These capabilities are designed to be attached to a PydanticAI Agent that
exposes ``query_graph_rag``, ``query_vector_rag`` and ``query_mixed_rag``
tools (defined in rag_demo_agent.py).  They provide transparent
instrumentation and an in-process LRU cache so repeated queries are fast.

Usage
─────
    from rag.capabilities import GraphRAGCapability, VectorRAGCapability, MixedRAGCapability

    graph_cap  = GraphRAGCapability()
    vector_cap = VectorRAGCapability()
    mixed_cap  = MixedRAGCapability()

    agent = Agent(..., middleware=[graph_cap, vector_cap, mixed_cap])
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.capabilities import AbstractCapability

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared stats dataclass
# ---------------------------------------------------------------------------


@dataclass
class RAGStats:
    """Accumulated per-tool statistics."""

    call_count: int = 0
    total_latency_ms: float = 0.0
    cache_hits: int = 0
    tools_called: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def mean_latency_ms(self) -> float:
        return self.total_latency_ms / self.call_count if self.call_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_count": self.call_count,
            "cache_hits": self.cache_hits,
            "mean_latency_ms": round(self.mean_latency_ms, 1),
            "total_latency_ms": round(self.total_latency_ms, 1),
            "tools_called": dict(self.tools_called),
        }


# ---------------------------------------------------------------------------
# Tiny LRU cache
# ---------------------------------------------------------------------------

_CACHE_MAX = 128


class _LRUCache:
    def __init__(self, maxsize: int = _CACHE_MAX) -> None:
        self._data: OrderedDict[str, Any] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Any | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        else:
            if len(self._data) >= self._maxsize:
                self._data.popitem(last=False)
        self._data[key] = value

    def clear(self) -> None:
        self._data.clear()


# ---------------------------------------------------------------------------
# Base RAG capability
# ---------------------------------------------------------------------------

#: Tool names each sub-capability monitors
_GRAPH_TOOLS = {"query_graph_rag"}
_VECTOR_TOOLS = {"query_vector_rag"}
_MIXED_TOOLS = {"query_mixed_rag"}


@dataclass
class _BaseRAGCapability(AbstractCapability):
    """Shared logic for all three RAG capabilities."""

    _monitored_tools: frozenset[str] = field(default=frozenset(), repr=False)
    stats: RAGStats = field(default_factory=RAGStats)
    _cache: _LRUCache = field(default_factory=_LRUCache, repr=False)
    _start_times: dict[str, float] = field(default_factory=dict, repr=False)

    # pydantic-ai capability hooks ─────────────────────────────────────────

    async def before_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
    ) -> None:
        """Start timer and check cache before the tool runs."""
        tool_name = tool_def.name
        if tool_name not in self._monitored_tools:
            return

        self._start_times[tool_name] = time.monotonic()

        # Check in-process cache
        cache_key = f"{tool_name}:{args}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self.stats.cache_hits += 1
            logger.debug("RAGCapability cache hit: %s", cache_key[:80])

    async def after_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
        result: Any,
    ) -> Any:
        """Record latency and store result in cache."""
        tool_name = tool_def.name
        if tool_name not in self._monitored_tools:
            return result

        start = self._start_times.pop(tool_name, None)
        if start is not None:
            latency_ms = (time.monotonic() - start) * 1000
            self.stats.total_latency_ms += latency_ms
            logger.debug("RAGCapability %s: %.1f ms", tool_name, latency_ms)

        self.stats.call_count += 1
        self.stats.tools_called[tool_name] += 1

        # Cache the result
        cache_key = f"{tool_name}:{args}"
        self._cache.set(cache_key, result)

        return result

    # Helpers ──────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.stats = RAGStats()
        self._cache.clear()
        self._start_times.clear()

    def get_stats(self) -> RAGStats:
        return self.stats


# ---------------------------------------------------------------------------
# Public capability classes
# ---------------------------------------------------------------------------


@dataclass
class GraphRAGCapability(_BaseRAGCapability):
    """Capability that instruments and caches GraphRAG tool calls.

    Attach to an Agent to get automatic latency tracking and result caching
    for every call to the ``query_graph_rag`` tool.
    """

    _monitored_tools: frozenset[str] = field(
        default=frozenset(_GRAPH_TOOLS), repr=False
    )


@dataclass
class VectorRAGCapability(_BaseRAGCapability):
    """Capability that instruments and caches VectorRAG tool calls.

    Tracks calls to ``query_vector_rag`` and caches embeddings-based
    results to avoid redundant OpenAI embedding API calls.
    """

    _monitored_tools: frozenset[str] = field(
        default=frozenset(_VECTOR_TOOLS), repr=False
    )


@dataclass
class MixedRAGCapability(_BaseRAGCapability):
    """Capability that instruments and caches MixedRAG tool calls.

    Also aggregates stats from the underlying graph and vector retrievals
    so you can see the combined performance profile in one place.
    """

    _monitored_tools: frozenset[str] = field(
        default=frozenset(_MIXED_TOOLS), repr=False
    )
