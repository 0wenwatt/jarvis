"""Coding agent package — dual-skill AST + legacy tools."""

from .tools import (
    CapabilitiesConfig,
    CodingAgentDeps,
    coding_agent,
)

__all__ = [
    "coding_agent",
    "CapabilitiesConfig",
    "CodingAgentDeps",
]
