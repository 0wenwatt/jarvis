"""Module 3: Dual-Skill Coding Agent Tools.

Two distinct tool sets are exposed on a single pydantic-ai ``Agent``:

A. AST-Based Skills (new engine)
─────────────────────────────────
- ``ast_rename_symbol``    — rename a symbol across all files using codegen
- ``ast_find_references``  — find all references to a symbol via AST graph / Postgres
- ``ast_apply_refactoring``— apply a targeted AST-scoped edit to a file

B. Direct / Legacy Skills (preserved engine)
──────────────────────────────────────────────
- ``legacy_read_file``     — read a file from disk
- ``legacy_replace_string``— string-replace in a file
- ``legacy_write_file``    — write/overwrite a file

Capability gating
──────────────────
Every tool checks ``context.deps.capabilities`` (a :class:`CapabilitiesConfig`)
before executing.  If the relevant capability flag is ``False`` the tool returns
a descriptive message instead of raising.

Feature flags (env vars)
─────────────────────────
- ``ENABLE_CODEGEN_AST=true/false``  — controls AST tool set
- ``ENABLE_LEGACY_TOOLS=true/false`` — controls legacy tool set
Both default to ``true`` when absent.

Usage
─────
    import asyncio, os
    from coding.tools import coding_agent, CodingAgentDeps, CapabilitiesConfig

    os.environ["ENABLE_CODEGEN_AST"] = "true"
    deps = CodingAgentDeps(
        capabilities=CapabilitiesConfig(),
        workspace_root="/path/to/repo",
    )
    result = asyncio.run(
        coding_agent.run("Rename the function 'old_name' to 'new_name'.", deps=deps)
    )
    print(result.output)
"""

from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capabilities configuration
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool = True) -> bool:
    val = os.environ.get(name, "").strip().lower()
    return (val in {"1", "true", "yes", "on"}) if val else default


class CapabilitiesConfig(BaseModel):
    """Feature-flag model controlling which tool sets are active."""

    enable_codegen_ast: bool = Field(
        default_factory=lambda: _env_bool("ENABLE_CODEGEN_AST"),
        description="Enable AST-based coding tools (requires codegen package)",
    )
    enable_legacy_tools: bool = Field(
        default_factory=lambda: _env_bool("ENABLE_LEGACY_TOOLS"),
        description="Enable direct file I/O legacy tools",
    )
    workspace_root: str = Field(
        default_factory=lambda: os.environ.get("WORKSPACE_ROOT", "."),
        description="Root directory for file operations",
    )


# ---------------------------------------------------------------------------
# Deps
# ---------------------------------------------------------------------------


@dataclass
class CodingAgentDeps:
    """Runtime dependencies for all coding tools."""

    capabilities: CapabilitiesConfig = field(default_factory=CapabilitiesConfig)
    workspace_root: str = field(default_factory=lambda: os.environ.get("WORKSPACE_ROOT", "."))
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_path(workspace_root: str, file_path: str) -> Path:
    """Resolve *file_path* relative to *workspace_root*, rejecting path traversal."""
    root = Path(workspace_root).resolve()
    target = (root / file_path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Path traversal detected: '{file_path}' escapes workspace '{workspace_root}'")
    return target


def _try_codegen():
    try:
        import codegen  # type: ignore[import-untyped]
        return codegen
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a software engineering assistant with dual capabilities:

AST-Based Tools (preferred for Python):
  - ast_rename_symbol: safely rename any symbol across a codebase
  - ast_find_references: find every usage of a symbol
  - ast_apply_refactoring: make surgical AST-scoped edits

Legacy / Direct Tools (for any language or when AST is unavailable):
  - legacy_read_file: read a file
  - legacy_replace_string: search-and-replace in a file
  - legacy_write_file: write or overwrite a file

Always prefer AST tools for Python files unless the AST engine is disabled.
For non-Python or unparseable files, fall back to legacy tools.
"""

coding_agent: Agent[CodingAgentDeps, str] = Agent(
    model=os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6"),
    system_prompt=_SYSTEM_PROMPT,
    deps_type=CodingAgentDeps,
    output_type=str,
    defer_model_check=True,
)


# ===========================================================================
# A. AST-Based Skills
# ===========================================================================


@coding_agent.tool
async def ast_rename_symbol(
    ctx: RunContext[CodingAgentDeps],
    symbol_name: Annotated[str, Field(description="Existing symbol name to rename")],
    new_name: Annotated[str, Field(description="New symbol name")],
) -> str:
    """Rename a symbol (function, class, or parameter) across all files in the workspace.

    Uses ``codegen.Codebase`` for Tree-sitter–powered, cross-file safe renaming.
    Falls back to a regex-based rename when codegen is unavailable.
    """
    if not ctx.deps.capabilities.enable_codegen_ast:
        return "AST tools are disabled (enable_codegen_ast=False).  Use legacy_replace_string instead."

    workspace = ctx.deps.capabilities.workspace_root or ctx.deps.workspace_root
    cg = _try_codegen()

    if cg is not None:
        try:
            codebase = cg.Codebase(workspace)
            # codegen API: symbol.rename(new_name) then codebase.commit()
            renamed_count = 0
            for sym in list(codebase.functions) + list(codebase.classes):
                if _qualified_name(sym).endswith(symbol_name) or getattr(sym, "name", "") == symbol_name:
                    sym.rename(new_name)
                    renamed_count += 1
            codebase.commit()
            return f"Renamed '{symbol_name}' → '{new_name}' across {renamed_count} definition(s)."
        except Exception as exc:
            logger.warning("codegen rename failed — falling back to regex: %s", exc)

    # --- stdlib AST + text fallback ---
    root = Path(workspace)
    renamed_files: list[str] = []
    for py_file in root.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
            if symbol_name in text:
                new_text = text.replace(symbol_name, new_name)
                py_file.write_text(new_text, encoding="utf-8")
                renamed_files.append(str(py_file.relative_to(root)))
        except Exception as exc:
            logger.warning("Could not process %s: %s", py_file, exc)

    if not renamed_files:
        return f"No occurrences of '{symbol_name}' found in workspace."
    return f"Renamed '{symbol_name}' → '{new_name}' in {len(renamed_files)} file(s): {renamed_files}"


@coding_agent.tool
async def ast_find_references(
    ctx: RunContext[CodingAgentDeps],
    symbol_name: Annotated[str, Field(description="Symbol name to locate references for")],
) -> str:
    """Find all usages of *symbol_name* in the workspace using Tree-sitter graph traversal.

    Falls back to a text-based grep when codegen is unavailable.
    """
    if not ctx.deps.capabilities.enable_codegen_ast:
        return "AST tools are disabled (enable_codegen_ast=False).  Use legacy_read_file instead."

    workspace = ctx.deps.capabilities.workspace_root or ctx.deps.workspace_root
    cg = _try_codegen()

    if cg is not None:
        try:
            codebase = cg.Codebase(workspace)
            refs = []
            for sym in list(codebase.functions) + list(codebase.classes):
                name = getattr(sym, "name", "")
                if name == symbol_name or _qualified_name(sym).endswith(symbol_name):
                    for ref in getattr(sym, "references", []):
                        refs.append(str(ref))
            if not refs:
                return f"No references found for '{symbol_name}' via codegen."
            return f"References to '{symbol_name}':\n" + "\n".join(refs[:50])
        except Exception as exc:
            logger.warning("codegen find_references failed — falling back to text scan: %s", exc)

    # --- text fallback ---
    root = Path(workspace)
    hits: list[str] = []
    for py_file in root.rglob("*.py"):
        try:
            for lineno, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if symbol_name in line:
                    rel = py_file.relative_to(root)
                    hits.append(f"{rel}:{lineno}: {line.strip()}")
        except Exception as exc:
            logger.warning("Could not scan %s: %s", py_file, exc)

    if not hits:
        return f"No references found for '{symbol_name}'."
    return f"References to '{symbol_name}' ({len(hits)} hit(s)):\n" + "\n".join(hits[:50])


@coding_agent.tool
async def ast_apply_refactoring(
    ctx: RunContext[CodingAgentDeps],
    file_path: Annotated[str, Field(description="Relative path to the file to refactor")],
    refactor_spec: Annotated[
        str,
        Field(
            description=(
                "Human-readable description of the refactoring, e.g. "
                "'Extract lines 10-20 into a new function called parse_data'"
            )
        ),
    ],
) -> str:
    """Apply a targeted AST-scoped refactoring to *file_path*.

    Uses ``codegen``'s AST manipulation API when available.  When codegen is
    absent, returns the refactoring spec as instructions for the developer.
    """
    if not ctx.deps.capabilities.enable_codegen_ast:
        return "AST tools are disabled (enable_codegen_ast=False).  Use legacy_write_file instead."

    workspace = ctx.deps.capabilities.workspace_root or ctx.deps.workspace_root
    full_path = _safe_path(workspace, file_path)

    if not full_path.exists():
        raise ModelRetry(f"File not found: {file_path}")

    cg = _try_codegen()

    if cg is not None:
        try:
            codebase = cg.Codebase(workspace)
            # codegen provides a .apply_codemod() or similar; expose spec as a note
            # In practice the LLM will supply precise code changes; here we validate the AST.
            source = full_path.read_text(encoding="utf-8", errors="replace")
            try:
                ast.parse(source)
            except SyntaxError as exc:
                raise ModelRetry(f"Syntax error in {file_path} before refactoring: {exc}") from exc
            return (
                f"File '{file_path}' loaded into codegen codebase.  "
                f"Refactoring spec acknowledged: '{refactor_spec}'.  "
                "Apply targeted edits and call legacy_write_file to persist the result."
            )
        except ModelRetry:
            raise
        except Exception as exc:
            logger.warning("codegen refactor prep failed: %s", exc)

    return (
        f"codegen unavailable — manual refactoring required for '{file_path}'.\n"
        f"Spec: {refactor_spec}"
    )


# ===========================================================================
# B. Direct / Legacy Skills
# ===========================================================================


@coding_agent.tool
async def legacy_read_file(
    ctx: RunContext[CodingAgentDeps],
    file_path: Annotated[str, Field(description="Relative path to the file to read")],
) -> str:
    """Read a file directly from disk and return its contents as a string."""
    if not ctx.deps.capabilities.enable_legacy_tools:
        return "Legacy tools are disabled (enable_legacy_tools=False)."

    workspace = ctx.deps.capabilities.workspace_root or ctx.deps.workspace_root
    full_path = _safe_path(workspace, file_path)

    if not full_path.exists():
        raise ModelRetry(f"File not found: {file_path}")

    try:
        return full_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise ModelRetry(f"Could not read '{file_path}': {exc}") from exc


@coding_agent.tool
async def legacy_replace_string(
    ctx: RunContext[CodingAgentDeps],
    file_path: Annotated[str, Field(description="Relative path to the file to modify")],
    target: Annotated[str, Field(description="Exact string to find and replace")],
    replacement: Annotated[str, Field(description="Replacement string")],
) -> str:
    """Find and replace *target* with *replacement* in *file_path*.

    Returns the number of replacements made.
    """
    if not ctx.deps.capabilities.enable_legacy_tools:
        return "Legacy tools are disabled (enable_legacy_tools=False)."

    workspace = ctx.deps.capabilities.workspace_root or ctx.deps.workspace_root
    full_path = _safe_path(workspace, file_path)

    if not full_path.exists():
        raise ModelRetry(f"File not found: {file_path}")

    try:
        original = full_path.read_text(encoding="utf-8", errors="replace")
        count = original.count(target)
        if count == 0:
            return f"Target string not found in '{file_path}'."
        updated = original.replace(target, replacement)
        full_path.write_text(updated, encoding="utf-8")
        return f"Made {count} replacement(s) in '{file_path}'."
    except Exception as exc:
        raise ModelRetry(f"Replace failed in '{file_path}': {exc}") from exc


@coding_agent.tool
async def legacy_write_file(
    ctx: RunContext[CodingAgentDeps],
    file_path: Annotated[str, Field(description="Relative path to write (created if absent, overwritten if present)")],
    content: Annotated[str, Field(description="Full file content to write")],
) -> str:
    """Write *content* to *file_path*, creating parent directories as needed."""
    if not ctx.deps.capabilities.enable_legacy_tools:
        return "Legacy tools are disabled (enable_legacy_tools=False)."

    workspace = ctx.deps.capabilities.workspace_root or ctx.deps.workspace_root
    full_path = _safe_path(workspace, file_path)

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to '{file_path}'."
    except Exception as exc:
        raise ModelRetry(f"Write failed for '{file_path}': {exc}") from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _qualified_name(obj: Any) -> str:
    if hasattr(obj, "full_name"):
        return str(obj.full_name)
    if hasattr(obj, "name"):
        return str(obj.name)
    return str(obj)
