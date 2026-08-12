"""Demo package — unified demo agent & LangGraph node handler."""

from .demo_agent import (
    AgentCapabilitiesConfig,
    ResearchCodingDeps,
    demo_agent,
    langgraph_node,
)

__all__ = [
    "demo_agent",
    "langgraph_node",
    "AgentCapabilitiesConfig",
    "ResearchCodingDeps",
]
