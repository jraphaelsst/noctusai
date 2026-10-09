"""SessionStart worktree-sweep hook: plumbing only. The safety guards (dirty /
stash / lock / pointer / mtime / min-age) are covered against real git in
test_cleanup_worktrees.py; here: silent no-op, one-line summary, and the hook
always passes --force WITH --cleanup-respect-min-age (never force alone)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "claude-session-start-worktree-sweep.py"
spec = importlib.util.spec_from_file_location("noc_sweep_hook", HOOK)
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)


def _root(tmp_path: Path, cli_body: str) -> Path:
    (tmp_path / ".claude" / "worktrees" / "feat-a").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    cli = tmp_path / "mcp" / "noctusai" / "cli.py"
    cli.parent.mkdir(parents=True)
    cli.write_text(cli_body)
    return tmp_path


def test_summarize_silent_on_noop():
    assert H.summarize({"removed": 0, "stale": []}) == ""


def test_summarize_one_line_lists_names():
    line = H.summarize({"removed": 2, "stale": ["/r/.claude/worktrees/a", "/r/.claude/worktrees/b"]})
    assert "\n" not in line and "a, b" in line


def test_sweep_passes_force_and_respect_min_age(tmp_path):
    body = ("import sys, json\n"
            "ok = '--force' in sys.argv and '--cleanup-respect-min-age' in sys.argv\n"
            "print(json.dumps({'removed': 1 if ok else 0, 'stale': ['/x/wt']}))\n")
    assert "reclaimed 1" in H.sweep(_root(tmp_path, body))


def test_sweep_no_worktrees_dir_is_silent(tmp_path):
    assert H.sweep(tmp_path) == ""


def test_sweep_cli_failure_is_silent_on_stdout(tmp_path):
    assert H.sweep(_root(tmp_path, "import sys; sys.exit(2)\n")) == ""
