"""Reproduces the 2026-09-17 incident: `session_end_sweep.sweep()` called
with no explicit `repo_root` must append its summary row to the PRIMARY
checkout's `project-history/worktree-salvage.ndjson` — never to wherever
`settings.REPO_ROOT` happened to drift to when the MCP server booted with
cwd inside a worktree.

Before the fix, `sweep()`'s implicit fallback was `from settings import
REPO_ROOT; repo_root = REPO_ROOT` — and REPO_ROOT/get_noctusai_home()
deliberately STOPS at a `.claude/worktrees/<slug>` boundary. Two summary
rows landed in `.claude/worktrees/worktree-liveness-not-just-ledger/
project-history/worktree-salvage.ndjson` this way and were only recovered
by a human noticing.

After the fix, the fallback is `from settings import LEDGER_ROOT` (lazy,
re-read at call time), which UNWRAPS the worktree boundary instead of
stopping at it. This test proves the row lands at `settings.LEDGER_ROOT`
even when a decoy directory (standing in for "wherever REPO_ROOT would
have wrongly pointed") is never touched.

KB § PATTERNS/common/claim-vs-evidence-shared-state.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings  # noqa: E402
from tools.noctus.dev import session_end_sweep as SES  # noqa: E402


def _git_init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(repo), check=True)
    (repo / ".gitkeep").touch()
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True)


def test_sweep_writes_ledger_to_ledger_root_not_a_decoy_worktree(tmp_path, monkeypatch):
    primary = tmp_path / "noctusai"
    _git_init(primary)

    # Decoy: stands in for "wherever settings.REPO_ROOT would have wrongly
    # resolved to, had the MCP server booted with cwd inside a worktree".
    # session_end_sweep.py no longer imports REPO_ROOT at all post-fix, but
    # this decoy proves the row lands ONLY at LEDGER_ROOT — nothing else on
    # the filesystem gets touched.
    decoy_worktree = tmp_path / "noctusai" / ".claude" / "worktrees" / "some-engineer-slug"
    decoy_worktree.mkdir(parents=True)

    monkeypatch.setattr(settings, "LEDGER_ROOT", primary)

    result = SES.sweep(repo_root=None, deliver_ledgers=False, heal_pointers=False)
    assert result["ok"] is True

    primary_ledger = primary / "project-history" / "worktree-salvage.ndjson"
    decoy_ledger = decoy_worktree / "project-history" / "worktree-salvage.ndjson"

    assert primary_ledger.exists(), "sweep summary row must land in LEDGER_ROOT (primary)"
    assert not decoy_ledger.exists(), "sweep summary row must NEVER land in a worktree"

    lines = primary_ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "session-end-sweep"


def test_sweep_explicit_repo_root_still_honored(tmp_path, monkeypatch):
    """The explicit `repo_root=` test seam (and any real caller-supplied
    override) must keep working unchanged — only the IMPLICIT default
    changed."""
    explicit = tmp_path / "explicit-target"
    _git_init(explicit)

    # A different LEDGER_ROOT must NOT be used when repo_root is explicit.
    decoy_ledger_root = tmp_path / "decoy-ledger-root"
    decoy_ledger_root.mkdir()
    monkeypatch.setattr(settings, "LEDGER_ROOT", decoy_ledger_root)

    result = SES.sweep(repo_root=explicit, deliver_ledgers=False, heal_pointers=False)
    assert result["ok"] is True

    assert (explicit / "project-history" / "worktree-salvage.ndjson").exists()
    assert not (decoy_ledger_root / "project-history" / "worktree-salvage.ndjson").exists()
