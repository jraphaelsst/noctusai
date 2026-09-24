"""Wiring tests: every repo-global append-only ledger writer must derive its
path from `settings.LEDGER_ROOT` (which UNWRAPS a worktree boundary),
never from `settings.REPO_ROOT` (which STOPS at one). This is the fifth
confirmed incident of the ledger-into-worktree data-loss family
(2026-09-17) — see `workspace.get_ledger_root()`'s docstring for the
incident writeup.

Three writer shapes, three test strategies:

1. MODULE-LEVEL FROZEN CONSTANT (`LEDGER_PATH = LEDGER_ROOT / "..."`,
   computed once at import time) — patch `settings.LEDGER_ROOT` THEN
   `importlib.reload()` the writer module so its constant is recomputed
   against the patched value; assert it followed. Always undone via
   `monkeypatch.undo()` + a second reload so no state leaks to later tests.

2. LATE-BOUND MODULE GLOBAL (`from settings import LEDGER_ROOT` at module
   level, but consumed inside a function's `else: root = LEDGER_ROOT`
   branch at CALL time) — monkeypatch the WRITER's own already-imported
   `LEDGER_ROOT` name directly; no reload needed (Python resolves the
   name at call time).

3. LAZY IMPORT INSIDE THE FUNCTION BODY (`from settings import
   LEDGER_ROOT` executed fresh on every call) — monkeypatch
   `settings.LEDGER_ROOT` directly; the writer re-reads it on the next
   call, no reload needed.

`session_end_sweep.py` and `cleanup_worktrees.py` / `mole.py`'s
salvage-ledger call sites have their OWN dedicated incident-reproduction
tests (`test_session_end_sweep_ledger_root.py`,
`test_salvage_ledger_unwraps_worktree_root.py`) — not repeated here.
"""
from __future__ import annotations

import contextlib
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings  # noqa: E402


@contextlib.contextmanager
def _reloaded_with_ledger_root(module, new_root: Path, monkeypatch):
    """Patch settings.LEDGER_ROOT, reload `module` so its frozen
    module-level constants recompute against it, yield, then ALWAYS
    restore (undo the patch + reload again) so no other test in the same
    session inherits a mutated module."""
    monkeypatch.setattr(settings, "LEDGER_ROOT", new_root)
    importlib.reload(module)
    try:
        yield module
    finally:
        monkeypatch.undo()
        importlib.reload(module)


class TestModuleLevelFrozenConstants:
    """Shape 1 — `LEDGER_PATH`/`BASELINE_DIR`/etc. computed at import time."""

    def test_auto_improvement(self, tmp_path, monkeypatch):
        from tools.noctus.dev import auto_improvement as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.LEDGER_PATH == tmp_path / "project-history" / "auto-improvement.ndjson"

    def test_vector_costs(self, tmp_path, monkeypatch):
        from tools.noctus.dev import vector_costs as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.LEDGER_PATH == tmp_path / "project-history" / "vector-costs.ndjson"
            assert m.SPOOL_PATH == tmp_path / "project-history" / ".vector-costs-spool.ndjson"

    def test_dispatch_budget(self, tmp_path, monkeypatch):
        from tools.noctus.dev import dispatch_budget as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.LEDGER_PATH == tmp_path / "project-history" / "dispatch-budget.ndjson"

    def test_absorption_tracking(self, tmp_path, monkeypatch):
        from tools.noctus.dev import absorption_tracking as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.LEDGER_PATH == tmp_path / "project-history" / "absorptions.ndjson"

    def test_branch_pointer(self, tmp_path, monkeypatch):
        from tools.noctus.dev import branch_pointer as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.LEDGER_PATH == tmp_path / "project-history" / "branch-tree.ndjson"
            # the mirror file was deleted 2026-09-24 — no MIRROR_PATH to derive
            assert not hasattr(m, "MIRROR_PATH")

    def test_vector_calibration(self, tmp_path, monkeypatch):
        from tools.noctus.dev import vector_calibration as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.SIGNALS_PATH == tmp_path / "project-history" / "vector-signals.ndjson"
            assert m.DECISIONS_PATH == tmp_path / "project-history" / "vector-calibration.ndjson"

    def test_code_baseline(self, tmp_path, monkeypatch):
        from tools.noctus.dev import code_baseline as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.BASELINE_DIR == tmp_path / "project-history" / "code-baselines"

    def test_kb_baseline(self, tmp_path, monkeypatch):
        from tools.noctus.dev import kb_baseline as m
        with _reloaded_with_ledger_root(m, tmp_path, monkeypatch):
            assert m.BASELINE_DIR == tmp_path / "project-history" / "kb-baselines"


class TestLateBoundModuleGlobalElseBranch:
    """Shape 2 — `history.py` / `archive.py`'s implicit-default
    `else: root = LEDGER_ROOT` branch, exercised with neither `repo_root`
    nor `worktree_path` supplied (the exact call shape that broke before
    this fix)."""

    def test_history_record_implicit_default(self, tmp_path, monkeypatch):
        from tools.noctus.dev import history as m

        primary = tmp_path / "primary"
        (primary / "project-history").mkdir(parents=True)
        (primary / "projects" / "demo-proj").mkdir(parents=True)
        (primary / "projects" / "demo-proj" / "PROJECT.md").write_text(
            "# Demo\n\n## 1 Context\ntext\n", encoding="utf-8"
        )
        monkeypatch.setattr(m, "LEDGER_ROOT", primary)

        result = m.history_record(
            project_path="projects/demo-proj",
            status_at_close="shipped",
            summary_md="Demo summary.",
            review_md="- did a thing",
            repo_root=None,
            worktree_path=None,
        )
        ledger = primary / "project-history" / "ledger.ndjson"
        assert ledger.exists()
        assert result["ledger_path"] == "project-history/ledger.ndjson"

    def test_backfill_project_history_implicit_default(self, tmp_path, monkeypatch):
        from tools.noctus.dev import history as m

        primary = tmp_path / "primary"
        (primary / "project-history").mkdir(parents=True)
        (primary / "archive" / "projects").mkdir(parents=True)
        monkeypatch.setattr(m, "LEDGER_ROOT", primary)

        # No archived projects at all — dry_run walk should just report
        # zero, proving it resolved `repo` to `primary` without raising.
        result = m.backfill_project_history(dry_run=True, repo_root=None, worktree_path=None)
        assert result["archives_seen"] == 0

    def test_archive_implicit_default(self, tmp_path, monkeypatch):
        from tools.noctus.dev import archive as m

        primary = tmp_path / "primary"
        _git_init_no_remote(primary)
        (primary / "project-history").mkdir(parents=True, exist_ok=True)
        target = primary / "ad-hoc-thing"
        target.mkdir(parents=True)
        (target / "note.md").write_text("scratch\n", encoding="utf-8")
        _git_commit_all(primary, "add ad-hoc-thing")
        monkeypatch.setattr(m, "LEDGER_ROOT", primary)

        result = m.archive(
            target_path=str(target),
            mode="ad_hoc",
            name="demo-adhoc",
            repo_root=None,
            worktree_path=None,
            skip_history=True,
        )
        archived_to = primary / result["archived_to"]
        assert archived_to.exists(), (
            f"expected archive target under LEDGER_ROOT (primary): {archived_to}"
        )


class TestLazyImportInsideFunctionBody:
    """Shape 3 — `from settings import LEDGER_ROOT` executed fresh on
    every call; monkeypatch `settings.LEDGER_ROOT` directly, no reload."""

    def test_salvage_before_delete_implicit_default(self, tmp_path, monkeypatch):
        from tools.noctus.dev import salvage_before_delete as m

        primary = tmp_path / "primary"
        primary.mkdir()
        monkeypatch.setattr(settings, "LEDGER_ROOT", primary)

        result = m.salvage_before_delete(
            target="some/nonexistent/path", kind="path", dry_run=False,
        )
        assert result["ledger_entry_written"] is True
        ledger = primary / "project-history" / "worktree-salvage.ndjson"
        assert ledger.exists()

    def test_remote_branch_hygiene_classify_implicit_default(self, tmp_path, monkeypatch):
        from tools.noctus.dev import remote_branch_hygiene as m

        primary = tmp_path / "primary"
        primary.mkdir()
        _git_init_no_remote(primary)
        monkeypatch.setattr(settings, "LEDGER_ROOT", primary)

        calls: list[list[str]] = []
        orig_run_git = m._run_git

        def _spy(args, cwd=None, timeout=30):
            calls.append(list(args))
            return orig_run_git(args, cwd=cwd, timeout=timeout)

        monkeypatch.setattr(m, "_run_git", _spy)
        result = m.classify_remote_branches(repo_root=None)
        assert isinstance(result, list)
        assert calls, "expected at least one git invocation against LEDGER_ROOT"

    def test_orphan_branch_sweeper_scan_implicit_default(self, tmp_path, monkeypatch):
        from tools.noctus.dev import orphan_branch_sweeper as m

        primary = tmp_path / "primary"
        _git_init_no_remote(primary, branch="only-in-ledger-root")
        monkeypatch.setattr(settings, "LEDGER_ROOT", primary)

        result = m.scan(repo_root=None)
        assert result["current_branch"] == "only-in-ledger-root"

    def test_dispatch_token_log_implicit_default(self, tmp_path, monkeypatch):
        from tools.noctus.dev import dispatch_token_log as m

        primary = tmp_path / "primary"
        primary.mkdir()
        monkeypatch.setattr(settings, "LEDGER_ROOT", primary)

        result = m.log_completion(slug="demo-slug", agent="engineer-seed", duration_minutes=1.0)
        assert result["ok"] is True
        ledger = primary / "project-history" / "dispatch-budget.ndjson"
        assert ledger.exists()

    def test_product_centroid_drift_ledger_path(self, tmp_path, monkeypatch):
        from tools.noctus.dev import product_centroid_drift as m

        primary = tmp_path / "primary"
        primary.mkdir()
        monkeypatch.setattr(settings, "LEDGER_ROOT", primary)

        assert m._ledger_path() == primary / "project-history" / "product-drift.ndjson"

    def test_task_branch_resolve_primary_root(self, tmp_path, monkeypatch):
        from tools.noctus.dev import task_branch as m

        primary = tmp_path / "primary"
        primary.mkdir()
        monkeypatch.setattr(settings, "LEDGER_ROOT", primary)

        assert m._resolve_primary_root(None) == str(primary)
        # Explicit injection still wins (test seam / real orchestration).
        assert m._resolve_primary_root("/some/injected/path") == "/some/injected/path"


def _git_init_no_remote(repo: Path, branch: str = "main") -> None:
    import subprocess

    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(repo), check=True)
    (repo / "f").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=str(repo), check=True)


def _git_commit_all(repo: Path, message: str) -> None:
    import subprocess

    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=str(repo), check=True)
