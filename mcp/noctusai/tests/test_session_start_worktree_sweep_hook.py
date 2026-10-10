"""SessionStart worktree-sweep hook: plumbing only. The safety guards (dirty /
stash / lock / pointer / mtime / min-age) are covered against real git in
test_cleanup_worktrees.py; here: silent no-op, one-line summary, and the hook
always passes --force WITH --cleanup-respect-min-age (never force alone)."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
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


def test_hook_returns_quickly_while_detached_child_does_the_work(tmp_path):
    body = ("import time, json\ntime.sleep(3)\n"
            "print(json.dumps({'removed': 2, 'stale': ['/x/a', '/x/b']}))\n")
    root = _root(tmp_path, body)
    t0 = time.monotonic()
    H.spawn_detached(root)
    assert time.monotonic() - t0 < 1.5, "spawn must not wait for the sweep"
    last = root / ".git" / H.LAST_NAME
    assert not last.exists(), "child is still working when the hook has returned"
    deadline = time.monotonic() + 20
    while not last.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert "reclaimed 2" in json.loads(last.read_text())["line"]


def test_next_start_prints_previous_line_once(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / H.LAST_NAME).write_text(json.dumps({"line": "noc: reclaimed 3", "shown": False}))
    assert H.take_previous_line(tmp_path) == "noc: reclaimed 3"
    assert H.take_previous_line(tmp_path) == ""


def test_child_fast_forwards_the_primary_and_records_the_line(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    mod = tmp_path / "mcp" / "noctusai" / "primary_ff.py"
    mod.parent.mkdir(parents=True)
    mod.write_text(
        "def ff_primary_to_dev(root, fetch=False):\n"
        "    assert fetch is True\n"
        "    return {'status': 'fast_forwarded', 'from': 'a1', 'to': 'b2', 'commits': 3}\n"
        "def summary_line(r):\n"
        "    return f\"noc: primary checkout fast-forwarded {r['from']}..{r['to']}\"\n")

    H.run_child(tmp_path)  # no worktrees dir: the sweep is a no-op, the FF still runs

    data = json.loads((tmp_path / ".git" / H.LAST_NAME).read_text())
    assert data == {"line": "noc: primary checkout fast-forwarded a1..b2", "shown": False}


def test_hook_spawns_the_child_even_without_worktrees(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(H, "spawn_detached", lambda root: spawned.append(root))
    monkeypatch.setattr(H, "primary_root", lambda start: tmp_path)
    monkeypatch.setattr(H.sys, "stdin", __import__("io").StringIO("{}"))
    monkeypatch.setattr(H.sys, "argv", ["hook"])

    assert H.main() == 0
    assert spawned == [tmp_path]


def test_pglite_hint_one_line_when_missing(tmp_path):
    hint = H.pglite_hint(tmp_path)
    assert hint == "migration_replay unavailable: run npm ci --prefix mcp/noctusai/node"
    assert "\n" not in hint


def test_pglite_hint_silent_when_installed(tmp_path):
    (tmp_path / H.PGLITE_REL).mkdir(parents=True)
    assert H.pglite_hint(tmp_path) == ""
