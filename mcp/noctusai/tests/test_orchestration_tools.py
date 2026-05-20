"""Colocated tests — noctus.dev.{salvage_worktree, dispatch_preflight,
findings}. Every dev tool ships regression coverage (meta-detector)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import dispatch_preflight as dp  # noqa: E402
from tools.noctus.dev import findings as fnd  # noqa: E402
from tools.noctus.dev import salvage_worktree as sw  # noqa: E402


def _name(mod):
    captured = {}

    class _S:
        def tool(self, *, name, description):
            captured["n"] = name
            return lambda fn: fn

    mod.register(_S())
    return captured["n"]


class TestFindingsAppend:
    def test_appends_and_drops_placeholder(self, tmp_path, monkeypatch):
        proj = tmp_path / "projects" / "demo"
        proj.mkdir(parents=True)
        (proj / "findings.md").write_text(
            "# findings — demo\n\n## Lessons\n- _(none yet)_\n"
        )
        monkeypatch.setattr(fnd, "REPO_ROOT", tmp_path)
        out = fnd.findings_append("demo", "Lessons", "the lesson", "W1-X1")
        assert out["ok"] is True
        body = (proj / "findings.md").read_text()
        assert "- **W1-X1** — the lesson" in body
        assert "_(none yet)_" not in body

    def test_rejects_bad_category(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fnd, "REPO_ROOT", tmp_path)
        out = fnd.findings_append("x", "Bogus", "e")
        assert out["ok"] is False and "category" in out["error"]

    def test_missing_project(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fnd, "REPO_ROOT", tmp_path)
        out = fnd.findings_append("nope", "Lessons", "e")
        assert out["ok"] is False and "no findings.md" in out["error"]

    def test_registered_name(self):
        assert _name(fnd) == "noctus.dev.findings"


class TestSalvageWorktree:
    def test_divergence_refused_when_nothing_staged(self, tmp_path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        out = sw.salvage_worktree(str(tmp_path), "msg")
        assert out["ok"] is False
        assert out["divergence_suspected"] is True
        assert "do NOT loop-redispatch" in out["error"].lower() or \
               "loop-redispatch" in out["error"]

    def test_non_worktree_path(self, tmp_path):
        out = sw.salvage_worktree(str(tmp_path / "nope"), "m")
        assert out["ok"] is False and "not a git worktree" in out["error"]

    def test_registered_name(self):
        assert _name(sw) == "noctus.dev.salvage_worktree"


class TestDispatchPreflight:
    def test_clear_when_nothing_to_flag(self):
        out = dp.dispatch_preflight(
            target_paths=[], wrap_paths=[], check_env_pins=False
        )
        assert set(("ok", "missing_on_base", "colliding_worktrees",
                    "merge_debt", "env_pin_drift", "active_interpreter",
                    "recommendation")).issubset(out)

    def test_missing_wrap_path_on_base_blocks(self):
        out = dp.dispatch_preflight(
            target_paths=[], wrap_paths=["does/not/exist/anywhere.py"],
            check_env_pins=False,
        )
        assert out["ok"] is False
        assert "does/not/exist/anywhere.py" in out["missing_on_base"]
        assert "BLOCK" in out["recommendation"]

    def test_project_slug_auto_includes_project_doc(self):
        """K-3 cure: passing project_slug auto-adds projects/<slug>/PROJECT.md
        to wrap_paths so a locally-committed-but-unpushed project doc fails
        loud at dispatch instead of as a phantom path on the engineer's
        worktree."""
        out = dp.dispatch_preflight(
            target_paths=[], project_slug="does-not-exist-yet",
            check_env_pins=False,
        )
        assert out["ok"] is False
        assert "projects/does-not-exist-yet/PROJECT.md" in out["missing_on_base"]

    def test_env_pin_drift_parser_handles_empty_pyproject(self, tmp_path,
                                                          monkeypatch):
        """The parser must tolerate a missing/empty seed pyproject without
        crashing (pre-bootstrap environments)."""
        monkeypatch.setattr(dp, "REPO_ROOT", tmp_path)
        out = dp._env_pin_drift()
        assert out == []

    def test_env_pin_drift_flags_capped_pin_violation(self, tmp_path,
                                                     monkeypatch):
        """The watchlist pins (starlette/fastapi/supabase/pydantic) are
        checked against the active interpreter's installed versions; a pin
        like `starlette<0.1.0` is guaranteed to fail on any modern env."""
        pyproject = tmp_path / "seed" / "lib" / "backend" / "pyproject.toml"
        pyproject.parent.mkdir(parents=True)
        pyproject.write_text(
            "[project]\n"
            "dependencies = [\n"
            '  "starlette>=0.0.1,<0.1.0",\n'  # impossible cap → drift
            "]\n"
        )
        monkeypatch.setattr(dp, "REPO_ROOT", tmp_path)
        out = dp._env_pin_drift()
        # If starlette is installed at all, it will be ≥0.1.0 → drift.
        # If starlette is NOT installed, the tool reports that too.
        assert len(out) == 1
        assert out[0]["name"] == "starlette"

    def test_registered_name(self):
        assert _name(dp) == "noctus.dev.dispatch_preflight"
