"""Tests for noctus.dev.branch_pointer.

Covers:
  - Latest-per-branch resolution (append-only → latest-by-ts wins).
  - paths_overlap collision filter (the pre-dispatch planner).
  - append / update round-trip (enum validation, delta carry-forward).
  - cache-exemption: a branch-tree.ndjson-only change is classified exempt
    (should_skip_cache_refresh), non-exempt paths are not.
  - from_dev=True reads origin/dev via git-show (injected runner) rather
    than the local file; falls back to local when git-show fails.
  - push_dev=True triggers the FF-push idiom; push_dev=False skips it.
  - list_pointers excludes terminal statuses by default; includes when
    include_terminal=True.

Zero real git — a FakeRunner is injected for all git IO.
Zero real remote — push assertions verify the command shape, never a real push.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.noctus.dev.branch_pointer as BP  # noqa: E402
from tools.noctus.dev.refresh_all_caches import should_skip_cache_refresh  # noqa: E402


@pytest.fixture(autouse=True)
def _autofill_session_env(monkeypatch):
    """`append`/`update` auto-fill `session` from CLAUDE_CODE_SESSION_ID (a row is
    NEVER written session=null — check_branch_tree_mirror gates that). Set a
    deterministic id so unit tests exercise the always-fill path regardless of
    whether the pytest host is inside a live Claude session (CI is not)."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "test-session-id")


# ── Helpers ────────────────────────────────────────────────────────────────────
def _row(
    branch: str,
    ts: str,
    status: str = "on_going",
    paths: list[str] | None = None,
    agent: str = "eng",
) -> dict:
    return {
        "ts": ts,
        "branch": branch,
        "base": "origin/dev",
        "commit": "abc1234",
        "worktree": None,
        "role": "engineer",
        "agent": agent,
        "parent": "tech-lead",
        "session": None,
        "paths": paths or ["mcp/noctusai/tools/x.py"],
        "status": status,
        "brief": f"brief for {branch}",
        "notes": "",
    }


def _ndjson(rows: list[dict]) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


class FakeRunner:
    """Scriptable git runner.

    `dev_content`: str that `git show origin/dev:...` returns (or None → rc=1).
    Records calls as (cmd, cwd) for assertion.
    """

    def __init__(self, dev_content: str | None = None, push_rc: int = 0):
        self.dev_content = dev_content
        self.push_rc = push_rc
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
        self.calls.append((cmd, cwd))
        sub = cmd[1] if len(cmd) > 1 else ""
        if sub == "show":
            if self.dev_content is not None:
                return 0, self.dev_content, ""
            return 1, "", "not found"
        if sub == "fetch":
            return 0, "", ""
        if sub == "status":
            # Simulate the ledger being dirty (needs commit)
            return 0, "M project-history/branch-tree.ndjson\n", ""
        if sub == "add":
            return 0, "", ""
        if sub == "commit":
            return 0, "[feat/x abc1234] chore(branch-pointer): ...\n", ""
        if sub == "push":
            return self.push_rc, "", "" if self.push_rc == 0 else "non-fast-forward"
        return 0, "", ""


# ── Latest-per-branch resolution ─────────────────────────────────────────────
class TestLatestPerBranch:
    def test_latest_wins_by_ts(self):
        rows = [
            _row("feat/a", "2026-06-01T10:00:00+00:00", status="on_going"),
            _row("feat/a", "2026-06-01T12:00:00+00:00", status="blocked"),
            _row("feat/b", "2026-06-01T09:00:00+00:00", status="on_going"),
        ]
        best = BP._latest_per_branch(rows)
        assert best["feat/a"]["status"] == "blocked"
        assert best["feat/b"]["status"] == "on_going"

    def test_single_row_per_branch(self):
        rows = [_row("feat/only", "2026-06-01T11:00:00+00:00", status="shipped")]
        best = BP._latest_per_branch(rows)
        assert best["feat/only"]["status"] == "shipped"

    def test_empty_rows(self):
        assert BP._latest_per_branch([]) == {}

    def test_missing_branch_key_skipped(self):
        rows = [{"ts": "2026-06-01T10:00:00+00:00", "status": "on_going"}]
        best = BP._latest_per_branch(rows)
        assert best == {}


# ── paths_overlap ─────────────────────────────────────────────────────────────
class TestPathsOverlap:
    def test_intersecting_returns_true(self):
        assert BP._paths_overlap(["mcp/a.py", "mcp/b.py"], ["mcp/b.py", "mcp/c.py"])

    def test_disjoint_returns_false(self):
        assert not BP._paths_overlap(["mcp/a.py"], ["mcp/b.py"])

    def test_empty_a_returns_false(self):
        assert not BP._paths_overlap([], ["mcp/b.py"])

    def test_empty_b_returns_false(self):
        assert not BP._paths_overlap(["mcp/a.py"], [])

    def test_both_empty_returns_false(self):
        assert not BP._paths_overlap([], [])


# ── Cache-exemption ───────────────────────────────────────────────────────────
class TestCacheExemption:
    def test_only_branch_tree_is_exempt(self):
        assert should_skip_cache_refresh(["project-history/branch-tree.ndjson"]) is True

    def test_non_exempt_path_not_exempt(self):
        assert should_skip_cache_refresh(["mcp/noctusai/tools/noctus/dev/foo.py"]) is False

    def test_mixed_paths_not_exempt(self):
        # Any non-exempt file → not exempt
        assert should_skip_cache_refresh([
            "project-history/branch-tree.ndjson",
            "mcp/noctusai/tools/noctus/dev/foo.py",
        ]) is False

    def test_empty_list_not_exempt(self):
        # Conservative: empty = unknown = refresh
        assert should_skip_cache_refresh([]) is False

    def test_auto_improvement_not_exempt(self):
        assert should_skip_cache_refresh(["project-history/auto-improvement.ndjson"]) is False

    def test_branch_pointer_module_exempt_sentinel_matches(self):
        # branch_pointer.is_cache_exempt_path and refresh_all_caches.should_skip_cache_refresh
        # must agree on the canonical path.
        assert BP.is_cache_exempt_path("project-history/branch-tree.ndjson") is True
        assert BP.is_cache_exempt_path("project-history/auto-improvement.ndjson") is False
        assert BP.changed_files_are_all_cache_exempt(
            ["project-history/branch-tree.ndjson"]
        ) is True
        assert BP.changed_files_are_all_cache_exempt(
            ["project-history/branch-tree.ndjson", "mcp/foo.py"]
        ) is False


# ── from_dev reads origin/dev via git-show ────────────────────────────────────
class TestReadDevLedger:
    def test_reads_dev_copy(self):
        rows = [_row("feat/x", "2026-06-01T10:00:00+00:00")]
        runner = FakeRunner(dev_content=_ndjson(rows))
        result = BP._read_dev_ledger(runner=runner)
        assert len(result) == 1
        assert result[0]["branch"] == "feat/x"
        # Verify git show was called with the right path
        show_cmds = [c for c, _ in runner.calls if c[1:2] == ["show"]]
        assert show_cmds, "git show should have been called"
        assert BP.LEDGER_REL in show_cmds[0][-1]

    def test_falls_back_to_local_on_git_show_failure(self, tmp_path, monkeypatch):
        rows = [_row("feat/y", "2026-06-01T11:00:00+00:00")]
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(_ndjson(rows), encoding="utf-8")
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)

        runner = FakeRunner(dev_content=None)  # git show fails
        result = BP._read_dev_ledger(runner=runner)
        assert len(result) == 1
        assert result[0]["branch"] == "feat/y"

    def test_empty_ledger_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(BP, "LEDGER_PATH", tmp_path / "no-file.ndjson")
        runner = FakeRunner(dev_content=None)
        result = BP._read_dev_ledger(runner=runner)
        assert result == []


# ── append ────────────────────────────────────────────────────────────────────
class TestAppend:
    def test_append_writes_row_to_ledger(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.setattr(BP, "LEDGER_REL", "project-history/branch-tree.ndjson")

        runner = FakeRunner()
        result = BP.append(
            branch="feat/my-tool",
            base="origin/dev",
            commit="abc1234",
            role="engineer",
            agent="my-tool",
            parent="tech-lead",
            paths=["mcp/noctusai/tools/noctus/dev/my_tool.py"],
            status="on_going",
            brief="implement my-tool",
            push_dev=False,
            runner=runner,
        )
        assert result["ok"] is True
        assert ledger.exists()
        rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        assert rows[0]["branch"] == "feat/my-tool"
        assert rows[0]["status"] == "on_going"
        assert rows[0]["agent"] == "my-tool"
        # Auto-filled the owning session (never null) — from the env fixture.
        assert rows[0]["session"] == "test-session-id"

    def test_append_autofills_session_from_env(self, tmp_path, monkeypatch):
        """append(session=None) resolves the session from CLAUDE_CODE_SESSION_ID."""
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-xyz-123")
        result = BP.append(
            branch="feat/s", base="origin/dev", commit="abc", role="engineer",
            agent="s", parent="tech-lead", paths=[], status="on_going",
            brief="s", session=None, push_dev=False, runner=FakeRunner(),
        )
        assert result["ok"] is True
        assert result["row"]["session"] == "sess-xyz-123"

    def test_append_errors_when_session_unresolvable(self, tmp_path, monkeypatch):
        """No env + no transcript → append refuses rather than writing null."""
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.setattr(BP, "_resolve_session_id", lambda: None)
        result = BP.append(
            branch="feat/s", base="origin/dev", commit="abc", role="engineer",
            agent="s", parent="tech-lead", paths=[], status="on_going",
            brief="s", session=None, push_dev=False, runner=FakeRunner(),
        )
        assert result["ok"] is False
        assert "session could not be auto-resolved" in result["error"]

    def test_append_invalid_status_rejected(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        result = BP.append(
            branch="feat/x", base="dev", commit="abc", role="engineer",
            agent="x", parent="tl", paths=[], status="invalid_status",
            brief="x", push_dev=False,
        )
        assert result["ok"] is False
        assert "status must be one of" in result["error"]

    def test_append_invalid_role_rejected(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        result = BP.append(
            branch="feat/x", base="dev", commit="abc", role="overlord",
            agent="x", parent="tl", paths=[], status="on_going",
            brief="x", push_dev=False,
        )
        assert result["ok"] is False
        assert "role must be one of" in result["error"]

    def test_append_push_dev_calls_ff_push(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.setattr(BP, "LEDGER_REL", "project-history/branch-tree.ndjson")

        runner = FakeRunner(push_rc=0)
        result = BP.append(
            branch="feat/push-test", base="origin/dev", commit="def5678",
            role="engineer", agent="push-test", parent="tl",
            paths=["mcp/foo.py"], status="on_going", brief="push test",
            push_dev=True, runner=runner,
        )
        assert result["ok"] is True
        push_cmds = [c for c, _ in runner.calls if len(c) > 1 and c[1] == "push"]
        assert push_cmds, "push should have been called"
        # Verify push targets dev
        push_args = push_cmds[0]
        assert any("refs/heads/dev" in a or a.endswith(":dev") for a in push_args)


# ── update ────────────────────────────────────────────────────────────────────
class TestUpdate:
    def test_update_carries_forward_prev_values(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        # Seed one row
        prev = _row("feat/upd", "2026-06-01T10:00:00+00:00", status="on_going")
        ledger.write_text(_ndjson([prev]), encoding="utf-8")
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.setattr(BP, "LEDGER_REL", "project-history/branch-tree.ndjson")

        runner = FakeRunner(dev_content=_ndjson([prev]))
        result = BP.update(
            branch="feat/upd",
            status="blocked",
            notes="waiting for tech-lead",
            push_dev=False,
            runner=runner,
        )
        assert result["ok"] is True
        rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
        assert len(rows) == 2  # original + delta
        latest = max(rows, key=lambda r: r["ts"])
        assert latest["status"] == "blocked"
        assert latest["notes"] == "waiting for tech-lead"
        # Carried forward from prev
        assert latest["agent"] == prev["agent"]
        assert latest["brief"] == prev["brief"]

    def test_update_missing_branch_errors(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        runner = FakeRunner(dev_content="")  # empty ledger on dev
        result = BP.update(branch="feat/nonexistent", push_dev=False, runner=runner)
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_update_invalid_status_rejected(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        prev = _row("feat/valcheck", "2026-06-01T10:00:00+00:00")
        ledger.write_text(_ndjson([prev]), encoding="utf-8")
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        runner = FakeRunner(dev_content=_ndjson([prev]))
        result = BP.update(branch="feat/valcheck", status="bad_status",
                           push_dev=False, runner=runner)
        assert result["ok"] is False
        assert "status must be one of" in result["error"]


# ── query / list_pointers ────────────────────────────────────────────────────
class TestQueryAndList:
    def _make_runner_with(self, *rows) -> FakeRunner:
        return FakeRunner(dev_content=_ndjson(list(rows)))

    def test_query_returns_latest_per_branch(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00", status="on_going")
        r2 = _row("feat/a", "2026-06-01T12:00:00+00:00", status="blocked")
        r3 = _row("feat/b", "2026-06-01T11:00:00+00:00", status="on_going")
        runner = self._make_runner_with(r1, r2, r3)
        result = BP.query(from_dev=True, runner=runner)
        by_branch = {r["branch"]: r for r in result}
        assert by_branch["feat/a"]["status"] == "blocked"
        assert by_branch["feat/b"]["status"] == "on_going"

    def test_query_status_filter(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00", status="on_going")
        r2 = _row("feat/b", "2026-06-01T11:00:00+00:00", status="shipped")
        runner = self._make_runner_with(r1, r2)
        result = BP.query(from_dev=True, status="on_going", runner=runner)
        assert len(result) == 1
        assert result[0]["branch"] == "feat/a"

    def test_query_branch_filter(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00")
        r2 = _row("feat/b", "2026-06-01T11:00:00+00:00")
        runner = self._make_runner_with(r1, r2)
        result = BP.query(from_dev=True, branch="feat/b", runner=runner)
        assert len(result) == 1
        assert result[0]["branch"] == "feat/b"

    def test_query_agent_filter(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00", agent="alice")
        r2 = _row("feat/b", "2026-06-01T11:00:00+00:00", agent="bob")
        runner = self._make_runner_with(r1, r2)
        result = BP.query(from_dev=True, agent="alice", runner=runner)
        assert len(result) == 1
        assert result[0]["agent"] == "alice"

    def test_query_paths_overlap_filter(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00",
                  paths=["mcp/noctusai/tools/noctus/dev/foo.py"])
        r2 = _row("feat/b", "2026-06-01T11:00:00+00:00",
                  paths=["mcp/noctusai/tools/noctus/dev/bar.py"])
        runner = self._make_runner_with(r1, r2)
        result = BP.query(
            from_dev=True,
            paths_overlap=["mcp/noctusai/tools/noctus/dev/foo.py"],
            runner=runner,
        )
        assert len(result) == 1
        assert result[0]["branch"] == "feat/a"

    def test_query_paths_overlap_no_match_returns_empty(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00",
                  paths=["mcp/noctusai/tools/noctus/dev/foo.py"])
        runner = self._make_runner_with(r1)
        result = BP.query(
            from_dev=True,
            paths_overlap=["mcp/some/other/file.py"],
            runner=runner,
        )
        assert result == []

    def test_list_excludes_terminal_by_default(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00", status="on_going")
        r2 = _row("feat/b", "2026-06-01T11:00:00+00:00", status="shipped")
        r3 = _row("feat/c", "2026-06-01T12:00:00+00:00", status="canceled")
        r4 = _row("feat/d", "2026-06-01T13:00:00+00:00", status="blocked")
        runner = self._make_runner_with(r1, r2, r3, r4)
        result = BP.list_pointers(from_dev=True, include_terminal=False, runner=runner)
        branches = {r["branch"] for r in result}
        assert "feat/a" in branches
        assert "feat/d" in branches
        assert "feat/b" not in branches  # shipped = terminal
        assert "feat/c" not in branches  # canceled = terminal

    def test_list_includes_terminal_when_requested(self):
        r1 = _row("feat/a", "2026-06-01T10:00:00+00:00", status="on_going")
        r2 = _row("feat/b", "2026-06-01T11:00:00+00:00", status="shipped")
        runner = self._make_runner_with(r1, r2)
        result = BP.list_pointers(from_dev=True, include_terminal=True, runner=runner)
        branches = {r["branch"] for r in result}
        assert "feat/a" in branches
        assert "feat/b" in branches


# ── Push-to-dev FF idiom ──────────────────────────────────────────────────────
class TestPushLedger:
    def test_push_retries_on_race(self, tmp_path, monkeypatch):
        """First push fails (non-FF), second push succeeds after fetch."""
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.setattr(BP, "LEDGER_REL", "project-history/branch-tree.ndjson")

        calls: list[list[str]] = []

        def _runner(cmd: list[str], cwd=None) -> tuple[int, str, str]:
            calls.append(cmd)
            sub = cmd[1] if len(cmd) > 1 else ""
            if sub == "status":
                return 0, "M project-history/branch-tree.ndjson\n", ""
            if sub == "add":
                return 0, "", ""
            if sub == "commit":
                return 0, "[x] chore\n", ""
            if sub == "fetch":
                return 0, "", ""
            if sub == "push":
                # First push fails; second succeeds
                push_calls = [c for c in calls if len(c) > 1 and c[1] == "push"]
                if len(push_calls) == 1:
                    return 1, "", "non-fast-forward"
                return 0, "", ""
            return 0, "", ""

        result = BP._push_ledger_to_dev(
            commit_msg="test push", runner=_runner, dev_branch="dev"
        )
        assert result["ok"] is True
        push_calls = [c for c in calls if len(c) > 1 and c[1] == "push"]
        assert len(push_calls) == 2, "should have retried after first push failure"

    def test_push_skips_when_ledger_clean(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.setattr(BP, "LEDGER_REL", "project-history/branch-tree.ndjson")

        def _runner(cmd: list[str], cwd=None) -> tuple[int, str, str]:
            sub = cmd[1] if len(cmd) > 1 else ""
            if sub == "status":
                return 0, "", ""  # clean
            if sub == "fetch":
                return 0, "", ""
            return 0, "", ""

        result = BP._push_ledger_to_dev(commit_msg="x", runner=_runner)
        assert result["ok"] is True
        assert result["status"] == "already_clean"
        assert result["pushed"] is False

    def test_push_fails_cleanly_on_persistent_failure(self, tmp_path, monkeypatch):
        ledger = tmp_path / "project-history" / "branch-tree.ndjson"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
        monkeypatch.setattr(BP, "LEDGER_REL", "project-history/branch-tree.ndjson")

        def _runner(cmd: list[str], cwd=None) -> tuple[int, str, str]:
            sub = cmd[1] if len(cmd) > 1 else ""
            if sub == "status":
                return 0, "M project-history/branch-tree.ndjson\n", ""
            if sub in ("add", "commit", "fetch"):
                return 0, "", ""
            if sub == "push":
                return 1, "", "permission denied"
            return 0, "", ""

        result = BP._push_ledger_to_dev(commit_msg="x", runner=_runner)
        assert result["ok"] is False
        assert "FF-push" in result["error"] or "failed" in result["error"]
        assert result.get("committed_locally") is True


# ── noc_graph_cache exclusion ─────────────────────────────────────────────────
class TestNocGraphExclusion:
    def test_branch_tree_not_in_source_files(self, tmp_path):
        """branch-tree.ndjson must NOT appear in noc_graph_cache._source_files."""
        # Create a minimal project-history/ with branch-tree.ndjson
        ph = tmp_path / "project-history"
        ph.mkdir()
        (ph / "branch-tree.ndjson").write_text('{"ts":"2026-06-02"}\n', encoding="utf-8")
        (ph / "auto-improvement.ndjson").write_text('{"ts":"2026-06-02"}\n', encoding="utf-8")
        (ph / "PROJECT-HISTORY.md").write_text("# History\n", encoding="utf-8")
        # Create stub CLAUDE.md so the function doesn't fail on missing files
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")

        import importlib
        import tools.noctus.dev.noc_graph_cache as ngc

        files = ngc._source_files(tmp_path)
        rel_paths = set()
        for f in files:
            try:
                rel_paths.add(f.relative_to(tmp_path).as_posix())
            except ValueError:
                rel_paths.add(f.as_posix())

        assert "project-history/branch-tree.ndjson" not in rel_paths, (
            "branch-tree.ndjson must be excluded from noc_graph_cache source files "
            "(cache-exemption: pointer pushes must not trigger graph rebuild)"
        )
        # auto-improvement.ndjson is still included (not exempt)
        assert "project-history/auto-improvement.ndjson" in rel_paths
