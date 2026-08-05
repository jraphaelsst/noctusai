"""Regression tests for check_primary_checkout_commit.

THE INCIDENT THIS ENCODES
─────────────────────────
`CLAUDE.md` §1 has carried "🔴 ABSOLUTE: never work on `dev`" since
self-branching mode was introduced, and `.claude/skills/noc-self-branch`
restates it as step 0. The rule was violated in essentially every session
regardless — twice in the 2026-08-04/05 session alone, by an agent with the
rule in its context both times.

The reason is mechanical, not motivational: **nothing fails at commit time.**
`git commit` on `dev` in the primary checkout succeeds, every hook passes,
every test passes. Local `dev` diverges from `origin/dev` silently, and the
cost lands minutes-to-hours later as:

    hint: Diverging branches can't be fast-forwarded

at integrate or deploy — far from the cause, and reading like a git problem
rather than the process slip it actually is. That gap between the mistake and
its symptom is precisely what a gate closes and a reminder cannot.

WHY EVERY INPUT IS INJECTED
───────────────────────────
The forbidden state is "primary checkout, on a shared branch, with staged work".
A test cannot create that honestly — it would have to check out `dev` in the
real repo and stage files there, which is the very thing being forbidden, and
would corrupt the developer's tree. So the detector takes `is_primary`,
`branch` and `staged` as parameters and the tests drive those directly.

KB § PATTERNS/common/self-branching-mode.md ·
KB § PATTERNS/common/gate-methodology-sync.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    SHARED_BRANCHES,
    check_primary_checkout_commit,
)

WORK = ["products/social-wiring/backend/app/main.py"]
LEDGER = ["project-history/branch-tree.ndjson"]


def _check(**kw):
    kw.setdefault("is_primary", True)
    kw.setdefault("branch", "dev")
    kw.setdefault("staged", WORK)
    kw.setdefault("allow_override", False)
    return check_primary_checkout_commit(**kw)


# ── the block ──────────────────────────────────────────────────────────────

def test_work_on_dev_in_the_primary_checkout_is_blocked():
    """🔴 THE incident. If this stops failing, the slip is live again."""
    found = _check()
    assert len(found) == 1
    assert found[0]["severity"] == "high"
    assert "dev" in found[0]["issue"]
    # The message must name the remedy, not just the sin — an agent reading it
    # mid-commit needs the next command, not a lecture.
    assert "task_branch" in found[0]["issue"]


def test_every_shared_branch_is_guarded_not_just_dev():
    for branch in SHARED_BRANCHES:
        assert _check(branch=branch), f"{branch} was not guarded"
    assert {"dev", "main", "prod"} <= SHARED_BRANCHES


def test_the_finding_names_the_offending_files():
    found = _check(staged=["a.py", "b.py"])
    assert "a.py" in found[0]["file"] and "b.py" in found[0]["file"]


def test_a_long_file_list_is_summarised_not_dumped():
    found = _check(staged=[f"f{i}.py" for i in range(12)])
    assert "+8 more" in found[0]["file"]


# ── the permitted cases ────────────────────────────────────────────────────

def test_a_worktree_commit_is_always_fine():
    """The whole point: work belongs in a worktree, so a worktree never trips."""
    assert _check(is_primary=False) == []
    assert _check(is_primary=False, branch="dev", staged=WORK) == []


def test_a_feature_branch_in_the_primary_checkout_is_fine():
    """Guarding SHARED branches, not the checkout itself. Someone working on a
    feat/* branch in the primary tree is not causing divergence."""
    assert _check(branch="feat/whatever") == []


def test_a_LEDGER_ONLY_commit_on_dev_is_the_sanctioned_exception():
    """`branch_pointer` and the salvage/cost ledgers commit straight to dev
    from the primary checkout BY DESIGN. Blocking those would break the tools
    that make parallel agents coordinate."""
    assert _check(staged=LEDGER) == []
    assert _check(staged=LEDGER + ["project-history/vector-costs.ndjson"]) == []


def test_work_MIXED_INTO_a_ledger_commit_is_still_blocked():
    """🔴 The exemption must not be launderable. Staging one source file
    alongside the ledgers is exactly how "it's just a ledger commit" would
    become a hole big enough to drive the original slip through."""
    found = _check(staged=LEDGER + WORK)
    assert len(found) == 1
    assert "main.py" in found[0]["file"]
    assert "branch-tree.ndjson" not in found[0]["file"]  # only the work is named


def test_an_empty_commit_is_not_flagged():
    assert _check(staged=[]) == []


# ── the escape hatch ───────────────────────────────────────────────────────

def test_the_explicit_override_is_honoured():
    """There are real emergencies. The hatch is an env var rather than a flag
    so it cannot be baked into a script and forgotten."""
    assert _check(allow_override=True) == []


def test_the_override_is_off_by_default(monkeypatch):
    monkeypatch.delenv("NOCTUS_ALLOW_PRIMARY_COMMIT", raising=False)
    assert check_primary_checkout_commit(
        is_primary=True, branch="dev", staged=WORK
    ), "the guard must be on unless deliberately disabled"


def test_the_env_var_enables_the_override(monkeypatch):
    monkeypatch.setenv("NOCTUS_ALLOW_PRIMARY_COMMIT", "1")
    assert check_primary_checkout_commit(
        is_primary=True, branch="dev", staged=WORK
    ) == []


def test_a_non_1_env_value_does_NOT_enable_the_override(monkeypatch):
    """`=0`, `=false` and `=""` must all keep the guard ON. A truthy-string
    check would turn `NOCTUS_ALLOW_PRIMARY_COMMIT=0` into a bypass."""
    for value in ("0", "false", "no", ""):
        monkeypatch.setenv("NOCTUS_ALLOW_PRIMARY_COMMIT", value)
        assert check_primary_checkout_commit(
            is_primary=True, branch="dev", staged=WORK
        ), f"value {value!r} wrongly disabled the guard"


# ── never block on a broken probe ──────────────────────────────────────────

def test_a_missing_repo_root_does_not_explode():
    assert check_primary_checkout_commit(
        repo_root=Path("/nonexistent/xyz"), is_primary=True,
        branch="dev", staged=WORK, allow_override=False,
    )  # injected inputs still evaluate; the point is it does not raise
