"""pre-commit ledger-only fast path + bounded 8-way-sync step.

Runs the REAL hook in a throwaway git repo whose `mcp/noctusai/cli.py` is a
stub that records the flags it is called with (and can hang on demand).
KB § PATTERNS/common/eight-way-sync.md § Ledger-only fast path + timeout.
"""
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "pre-commit"

STUB = textwrap.dedent('''
    import os, sys, time
    with open(os.environ["STUB_LOG"], "a") as f:
        f.write(" ".join(a for a in sys.argv[1:] if a.startswith("--check") or a.startswith("--verify") or a.startswith("--update") or a.startswith("--stamp") or a.startswith("--sync")) + "\\n")
    if "--check-eight-way-sync" in sys.argv and os.environ.get("STUB_HANG"):
        time.sleep(60)
''')


def _git(repo, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path):
    repo = tmp_path / "r"
    (repo / "mcp/noctusai").mkdir(parents=True)
    (repo / "mcp/noctusai/cli.py").write_text(STUB)
    (repo / "project-history").mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")  # stub is history, not part of the staged set
    return repo


def _run(repo, tmp_path, **env):
    log = tmp_path / "log"
    log.write_text("")
    e = {**os.environ, "STUB_LOG": str(log), "PY": sys.executable, "PYTHON": sys.executable,
         "NOCTUS_ALLOW_PRIMARY_COMMIT": "1", **env}
    r = subprocess.run(["bash", str(HOOK)], cwd=repo, env=e, capture_output=True, text=True, timeout=60)
    return r, log.read_text()


def test_ledger_only_takes_fast_path(tmp_path):
    repo = _repo(tmp_path)
    (repo / "project-history/branch-tree.ndjson").write_text("{}\n")
    (repo / "project-history/branch-tree.mirror.ndjson").write_text("{}\n")
    _git(repo, "add", "-A")
    r, calls = _run(repo, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "FAST PATH: ledger-only" in r.stdout
    assert "--check-conflict-markers" in calls
    for slow in ("--check-eight-way-sync", "--verify-kb-sync", "--update-kb-counts"):
        assert slow not in calls


def test_mixed_commit_does_not_take_fast_path(tmp_path):
    repo = _repo(tmp_path)
    (repo / "project-history/branch-tree.ndjson").write_text("{}\n")
    (repo / "KNOWLEDGE-BASE").mkdir()
    (repo / "KNOWLEDGE-BASE/x.md").write_text("x\n")
    _git(repo, "add", "-A")
    r, calls = _run(repo, tmp_path)
    assert "FAST PATH" not in r.stdout
    assert "--check-eight-way-sync" in calls


def test_eight_way_timeout_fails_loudly(tmp_path):
    repo = _repo(tmp_path)
    (repo / "KNOWLEDGE-BASE").mkdir()
    (repo / "KNOWLEDGE-BASE/x.md").write_text("x\n")
    _git(repo, "add", "-A")
    r, _ = _run(repo, tmp_path, STUB_HANG="1", NOCTUS_EIGHT_WAY_TIMEOUT="2")
    assert r.returncode == 1
    assert "TIMED OUT" in r.stderr
