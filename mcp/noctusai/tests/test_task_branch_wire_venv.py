"""`task_branch start` wire_env links the PRIMARY's mcp/noctusai/.venv into the worktree.

Instance #2 of the 3fc8271ae class (gitignored toolchain absent from every fresh worktree): the pre-push keepers print
'SKIPPED - no toolkit venv at <wt>/mcp/noctusai/.venv (unmeasurable, not a pass)' in EVERY task_branch worktree, so the hook that
is meant to judge the push judges nothing. Same rules as node_modules: gitignored, never clobber a real dir, reported in
wired/skipped, dry-run honoured; a primary with no .venv reports the exact command to create it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_task_branch import FakeGit, _anc_pairs, _seed_primary, _seed_worktree_tree  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402

VENV_REL = os.path.join("mcp", "noctusai", ".venv")


def _primary_with_venv(tmp_path, *, venv=True):
    primary = tmp_path / "primary"
    wt = primary / ".claude" / "worktrees" / "feat-v"
    _seed_primary(primary, slugs=("alpha",), with_toolkit_venv=venv)
    if venv:
        (primary / VENV_REL / "bin" / "python").write_text("#!/bin/sh\n")
    _seed_worktree_tree(wt)
    return primary, wt


def test_the_plan_links_the_primarys_venv(tmp_path):
    primary, wt = _primary_with_venv(tmp_path)
    wire, _skipped = T._plan_env_wiring(str(primary), str(wt), T.FsOps())
    spec = next(w for w in wire if w["link"].endswith(VENV_REL))
    assert spec["target"] == str(primary / VENV_REL) and spec["kind"] == "venv"


def test_start_creates_the_symlink_and_reports_it_in_wired(tmp_path):
    primary, wt = _primary_with_venv(tmp_path)
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-v", confirm=True, verbose=True, wire_env=True,
                        primary_root=str(primary), run=fake)
    link = wt / VENV_REL
    assert link.is_symlink() and os.path.realpath(link) == os.path.realpath(primary / VENV_REL)
    assert (link / "bin" / "python").is_file()  # what scripts/hooks/pre-push executes
    assert any(w["link"].endswith(VENV_REL) for w in res["wired"])


def test_dry_run_reports_would_wire_and_touches_nothing(tmp_path):
    primary, wt = _primary_with_venv(tmp_path)
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-v", confirm=False, verbose=True, wire_env=True,
                        primary_root=str(primary), run=fake)
    assert res["status"] == "planned"
    assert any(w["link"].endswith(VENV_REL) for w in res["would_wire"])
    assert not (wt / VENV_REL).exists() and not (wt / VENV_REL).is_symlink()


def test_a_real_venv_in_the_worktree_is_never_clobbered(tmp_path):
    primary, wt = _primary_with_venv(tmp_path)
    real = wt / VENV_REL
    (real / "bin").mkdir(parents=True)
    (real / "bin" / "KEEP").write_text("mine")
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    res = T.task_branch(action="start", slug="feat-v", confirm=True, verbose=True, wire_env=True,
                        primary_root=str(primary), run=fake)
    assert real.is_dir() and not real.is_symlink() and (real / "bin" / "KEEP").read_text() == "mine"
    assert any(s["link"].endswith(VENV_REL) and "real .venv already present" in s["reason"] for s in res["skipped"])


def test_a_primary_without_a_venv_reports_the_exact_command_to_create_it(tmp_path):
    primary, wt = _primary_with_venv(tmp_path, venv=False)
    wire, skipped = T._plan_env_wiring(str(primary), str(wt), T.FsOps())
    assert not [w for w in wire if w["link"].endswith(VENV_REL)]
    reason = next(s["reason"] for s in skipped if s["link"].endswith(VENV_REL))
    tool = os.path.join(str(primary), "mcp", "noctusai")
    assert "primary toolkit .venv absent" in reason
    assert f"cd {tool} && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" in reason


def test_an_existing_symlink_is_replaced_like_ln_sfn(tmp_path):
    primary, wt = _primary_with_venv(tmp_path)
    stale = wt / VENV_REL
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.symlink_to(tmp_path / "somewhere-else")
    fake = FakeGit(refs={"origin/dev": "d0"}, anc=_anc_pairs([]))
    T.task_branch(action="start", slug="feat-v", confirm=True, verbose=True, wire_env=True, primary_root=str(primary), run=fake)
    assert os.path.realpath(stale) == os.path.realpath(primary / VENV_REL)
