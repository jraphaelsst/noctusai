"""Colocated tests for noctus.dev.testing (noctus.dev.pytest / vite_build).

Regression tests for the 2026-07-20 harness bug: without `worktree_path`,
`run_product_tests` / `run_all_tests` / `build_product_frontend` /
`build_all_frontends` resolved `PRODUCTS_DIR` from the MCP server's
primary-tree startup CWD — silently testing/building the WRONG tree from
inside an engineer worktree. Confirmed live: `noctus.dev.pytest` reported
"689 passed" from the primary while the worktree's real suite was never run
(a false-green — the exact failure class the seed compliance methodology
exists to prevent).

`subprocess.run` is monkeypatched (no real pytest/venv/npx needed) — these
tests assert the `cwd` (+ `env["PYTHONPATH"]` for pytest) resolve to the
CALLER's worktree, not the primary, and that omitting `worktree_path` stays
scoped to the (monkeypatched) primary — the established
`resolve_caller_root` convention shared with `build_parallel` / `mole` /
`gen_promotions_index`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from tools.noctus.dev import testing as T  # noqa: E402


def _make_fake_worktree(tmp_path, name, *, slug="alpha"):
    """A fake worktree with a product backend/tests dir + seed backend dirs
    — enough for `_products_dir_for` + `_worktree_pythonpath` to resolve
    against. `resolve_caller_root` only checks EXISTENCE of `.git` + the
    marker file — no real git init needed (mirrors the lightweight fixture
    in test_mole_tool.py / test_auto_improvement.py)."""
    wt = tmp_path / name
    wt.mkdir(parents=True)
    (wt / ".git").write_text("gitdir: /nowhere\n")
    (wt / ".noctusai-workspace").write_text("test\n")
    backend = wt / "products" / slug / "backend"
    (backend / "tests").mkdir(parents=True)
    (wt / "seed" / "framework" / "backend").mkdir(parents=True)
    (wt / "seed" / "lib" / "backend").mkdir(parents=True)
    return wt


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="1 passed", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestPytestWorktreeScoping:
    def test_run_product_tests_scopes_cwd_and_pythonpath_to_worktree(self, tmp_path, monkeypatch):
        wt = _make_fake_worktree(tmp_path, "wt")
        captured = {}

        def fake_run(cmd, cwd, capture_output, text, timeout, env):
            captured["cwd"] = cwd
            captured["env"] = env
            return _FakeCompletedProcess()

        monkeypatch.setattr(T.subprocess, "run", fake_run)
        r = T.run_product_tests("alpha", worktree_path=str(wt))

        assert captured["cwd"] == str(wt / "products" / "alpha" / "backend")
        pythonpath = captured["env"]["PYTHONPATH"]
        assert str(wt / "seed" / "framework" / "backend") in pythonpath
        assert str(wt / "seed" / "lib" / "backend") in pythonpath
        assert r["resolved_root"] == str(wt)
        assert r["passed"] == 1

    def test_run_product_tests_defaults_to_primary_without_worktree_path(self, tmp_path, monkeypatch):
        # No worktree_path → resolves against the module-level PRODUCTS_DIR
        # (monkeypatched here) — the primary-default convention every other
        # worktree_path tool in the toolkit follows (build_parallel / mole /
        # gen_promotions_index): omission is never an error, just primary.
        primary = tmp_path / "primary"
        (primary / "products" / "alpha" / "backend" / "tests").mkdir(parents=True)
        monkeypatch.setattr(T, "PRODUCTS_DIR", primary / "products")
        captured = {}

        def fake_run(cmd, cwd, capture_output, text, timeout, env):
            captured["cwd"] = cwd
            return _FakeCompletedProcess()

        monkeypatch.setattr(T.subprocess, "run", fake_run)
        r = T.run_product_tests("alpha")

        assert captured["cwd"] == str(primary / "products" / "alpha" / "backend")
        assert r["resolved_root"] == str(primary)

    def test_run_product_tests_worktree_path_rejects_non_worktree_dir(self, tmp_path):
        bogus = tmp_path / "not-a-worktree"
        bogus.mkdir()
        with pytest.raises(ValueError):
            T.run_product_tests("alpha", worktree_path=str(bogus))

    def test_run_all_tests_iterates_worktree_products_not_primary(self, tmp_path, monkeypatch):
        wt = _make_fake_worktree(tmp_path, "wt", slug="alpha")
        # a second product with no tests/ dir must still be skipped
        (wt / "products" / "beta" / "backend").mkdir(parents=True)

        def fake_run(cmd, cwd, capture_output, text, timeout, env):
            return _FakeCompletedProcess(stdout="2 passed")

        monkeypatch.setattr(T.subprocess, "run", fake_run)
        r = T.run_all_tests(worktree_path=str(wt))

        assert [p["product"] for p in r["products"]] == ["alpha"]
        assert r["total_passed"] == 2
        assert r["resolved_root"] == str(wt)


class TestViteBuildWorktreeScoping:
    def test_build_product_frontend_scopes_cwd_to_worktree(self, tmp_path, monkeypatch):
        wt = tmp_path / "wt"
        wt.mkdir(parents=True)
        (wt / ".git").write_text("gitdir: /nowhere\n")
        (wt / ".noctusai-workspace").write_text("test\n")
        (wt / "products" / "alpha" / "frontend").mkdir(parents=True)
        captured = {}

        def fake_run(cmd, cwd, capture_output, text, timeout):
            captured["cwd"] = cwd
            return _FakeCompletedProcess(stdout="built in 100ms")

        monkeypatch.setattr(T.subprocess, "run", fake_run)
        r = T.build_product_frontend("alpha", worktree_path=str(wt))

        assert captured["cwd"] == str(wt / "products" / "alpha" / "frontend")
        assert r["resolved_root"] == str(wt)
        assert r["success"] is True
