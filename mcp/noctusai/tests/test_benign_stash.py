"""Tests for the shared benign-refresh-artifact stash helper.

`_benign_stash` is the N=2 DRY lift of "classify dirty files benign-vs-real →
stash the benign ones → rebase → pop", previously implemented only inside
`task_branch.integrate` while `_ledger_push`'s identical rebase leg went without
it (the primary/origin divergence loop, fixed 2026-08-31).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tools.noctus.dev._benign_stash as BS  # noqa: E402


class TestStripStatusCode:
    """The path must never be silently truncated — a mangled path misclassifies
    as real work and blocks the rebase for a reason nobody can see."""

    def test_canonical_porcelain_forms(self):
        assert BS.strip_status_code(" M project-history/vector-costs.ndjson") == \
            "project-history/vector-costs.ndjson"
        assert BS.strip_status_code("M  project-history/vector-costs.ndjson") == \
            "project-history/vector-costs.ndjson"
        assert BS.strip_status_code("MM project-history/vector-costs.ndjson") == \
            "project-history/vector-costs.ndjson"
        assert BS.strip_status_code("?? some/new/file.py") == "some/new/file.py"

    def test_single_space_variant_is_not_truncated(self):
        """A fixed 3-char offset turns 'M path' into 'th' garbage. Regression pin:
        several existing test fakes emit this non-canonical shape, and the old
        parser silently corrupted it into a path that matched nothing."""
        got = BS.strip_status_code("M project-history/branch-tree.ndjson")
        assert got == "project-history/branch-tree.ndjson", got
        assert BS.is_benign(got), "a correctly-parsed ledger path must be benign"

    def test_rename_form_keeps_the_destination(self):
        assert BS.strip_status_code("R  old/path.py -> new/path.py") == "new/path.py"


class TestClassification:
    def test_ledger_and_cache_artifacts_are_benign(self):
        out = (" M project-history/vector-costs.ndjson\n"
               " M project-history/auto-improvement.ndjson\n"
               " M project-history/worktree-salvage.ndjson\n"
               " M project-history/branch-tree.ndjson\n"
               " M KNOWLEDGE-BASE/AGENT-CONTEXT.md\n"
               " M .claude/cache/noc-graph.json\n")
        benign, real = BS.classify_porcelain(out)
        assert len(benign) == 6 and real == [], (benign, real)

    def test_real_work_is_never_benign(self):
        out = (" M project-history/vector-costs.ndjson\n"
               " M products/social-wiring/backend/app/main.py\n")
        benign, real = BS.classify_porcelain(out)
        assert benign == ["project-history/vector-costs.ndjson"]
        assert real == ["products/social-wiring/backend/app/main.py"]

    def test_status_failure_is_treated_as_real_dirt(self):
        """Conservative by construction: if we cannot read the tree we must not
        assume it is clean."""
        benign, real = BS.classify_dirty(lambda *a: (1, "", "boom"))
        assert benign == [] and real == ["<git-status-failed>"]


class TestStashLegs:
    def test_nothing_to_stash_is_a_success(self):
        calls = []
        assert BS.stash_benign(lambda *a: calls.append(a) or (0, "", ""), []) is True
        assert calls == [], "must not issue a stash for an empty set"

    def test_stash_targets_only_the_named_paths(self):
        calls = []

        def run(*a):
            calls.append(a)
            return 0, "", ""

        assert BS.stash_benign(run, ["project-history/vector-costs.ndjson"]) is True
        (args,) = calls
        assert args[0] == "stash" and args[1] == "push"
        assert "--" in args and args[-1] == "project-history/vector-costs.ndjson"

    def test_stash_failure_reports_false_rather_than_pretending(self):
        assert BS.stash_benign(lambda *a: (1, "", "nope"),
                               ["project-history/vector-costs.ndjson"]) is False

    def test_pop_failure_never_raises(self):
        BS.pop_stash(lambda *a: (1, "", "conflict"))  # must not raise


class TestDirtyBlockedResult:
    def test_names_the_files_and_says_what_to_do(self):
        res = BS.dirty_blocked_result(["a/b.py", "c/d.py"], "origin/dev")
        assert res["ok"] is False
        assert res["status"] == "dirty_blocked"
        assert res["committed_locally"] is True
        assert res["dirty_files"] == ["a/b.py", "c/d.py"]
        assert "a/b.py" in res["error"] and "origin/dev" in res["error"]

    def test_long_lists_are_truncated_but_flagged(self):
        res = BS.dirty_blocked_result([f"f{i}.py" for i in range(20)], "origin/dev")
        assert "…" in res["error"]
        assert len(res["dirty_files"]) == 20, "the full list stays in the payload"
