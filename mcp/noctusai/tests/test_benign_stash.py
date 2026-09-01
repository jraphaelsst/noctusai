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


# ── The third bug (2026-09-01): the list itself was hand-maintained ────────────
#
# `BENIGN_REFRESH_PATTERNS` started as four hand-copied `project-history/*.ndjson`
# filenames plus two hand-copied KB paths. The pre-commit hook's own KB-counts
# regenerator (`kb_sync.update_kb_counts`, step 2) rewrites THREE marker-block
# targets — AGENT-CONTEXT.md, 06-AGENTS.md, AND 02-LANDSCAPE.md — and only the
# first two were ever copied in; `branch_pointer.py` writes its ledger AND a
# byte-identical mirror atomically, and only the ledger name was copied in. Both
# gaps refused a genuinely-clean-to-rebase primary checkout exactly like the
# `vector-costs.ndjson` bug this module already fixed once, one file over.
class TestPreFixRegressionProof:
    """Pins the EXACT pre-fix hand-copied tuple as it existed before this
    derivation landed (copied verbatim from the module's prior revision) and
    proves BOTH halves of the fix against it: the gap was real (the pre-fix
    list says False), and it is closed now (the live derived default says
    True). A test that only asserts the post-fix state can't tell a real fix
    from one that never mattered — this is the fail-before/pass-after proof
    the change itself requires."""

    _PRE_FIX_HAND_COPIED_PATTERNS = (
        "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
        "KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md",
        "project-history/vector-costs.ndjson",
        "project-history/auto-improvement.ndjson",
        "project-history/worktree-salvage.ndjson",
        "project-history/branch-tree.ndjson",
        ".claude/cache/*",
    )

    def test_02_landscape_was_a_real_gap_in_the_old_list(self):
        assert BS.is_benign(
            "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md",
            self._PRE_FIX_HAND_COPIED_PATTERNS,
        ) is False, "control failed: 02-LANDSCAPE.md must NOT be benign under the pre-fix list"

    def test_branch_tree_mirror_was_a_real_gap_in_the_old_list(self):
        assert BS.is_benign(
            "project-history/branch-tree.mirror.ndjson",
            self._PRE_FIX_HAND_COPIED_PATTERNS,
        ) is False, "control failed: the mirror must NOT be benign under the pre-fix list"

    def test_02_landscape_is_benign_under_the_live_derived_default(self):
        assert BS.is_benign("KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md") is True

    def test_branch_tree_mirror_is_benign_under_the_live_derived_default(self):
        assert BS.is_benign("project-history/branch-tree.mirror.ndjson") is True


class TestKbCountsDerivationGate:
    """THE GATE. Cross-checks `is_benign()` against `kb_sync`'s OWN live
    manifest (`_regions()`) — the SAME thing `scripts/hooks/pre-commit` step 2
    walks to decide what to `git add`. This is not a re-assertion of the
    production derivation against itself: it independently re-derives the
    manifest from `kb_sync` (a module `_benign_stash` does not otherwise
    control) and checks the OUTCOME. If a future edit to either module drifts
    them apart — say, `_benign_stash` reverts to a hand-copied list, or
    `kb_sync` adds a 4th marker-block target on a file with no benign
    coverage at all — this fails, which is exactly the FOURTH recurrence the
    task's gate requirement exists to catch before it strands a commit."""

    def test_every_kb_counts_region_target_is_benign(self):
        import pathlib
        import sys as _sys

        _sys.path.insert(0, str(pathlib.Path(BS.__file__).resolve().parents[1]))
        from settings import REPO_ROOT
        from tools.kb_sync import _regions

        repo = pathlib.Path(REPO_ROOT)
        targets = {
            str(path.relative_to(repo))
            for _region, (path, _renderer) in _regions(repo).items()
        }
        assert targets, "kb_sync._regions() returned nothing — the gate has nothing to check"
        assert "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md" in targets, (
            "sanity: 02-LANDSCAPE.md must still be one of kb_sync's own targets")
        not_benign = [t for t in targets if not BS.is_benign(t)]
        assert not not_benign, (
            f"kb_sync regenerates {not_benign} but is_benign() does not cover "
            f"{not_benign} — a rebase will refuse the moment the hook rewrites it")


class TestBranchTreeMirrorDerivationGate:
    """Sibling gate for the ledger half: cross-checks `is_benign()` against
    `branch_pointer`'s OWN ledger + mirror path constants — genuinely
    independent of `_benign_stash`'s production code (which derives the ledger
    coverage from a directory-wide glob, not from importing `branch_pointer`
    at all, to avoid the import cycle documented in `_benign_stash.py`)."""

    def test_ledger_and_mirror_paths_are_both_benign(self):
        import pathlib
        import sys as _sys

        _sys.path.insert(0, str(pathlib.Path(BS.__file__).resolve().parents[1]))
        from tools.noctus.dev.branch_pointer import LEDGER_REL, MIRROR_REL

        assert MIRROR_REL.endswith("branch-tree.mirror.ndjson")  # sanity
        assert BS.is_benign(LEDGER_REL) is True
        assert BS.is_benign(MIRROR_REL) is True


class TestWidenedGlobStillBlocksRealWork:
    """The property that must survive widening one literal filename into a
    directory-wide glob: content that merely LIVES beside the ledgers, but is
    not one of them, must still block. Stashing is safe for a machine-written
    append-only ledger (pop restores it losslessly); it is NOT an acceptable
    outcome for a human/agent's in-progress edit that happens to sit in the
    same directory."""

    def test_a_hand_authored_roadmap_doc_under_project_history_still_real(self):
        benign, real = BS.classify_porcelain(
            " M project-history/roadmaps/some-active-roadmap.md\n"
        )
        assert benign == [] and real == ["project-history/roadmaps/some-active-roadmap.md"]

    def test_a_novel_ndjson_dropped_beside_the_known_ledgers_is_still_stashable_not_lost(self):
        """The glob DOES cover a brand-new `project-history/*.ndjson` file —
        that is the whole point of generalizing away from one-literal-per-
        filename. Stashing is not discarding: `stash_benign` + `pop_stash`
        round-trip the content, so a genuinely novel ledger surviving the
        stash is the expected, safe outcome, not silent data loss."""
        assert BS.is_benign("project-history/some-new-agent-ledger.ndjson") is True

    def test_source_code_and_docs_outside_project_history_are_unaffected(self):
        for path in (
            "products/social-wiring/backend/app/main.py",
            "mcp/noctusai/tools/noctus/dev/task_branch.py",
            "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/self-branching-mode.md",
        ):
            assert BS.is_benign(path) is False, f"{path} must never classify as benign"
