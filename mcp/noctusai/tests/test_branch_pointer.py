"""Tests for noctus.dev.branch_pointer.

Covers:
  - Latest-per-branch resolution (append-only → latest-by-ts wins).
  - paths_overlap collision filter (the pre-dispatch planner).
  - append / update round-trip (enum validation, delta carry-forward).
  - cache-exemption: a branch-tree.ndjson-only change is classified exempt
    (should_skip_cache_refresh), non-exempt paths are not.
  - from_dev=True reads origin/dev via git-show (injected runner) rather
    than the local file; falls back to local when git-show fails.
  - push_dev=True publishes to origin/ledgers (Real store on a temp bare
    repo); push_dev=False spools the row for the next publish.
  - the dual-read: origin/dev's copy ∪ origin/ledgers.
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


@pytest.fixture(autouse=True)
def _isolated_ledger_path(tmp_path, monkeypatch):
    """Since 2026-09-24 every read is the dual-read (origin/dev's copy ∪ the
    ledger store), and the suite's Fake store is backed by `LEDGER_PATH` — the
    REAL primary ledger unless a test points it elsewhere. Default it to an
    empty per-test path so no test reads production pointers by accident;
    tests that need a local ledger still override it."""
    monkeypatch.setattr(BP, "LEDGER_PATH", tmp_path / "_isolated" / "branch-tree.ndjson")


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


# ── project field (ship-consent approval unit, 2026-09-22) ────────────────────
def _ledger_at(tmp_path, monkeypatch, rows=()):
    ledger = tmp_path / "project-history" / "branch-tree.ndjson"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(_ndjson(list(rows)) if rows else "", encoding="utf-8")
    monkeypatch.setattr(BP, "LEDGER_PATH", ledger)
    monkeypatch.setattr(BP, "LEDGER_REL", "project-history/branch-tree.ndjson")
    return ledger


def _append_kwargs(**over):
    kw = dict(base="origin/dev", commit="abc", role="engineer", agent="eng",
              paths=["x.py"], status="on_going", brief="b", push_dev=False)
    kw.update(over)
    return kw


class TestProjectField:
    def test_effective_project_defaults_to_branch_name(self):
        assert BP.effective_project({"branch": "feat/a"}) == "feat/a"
        assert BP.effective_project({"branch": "feat/a", "project": ""}) == "feat/a"
        assert BP.effective_project({"branch": "feat/a", "project": "roadmap-x"}) == "roadmap-x"

    def test_project_for_unknown_branch_is_the_branch(self):
        assert BP.project_for_branch("feat/nope", []) == "feat/nope"

    def test_append_explicit_project_is_written(self, tmp_path, monkeypatch):
        ledger = _ledger_at(tmp_path, monkeypatch)
        res = BP.append(branch="feat/o", parent="tech-lead", project="sw-extraction",
                        runner=FakeRunner(dev_content=""), **_append_kwargs())
        assert res["ok"] and res["row"]["project"] == "sw-extraction"
        assert json.loads(ledger.read_text().splitlines()[0])["project"] == "sw-extraction"

    def test_engineer_inherits_parent_branch_project(self, tmp_path, monkeypatch):
        parent = {**_row("feat/orch", "2026-09-01T00:00:00+00:00"), "project": "sw-extraction"}
        _ledger_at(tmp_path, monkeypatch, [parent])
        res = BP.append(branch="feat/eng1", parent="feat/orch",
                        runner=FakeRunner(dev_content=_ndjson([parent])), **_append_kwargs())
        assert res["row"]["project"] == "sw-extraction"

    def test_engineer_inherits_sibling_project_under_same_parent(self, tmp_path, monkeypatch):
        sib = {**_row("feat/eng1", "2026-09-01T00:00:00+00:00"), "parent": "sw-orchestrator",
               "project": "sw-extraction"}
        _ledger_at(tmp_path, monkeypatch, [sib])
        res = BP.append(branch="feat/eng2", parent="sw-orchestrator",
                        runner=FakeRunner(dev_content=_ndjson([sib])), **_append_kwargs())
        assert res["row"]["project"] == "sw-extraction"

    def test_unmapped_append_omits_project_and_reads_as_branch(self, tmp_path, monkeypatch):
        _ledger_at(tmp_path, monkeypatch)
        res = BP.append(branch="feat/solo", parent="tech-lead",
                        runner=FakeRunner(dev_content=""), **_append_kwargs())
        assert "project" not in res["row"]
        assert BP.effective_project(res["row"]) == "feat/solo"

    def test_update_carries_project_forward_and_can_override(self, tmp_path, monkeypatch):
        prev = {**_row("feat/p", "2026-09-01T00:00:00+00:00"), "project": "alpha"}
        _ledger_at(tmp_path, monkeypatch, [prev])
        r1 = BP.update(branch="feat/p", notes="n", push_dev=False,
                       runner=FakeRunner(dev_content=_ndjson([prev])))
        assert r1["row"]["project"] == "alpha"
        r2 = BP.update(branch="feat/p", project="beta", push_dev=False,
                       runner=FakeRunner(dev_content=_ndjson([prev])))
        assert r2["row"]["project"] == "beta"

    def test_query_and_list_filter_by_effective_project(self):
        a = {**_row("feat/a", "2026-09-01T00:00:00+00:00"), "project": "alpha"}
        b = _row("feat/b", "2026-09-01T00:00:01+00:00")
        runner = FakeRunner(dev_content=_ndjson([a, b]))
        assert [r["branch"] for r in BP.query(project="alpha", runner=runner)] == ["feat/a"]
        assert [r["branch"] for r in BP.query(project="feat/b", runner=runner)] == ["feat/b"]
        assert [r["branch"] for r in BP.list_pointers(project="alpha", runner=runner)] == ["feat/a"]



# ── origin/ledgers (2026-09-24): Real store on a temp bare repo ────────────────
class TestLedgerStoreRealMode:
    @pytest.fixture
    def real(self, ledger_repo, monkeypatch):
        bare, clone, show = ledger_repo
        monkeypatch.setattr(BP, "LEDGER_PATH", clone / "project-history" / "branch-tree.ndjson")
        return clone, show

    def test_append_publishes_to_ledgers_never_dev(self, real):
        clone, show = real
        runner = FakeRunner(dev_content=None)
        r = BP.append(branch="feat/p", base="origin/dev", commit="abc", role="engineer",
                      agent="eng", parent="tl", paths=["x.py"], status="on_going",
                      brief="b", push_dev=True, runner=runner)
        assert r["ok"] and r["push"]["status"] == "pushed", r
        assert json.loads(show("branch-tree.ndjson"))["branch"] == "feat/p"
        assert not BP.LEDGER_PATH.exists(), "the dev copy is never written"
        # no porcelain git at all — no add/commit/push through the runner
        assert not [c for c, _ in runner.calls if c[1] in ("add", "commit", "push", "rebase")]

    def test_push_dev_false_spools_then_reads_own_write(self, real):
        clone, show = real
        runner = FakeRunner(dev_content=None)
        BP.append(branch="feat/s", base="origin/dev", commit="abc", role="engineer",
                  agent="eng", parent="tl", paths=["x.py"], status="on_going",
                  brief="b", push_dev=False, runner=runner)
        assert show("branch-tree.ndjson") == ""
        assert [r["branch"] for r in BP.query(runner=runner)] == ["feat/s"]

    def test_update_carries_forward_across_the_dual_read(self, real):
        """A pointer that exists only on origin/dev (a stale-code peer) is
        updated; the delta row lands on origin/ledgers."""
        clone, show = real
        runner = FakeRunner(dev_content=_ndjson([
            {**_row("feat/old", "2026-09-01T00:00:00+00:00"), "session": "s-old"}]))
        u = BP.update(branch="feat/old", status="shipped", runner=runner)
        assert u["ok"] and u["push"]["status"] == "pushed", u
        assert json.loads(show("branch-tree.ndjson"))["status"] == "shipped"
        latest = {r["branch"]: r for r in BP.query(runner=runner)}
        assert latest["feat/old"]["status"] == "shipped"

    def test_dual_read_dedupes_seeded_rows(self, real):
        clone, show = real
        row = {**_row("feat/d", "2026-09-01T00:00:00+00:00"), "session": "s"}
        from tools.noctus.dev import _ledger_store as ls
        ls.default_store().append("branch-tree.ndjson", [json.dumps(row)], message="seed")
        runner = FakeRunner(dev_content=_ndjson([row]))
        assert len(BP._read_dev_ledger(runner=runner)) == 1
