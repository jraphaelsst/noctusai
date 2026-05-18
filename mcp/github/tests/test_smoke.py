"""Smoke tests for the GitHub connector MCP.

No network: every test either exercises pure validation (confirm gate)
or `unittest.mock.patch`-es the external `gh` CLI seam
(`github.gh.run_gh` / `github.gh.gh_available`). Patching an external
service is sanctioned by CLAUDE.md §1; our own code is never patched.
Mirrors `mcp/meta/tests/test_smoke.py`.

Pins, per the connector contract:
- the exact registered tool-name set (guards silent additions),
- 3-segment dotted naming under the `github.*` umbrella,
- the confirm gate (write tools refuse + perform NO side-effect),
- gated-capability honesty (`gh` absent ⇒ typed 424, never faked),
- descriptors/handlers aggregation coherence.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

# Put `mcp/` on sys.path so `from github.X import ...` + `from _kit.X
# import ...` resolve — same trick mcp/meta/tests uses.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively pulled by `_kit`) MUST resolve against
# THIS worktree's seed. The repo's editable install registers a
# `MetaPathFinder` hard-mapping it to whichever worktree `pip install -e`
# last ran in — possibly a stale one. `sys.meta_path` runs before
# `sys.path`, so a plain insert can't win. Drop the stale editable
# finder + already-imported stale modules, then prepend this worktree's
# seed. NOT a monkeypatch — it corrects a mis-pointed package *locator*
# ("codebase is source of truth" applied to import resolution).
_SEED = _REPO_ROOT / "seed" / "lib" / "backend"
_seed_lib = _SEED / "noctusai_lib"


def _resolves_to_this_worktree() -> bool:
    try:
        import noctusai_lib  # noqa
    except ModuleNotFoundError:
        return False
    f = getattr(noctusai_lib, "__file__", "") or ""
    return str(_seed_lib) in f


if not _resolves_to_this_worktree():
    def _is_noctus_editable_finder(mp) -> bool:
        mod = getattr(mp, "__module__", "") or ""
        nm = getattr(mp, "__name__", "") or ""
        return "__editable__" in mod and nm == "_EditableFinder"

    sys.meta_path = [
        mp for mp in sys.meta_path if not _is_noctus_editable_finder(mp)
    ]
    for _name in list(sys.modules):
        if _name == "noctusai_lib" or _name.startswith("noctusai_lib."):
            del sys.modules[_name]

sys.path.insert(0, str(_SEED))

import pytest

_EXPECTED_TOOLS = {
    "github.pr.list",
    "github.pr.view",
    "github.pr.diff",
    "github.pr.checks",
    "github.pr.create",
    "github.pr.ready",
    "github.repo.view",
    "github.diagnostics.connection_status",
}


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from github import gh, settings, types  # noqa: F401
    from github.tools import diagnostics, pr, repo  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401

    assert hasattr(gh, "run_gh")
    assert hasattr(gh, "gh_available")


def test_registered_tool_name_set_is_pinned():
    from github.tools import all_handlers

    assert set(all_handlers().keys()) == _EXPECTED_TOOLS


def test_all_handlers_aggregates_every_leaf():
    from github.tools import all_descriptors, all_handlers

    descriptor_names = {d.name for d in all_descriptors()}
    handler_names = set(all_handlers().keys())
    assert descriptor_names == handler_names, (
        f"mismatch — descriptors only: {descriptor_names - handler_names}; "
        f"handlers only: {handler_names - descriptor_names}"
    )


def test_dotted_naming_convention():
    """KB § PATTERNS/mcp-tool-conventions.md § 1: 3-segment dotted names."""
    from github.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"tool {name!r} not 3-segment dotted"
        assert parts[0] == "github", f"tool {name!r} not under github.* umbrella"


# ─── Settings ────────────────────────────────────────────────────────────


def test_settings_lenient_construction_no_config():
    from github.settings import GitHubConnectorSettings

    s = GitHubConnectorSettings()
    assert s.default_repo is None
    assert s.effective_gh_path == "gh"


def test_settings_effective_gh_path_override():
    from github.settings import GitHubConnectorSettings

    assert GitHubConnectorSettings(gh_path="/opt/gh").effective_gh_path == "/opt/gh"


# ─── Confirm gate — writes refuse + perform NO side-effect ───────────────


def test_pr_create_without_confirm_blocks_no_side_effect():
    from github.tools.pr import pr_create

    with patch("github.gh.run_gh") as runner:
        out = asyncio.run(pr_create({"title": "t", "body": "b"}))
    runner.assert_not_called()  # NO gh subprocess — the gate fired first
    assert out["created"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412
    assert out["url"] is None


def test_pr_ready_confirm_false_explicit_also_blocks():
    from github.tools.pr import pr_ready

    with patch("github.gh.run_gh") as runner:
        out = asyncio.run(pr_ready({"number": 7, "confirm": False}))
    runner.assert_not_called()
    assert out["ready"] is False
    assert out["error"]["status"] == 412


# ─── Read path — patched gh seam (no network) ────────────────────────────


def test_pr_list_maps_gh_json():
    from github.tools.pr import pr_list

    fake = [
        {
            "number": 12,
            "title": "feat: x",
            "state": "OPEN",
            "author": {"login": "octocat"},
            "headRefName": "feat/x",
            "baseRefName": "main",
            "isDraft": False,
            "url": "https://github.com/o/r/pull/12",
        }
    ]
    with patch("github.gh.run_gh", return_value=fake):
        out = asyncio.run(pr_list({"state": "open"}))
    assert out["error"] is None
    assert out["pulls"][0]["number"] == 12
    assert out["pulls"][0]["author"] == "octocat"  # author.login flattened


def test_pr_checks_all_passing_logic():
    from github.tools.pr import pr_checks

    passing = [
        {"name": "build", "state": "SUCCESS", "bucket": "pass"},
        {"name": "lint", "state": "SKIPPED", "bucket": "skipping"},
    ]
    with patch("github.gh.run_gh", return_value=passing):
        out = asyncio.run(pr_checks({"number": 1}))
    assert out["all_passing"] is True

    failing = [{"name": "test", "state": "FAILURE", "bucket": "fail"}]
    with patch("github.gh.run_gh", return_value=failing):
        out = asyncio.run(pr_checks({"number": 1}))
    assert out["all_passing"] is False

    with patch("github.gh.run_gh", return_value=[]):
        out = asyncio.run(pr_checks({"number": 1}))
    # No checks ⇒ cannot assert pass on an empty set.
    assert out["all_passing"] is None


def test_repo_view_flattens_default_branch_ref():
    from github.tools.repo import repo_view

    fake = {
        "nameWithOwner": "o/r",
        "defaultBranchRef": {"name": "main"},
        "description": "d",
        "isPrivate": True,
        "url": "https://github.com/o/r",
    }
    with patch("github.gh.run_gh", return_value=fake):
        out = asyncio.run(repo_view({}))
    assert out["error"] is None
    assert out["defaultBranch"] == "main"
    assert out["isPrivate"] is True


def test_pr_create_with_confirm_invokes_gh_and_parses_number():
    from github.tools.pr import pr_create

    with patch(
        "github.gh.run_gh", return_value="https://github.com/o/r/pull/42"
    ) as runner:
        out = asyncio.run(
            pr_create({"title": "t", "body": "b", "confirm": True})
        )
    runner.assert_called_once()
    assert out["created"] is True
    assert out["number"] == 42


# ─── Gated-capability honesty — gh absent ⇒ typed 424, never faked ───────


def test_pr_list_gh_absent_returns_typed_424_not_fake():
    from github.tools.pr import pr_list

    with patch("github.gh.gh_available", return_value=False):
        out = asyncio.run(pr_list({}))
    assert out["pulls"] == []
    assert out["error"]["status"] == 424  # never a fabricated success


def test_connection_status_gh_absent():
    from github.tools.diagnostics import connection_status

    with patch("github.gh.gh_available", return_value=False):
        out = asyncio.run(connection_status({}))
    assert out["gh_available"] is False
    assert out["error"]["status"] == 424


def test_connection_status_present_but_logged_out():
    """`gh` present, `gh api user` fails ⇒ authenticated=false (honest)."""
    from github.tools.diagnostics import connection_status
    from github import gh

    def _runner(args, **kw):
        if args[:1] == ["--version"]:
            return "gh version 2.92.0 (2026-04-28)"
        raise gh.GitHubCliError("not logged in", status=424)

    with patch("github.gh.gh_available", return_value=True), patch(
        "github.gh.run_gh", side_effect=_runner
    ):
        out = asyncio.run(connection_status({}))
    assert out["gh_available"] is True
    assert out["authenticated"] is False
    assert out["account"] is None
    assert out["error"]["status"] == 424


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
