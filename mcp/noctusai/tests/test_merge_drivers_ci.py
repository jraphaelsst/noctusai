"""Merge drivers must work on the merge-queue runner (2026-11-05 incident).

Part 1: keeper `check_merge_drivers_registered_in_ci` fixtures.
Part 2: end-to-end — two branches bump the same kb-counts block; merged with the
drain's own `merge --no-ff` and `rebase --onto`, drivers registered by the real
register-merge-drivers.sh, no conflict and counts re-derived (fake renderer via
a stub cli.py, as in test_merge_kb_counts_driver).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev.compliance import check_merge_drivers_registered_in_ci  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
HOOKS = REPO / "scripts" / "hooks"


def _git(cwd, *a, check=True):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          cwd=cwd, check=check, capture_output=True, text=True)


# ── keeper ────────────────────────────────────────────────────────────────
def _fixture(tmp_path, attrs, script, wf):
    (tmp_path / ".gitattributes").write_text(attrs)
    if script is not None:
        (tmp_path / "scripts/hooks").mkdir(parents=True)
        (tmp_path / "scripts/hooks/register-merge-drivers.sh").write_text(script)
    if wf is not None:
        (tmp_path / ".github/workflows").mkdir(parents=True)
        (tmp_path / ".github/workflows/merge-queue.yml").write_text(wf)
    return tmp_path


GOOD_SCRIPT = "reg kb-counts x a.sh\ngit config merge.lgpd-warnings.driver y\n"
ATTRS = "a.ndjson merge=union\nA.md merge=kb-counts\nL.md merge=lgpd-warnings\n"


class TestMergeDriversRegisteredInCi:
    def test_keeper_clean(self, tmp_path):
        r = _fixture(tmp_path, ATTRS, GOOD_SCRIPT, "run: bash scripts/hooks/register-merge-drivers.sh\n")
        assert check_merge_drivers_registered_in_ci(r) == []


    def test_keeper_unregistered_driver(self, tmp_path):
        r = _fixture(tmp_path, ATTRS + "B.md merge=newdrv\n", GOOD_SCRIPT,
                     "register-merge-drivers.sh")
        out = check_merge_drivers_registered_in_ci(r)
        assert len(out) == 1 and "newdrv" in out[0]["issue"]


    def test_keeper_workflow_does_not_invoke_script(self, tmp_path):
        r = _fixture(tmp_path, ATTRS, GOOD_SCRIPT, "run: echo hi\n")
        out = check_merge_drivers_registered_in_ci(r)
        assert len(out) == 1 and "merge-queue.yml" in out[0]["file"]


    def test_keeper_missing_script(self, tmp_path):
        r = _fixture(tmp_path, ATTRS, None, "register-merge-drivers.sh")
        assert len(check_merge_drivers_registered_in_ci(r)) == 1


    def test_keeper_builtins_only_needs_nothing(self, tmp_path):
        r = _fixture(tmp_path, "a merge=union\nb merge=binary\n", None, None)
        assert check_merge_drivers_registered_in_ci(r) == []


    def test_real_repo_is_clean(self):
        assert check_merge_drivers_registered_in_ci(REPO) == []


# ── end-to-end ────────────────────────────────────────────────────────────
STUB_CLI = '''
import sys, re
a = sys.argv[1:]
src = open(a[a.index("--source") + 1]).read()
out = a[a.index("--out") + 1]
# "render": re-derive the block (deterministic marker; the real renderer counts the tree)
src = re.sub(r"(<!-- kb-counts:start:x -->\\n).*?(\\n<!-- kb-counts:end:x -->)",
             lambda m: m.group(1) + "count=derived" + m.group(2), src, flags=re.S)
open(out, "w").write(src)
'''
DOC = "# Doc\n<!-- kb-counts:start:x -->\ncount={n}\n<!-- kb-counts:end:x -->\n"


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    (root / "scripts/hooks").mkdir(parents=True)
    (root / "mcp/noctusai").mkdir(parents=True)
    for f in ("merge-kb-counts.sh", "merge-lgpd-warnings.sh", "register-merge-drivers.sh"):
        shutil.copy(HOOKS / f, root / "scripts/hooks" / f)
    (root / "mcp/noctusai/cli.py").write_text(STUB_CLI)
    (root / ".gitattributes").write_text("DOC.md merge=kb-counts\n")
    (root / "DOC.md").write_text(DOC.format(n=0))
    _git(root, "init", "-q", "-b", "dev")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    for b, k in (("a", 1), ("b", 2)):  # each bumps the SAME block to a different value
        _git(root, "checkout", "-q", "-b", b, "dev")
        for i in range(k):
            (root / f"f_{b}{i}").write_text(b)
        (root / "DOC.md").write_text(DOC.format(n=k))
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", b)
    _git(root, "checkout", "-q", "dev")
    return root


def _register(root, env):
    subprocess.run(["bash", str(root / "scripts/hooks/register-merge-drivers.sh"), str(root)],
                   check=True, capture_output=True, env=env)


@pytest.fixture
def env():
    return {**os.environ, "PYTHON": sys.executable}


def test_unregistered_reproduces_the_incident(repo):
    _git(repo, "merge", "--no-ff", "-qm", "m", "a")
    r = _git(repo, "merge", "--no-ff", "-m", "m", "b", check=False)
    assert r.returncode != 0  # plain text merge → conflict (what the runner did)


def test_merge_no_ff_with_registered_drivers(repo, env, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    _register(repo, env)
    _git(repo, "merge", "--no-ff", "-qm", "m", "a")
    r = _git(repo, "merge", "--no-ff", "--no-edit", "-m", "mq: merge b", "b", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "count=derived" in (repo / "DOC.md").read_text()


def test_rebase_onto_with_registered_drivers(repo, env, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    _register(repo, env)
    _git(repo, "merge", "--no-ff", "-qm", "m", "a")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", "--detach", head)
    mb = _git(repo, "merge-base", head, "b").stdout.strip()
    r = _git(repo, "rebase", "--quiet", "--onto", head, mb, "b", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "count=derived" in (repo / "DOC.md").read_text()
