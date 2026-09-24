"""Regression for settings.resolve_test_python() — the shared interpreter resolver.

Root of an N=2 bug (deploy-hardening, 2026-05-22): both
`noctus.dev.predeploy_check` (P5 gate, predeploy_check.py) and
`noctus.dev.pytest` (testing.py) shelled out to a bare ``"python"``, which on
a dev box resolves to a system interpreter WITHOUT pytest — a false *block*
in the P5 gate and a false *green* in the test runner. The resolver MUST hand
back an interpreter that can actually import pytest.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from settings import REPO_ROOT, resolve_test_python  # noqa: E402
from workspace import unwrap_worktree_root  # noqa: E402


def test_resolves_to_an_existing_interpreter():
    p = resolve_test_python()
    assert Path(p).exists(), f"resolve_test_python() returned a non-existent path: {p}"


def test_resolved_interpreter_can_import_pytest():
    """The behavioral contract: whatever we hand the test runners can run
    pytest. This is the exact regression — bare 'python' could not."""
    p = resolve_test_python()
    r = subprocess.run([p, "-c", "import pytest"], capture_output=True, text=True)
    assert r.returncode == 0, f"resolved interpreter lacks pytest: {p}\n{r.stderr}"


def test_prefers_repo_root_venv_else_current_interpreter():
    """Documents the FULL resolution order (KB § `resolve_test_python`'s own
    docstring): REPO_ROOT's own venv, else the PRIMARY checkout's venv when
    REPO_ROOT is a linked worktree (`test_worktree_without_venv_falls_back_
    to_primary_checkout` below is the dedicated regression for that leg),
    else the running interpreter — never bare 'python'.

    NOT `REPO_ROOT / "venv"` alone: this suite genuinely runs from INSIDE a
    worktree sometimes (an engineer/tech-lead verifying a branch's own
    changes before integrating), where that naive check reads False and
    wrongly expects `sys.executable` — while the real resolver correctly
    walks up to the primary's venv (2026-09-24, found running this exact
    suite from `.claude/worktrees/release-no-freeze`)."""
    for root in (REPO_ROOT, unwrap_worktree_root(REPO_ROOT)):
        if root is None:
            continue
        cand = root / "venv" / "bin" / "python"
        if cand.exists():
            expected = str(cand)
            break
    else:
        expected = sys.executable
    assert resolve_test_python() == expected


def test_worktree_without_venv_falls_back_to_primary_checkout(tmp_path, monkeypatch):
    """The 2026-09-22 regression: a linked worktree has NO `venv/` of its own
    (nobody pip-installs per worktree), so the old lookup missed and fell
    through to `sys.executable` — the MCP server's venv, which lacks the
    product deps. Every agents-suite run from a worktree then died at
    COLLECTION on `claude_agent_sdk` and predeploy_check called the product
    'blocked'. Two sessions in one day re-ran the suite by hand to find it
    was green (1209 passed).

    Structure mirrors a real worktree: <primary>/.claude/worktrees/<slug>.
    """
    import settings as settings_mod

    primary = tmp_path / "noctusai"
    primary_venv = primary / "venv" / "bin"
    primary_venv.mkdir(parents=True)
    (primary_venv / "python").write_text("#!/bin/sh\n")
    worktree = primary / ".claude" / "worktrees" / "some-slice"
    worktree.mkdir(parents=True)
    assert not (worktree / "venv").exists(), "a fresh worktree has no venv — that IS the bug"

    monkeypatch.setattr(settings_mod, "REPO_ROOT", worktree)
    assert settings_mod.resolve_test_python() == str(primary_venv / "python")


def test_worktree_venv_still_wins_when_it_exists(tmp_path, monkeypatch):
    """The fallback must not override a worktree that DOES carry its own
    venv — the caller's tree stays authoritative."""
    import settings as settings_mod

    primary = tmp_path / "noctusai"
    (primary / "venv" / "bin").mkdir(parents=True)
    (primary / "venv" / "bin" / "python").write_text("#!/bin/sh\n")
    worktree = primary / ".claude" / "worktrees" / "some-slice"
    own_venv = worktree / "venv" / "bin"
    own_venv.mkdir(parents=True)
    (own_venv / "python").write_text("#!/bin/sh\n")

    monkeypatch.setattr(settings_mod, "REPO_ROOT", worktree)
    assert settings_mod.resolve_test_python() == str(own_venv / "python")
