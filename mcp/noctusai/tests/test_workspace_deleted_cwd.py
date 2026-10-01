"""Regression: repo-root resolution must survive a deleted cwd.

A session that was inside a worktree removed by `task_branch action=cleanup`
has a dead cwd; `Path.cwd()` raises FileNotFoundError, which used to break
`settings` import (and so every task_branch call).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MCP = Path(__file__).resolve().parents[1]


def _run_in_dead_cwd(code: str) -> subprocess.CompletedProcess:
    dead = tempfile.mkdtemp()
    env = {k: v for k, v in os.environ.items() if k != "NOCTUSAI_HOME"}
    env["PYTHONPATH"] = str(MCP)
    # chdir into the dir, remove it, then run the probe in that dead cwd.
    wrapper = f"import os,shutil;os.chdir({dead!r});shutil.rmtree({dead!r});{code}"
    return subprocess.run([sys.executable, "-c", wrapper], capture_output=True, text=True, env=env)


def test_get_ledger_root_with_deleted_cwd():
    r = _run_in_dead_cwd(
        "import workspace;p=workspace.get_ledger_root();print(p)"
    )
    assert r.returncode == 0, r.stderr
    assert (Path(r.stdout.strip()) / "mcp" / "noctusai").is_dir()


def test_settings_import_with_deleted_cwd():
    r = _run_in_dead_cwd(
        "import settings;print(settings.LEDGER_ROOT)"
    )
    assert r.returncode == 0, r.stderr


def test_task_branch_status_with_deleted_cwd():
    r = _run_in_dead_cwd(
        "from tools.noctus.dev import task_branch as t;print(type(t).__name__)"
    )
    assert r.returncode == 0, r.stderr
