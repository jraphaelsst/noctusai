"""A clean merge must end with current kb-counts (scripts/hooks/post-merge follow-up commit).

Real git in a throwaway repo; the hook is installed through core.hooksPath and
the counts regeneration is a stub CLI handed over the NOCTUS_CLI seam (the real
one is exercised by its own tests). No code of ours is patched.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "post-merge"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

STUB = '''import sys
from pathlib import Path
n = len(list(Path("KNOWLEDGE-BASE").glob("n*.md")))
p = Path("KNOWLEDGE-BASE/COUNTS.md")
p.write_text(f"<!-- kb-counts:start:x -->\\ntotal {n}\\n<!-- kb-counts:end:x -->\\n")
'''


def git(cwd, *a, extra_env=None):
    r = subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True,
                       env={**ENV, **(extra_env or {})})
    assert r.returncode == 0, (a, r.stdout, r.stderr)
    return r.stdout


def _setup(tmp_path, with_hook):
    git(tmp_path, "init", "-q", "-b", "dev")
    hooks = tmp_path / "hk"
    hooks.mkdir()
    if with_hook:
        shutil.copy(HOOK, hooks / "post-merge")
    git(tmp_path, "config", "core.hooksPath", str(hooks))
    kb = tmp_path / "KNOWLEDGE-BASE"
    kb.mkdir()
    (tmp_path / "stub_cli.py").write_text(STUB)
    (kb / "COUNTS.md").write_text("<!-- kb-counts:start:x -->\ntotal 0\n<!-- kb-counts:end:x -->\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "root")
    git(tmp_path, "checkout", "-qb", "feat")
    (kb / "n_feat.md").write_text("f\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "feat adds a doc")
    git(tmp_path, "checkout", "-q", "dev")
    (kb / "n_dev.md").write_text("d\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "dev adds a doc")
    git(tmp_path, "checkout", "-q", "feat")


def _merge(tmp_path):
    git(tmp_path, "merge", "--no-edit", "dev",
        extra_env={"NOCTUS_CLI": str(tmp_path / "stub_cli.py"), "PYTHON": "python3"})


def test_clean_merge_lands_with_current_counts(tmp_path):
    _setup(tmp_path, with_hook=True)
    _merge(tmp_path)
    assert "total 2" in (tmp_path / "KNOWLEDGE-BASE/COUNTS.md").read_text()
    assert git(tmp_path, "status", "--porcelain").strip() == ""
    assert "total 2" in git(tmp_path, "show", "HEAD:KNOWLEDGE-BASE/COUNTS.md")
    assert git(tmp_path, "log", "-1", "--format=%s").startswith("chore(kb-counts)")


def test_without_the_hook_the_counts_go_stale(tmp_path):
    _setup(tmp_path, with_hook=False)
    _merge(tmp_path)
    assert "total 0" in git(tmp_path, "show", "HEAD:KNOWLEDGE-BASE/COUNTS.md")
