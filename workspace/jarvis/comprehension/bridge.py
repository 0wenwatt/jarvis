"""Module 1: Core Codebase Ingestion Bridge.

Technology stack
────────────────
- ``codegen`` (Tree-sitter wrapper) — AST parsing of Python source files
- ``cognee`` — vector + relational graph persistence in PostgreSQL
- PostgreSQL (pgvector + AGE via Cognee)

Feature flag
────────────
Set the environment variable ``USE_CODEGEN_AST=true`` (case-insensitive) to
enable the AST bridge.  When the flag is absent or falsy the bridge is disabled
and :func:`ingest_codebase` / :func:`ingest_local_path` raise
``ASTBridgeDisabledError``.

Public API
──────────
    is_ast_bridge_enabled() -> bool
    ingest_codebase(deps, codebase_path) -> IngestCodebaseResult
    ingest_local_path(path, cognee_dataset) -> IngestCodebaseResult
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


def is_ast_bridge_enabled() -> bool:
    """Return ``True`` when ``USE_CODEGEN_AST`` env var is truthy.

    Accepted truthy values (case-insensitive): ``1``, ``true``, ``yes``, ``on``.
    Everything else (including missing) is treated as disabled.
    """
    val = os.environ.get("USE_CODEGEN_AST", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


class ASTBridgeDisabledError(RuntimeError):
    """Raised when AST bridge methods are called while the flag is off."""

    def __init__(self) -> None:
        super().__init__(
            "AST bridge is disabled.  Set USE_CODEGEN_AST=true to enable it."
        )


# ---------------------------------------------------------------------------
# Pydantic models for AST graph payloads
# ---------------------------------------------------------------------------


class ASTNodeKind(str, Enum):
    """Category of an AST symbol node."""

    FUNCTION = "Function"
    CLASS = "Class"
    IMPORT = "Import"
    PARAMETER = "Parameter"
    VARIABLE = "Variable"
    MODULE = "Module"
    OTHER = "Other"


class ASTEdgeKind(str, Enum):
    """Category of a directed edge between AST nodes."""

    CALLS = "CALLS"
    DEPENDS_ON = "DEPENDS_ON"
    INHERITS = "INHERITS"
    IMPORTS = "IMPORTS"
    DEFINES = "DEFINES"
    USES = "USES"


class ASTNode(BaseModel):
    """A vertex in the AST-derived code property graph."""

    name: str = Field(..., description="Canonical symbol name (e.g. 'MyClass.method')")
    kind: ASTNodeKind = ASTNodeKind.OTHER
    file_path: str = Field(..., description="Relative path to the source file")
    line_start: int | None = None
    line_end: int | None = None
    docstring: str | None = None
    source_snippet: str | None = Field(
        default=None,
        description="Short source excerpt (first 300 chars)",
    )
    properties: dict[str, Any] = Field(default_factory=dict)


class ASTEdge(BaseModel):
    """A directed edge in the AST code property graph."""

    source: str = Field(..., description="Source symbol name")
    target: str = Field(..., description="Target symbol name")
    kind: ASTEdgeKind = ASTEdgeKind.DEPENDS_ON
    properties: dict[str, Any] = Field(default_factory=dict)


class ASTGraph(BaseModel):
    """Full extracted symbol graph for one codebase / repository."""

    nodes: list[ASTNode] = Field(default_factory=list)
    edges: list[ASTEdge] = Field(default_factory=list)
    codebase_root: str = ""
    extracted_at: float = Field(default_factory=time.time)

    @property
    def node_names(self) -> set[str]:
        return {n.name for n in self.nodes}


class IngestCodebaseResult(BaseModel):
    """Summary of one AST codebase ingestion run."""

    codebase_root: str
    nodes_extracted: int
    edges_extracted: int
    cognee_dataset: str
    elapsed_seconds: float
    ast_enabled: bool
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Deps model for pydantic-ai tool injection
# ---------------------------------------------------------------------------


@dataclass
class CodebaseBridgeDeps:
    """Runtime dependencies passed to AST bridge tools via RunContext."""

    codebase_root: str = ""
    cognee_dataset: str = "jarvis_ast"
    ast_enabled: bool = field(default_factory=is_ast_bridge_enabled)


# ---------------------------------------------------------------------------
# Internal — codegen (Tree-sitter) parsing helpers
# ---------------------------------------------------------------------------


def _try_import_codegen() -> Any:
    """Attempt to import the ``codegen`` package.

    Returns the module on success, ``None`` if not installed.
    """
    try:
        import codegen  # type: ignore[import-untyped]

        return codegen
    except ImportError:
        logger.warning(
            "codegen package not installed — AST parsing unavailable. "
            "Install with: pip install codegen"
        )
        return None


def _extract_graph_via_codegen(codebase_path: str) -> ASTGraph:
    """Parse *codebase_path* with ``codegen`` and return an :class:`ASTGraph`.

    Falls back to a lightweight manual scan when ``codegen`` is absent.
    """
    cg = _try_import_codegen()
    nodes: list[ASTNode] = []
    edges: list[ASTEdge] = []
    warnings: list[str] = []

    if cg is not None:
        # ----------------------------------------------------------------
        # codegen-powered path
        # ----------------------------------------------------------------
        try:
            codebase = cg.Codebase(codebase_path)

            for func in codebase.functions:
                node = ASTNode(
                    name=_qualified_name(func),
                    kind=ASTNodeKind.FUNCTION,
                    file_path=_rel_path(func, codebase_path),
                    line_start=getattr(func, "start_line", None),
                    line_end=getattr(func, "end_line", None),
                    docstring=getattr(func, "docstring", None),
                    source_snippet=_snippet(func),
                )
                nodes.append(node)

                # CALLS edges from function call sites
                for called in getattr(func, "calls", []):
                    edges.append(
                        ASTEdge(
                            source=node.name,
                            target=_qualified_name(called),
                            kind=ASTEdgeKind.CALLS,
                        )
                    )

            for cls in codebase.classes:
                cls_node = ASTNode(
                    name=_qualified_name(cls),
                    kind=ASTNodeKind.CLASS,
                    file_path=_rel_path(cls, codebase_path),
                    line_start=getattr(cls, "start_line", None),
                    line_end=getattr(cls, "end_line", None),
                    docstring=getattr(cls, "docstring", None),
                    source_snippet=_snippet(cls),
                )
                nodes.append(cls_node)

                # INHERITS edges
                for base in getattr(cls, "bases", []):
                    edges.append(
                        ASTEdge(
                            source=cls_node.name,
                            target=str(base),
                            kind=ASTEdgeKind.INHERITS,
                        )
                    )

            for imp in codebase.imports:
                imp_node = ASTNode(
                    name=_qualified_name(imp),
                    kind=ASTNodeKind.IMPORT,
                    file_path=_rel_path(imp, codebase_path),
                )
                nodes.append(imp_node)

        except Exception as exc:
            warnings.append(f"codegen parsing error: {exc}")
            logger.warning("codegen failed — falling back to manual scan: %s", exc)
            nodes, edges = _manual_scan(codebase_path, warnings)
    else:
        # ----------------------------------------------------------------
        # Manual fallback (no codegen)
        # ----------------------------------------------------------------
        nodes, edges = _manual_scan(codebase_path, warnings)

    graph = ASTGraph(nodes=nodes, edges=edges, codebase_root=codebase_path)
    if warnings:
        logger.warning("AST extraction warnings: %s", warnings)
    return graph


def _qualified_name(obj: Any) -> str:
    """Return a dotted-qualified name from a codegen symbol object."""
    if hasattr(obj, "full_name"):
        return str(obj.full_name)
    if hasattr(obj, "name"):
        return str(obj.name)
    return str(obj)


def _rel_path(obj: Any, root: str) -> str:
    fp = getattr(obj, "file_path", None) or getattr(obj, "filepath", None) or ""
    try:
        return str(Path(fp).relative_to(root))
    except ValueError:
        return fp


def _snippet(obj: Any) -> str | None:
    src = getattr(obj, "source", None)
    if src:
        return str(src)[:300]
    return None


def _manual_scan(root: str, warnings: list[str]) -> tuple[list[ASTNode], list[ASTEdge]]:
    """Lightweight Python-only scan using the ``ast`` stdlib module."""
    import ast as _ast

    nodes: list[ASTNode] = []
    edges: list[ASTEdge] = []
    root_path = Path(root)

    for py_file in root_path.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = _ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            warnings.append(f"Syntax error in {py_file}: {exc}")
            continue
        except Exception as exc:
            warnings.append(f"Could not read {py_file}: {exc}")
            continue

        rel = str(py_file.relative_to(root_path))

        for item in _ast.walk(tree):
            if isinstance(item, _ast.FunctionDef | _ast.AsyncFunctionDef):
                nodes.append(
                    ASTNode(
                        name=item.name,
                        kind=ASTNodeKind.FUNCTION,
                        file_path=rel,
                        line_start=item.lineno,
                        line_end=getattr(item, "end_lineno", None),
                    )
                )
            elif isinstance(item, _ast.ClassDef):
                cls_node = ASTNode(
                    name=item.name,
                    kind=ASTNodeKind.CLASS,
                    file_path=rel,
                    line_start=item.lineno,
                    line_end=getattr(item, "end_lineno", None),
                )
                nodes.append(cls_node)
                for base in item.bases:
                    if isinstance(base, _ast.Name):
                        edges.append(
                            ASTEdge(
                                source=item.name,
                                target=base.id,
                                kind=ASTEdgeKind.INHERITS,
                            )
                        )
            elif isinstance(item, _ast.Import | _ast.ImportFrom):
                for alias in getattr(item, "names", []):
                    nodes.append(
                        ASTNode(
                            name=alias.name,
                            kind=ASTNodeKind.IMPORT,
                            file_path=rel,
                            line_start=item.lineno,
                        )
                    )

    return nodes, edges


# ---------------------------------------------------------------------------
# Internal — cognee persistence helpers
# ---------------------------------------------------------------------------


def _try_import_cognee() -> Any:
    """Attempt to import the ``cognee`` package.

    Returns the module on success, ``None`` if not installed.
    """
    try:
        import cognee  # type: ignore[import-untyped]

        return cognee
    except ImportError:
        logger.warning(
            "cognee package not installed — graph persistence will be skipped. "
            "Install with: pip install cognee"
        )
        return None


async def _persist_via_cognee(graph: ASTGraph, dataset: str) -> list[str]:
    """Persist *graph* nodes/edges to PostgreSQL via ``cognee``.

    Returns a list of warning strings (empty on full success).
    """
    warnings: list[str] = []
    cognee = _try_import_cognee()
    if cognee is None:
        warnings.append("cognee not installed — skipping persistence")
        return warnings

    # Serialise nodes and edges to a JSON-serialisable dict
    payload = graph.model_dump()

    try:
        await cognee.add(payload, dataset_name=dataset)
        await cognee.cognify()
        logger.info(
            "cognee: persisted %d nodes and %d edges to dataset '%s'",
            len(graph.nodes),
            len(graph.edges),
            dataset,
        )
    except Exception as exc:
        warnings.append(f"cognee persistence failed: {exc}")
        logger.error("cognee persistence error: %s", exc)

    return warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ingest_codebase(
    deps: CodebaseBridgeDeps,
    codebase_path: str | None = None,
) -> IngestCodebaseResult:
    """Parse *codebase_path* (or ``deps.codebase_root``) and persist to PostgreSQL.

    Raises :class:`ASTBridgeDisabledError` when ``USE_CODEGEN_AST`` is off.
    """
    if not deps.ast_enabled:
        raise ASTBridgeDisabledError()

    root = codebase_path or deps.codebase_root
    if not root:
        raise ValueError("codebase_path must be provided or set in deps.codebase_root")

    t0 = time.monotonic()
    graph = _extract_graph_via_codegen(root)
    warnings = await _persist_via_cognee(graph, deps.cognee_dataset)

    return IngestCodebaseResult(
        codebase_root=root,
        nodes_extracted=len(graph.nodes),
        edges_extracted=len(graph.edges),
        cognee_dataset=deps.cognee_dataset,
        elapsed_seconds=round(time.monotonic() - t0, 3),
        ast_enabled=True,
        warnings=warnings,
    )


async def ingest_local_path(
    path: str,
    cognee_dataset: str = "jarvis_ast",
) -> IngestCodebaseResult:
    """Convenience wrapper — creates :class:`CodebaseBridgeDeps` automatically.

    Respects the ``USE_CODEGEN_AST`` feature flag.
    """
    deps = CodebaseBridgeDeps(codebase_root=path, cognee_dataset=cognee_dataset)
    return await ingest_codebase(deps)
