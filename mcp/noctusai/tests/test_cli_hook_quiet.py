"""Hook quiet mode: a git hook exports NOCTUS_HOOK_QUIET=1 so each of its ~20-77
toolkit CLI calls prints only its verdict, not a banner + INFO lines (2026-11-05)."""
import os
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "cli.py"
REPO = Path(__file__).resolve().parents[3]


def _run(extra_env: dict) -> str:
    env = {**os.environ, **extra_env}
    env.pop("NOCTUS_HOOK_VERBOSE", None) if "NOCTUS_HOOK_VERBOSE" not in extra_env else None
    r = subprocess.run(
        [sys.executable, str(CLI), "--worktree-path", str(REPO), "--check-conflict-markers"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    return r.stdout + r.stderr


def test_quiet_drops_banner_and_info_but_keeps_verdict():
    out = _run({"NOCTUS_HOOK_QUIET": "1"})
    assert "conflict-markers" in out
    assert "NoctusAI Dev Toolkit" not in out
    assert "worktree override" not in out
    assert "| INFO" not in out


def test_verbose_wins_over_quiet():
    out = _run({"NOCTUS_HOOK_QUIET": "1", "NOCTUS_HOOK_VERBOSE": "1"})
    assert "NoctusAI Dev Toolkit" in out


def test_every_git_hook_exports_quiet():
    for hook in ("pre-commit", "pre-push", "post-merge", "post-checkout"):
        assert "export NOCTUS_HOOK_QUIET=1" in (REPO / "scripts/hooks" / hook).read_text(), hook
