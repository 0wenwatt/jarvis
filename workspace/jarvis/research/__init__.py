"""Research package — multi-source research & web ingestion pipeline."""

from .pipeline import (
    ResearchAgent,
    ResearchAgentDeps,
    ResearchResult,
    research_agent,
)

__all__ = [
    "research_agent",
    "ResearchAgent",
    "ResearchAgentDeps",
    "ResearchResult",
]
