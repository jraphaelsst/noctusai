"""Contract tests for the kb-counts git merge driver (scripts/hooks/merge-kb-counts.sh).

The Python half (``kb_sync.render_kb_counts``) is covered in test_kb_sync.py; this
file covers the SHELL half — the part git actually invokes — by running the real
script inside a throwaway repo whose ``mcp/noctusai/cli.py`` is a recording stub.

The contract under test (see the script header):
  * exit 0 + regenerated content in %A when the render leaves no conflict markers;
  * exit 1 + %A byte-identical when markers remain (a real prose conflict);
  * a failed render exits 1 (real conflict, %A untouched) — never stale counts;
  * no %P → exit 1 without invoking the CLI;
  * the driver writes %A and NOTHING else — no tracked file, no temp leftover
    (the 2026-08-17 rebase-loop regression).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
DRIVER = REPO / "scripts" / "hooks" / "merge-kb-counts.sh"

CONFLICTED = "# Doc\n<<<<<<< ours\n| a | 1 |\n=======\n| a | 2 |\n>>>>>>> theirs\n"
RESOLVED = "# Doc\n| a | 3 |\n"

# Stub CLI: records its argv, then behaves per STUB_MODE —
#   render → write RESOLVED to --out;  keep → copy --source to --out;  fail → exit 2.
_STUB_CLI = f"""
import json, os, shutil, sys
argv = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(json.dumps(argv) + "\\n")
mode = os.environ.get("STUB_MODE", "render")
if mode == "fail":
    sys.exit(2)
out = argv[argv.index("--out") + 1]
if mode == "keep":
    shutil.copy(argv[argv.index("--source") + 1], out)
else:
    with open(out, "w") as fh:
        fh.write({RESOLVED!r})
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "hooks").mkdir(parents=True)
    (root / "mcp" / "noctusai").mkdir(parents=True)
    shutil.copy(DRIVER, root / "scripts" / "hooks" / "merge-kb-counts.sh")
    (root / "mcp" / "noctusai" / "cli.py").write_text(_STUB_CLI)
    (root / "KB.md").write_text(RESOLVED)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(
        root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed"
    )
    return root


def _run(repo: Path, tmp_path: Path, current: Path, pathname: str | None, mode: str):
    scratch = tmp_path / "tmpdir"
    scratch.mkdir(exist_ok=True)
    log = tmp_path / "stub.log"
    env = {
        **os.environ,
        "PYTHON": sys.executable,
        "STUB_MODE": mode,
        "STUB_LOG": str(log),
        "TMPDIR": str(scratch),
    }
    args = ["bash", str(repo / "scripts/hooks/merge-kb-counts.sh"), "O", str(current), "B"]
    if pathname is not None:
        args.append(pathname)
    proc = subprocess.run(args, cwd=repo, env=env, capture_output=True, text=True)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return proc.returncode, calls, scratch


def _current(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "current.md"
    p.write_text(text)
    return p


def test_counts_only_conflict_resolves_into_A(fake_repo, tmp_path):
    current = _current(tmp_path, CONFLICTED)
    rc, calls, _ = _run(fake_repo, tmp_path, current, "KB.md", "render")
    assert rc == 0
    assert current.read_text() == RESOLVED
    assert len(calls) == 1
    argv = calls[0]
    assert argv[argv.index("--render-kb-counts") + 1] == "KB.md"
    assert argv[argv.index("--source") + 1] == str(current)
    assert Path(argv[argv.index("--worktree-path") + 1]).resolve() == fake_repo.resolve()


def test_prose_conflict_leaves_A_untouched_and_exits_1(fake_repo, tmp_path):
    current = _current(tmp_path, CONFLICTED)
    rc, _, _ = _run(fake_repo, tmp_path, current, "KB.md", "keep")
    assert rc == 1
    assert current.read_text() == CONFLICTED


def test_render_failure_is_a_real_conflict_never_stale_counts(fake_repo, tmp_path):
    # Missing toolkit deps must NOT silently keep stale counts: exit 1, %A untouched.
    for text in (CONFLICTED, RESOLVED):
        current = _current(tmp_path, text)
        rc, calls, _ = _run(fake_repo, tmp_path, current, "KB.md", "fail")
        assert calls  # the render was attempted
        assert rc == 1
        assert current.read_text() == text


def test_missing_pathname_exits_1_without_invoking_cli(fake_repo, tmp_path):
    current = _current(tmp_path, CONFLICTED)
    rc, calls, _ = _run(fake_repo, tmp_path, current, None, "render")
    assert rc == 1
    assert calls == []
    assert current.read_text() == CONFLICTED


@pytest.mark.parametrize("mode", ["render", "keep", "fail"])
def test_driver_writes_A_and_nothing_else(fake_repo, tmp_path, mode):
    current = _current(tmp_path, CONFLICTED)
    _, _, scratch = _run(fake_repo, tmp_path, current, "KB.md", mode)
    assert _git(fake_repo, "status", "--porcelain") == ""
    assert list(scratch.iterdir()) == []
