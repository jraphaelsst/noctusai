"""`node_toolchain.resolve` — the ONE node/ts-morph/PGlite resolver every AST-scan keeper shares.

Recurring refusal (N>=4, 2026-11-14/15): worktrees and scrubbed checkouts have no `mcp/noctusai/node/node_modules`, so the
ts-morph keepers refused merge commits until an engineer hand-symlinked the primary's install. The contract under test:
own install -> use it; else a matching primary (byte-identical package-lock.json) -> link it; else a LOUD reason naming
the exact `npm ci`. A mismatched install is never borrowed silently, and every keeper goes through this one resolver.
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import node_toolchain as NT  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DEV = REPO / "mcp" / "noctusai" / "tools" / "noctus" / "dev"


def _node(root: Path, lock: str, *, pkgs: tuple[str, ...] = ("ts-morph",)) -> Path:
    d = root.joinpath(*NT.NODE_REL)
    d.mkdir(parents=True)
    (d / "package-lock.json").write_text(lock)
    for p in pkgs:
        (d / "node_modules" / p).mkdir(parents=True)
    return d


class TestResolve:
    def test_own_install_is_used_as_is(self, tmp_path):
        _node(tmp_path / "wt", "L")
        tc = NT.resolve(tmp_path / "wt", sources=[])
        assert tc.ok and tc.source == "own" and tc.reason == ""

    def test_worktree_without_node_modules_and_a_matching_primary_resolves(self, tmp_path):
        _node(tmp_path / "primary", "L")
        wt = tmp_path / "wt"
        _node(wt, "L", pkgs=())
        tc = NT.resolve(wt, sources=[tmp_path / "primary"])
        assert tc.ok and tc.source == "linked"
        assert (wt.joinpath(*NT.NODE_REL) / "node_modules" / "ts-morph").exists()
        assert tc.invocation(wt / "s.mjs") == (["node", str(wt / "s.mjs")], None)

    def test_a_lockfile_mismatch_is_a_loud_error_never_a_silent_borrow(self, tmp_path):
        _node(tmp_path / "primary", "lock-a")
        wt = tmp_path / "wt"
        _node(wt, "lock-b", pkgs=())
        tc = NT.resolve(wt, sources=[tmp_path / "primary"])
        assert not tc.ok and tc.source == ""
        assert "differs" in tc.reason and f"npm ci --prefix {wt.joinpath(*NT.NODE_REL)}" in tc.reason
        assert not (wt.joinpath(*NT.NODE_REL) / "node_modules").exists(), "a mismatched install must never be linked"

    def test_a_missing_lockfile_in_the_worktree_is_unverifiable_so_loud(self, tmp_path):
        _node(tmp_path / "primary", "L")
        wt = tmp_path / "wt"
        wt.joinpath(*NT.NODE_REL).mkdir(parents=True)
        tc = NT.resolve(wt, sources=[tmp_path / "primary"])
        assert not tc.ok and "cannot compare" in tc.reason

    def test_a_primary_that_was_never_installed_says_so(self, tmp_path):
        _node(tmp_path / "primary", "L", pkgs=())
        wt = tmp_path / "wt"
        _node(wt, "L", pkgs=())
        tc = NT.resolve(wt, sources=[tmp_path / "primary"])
        assert not tc.ok and "is not installed" in tc.reason and "npm ci --prefix" in tc.reason

    def test_no_source_at_all_names_the_npm_ci_command(self, tmp_path):
        wt = tmp_path / "wt"
        _node(wt, "L", pkgs=())
        tc = NT.resolve(wt, sources=[])
        assert not tc.ok and f"npm ci --prefix {wt.joinpath(*NT.NODE_REL)}" in tc.reason

    def test_a_required_package_missing_from_an_own_install_is_not_ready(self, tmp_path):
        wt = tmp_path / "wt"
        _node(wt, "L", pkgs=("other",))
        tc = NT.resolve(wt, sources=[])
        assert not tc.ok and "ts-morph" in tc.reason

    def test_require_selects_the_package(self, tmp_path):
        _node(tmp_path / "primary", "L", pkgs=("@electric-sql/pglite",))
        wt = tmp_path / "wt"
        _node(wt, "L", pkgs=())
        assert NT.resolve(wt, require=("@electric-sql/pglite",), sources=[tmp_path / "primary"]).ok
        assert not NT.resolve(tmp_path / "wt2", sources=[tmp_path / "primary"]).ok

    def test_link_false_borrows_through_the_invocation_and_touches_nothing(self, tmp_path):
        _node(tmp_path / "primary", "L")
        wt = tmp_path / "wt"
        _node(wt, "L", pkgs=())
        script = wt / "s.mjs"
        script.write_text("// stub\n")
        tc = NT.resolve(wt, link=False, sources=[tmp_path / "primary"])
        assert tc.ok and tc.source == "borrowed"
        argv, cwd = tc.invocation(script)
        assert argv[:3] == ["node", "--input-type=module", "-e"] and argv[3] == "// stub\n"
        assert cwd == tmp_path / "primary" / Path(*NT.NODE_REL)
        assert not (wt.joinpath(*NT.NODE_REL) / "node_modules").exists()

    def test_a_dangling_link_is_replaced_but_a_real_directory_is_never_touched(self, tmp_path):
        _node(tmp_path / "primary", "L")
        wt = tmp_path / "wt"
        d = _node(wt, "L", pkgs=())
        (d / "node_modules").symlink_to(tmp_path / "gone", target_is_directory=True)
        assert NT.resolve(wt, sources=[tmp_path / "primary"]).source == "linked"
        wt2 = tmp_path / "wt2"
        d2 = _node(wt2, "L", pkgs=("other",))
        tc = NT.resolve(wt2, sources=[tmp_path / "primary"])
        assert (d2 / "node_modules" / "other").is_dir() and not (d2 / "node_modules").is_symlink()
        assert tc.source == "borrowed"

    @pytest.mark.skipif(shutil.which("git") is None, reason="NOT RUN: git unavailable")
    def test_the_primary_is_found_through_the_git_common_dir(self, tmp_path):
        primary = tmp_path / "primary"
        _node(primary, "lock-fixture")
        run = lambda *a, cwd=primary: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)  # noqa: E731
        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.invalid")
        run("config", "user.name", "t")
        (primary / ".gitignore").write_text("node_modules/\n")
        run("add", ".")
        run("commit", "-q", "-m", "init")
        wt = tmp_path / "wt"
        run("worktree", "add", "-q", str(wt), "-b", "feat/x")
        assert not (wt.joinpath(*NT.NODE_REL) / "node_modules").exists()
        tc = NT.resolve(wt)
        assert tc.ok and tc.source == "linked", tc.reason


class TestEveryKeeperUsesTheSharedResolver:
    """Static: the keepers resolve through `node_toolchain`, never by an ad-hoc `node` spawn of their own."""

    KEEPERS = ("compliance.py", "polling_request_budget.py", "ts_ast_edit.py", "migration_replay.py", "release_steward.py")

    @pytest.mark.parametrize("name", KEEPERS)
    def test_the_module_calls_node_toolchain(self, name):
        tree = ast.parse((DEV / name).read_text(encoding="utf-8"))
        used = {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
        assert used & {"_node_toolchain", "node_toolchain"}, f"{name} does not use node_toolchain"

    @pytest.mark.parametrize("name", ("compliance.py", "polling_request_budget.py"))
    def test_no_ad_hoc_node_spawn_is_left_in_the_scan_keepers(self, name):
        tree = ast.parse((DEV / name).read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "run" and n.args:
                a0 = n.args[0]
                assert not (isinstance(a0, ast.List) and a0.elts and isinstance(a0.elts[0], ast.Constant)
                            and a0.elts[0].value == "node"), f"{name}:{n.lineno} spawns node by hand"

    def test_silent_refusal_scan_fails_loud_on_a_lockfile_mismatch(self, tmp_path):
        if shutil.which("node") is None:
            pytest.skip("NOT RUN: node unavailable")
        from tools.noctus.dev import compliance

        d = tmp_path.joinpath(*NT.NODE_REL)
        d.mkdir(parents=True)
        shutil.copy(REPO.joinpath(*NT.NODE_REL, "silent_refusal_scan.mjs"), d)
        (d / "package-lock.json").write_text(json.dumps({"different": True}))
        f = tmp_path / "x.tsx"
        f.write_text("export const x = 1;\n")
        results, errors, boot = compliance.silent_refusal_scan([f], root=tmp_path)
        assert results == {} and boot is not None and boot.startswith("ts_morph_not_installed")
        assert "npm ci --prefix" in boot


class TestTaskBranchWiresOnlyAMatchingToolkitInstall:
    def _plan(self, tmp_path, lock_p, lock_w):
        from tools.noctus.dev import task_branch as T

        primary, wt = tmp_path / "primary", tmp_path / "wt"
        _node(primary, lock_p)
        _node(wt, lock_w, pkgs=())
        wire, skipped = T._plan_env_wiring(str(primary), str(wt), T.FsOps())
        return [w for w in wire if w["link"].endswith("node/node_modules")], skipped

    def test_matching_lockfiles_wire(self, tmp_path):
        wired, skipped = self._plan(tmp_path, "L", "L")
        assert [w["kind"] for w in wired] == ["node_modules"] and not [s for s in skipped if "package-lock" in s["reason"]]

    def test_a_differing_lockfile_plans_a_loud_install_never_a_borrow_and_never_a_silent_skip(self, tmp_path):
        wired, skipped = self._plan(tmp_path, "L1", "L2")
        assert [w["kind"] for w in wired] == ["node_install"] and "package-lock.json differs" in wired[0]["why"]
        assert not [s for s in skipped if s["link"].endswith("node/node_modules")]
