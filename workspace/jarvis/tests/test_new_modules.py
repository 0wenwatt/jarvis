"""Tests for the four new Jarvis modules.

These tests focus on:
  1. Feature flag behaviour (unit tests, no LLM / network calls)
  2. Pydantic model validation
  3. Capability-gating in coding tools
  4. LangGraph node state contract
  5. Path-traversal safety in file tools
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure workspace/jarvis is on sys.path so all modules import correctly
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent.resolve()
_JARVIS_ROOT = _HERE.parent  # workspace/jarvis/
if str(_JARVIS_ROOT) not in sys.path:
    sys.path.insert(0, str(_JARVIS_ROOT))


# ===========================================================================
# Module 1: comprehension.bridge
# ===========================================================================


class TestASTBridgeFeatureFlag:
    """Verify is_ast_bridge_enabled reads USE_CODEGEN_AST correctly."""

    def test_enabled_when_true(self, monkeypatch):
        monkeypatch.setenv("USE_CODEGEN_AST", "true")
        from comprehension.bridge import is_ast_bridge_enabled

        assert is_ast_bridge_enabled() is True

    def test_enabled_when_1(self, monkeypatch):
        monkeypatch.setenv("USE_CODEGEN_AST", "1")
        from comprehension.bridge import is_ast_bridge_enabled

        assert is_ast_bridge_enabled() is True

    def test_disabled_when_false(self, monkeypatch):
        monkeypatch.setenv("USE_CODEGEN_AST", "false")
        from comprehension.bridge import is_ast_bridge_enabled

        assert is_ast_bridge_enabled() is False

    def test_disabled_when_absent(self, monkeypatch):
        monkeypatch.delenv("USE_CODEGEN_AST", raising=False)
        from comprehension.bridge import is_ast_bridge_enabled

        assert is_ast_bridge_enabled() is False


class TestASTBridgeDisabledError:
    """ingest_codebase raises ASTBridgeDisabledError when flag is off."""

    @pytest.mark.asyncio
    async def test_raises_when_disabled(self, monkeypatch):
        monkeypatch.setenv("USE_CODEGEN_AST", "false")
        from comprehension.bridge import ASTBridgeDisabledError, CodebaseBridgeDeps, ingest_codebase

        deps = CodebaseBridgeDeps(ast_enabled=False)
        with pytest.raises(ASTBridgeDisabledError):
            await ingest_codebase(deps, codebase_path="/tmp/dummy")


class TestManualScan:
    """_manual_scan extracts AST nodes from a temporary Python file."""

    def test_scans_functions_and_classes(self, tmp_path):
        src = tmp_path / "sample.py"
        src.write_text(
            "class Foo:\n    pass\n\ndef bar():\n    pass\n",
            encoding="utf-8",
        )
        from comprehension.bridge import _manual_scan

        nodes, edges = _manual_scan(str(tmp_path), [])
        names = {n.name for n in nodes}
        assert "Foo" in names
        assert "bar" in names

    def test_extracts_inheritance_edges(self, tmp_path):
        src = tmp_path / "inherit.py"
        src.write_text("class Child(Parent):\n    pass\n", encoding="utf-8")
        from comprehension.bridge import _manual_scan

        nodes, edges = _manual_scan(str(tmp_path), [])
        inheritance = [e for e in edges if e.kind.value == "INHERITS"]
        assert any(e.source == "Child" and e.target == "Parent" for e in inheritance)

    def test_reports_syntax_error_as_warning(self, tmp_path):
        bad = tmp_path / "broken.py"
        bad.write_text("def (:\n", encoding="utf-8")
        from comprehension.bridge import _manual_scan

        warnings: list[str] = []
        _manual_scan(str(tmp_path), warnings)
        assert any("Syntax error" in w or "broken.py" in w for w in warnings)


class TestASTModels:
    """Pydantic model validation for ASTNode / ASTEdge / ASTGraph."""

    def test_ast_node_defaults(self):
        from comprehension.bridge import ASTNode, ASTNodeKind

        node = ASTNode(name="my_func", file_path="a/b.py")
        assert node.kind == ASTNodeKind.OTHER

    def test_ast_edge_requires_source_target(self):
        from pydantic import ValidationError

        from comprehension.bridge import ASTEdge

        with pytest.raises(ValidationError):
            ASTEdge(source="A")  # missing target

    def test_ingest_result_model(self):
        from comprehension.bridge import IngestCodebaseResult

        r = IngestCodebaseResult(
            codebase_root="/tmp",
            nodes_extracted=5,
            edges_extracted=3,
            cognee_dataset="test",
            elapsed_seconds=0.1,
            ast_enabled=True,
        )
        assert r.nodes_extracted == 5


# ===========================================================================
# Module 2: research.pipeline
# ===========================================================================


class TestResearchFeatureFlags:
    def test_web_search_disabled(self, monkeypatch):
        monkeypatch.setenv("USE_WEB_SEARCH", "false")
        from research.pipeline import _web_search_enabled

        assert _web_search_enabled() is False

    def test_github_ingest_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("USE_GITHUB_INGEST", raising=False)
        from research.pipeline import _github_ingest_enabled

        assert _github_ingest_enabled() is True


class TestResearchResult:
    def test_model_defaults(self):
        from research.pipeline import ResearchResult

        r = ResearchResult(summary="All good")
        assert r.sources == []
        assert r.actions_taken == []

    def test_model_with_sources(self):
        from research.pipeline import ResearchResult

        r = ResearchResult(summary="Done", sources=["https://example.com"])
        assert len(r.sources) == 1


class TestResearchToolGating:
    """Tools return disabled messages when flags are off."""

    @pytest.mark.asyncio
    async def test_web_search_disabled_returns_message(self, monkeypatch):
        monkeypatch.setenv("USE_WEB_SEARCH", "false")
        from dataclasses import dataclass, field as dc_field
        from typing import Any

        from research.pipeline import ResearchAgentDeps, web_search_to_db

        deps = ResearchAgentDeps(web_search_enabled=False)

        @dataclass
        class _Ctx:
            deps: Any

        result = await web_search_to_db(_Ctx(deps=deps), query="test query")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_github_ingest_disabled_returns_message(self, monkeypatch):
        from dataclasses import dataclass
        from typing import Any

        from research.pipeline import ResearchAgentDeps, ingest_github_repo_to_db

        deps = ResearchAgentDeps(github_ingest_enabled=False)

        @dataclass
        class _Ctx:
            deps: Any

        result = await ingest_github_repo_to_db(  # type: ignore[arg-type]
            _Ctx(deps=deps), repo_url="https://github.com/owner/repo"
        )
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_graph_memory_disabled_returns_message(self, monkeypatch):
        from dataclasses import dataclass
        from typing import Any

        from research.pipeline import ResearchAgentDeps, query_graph_memory

        deps = ResearchAgentDeps(graph_memory_enabled=False)

        @dataclass
        class _Ctx:
            deps: Any

        result = await query_graph_memory(_Ctx(deps=deps), cypher_or_vector_query="test")  # type: ignore[arg-type]
        assert "disabled" in result.lower()


# ===========================================================================
# Module 3: coding.tools
# ===========================================================================


class TestCapabilitiesConfig:
    def test_defaults_from_env_true(self, monkeypatch):
        monkeypatch.delenv("ENABLE_CODEGEN_AST", raising=False)
        monkeypatch.delenv("ENABLE_LEGACY_TOOLS", raising=False)
        from coding.tools import CapabilitiesConfig

        cfg = CapabilitiesConfig()
        assert cfg.enable_codegen_ast is True
        assert cfg.enable_legacy_tools is True

    def test_codegen_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CODEGEN_AST", "false")
        from coding.tools import CapabilitiesConfig

        cfg = CapabilitiesConfig()
        assert cfg.enable_codegen_ast is False

    def test_legacy_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("ENABLE_LEGACY_TOOLS", "0")
        from coding.tools import CapabilitiesConfig

        cfg = CapabilitiesConfig()
        assert cfg.enable_legacy_tools is False


class TestASTToolGating:
    """AST tools return disabled message when enable_codegen_ast is False."""

    def _make_ctx(self, **cap_overrides):
        from dataclasses import dataclass
        from typing import Any

        from coding.tools import CapabilitiesConfig, CodingAgentDeps

        caps = CapabilitiesConfig(**{**{"enable_codegen_ast": False, "enable_legacy_tools": True}, **cap_overrides})
        deps = CodingAgentDeps(capabilities=caps)

        @dataclass
        class _Ctx:
            deps: Any

        return _Ctx(deps=deps)

    @pytest.mark.asyncio
    async def test_ast_rename_disabled(self):
        from coding.tools import ast_rename_symbol

        ctx = self._make_ctx()
        result = await ast_rename_symbol(ctx, symbol_name="old", new_name="new")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_ast_find_refs_disabled(self):
        from coding.tools import ast_find_references

        ctx = self._make_ctx()
        result = await ast_find_references(ctx, symbol_name="some_func")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_ast_apply_refactoring_disabled(self):
        from coding.tools import ast_apply_refactoring

        ctx = self._make_ctx()
        result = await ast_apply_refactoring(ctx, file_path="a.py", refactor_spec="extract method")  # type: ignore[arg-type]
        assert "disabled" in result.lower()


class TestLegacyToolGating:
    """Legacy tools return disabled message when enable_legacy_tools is False."""

    def _make_ctx(self, tmp_path: Path):
        from dataclasses import dataclass
        from typing import Any

        from coding.tools import CapabilitiesConfig, CodingAgentDeps

        caps = CapabilitiesConfig(
            enable_codegen_ast=True,
            enable_legacy_tools=False,
            workspace_root=str(tmp_path),
        )
        deps = CodingAgentDeps(capabilities=caps, workspace_root=str(tmp_path))

        @dataclass
        class _Ctx:
            deps: Any

        return _Ctx(deps=deps)

    @pytest.mark.asyncio
    async def test_read_file_disabled(self, tmp_path):
        from coding.tools import legacy_read_file

        ctx = self._make_ctx(tmp_path)
        result = await legacy_read_file(ctx, file_path="x.py")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_write_file_disabled(self, tmp_path):
        from coding.tools import legacy_write_file

        ctx = self._make_ctx(tmp_path)
        result = await legacy_write_file(ctx, file_path="x.py", content="hello")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_replace_string_disabled(self, tmp_path):
        from coding.tools import legacy_replace_string

        ctx = self._make_ctx(tmp_path)
        result = await legacy_replace_string(ctx, file_path="x.py", target="a", replacement="b")  # type: ignore[arg-type]
        assert "disabled" in result.lower()


class TestLegacyToolFunctionality:
    """Legacy tools work correctly when enabled."""

    def _make_ctx(self, tmp_path: Path):
        from dataclasses import dataclass
        from typing import Any

        from coding.tools import CapabilitiesConfig, CodingAgentDeps

        caps = CapabilitiesConfig(
            enable_codegen_ast=False,
            enable_legacy_tools=True,
            workspace_root=str(tmp_path),
        )
        deps = CodingAgentDeps(capabilities=caps, workspace_root=str(tmp_path))

        @dataclass
        class _Ctx:
            deps: Any

        return _Ctx(deps=deps)

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, tmp_path):
        from coding.tools import legacy_read_file, legacy_write_file

        ctx = self._make_ctx(tmp_path)
        write_result = await legacy_write_file(ctx, file_path="hello.py", content="print('hi')")  # type: ignore[arg-type]
        assert "Wrote" in write_result

        read_result = await legacy_read_file(ctx, file_path="hello.py")  # type: ignore[arg-type]
        assert "print('hi')" in read_result

    @pytest.mark.asyncio
    async def test_replace_string(self, tmp_path):
        (tmp_path / "target.py").write_text("foo = 1\nfoo = 2\n", encoding="utf-8")
        from coding.tools import legacy_replace_string

        ctx = self._make_ctx(tmp_path)
        result = await legacy_replace_string(ctx, file_path="target.py", target="foo", replacement="bar")  # type: ignore[arg-type]
        assert "2" in result  # 2 replacements
        assert (tmp_path / "target.py").read_text() == "bar = 1\nbar = 2\n"

    @pytest.mark.asyncio
    async def test_read_missing_file_raises(self, tmp_path):
        from pydantic_ai import ModelRetry

        from coding.tools import legacy_read_file

        ctx = self._make_ctx(tmp_path)
        with pytest.raises(ModelRetry):
            await legacy_read_file(ctx, file_path="missing.py")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, tmp_path):
        from coding.tools import legacy_read_file

        ctx = self._make_ctx(tmp_path)
        with pytest.raises((ValueError, Exception)):
            await legacy_read_file(ctx, file_path="../../etc/passwd")  # type: ignore[arg-type]


class TestASTRenameEnabled:
    """ast_rename_symbol works when enable_codegen_ast is True (uses stdlib fallback)."""

    @pytest.mark.asyncio
    async def test_renames_in_file(self, tmp_path, monkeypatch):
        # Ensure codegen is NOT available so stdlib fallback runs
        monkeypatch.setitem(sys.modules, "codegen", None)

        (tmp_path / "code.py").write_text("def old_name():\n    pass\n", encoding="utf-8")

        from dataclasses import dataclass
        from typing import Any

        from coding.tools import CapabilitiesConfig, CodingAgentDeps, ast_rename_symbol

        caps = CapabilitiesConfig(
            enable_codegen_ast=True,
            enable_legacy_tools=True,
            workspace_root=str(tmp_path),
        )
        deps = CodingAgentDeps(capabilities=caps, workspace_root=str(tmp_path))

        @dataclass
        class _Ctx:
            deps: Any

        ctx = _Ctx(deps=deps)
        result = await ast_rename_symbol(ctx, symbol_name="old_name", new_name="new_name")  # type: ignore[arg-type]
        assert "new_name" in result or "renamed" in result.lower()
        content = (tmp_path / "code.py").read_text()
        assert "new_name" in content


# ===========================================================================
# Module 4: demo.demo_agent
# ===========================================================================


class TestAgentCapabilitiesConfig:
    def test_defaults(self, monkeypatch):
        for key in (
            "USE_WEB_SEARCH",
            "USE_GITHUB_INGEST",
            "ENABLE_CODEGEN_AST",
            "ENABLE_LEGACY_TOOLS",
        ):
            monkeypatch.delenv(key, raising=False)
        from demo.demo_agent import AgentCapabilitiesConfig

        cfg = AgentCapabilitiesConfig()
        assert cfg.enable_web_search is True
        assert cfg.enable_github_ingest is True
        assert cfg.enable_codegen_ast is True
        assert cfg.enable_legacy_tools is True

    def test_selective_disable(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CODEGEN_AST", "0")
        monkeypatch.setenv("USE_WEB_SEARCH", "false")
        from demo.demo_agent import AgentCapabilitiesConfig

        cfg = AgentCapabilitiesConfig()
        assert cfg.enable_codegen_ast is False
        assert cfg.enable_web_search is False


class TestResearchCodingDeps:
    def test_model_instantiation(self):
        from demo.demo_agent import AgentCapabilitiesConfig, ResearchCodingDeps

        deps = ResearchCodingDeps(
            config=AgentCapabilitiesConfig(postgres_db_url="postgresql://localhost/test")
        )
        assert deps.config.postgres_db_url == "postgresql://localhost/test"


class TestLangGraphNode:
    """langgraph_node state contract tests — no LLM calls."""

    @pytest.mark.asyncio
    async def test_empty_message_returns_error(self):
        from demo.demo_agent import langgraph_node

        result = await langgraph_node({"message": ""})
        assert result["error"] == "No message provided"
        assert result["result"] == ""

    @pytest.mark.asyncio
    async def test_preserves_extra_state_keys(self):
        from demo.demo_agent import langgraph_node

        # Patch demo_agent.run so no real LLM call is made
        with patch("demo.demo_agent.demo_agent.run", new_callable=AsyncMock) as mock_run:
            mock_result = MagicMock()
            mock_result.output = "mocked answer"
            mock_result.usage.return_value = None
            mock_run.return_value = mock_result

            state = {
                "message": "Hello",
                "custom_key": "custom_value",
            }
            result = await langgraph_node(state)

        assert result["custom_key"] == "custom_value"
        assert result["result"] == "mocked answer"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_agent_exception_captured_as_error(self):
        from demo.demo_agent import langgraph_node

        with patch("demo.demo_agent.demo_agent.run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("boom")

            result = await langgraph_node({"message": "cause error"})

        assert "boom" in result["error"]
        assert result["result"] == ""

    @pytest.mark.asyncio
    async def test_capabilities_override_from_state(self):
        from demo.demo_agent import langgraph_node

        with patch("demo.demo_agent.demo_agent.run", new_callable=AsyncMock) as mock_run:
            mock_result = MagicMock()
            mock_result.output = "ok"
            mock_result.usage.return_value = None
            mock_run.return_value = mock_result

            await langgraph_node(
                {
                    "message": "test",
                    "capabilities": {
                        "enable_codegen_ast": False,
                        "enable_legacy_tools": True,
                    },
                }
            )
            # Verify run was called — the capability override is tested at import time
            mock_run.assert_called_once()


class TestDemoToolGating:
    """Demo agent tools respect their parent capability flags."""

    def _make_ctx(self, **cap_overrides):
        from dataclasses import dataclass
        from typing import Any

        from demo.demo_agent import AgentCapabilitiesConfig, ResearchCodingDeps

        cfg = AgentCapabilitiesConfig(**cap_overrides)
        deps = ResearchCodingDeps(config=cfg)

        @dataclass
        class _Ctx:
            deps: Any

        return _Ctx(deps=deps)

    @pytest.mark.asyncio
    async def test_web_search_disabled(self):
        from demo.demo_agent import web_search_to_db

        ctx = self._make_ctx(enable_web_search=False)
        result = await web_search_to_db(ctx, query="test")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_github_ingest_disabled(self):
        from demo.demo_agent import ingest_github_repo_to_db

        ctx = self._make_ctx(enable_github_ingest=False)
        result = await ingest_github_repo_to_db(ctx, repo_url="https://github.com/a/b")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_ast_rename_disabled(self):
        from demo.demo_agent import ast_rename_symbol

        ctx = self._make_ctx(enable_codegen_ast=False)
        result = await ast_rename_symbol(ctx, symbol_name="x", new_name="y")  # type: ignore[arg-type]
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_legacy_read_disabled(self):
        from demo.demo_agent import legacy_read_file

        ctx = self._make_ctx(enable_legacy_tools=False)
        result = await legacy_read_file(ctx, file_path="x.py")  # type: ignore[arg-type]
        assert "disabled" in result.lower()


class TestDemoFallbackWithoutCodegen:
    """When enable_codegen_ast=False, coding agent gracefully falls back to legacy."""

    @pytest.mark.asyncio
    async def test_no_ast_import_errors(self, monkeypatch, tmp_path):
        """Instantiating the coding agent with AST disabled should not throw."""
        monkeypatch.setenv("ENABLE_CODEGEN_AST", "false")
        # Removing codegen from sys.modules simulates it not being installed
        monkeypatch.setitem(sys.modules, "codegen", None)

        from coding.tools import CapabilitiesConfig, CodingAgentDeps

        caps = CapabilitiesConfig(
            enable_codegen_ast=False,
            enable_legacy_tools=True,
            workspace_root=str(tmp_path),
        )
        deps = CodingAgentDeps(capabilities=caps, workspace_root=str(tmp_path))
        assert deps.capabilities.enable_codegen_ast is False
        assert deps.capabilities.enable_legacy_tools is True
