"""Unit tests for the shared `_worktree_staleness` predicate.

The helper holds the merged-base + is-merged core extracted from
`cleanup_worktrees.py` AND `mole.py` (the documented N=2 DRY dup). Every git
call routes through an injectable `run` callable returning `(rc, stdout, stderr)`
(mirroring `release.py`), so these tests drive every path with ZERO real git via
a scripted fake runner — no monkey-patching of our own code.

Real-git integration parity (ancestry / patch-id against a live repo) is still
covered by `test_cleanup_worktrees.py` + `test_mole_tool.py`, which build real
worktrees.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _worktree_staleness as wts


class FakeRunner:
    """A scripted git runner. Maps a git-args tuple → (rc, stdout, stderr).

    `calls` records every invocation so tests can assert which base ref the
    helper actually probed (the dev-keying assertion)."""

    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]]):
        self._responses = responses
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str]) -> tuple[int, str, str]:
        key = tuple(args)
        self.calls.append(key)
        # Default: command "succeeds" with no output unless scripted otherwise.
        return self._responses.get(key, (0, "", ""))


# ───────────────────────── base resolution ─────────────────────────────
def test_base_resolves_to_origin_dev_when_present():
    runner = FakeRunner({
        ("git", "rev-parse", "--verify", "--quiet", "origin/dev"): (0, "abc\n", ""),
    })
    assert wts.resolve_merged_base(runner) == "origin/dev"
    # It probed origin/dev — NOT origin/main (the dev-keying guarantee).
    assert ("git", "rev-parse", "--verify", "--quiet", "origin/dev") in runner.calls
    assert wts.PREFERRED_BASE == "origin/dev"


def test_base_falls_back_to_dev_when_origin_dev_absent():
    runner = FakeRunner({
        ("git", "rev-parse", "--verify", "--quiet", "origin/dev"): (1, "", ""),
    })
    assert wts.resolve_merged_base(runner) == "dev"
    assert wts.FALLBACK_BASE == "dev"


# ───────────────────────── merged predicate ────────────────────────────
def test_is_merged_true_on_sha_ancestry():
    # merge-base --is-ancestor returns 0 → SHA-merged; cherry is never reached.
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (0, "", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is True
    # cherry must not have been consulted once ancestry short-circuits.
    assert not any(c[:2] == ("git", "cherry") for c in runner.calls)


def test_is_merged_true_on_patch_id_when_not_ancestor():
    # Not a SHA ancestor, but `git cherry` reports ZERO '+' lines and the
    # branch has ≥1 commit → patch-id merged (the cherry-pick case).
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (1, "", ""),
        ("git", "cherry", "origin/dev", "br"): (0, "- aaaa\n- bbbb\n", ""),
        ("git", "log", "--oneline", "origin/dev..br"): (0, "aaaa x\nbbbb y\n", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is True


def test_is_merged_false_on_genuinely_unmerged_branch():
    # Not an ancestor; cherry shows a '+' line → genuinely unmerged → KEPT.
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (1, "", ""),
        ("git", "cherry", "origin/dev", "br"): (0, "+ cccc\n- dddd\n", ""),
        ("git", "log", "--oneline", "origin/dev..br"): (0, "cccc z\ndddd w\n", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is False


def test_is_merged_false_when_branch_has_no_commits_and_cherry_empty():
    # No '+' lines BUT zero total commits → NOT merged (mirrors the
    # `total > 0` guard — an empty diff is not a "merged" signal here).
    runner = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "br", "origin/dev"): (1, "", ""),
        ("git", "cherry", "origin/dev", "br"): (0, "", ""),
        ("git", "log", "--oneline", "origin/dev..br"): (0, "", ""),
    })
    assert wts.is_merged(runner, "br", "origin/dev") is False


def test_all_commits_cherry_picked_false_when_cherry_errors():
    # `git cherry` non-zero rc (e.g. unknown ref) → not merged, never raises.
    runner = FakeRunner({
        ("git", "cherry", "origin/dev", "br"): (128, "", "fatal: bad revision"),
    })
    assert wts.all_commits_cherry_picked(runner, "br", "origin/dev") is False


def test_is_ancestor_reflects_returncode():
    yes = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "a", "b"): (0, "", ""),
    })
    no = FakeRunner({
        ("git", "merge-base", "--is-ancestor", "a", "b"): (1, "", ""),
    })
    assert wts.is_ancestor(yes, "a", "b") is True
    assert wts.is_ancestor(no, "a", "b") is False


# ───────────────────── default subprocess runner ───────────────────────
def _init_repo_on_dev(root: Path) -> None:
    import subprocess

    def g(*a: str) -> None:
        subprocess.run(["git", *a], cwd=str(root), check=True,
                       capture_output=True, text=True)

    g("init", "-q", "-b", "dev")
    g("config", "user.email", "t@t.t")
    g("config", "user.name", "t")
    (root / "f").write_text("x\n")
    g("add", "f")
    g("commit", "-qm", "init")


def test_make_subprocess_runner_executes_git(tmp_path):
    _init_repo_on_dev(tmp_path)
    runner = wts.make_subprocess_runner(tmp_path)
    rc, out, _err = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    assert rc == 0
    assert out.strip() == "dev"


def test_make_subprocess_runner_forwards_timeout(tmp_path):
    _init_repo_on_dev(tmp_path)
    runner = wts.make_subprocess_runner(tmp_path, timeout=60)
    rc, out, _err = runner(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    assert rc == 0 and out.strip() == "dev"


# ─────────────────── helper is NOT an MCP tool ──────────────────────────
def test_helper_exposes_no_register_and_is_not_in_register_all():
    # The helper must NOT be a tool (no register) and must NOT be wired into
    # register_all → the registered tool count is unchanged (zero tools added).
    assert not hasattr(wts, "register")

    import tools.noctus.dev as dev_pkg
    import inspect

    src = inspect.getsource(dev_pkg.register_all)
    assert "_worktree_staleness" not in src, (
        "_worktree_staleness must NOT be registered in register_all"
    )
