"""check_engineer_slice_scored + check_guard_hooks_registered."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as C  # noqa: E402


def _tree(root: Path, rows: list[dict]) -> None:
    (root / "project-history").mkdir(parents=True, exist_ok=True)
    (root / "project-history" / "branch-tree.ndjson").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")


def _row(branch, agent, status="shipped", ts="2026-11-05T00:00:00Z", session="s1"):
    return {"ts": ts, "branch": branch, "agent": agent, "status": status, "session": session,
            "base": "origin/dev@abc", "commit": "abc", "role": "engineer", "parent": "dev",
            "paths": [], "brief": "b"}


def test_unscored_landed_engineer_slice_flagged(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "_branch_tree_text", lambda root: (tmp_path / "t").read_text())
    _tree(tmp_path, [])
    (tmp_path / "t").write_text("\n".join(json.dumps(r) for r in [
        _row("feat/a", "backend-engineer"), _row("feat/b", "backend-engineer"),
        _row("feat/c", "tech-lead"), _row("feat/d", "backend-engineer", ts="2026-10-01T00:00:00Z"),
        _row("feat/e", "backend-engineer", status="on_going")]))
    out = C.check_engineer_slice_scored(
        session="s1", repo_root=tmp_path, scores_text=json.dumps({"slug": "b"}))
    assert [i["issue"].split("'")[1] for i in out] == ["feat/a"]
    assert out[0]["severity"] == "high"
    peer = C.check_engineer_slice_scored(session="other", repo_root=tmp_path, scores_text="")
    assert {i["severity"] for i in peer} == {"warning"}


def _guards(tmp_path, registered: list[str], present: list[str]):
    (tmp_path / "scripts" / "hooks").mkdir(parents=True)
    for g in present:
        (tmp_path / "scripts" / "hooks" / g).write_text("")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Edit", "hooks": [{"type": "command",
         "command": f'python3 "$CLAUDE_PROJECT_DIR/scripts/hooks/{g}"'} for g in registered]}]}}))


def test_unregistered_guard_flagged(tmp_path):
    _guards(tmp_path, ["claude-guard-a.py"], ["claude-guard-a.py", "claude-guard-b.py"])
    out = C.check_guard_hooks_registered(repo_root=tmp_path)
    assert len(out) == 1 and "claude-guard-b.py" in out[0]["issue"] and out[0]["severity"] == "high"


def test_all_registered_clean(tmp_path):
    _guards(tmp_path, ["claude-guard-a.py"], ["claude-guard-a.py"])
    assert C.check_guard_hooks_registered(repo_root=tmp_path) == []


def test_real_repo_guards_are_registered():
    root = Path(__file__).resolve().parents[3]
    assert C.check_guard_hooks_registered(repo_root=root) == []


class TestEngineerSliceScored:
    """check_engineer_slice_scored: true-positive + false-positive shapes."""

    def test_flags_unscored_engineer_and_spares_inline_and_scored(self, monkeypatch, tmp_path):
        test_unscored_landed_engineer_slice_flagged(monkeypatch, tmp_path)


class TestGuardHooksRegistered:
    """check_guard_hooks_registered: true-positive + false-positive shapes."""

    def test_unregistered_flagged(self, tmp_path):
        test_unregistered_guard_flagged(tmp_path)

    def test_registered_clean(self, tmp_path):
        test_all_registered_clean(tmp_path)
