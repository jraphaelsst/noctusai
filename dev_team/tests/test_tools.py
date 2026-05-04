"""B2 engineer-B tests — 15-tool catalog + allowlist resolvers.

Per the engineer-B brief:
- ``_RESOLVERS`` covers every tool name in ``TOOL_ALLOWLIST``.
- Each ``build_<tool>_tool`` returns a callable.
- ``shell`` rejects out-of-allowlist commands with a clear error.
- ``delegation.delegate`` raises PermissionError when caller is not "leader".
- ``kb.read_kb`` rejects paths outside ``KNOWLEDGE-BASE/``.
- ``web_search`` stub raises NotImplementedError mentioning ``SERPER_API_KEY``.

External-integration patches (e.g. ``mcp.tools.noctus.dev.recurrence``)
use ``unittest.mock.patch.object`` per `feedback_no_monkeypatching_in_tests`.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Catalog completeness
# ---------------------------------------------------------------------------


def test_resolvers_cover_every_allowlist_tool():
    """Every tool name appearing in TOOL_ALLOWLIST has a _RESOLVERS entry."""
    from dev_team.tools.allowlists import TOOL_ALLOWLIST, _RESOLVERS

    referenced = set()
    for tools in TOOL_ALLOWLIST.values():
        referenced.update(tools)
    missing = referenced - set(_RESOLVERS.keys())
    assert not missing, f"_RESOLVERS missing entries for: {sorted(missing)}"


def test_resolvers_15_tool_catalog():
    """The 15-tool catalog (per design-reference.md §3) is fully resolved."""
    from dev_team.tools.allowlists import _RESOLVERS

    expected = {
        "read_kb",
        "read_memory",
        "write_memory",
        "delegate",
        "invoke_subteam",
        "read_files",
        "write_files",
        "edit_files",
        "shell",
        "web_search",
        "recurrence_scan",
        "keeper_validate",
        "keeper_review",
        "ast_python",
        "ast_typescript",
        "file_proposal",
    }
    assert set(_RESOLVERS.keys()) == expected


def test_tools_for_leader_returns_callables():
    from dev_team.tools.allowlists import tools_for

    leader_tools = tools_for("leader")
    assert len(leader_tools) == 5  # read_kb / read_memory / write_memory / delegate / invoke_subteam
    for tool in leader_tools:
        assert callable(tool)


def test_tools_for_backend_engineer_returns_9_callables():
    from dev_team.tools.allowlists import tools_for

    backend_tools = tools_for("backend_engineer")
    assert len(backend_tools) == 9
    for tool in backend_tools:
        assert callable(tool)


# ---------------------------------------------------------------------------
# Each build_<tool>_tool returns a callable
# ---------------------------------------------------------------------------


def test_build_functions_return_callables():
    from dev_team.tools import (
        ast_tools,
        delegation,
        files,
        kb,
        keeper,
        memory_tool,
        proposals,
        recurrence,
        shell,
        web,
    )

    for builder in (
        kb.build_read_kb_tool,
        memory_tool.build_read_memory_tool,
        memory_tool.build_write_memory_tool,
        delegation.build_delegate_tool,
        delegation.build_invoke_subteam_tool,
        files.build_read_files_tool,
        files.build_write_files_tool,
        files.build_edit_files_tool,
        shell.build_shell_tool,
        web.build_web_search_tool,
        recurrence.build_recurrence_scan_tool,
        keeper.build_keeper_validate_tool,
        keeper.build_keeper_review_tool,
        ast_tools.build_ast_python_tool,
        ast_tools.build_ast_typescript_tool,
        proposals.build_file_proposal_tool,
    ):
        result = builder()
        assert callable(result), f"{builder.__name__} did not return a callable"


# ---------------------------------------------------------------------------
# shell — out-of-allowlist rejection
# ---------------------------------------------------------------------------


def test_shell_rejects_out_of_allowlist():
    from dev_team.tools.shell import shell

    with pytest.raises(PermissionError, match="not in allowlist"):
        shell("rm -rf /", allowlist=["pytest"])


def test_shell_rejects_with_empty_allowlist():
    from dev_team.tools.shell import shell

    with pytest.raises(PermissionError):
        shell("ls", allowlist=[])


def test_shell_accepts_in_allowlist():
    from dev_team.tools.shell import shell

    result = shell("echo dev_team", allowlist=["echo"], timeout=5)
    assert result["returncode"] == 0
    assert "dev_team" in result["stdout"]


def test_shell_handles_multiword_allowlist_entries():
    from dev_team.tools.shell import _command_is_allowed

    assert _command_is_allowed("docker compose up -d", ["docker compose"])
    assert not _command_is_allowed("docker run alpine", ["docker compose"])


def test_build_shell_tool_binds_allowlist():
    from dev_team.tools.shell import build_shell_tool

    backend_shell = build_shell_tool(allowlist=["pytest", "ruff", "mypy"])
    with pytest.raises(PermissionError):
        backend_shell("docker run alpine")


# ---------------------------------------------------------------------------
# delegation — PermissionError when caller is not leader
# ---------------------------------------------------------------------------


def test_delegate_refuses_non_leader_caller():
    from dev_team.tools.delegation import delegate

    with pytest.raises(PermissionError, match="leader-only"):
        delegate("backend_engineer", "implement X", caller="backend_engineer")


def test_invoke_subteam_refuses_non_leader_caller():
    from dev_team.tools.delegation import invoke_subteam

    with pytest.raises(PermissionError, match="leader-only"):
        invoke_subteam("design_review_team", "review", caller="ux_designer")


def test_delegate_succeeds_when_caller_is_leader():
    from dev_team.tools.delegation import delegate

    result = delegate("backend_engineer", "implement X", caller="leader")
    assert result["specialist"] == "backend_engineer"
    assert result["task"] == "implement X"


def test_build_delegate_tool_defaults_to_leader_caller():
    from dev_team.tools.delegation import build_delegate_tool

    leader_delegate = build_delegate_tool()
    result = leader_delegate("qa_engineer", "run tests")
    assert result["specialist"] == "qa_engineer"


def test_build_delegate_tool_with_non_leader_caller_refuses():
    from dev_team.tools.delegation import build_delegate_tool

    bogus_delegate = build_delegate_tool(caller="backend_engineer")
    with pytest.raises(PermissionError):
        bogus_delegate("frontend_engineer", "do work")


# ---------------------------------------------------------------------------
# read_kb — path validation
# ---------------------------------------------------------------------------


def test_read_kb_rejects_non_kb_path():
    from dev_team.tools.kb import read_kb

    with pytest.raises(ValueError, match="KNOWLEDGE-BASE"):
        read_kb("CLAUDE.md")


def test_read_kb_rejects_traversal():
    from dev_team.tools.kb import read_kb

    with pytest.raises(ValueError):
        read_kb("KNOWLEDGE-BASE/../CLAUDE.md")


def test_read_kb_reads_real_kb_doc():
    """Smoke — INDEX.md exists in the repo, read it (capped)."""
    from dev_team.tools.kb import read_kb

    body = read_kb("KNOWLEDGE-BASE/INDEX.md", max_chars=2000)
    assert isinstance(body, str)
    assert len(body) > 0


def test_read_kb_section_extract():
    """If a section is given but missing, raises ValueError."""
    from dev_team.tools.kb import read_kb

    with pytest.raises(ValueError, match="section"):
        read_kb("KNOWLEDGE-BASE/INDEX.md", section="this-section-does-not-exist-xyzzy")


# ---------------------------------------------------------------------------
# web_search — stub raises NotImplementedError mentioning SERPER_API_KEY
# ---------------------------------------------------------------------------


def test_web_search_stub_without_key():
    from dev_team.tools.web import web_search

    # Drop the env var if it exists for the test duration.
    saved = os.environ.pop("SERPER_API_KEY", None)
    try:
        with pytest.raises(NotImplementedError, match="SERPER_API_KEY"):
            web_search("query")
    finally:
        if saved is not None:
            os.environ["SERPER_API_KEY"] = saved


# ---------------------------------------------------------------------------
# files — path safety + edit_files AST-only
# ---------------------------------------------------------------------------


def test_write_files_rejects_outside_repo(tmp_path):
    from dev_team.tools.files import write_files

    with pytest.raises(ValueError, match="escapes the repo root"):
        write_files({"../../../etc/passwd": "x"})


def test_edit_files_rejects_non_ast_mode():
    from dev_team.tools.files import edit_files

    with pytest.raises(ValueError, match="mode='ast'"):
        edit_files([{"path": "x.py", "action": "rename"}], mode="regex")


def test_read_files_round_trip(tmp_path, monkeypatch):
    """write -> read in a temp file under the repo root."""
    from dev_team.tools._mcp_path import repo_root
    from dev_team.tools.files import read_files, write_files

    root = repo_root()
    target_rel = "dev_team/tests/_tmp_test_round_trip.txt"
    target_abs = root / target_rel
    try:
        write_files({target_rel: "hello world"})
        out = read_files([target_rel])
        assert out[target_rel] == "hello world"
    finally:
        if target_abs.exists():
            target_abs.unlink()


# ---------------------------------------------------------------------------
# ast_python — libcst-backed
# ---------------------------------------------------------------------------


def test_ast_python_find_pattern(tmp_path):
    """find_pattern returns ClassDef matches for our own allowlists.py."""
    from dev_team.tools.ast_tools import ast_python

    result = ast_python(
        "find_pattern",
        "dev_team/src/dev_team/tools/allowlists.py",
        pattern_kind="FunctionDef",
    )
    assert result["action"] == "find_pattern"
    assert isinstance(result["matches"], list)
    assert len(result["matches"]) > 0


def test_ast_typescript_stub_raises():
    from dev_team.tools.ast_tools import ast_typescript

    with pytest.raises(NotImplementedError, match="ts-morph"):
        ast_typescript("rename", "x.ts")


# ---------------------------------------------------------------------------
# recurrence + keeper + proposals — wrappers patch at boundary
# ---------------------------------------------------------------------------


def test_recurrence_scan_invalid_mode():
    from dev_team.tools.recurrence import recurrence_scan

    with pytest.raises(ValueError, match="unknown recurrence mode"):
        recurrence_scan(mode="not_a_mode")


def test_recurrence_scan_dispatches_to_wrap_target():
    """Patch the wrap target — verify the wrapper forwards correctly.

    Per `feedback_no_monkeypatching_in_tests`, patching at the module
    boundary (``tools.noctus.dev.recurrence``) is OK — that's the
    external-integration boundary from dev_team's POV.
    """
    from dev_team.tools._mcp_path import ensure_mcp_path

    ensure_mcp_path()
    from tools.noctus.dev import recurrence as wrap_target  # type: ignore[import-not-found]

    fake_result = {"findings": [], "stats": {"calls": 1}}
    with patch.object(wrap_target, "scan_recurrence", return_value=fake_result) as mocked:
        from dev_team.tools.recurrence import recurrence_scan

        result = recurrence_scan(mode="recurrence")
        assert result == fake_result
        mocked.assert_called_once()


def test_keeper_validate_dispatches_to_wrap_target():
    from dev_team.tools._mcp_path import ensure_mcp_path

    ensure_mcp_path()
    from tools.noctus.dev import compliance as wrap_target  # type: ignore[import-not-found]

    fake_result = (95, [{"severity": "warning", "message": "test"}])
    with patch.object(wrap_target, "check_all_products", return_value=fake_result) as mocked:
        from dev_team.tools.keeper import keeper_validate

        result = keeper_validate()
        assert result["score"] == 95
        assert len(result["issues"]) == 1
        mocked.assert_called_once()


def test_keeper_validate_with_slug_uses_validate_one_product():
    from dev_team.tools._mcp_path import ensure_mcp_path

    ensure_mcp_path()
    from tools.noctus.dev import compliance as wrap_target  # type: ignore[import-not-found]

    fake_result = {"product": "erp", "score": 88, "issues": []}
    with patch.object(wrap_target, "validate_one_product", return_value=fake_result) as mocked:
        from dev_team.tools.keeper import keeper_validate

        result = keeper_validate(slug="erp")
        assert result == fake_result
        mocked.assert_called_once_with("erp")


def test_keeper_review_dispatches_to_wrap_target():
    from dev_team.tools._mcp_path import ensure_mcp_path

    ensure_mcp_path()
    from tools.noctus.dev import review as wrap_target  # type: ignore[import-not-found]

    fake_result = {"mode": "agent", "issues_found": 0, "issues": []}
    with patch.object(wrap_target, "run_review", return_value=fake_result) as mocked:
        from dev_team.tools.keeper import keeper_review

        result = keeper_review(product_slug="erp", mode="agent")
        assert result == fake_result
        mocked.assert_called_once()


def test_file_proposal_dispatches_to_wrap_target():
    from dev_team.tools._mcp_path import ensure_mcp_path

    ensure_mcp_path()
    from tools.noctus.dev import proposals as wrap_target  # type: ignore[import-not-found]

    fake_result = {"created": True, "file": "x.md", "path": "/tmp/x.md"}
    with patch.object(wrap_target, "file_proposal", return_value=fake_result) as mocked:
        from dev_team.tools.proposals import file_proposal

        result = file_proposal(
            title="Test proposal",
            body="body",
            agent="qa",
            project="agno-dev-team-rollout",
        )
        assert result == fake_result
        mocked.assert_called_once()


# ---------------------------------------------------------------------------
# memory tool — exercises the stub MemoryStore until C engineer's real impl
# ---------------------------------------------------------------------------


def test_memory_read_returns_value_or_none():
    from dev_team.tools.memory_tool import read_memory

    # Stub store returns None for missing keys; never crashes.
    value = read_memory("project", "anything")
    assert value is None or isinstance(value, (dict, str, int, list))


def test_memory_write_does_not_raise():
    from dev_team.tools.memory_tool import write_memory

    write_memory("project", "test_key", {"foo": "bar"})


def test_memory_scope_validation():
    from dev_team.tools.memory_tool import read_memory

    with pytest.raises(ValueError):
        read_memory("", "key")  # empty scope rejected
