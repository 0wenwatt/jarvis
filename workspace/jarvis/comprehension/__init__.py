"""Codebase Comprehension package — AST/CPG ingestion bridge."""

from .bridge import (
    ASTEdge,
    ASTGraph,
    ASTNode,
    CodebaseBridgeDeps,
    IngestCodebaseResult,
    is_ast_bridge_enabled,
    ingest_codebase,
    ingest_local_path,
)

__all__ = [
    "is_ast_bridge_enabled",
    "ingest_codebase",
    "ingest_local_path",
    "ASTNode",
    "ASTEdge",
    "ASTGraph",
    "CodebaseBridgeDeps",
    "IngestCodebaseResult",
]
