"""Regression tests: `dead_function` must not tell us to delete our own gates.

THE BUG (2026-08-10)
--------------------
`scan_optimizations` reported 21 HIGH-severity `dead_function` findings, 8 of
them on `tools/noctus/dev/compliance.py` — including
`check_primary_checkout_commit` and `check_tunnel_ingress_snapshot_sync`, the
keepers that enforce self-branching mode and the tunnel ingress contract. Each
came with `"Verify cross-module callers via grep, then delete."`

They were never dead. The reference universe was `tools/noctus/` only, but
nothing in `tools/` calls a keeper — the callers are `mcp/noctusai/cli.py`
(flag → `from tools.noctus.dev.compliance import ...`), `mcp/noctusai/tests/`,
and `scripts/hooks/pre-commit`. All three sit outside the scanned tree.

Two independent causes, two fixes, one test file:
  1. the reference universe excluded the consumers  → `_REF_ROOTS`
  2. `__all__` is a list of STRING constants, so an exported-but-uncalled
     public symbol has no `ast.Name` node anywhere → `_module_exports`

The asymmetry that justifies both: findings still come only from `tools_dir`,
so widening references can only REMOVE findings. For a detector whose
suggestion is "delete this", a false positive costs a deleted safety net and a
false negative costs one surviving dead function.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.seed import scan_optimizations as so

# The exact keepers the broken detector wanted deleted. Named literally so a
# future refactor that renames one has to come here and think.
#
# 2026-08-14 — `check_migration_number_collision` REMOVED, and the removal is
# the point of this note. It stopped being a valid SPECIMEN because the
# migration-number reservation work (`c164d560`) made `scaffold_migration.py`
# and `task_branch.py` reference it from inside `tools/`. It is now genuinely
# tree-visible, so it can no longer demonstrate the narrow-universe false
# positive this module exists to pin. The test below detected that itself and
# said "rewrite it against a keeper that still isn't" — this is that rewrite,
# not a silenced failure. Six specimens remain, and the emptiness guard below
# stops this list being whittled to nothing by repeating the manoeuvre.
KEEPERS_THAT_WERE_REPORTED_DEAD = [
    "check_primary_checkout_commit",
    "check_tunnel_ingress_snapshot_sync",
    "check_branch_tree_mirror",
    "check_conflict_markers",
    "check_codification_pipeline_health",
    "check_postgrest_schema_qualified_table",
]


@pytest.fixture(scope="module")
def tools_files():
    return so._walk_python_files(so._DEFAULT_TOOLS_DIR)


class TestReferenceUniverse:
    def test_tools_tree_is_not_empty(self, tools_files):
        """Guards the guard: `_SKIP_DIRS` matches against every part of an
        ABSOLUTE path, so one careless entry (`.claude`) made the scanner walk
        zero files whenever it ran from a self-branching worktree — a green
        report produced by scanning nothing. Caught exactly that way."""
        assert len(tools_files) > 50, (
            f"only {len(tools_files)} python files found under "
            f"{so._DEFAULT_TOOLS_DIR} — check _SKIP_DIRS for an entry that "
            "matches a parent directory of the repo itself"
        )

    def test_specimen_list_is_not_empty(self):
        """Guards the guard, again. Removing a specimen that legitimately went
        tree-visible (see the 2026-08-14 note) is correct; emptying the list by
        repeating that is not — both assertions below pass vacuously on an
        empty list, so attrition would silently retire this whole module."""
        assert len(KEEPERS_THAT_WERE_REPORTED_DEAD) >= 3, (
            f"only {len(KEEPERS_THAT_WERE_REPORTED_DEAD)} specimen(s) left to "
            "demonstrate the narrow-universe false positive — add a "
            "currently-unreferenced keeper rather than shrinking the list"
        )

    def test_consumer_roots_exist(self):
        assert any(r.is_dir() for r in so._REF_ROOTS), (
            f"none of {so._REF_ROOTS} exist — the widening is a no-op"
        )

    def test_keeper_names_absent_from_the_old_narrow_universe(self, tools_files):
        """Pins the CAUSE, not just the symptom: with references harvested
        from the scanned tree alone, these names really are unreferenced.
        If this ever starts failing, the false positive fixed itself for some
        other reason and the test below no longer proves what it claims."""
        narrow = so._build_tree_wide_refs(tools_files, ref_roots=())
        for name in KEEPERS_THAT_WERE_REPORTED_DEAD:
            assert name not in narrow, (
                f"{name} is now referenced inside tools/ — this test's premise "
                "is stale, rewrite it against a keeper that still isn't"
            )

    def test_keeper_names_present_once_consumers_are_included(self, tools_files):
        wide = so._build_tree_wide_refs(tools_files)
        missing = [n for n in KEEPERS_THAT_WERE_REPORTED_DEAD if n not in wide]
        assert not missing, f"consumer roots do not reach: {missing}"


class TestDeadFunctionOnTheRealTree:
    def test_no_compliance_keeper_is_reported_dead(self):
        """THE regression. Any finding on compliance.py is a finding that says
        'delete a keeper' — there must be none."""
        result = so.scan_optimizations(
            include_detectors=["dead_function"], min_severity="info"
        )
        offenders = [
            f["name"] for f in result["findings"] if "compliance.py" in f["file"]
        ]
        assert not offenders, (
            "dead_function wants these compliance keepers deleted: " + str(offenders)
        )

    def test_survivors_are_few_and_private(self):
        """The detector must still WORK — this is not a blanket mute. What
        survives should be a short list of genuinely uncalled helpers."""
        result = so.scan_optimizations(
            include_detectors=["dead_function"], min_severity="info"
        )
        assert len(result["findings"]) < 10, (
            "dead_function got noisy again: "
            + str([f["name"] for f in result["findings"]])
        )


class TestModuleExports:
    """`__all__` membership is a declaration that a symbol is public API."""

    def test_extracts_list_of_string_constants(self):
        tree = ast.parse('__all__ = ["alpha", "beta"]\ndef alpha(): pass\n')
        assert so._module_exports(tree) == {"alpha", "beta"}

    def test_extracts_tuple_form(self):
        assert so._module_exports(ast.parse('__all__ = ("a", "b")')) == {"a", "b"}

    def test_annotated_assignment_form(self):
        tree = ast.parse('__all__: list[str] = ["a"]')
        assert so._module_exports(tree) == {"a"}

    def test_ignores_non_string_and_dynamic_forms(self):
        """A computed `__all__` is not something we can read statically —
        return nothing rather than guess (no silent wrong answer)."""
        assert so._module_exports(ast.parse("__all__ = _build_exports()")) == set()
        assert so._module_exports(ast.parse("__all__ = [SOME_CONST]")) == set()

    def test_no_all_at_all(self):
        assert so._module_exports(ast.parse("def f(): pass")) == set()

    def test_exported_function_is_not_dead(self, tmp_path):
        """End-to-end on a synthetic file: uncalled + exported → not reported."""
        f = tmp_path / "mod.py"
        f.write_text(
            "__all__ = ['public_api']\n\n\n"
            "def public_api():\n" + "    pass\n" * 12 + "\n\n"
            "def truly_dead():\n" + "    pass\n" * 12
        )
        names = {
            x["name"]
            for x in so._scan_one_file(f, tree_wide_refs=set())
            if x["detector"] == "dead_function"
        }
        assert names == {"truly_dead"}
