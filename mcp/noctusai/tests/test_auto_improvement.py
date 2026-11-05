"""Regression tests for the scoped-auto-improvement ledger + cache +
`check_auto_improvement_cache_freshness` keeper.

KB § PATTERNS/common/scoped-auto-improvement.md. Phase B (2026-05-26).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import auto_improvement as ai  # noqa: E402
from tools.noctus.dev import codification_radar as cr  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    check_auto_improvement_cache_freshness,
    check_open_drift_has_resolution_handle,
    check_s2_drift_has_resolution_handle,
)


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / ".claude" / "cache")
    monkeypatch.setattr(ai, "CACHE_PATH", tmp_path / ".claude" / "cache" / "auto-improvement.sqlite")
    monkeypatch.setattr(ai, "LEDGER_PATH", tmp_path / "project-history" / "auto-improvement.ndjson")
    return tmp_path


class TestLogEntry:
    def test_log_appends_to_ndjson(self, tmp_repo):
        r = ai.log_entry(
            scope="scoped", kind="drift",
            target=".claude/agents/backend-engineer.md",
            description="Pydantic silent-drop in routers.example",
            agent="backend-engineer", resolve_when="manual:test",
        )
        assert r["ok"] is True
        text = ai.LEDGER_PATH.read_text(encoding="utf-8")
        line = text.strip()
        e = json.loads(line)
        assert e["scope"] == "scoped"
        assert e["kind"] == "drift"
        assert e["target"] == ".claude/agents/backend-engineer.md"
        assert e["status"] == "s1-emergent"  # default

    def test_invalid_scope_rejected(self, tmp_repo):
        r = ai.log_entry(scope="invalid", kind="improvement", target="*", description="x")
        assert r["ok"] is False
        assert "scope must be one of" in r["error"]

    def test_invalid_kind_rejected(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="bogus", target="*", description="x")
        assert r["ok"] is False
        assert "kind must be one of" in r["error"]

    def test_invalid_status_rejected(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="improvement", target="*", description="x", status="bogus")
        assert r["ok"] is False
        assert "status must be one of" in r["error"]


class TestRefreshAndQuery:
    def test_refresh_populates_cache(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="A pattern", agent="tech-lead")
        ai.log_entry(scope="scoped", kind="improvement", target=".claude/agents/x.md", description="B drift", agent="alpha")
        r = ai.refresh(force=True)
        assert r["status"] == "rebuilt"
        assert r["rows_written"] == 2

    def test_idempotent_short_circuit(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="X", agent="tech-lead")
        ai.refresh(force=True)
        r2 = ai.refresh()
        assert r2["status"] == "in-sync"

    def test_lazy_rebuild_on_sha_mismatch(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="first", agent="tl")
        ai.refresh(force=True)
        # Add a new entry — sha drifts; next query rebuilds.
        ai.log_entry(scope="broad", kind="improvement", target="t2", description="second", agent="tl")
        rows = ai.query()
        assert len(rows) == 2

    def test_query_filters_by_target(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target=".claude/agents/a.md", description="x", agent="tl")
        ai.log_entry(scope="broad", kind="improvement", target=".claude/agents/b.md", description="y", agent="tl")
        ai.log_entry(scope="broad", kind="improvement", target="KB § PATTERNS/z.md", description="z", agent="tl")
        ai.refresh(force=True)
        rows_a = ai.query(target=".claude/agents/a.md")
        assert len(rows_a) == 1
        rows_agents = ai.query(target=".claude/agents/")  # substring
        assert len(rows_agents) == 2
        rows_kb = ai.query(target="KB §")
        assert len(rows_kb) == 1

    def test_query_open_only_excludes_terminal(self, tmp_repo):
        # "open" = still-needs-work = NOT terminal. Terminal = closed ∪ s4-keeper
        # (a keeper now guards it). s1/s2/s3 are returned; closed + s4 are not.
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="x", agent="tl", status="s1-emergent")
        ai.log_entry(scope="broad", kind="improvement", target="t2", description="y", agent="tl", status="closed")
        ai.log_entry(scope="broad", kind="improvement", target="t3", description="z", agent="tl", status="s4-keeper")
        ai.log_entry(scope="broad", kind="improvement", target="t4", description="w", agent="tl", status="s3-codified")
        ai.refresh(force=True)
        targets = {r["target"] for r in ai.query(open_only=True, skip_reconcile=True)}
        assert targets == {"t1", "t4"}      # s1 + s3 surface
        assert "t2" not in targets          # closed — terminal
        assert "t3" not in targets          # s4-keeper — terminal (the fix)

    def test_query_filter_by_kind(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x", agent="tl",
                     resolve_when="manual:test")
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="y", agent="tl")
        ai.refresh(force=True)
        assert len(ai.query(kind="drift")) == 1
        assert len(ai.query(kind="improvement")) == 1

    def test_malformed_ndjson_line_skipped(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="x", agent="tl")
        # Write a malformed line directly.
        with ai.LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write("not valid json at all\n")
        ai.log_entry(scope="broad", kind="improvement", target="t2", description="y", agent="tl")
        ai.refresh(force=True)
        rows = ai.query()
        # Two valid entries; the malformed line was silently skipped.
        targets = {r["target"] for r in rows}
        assert targets == {"t1", "t2"}


class TestWorktreePathScoping:
    """Regression test for the 2026-07-20 bug: `refresh()`/`query()` without
    `worktree_path` silently hashed/read the PRIMARY's ndjson (bound at
    MCP-server-startup CWD) even when called from inside an engineer
    worktree with its own uncommitted ndjson appends — reporting a false
    'in-sync' the worktree's own pre-commit hook correctly caught as stale."""

    @staticmethod
    def _make_fake_worktree(tmp_path, name):
        # `resolve_caller_root` only checks EXISTENCE of `.git` + the marker
        # file (KB § PATTERNS/common/... resolve_caller_root contract) — no
        # real git init needed, mirrors the lightweight fixture in
        # test_mole_tool.py.
        wt = tmp_path / name
        wt.mkdir(parents=True)
        (wt / ".git").write_text("gitdir: /nowhere\n")
        (wt / ".noctusai-workspace").write_text("test\n")
        (wt / "project-history").mkdir()
        return wt

    def test_refresh_reads_worktree_ndjson_not_primary(self, tmp_repo):
        wt = self._make_fake_worktree(tmp_repo, "wt")
        wt_ledger = wt / "project-history" / "auto-improvement.ndjson"
        wt_ledger.write_text(
            json.dumps({"ts": "2026-07-20T00:00:00Z", "scope": "scoped", "kind": "drift",
                        "target": "x", "description": "worktree-local, uncommitted",
                        "status": "s1-emergent"}) + "\n",
            encoding="utf-8",
        )
        assert not ai.LEDGER_PATH.exists()  # primary's own copy genuinely absent

        r = ai.refresh(force=True, worktree_path=str(wt))
        assert r["status"] == "rebuilt"
        assert r["rows_written"] == 1
        assert r["resolved_ledger_path"] == str(wt_ledger)

        rows = ai.query(worktree_path=str(wt))
        assert len(rows) == 1 and rows[0]["target"] == "x"

        # Omitting worktree_path stays scoped to the (empty) primary — the
        # bug (a silent, wrong-tree false-'in-sync') is closed by never
        # reading the worktree's content without being explicitly told to.
        r_primary = ai.refresh(force=True)
        assert r_primary["rows_written"] == 0
        assert r_primary["resolved_ledger_path"] == str(ai.LEDGER_PATH)

    def test_refresh_worktree_path_rejects_non_worktree_dir(self, tmp_repo, tmp_path):
        bogus = tmp_path / "not-a-worktree"
        bogus.mkdir()
        with pytest.raises(ValueError):
            ai.refresh(worktree_path=str(bogus))


class TestInvokingTree:
    """`invoking_tree` — the refresher resolves the ledger from the tree the
    gate hashes (settings.REPO_ROOT), not the primary-pinned LEDGER_PATH."""

    def test_explicit_worktree_path_wins(self):
        assert ai.invoking_tree("/some/wt") == "/some/wt"

    def test_repo_root_equal_to_ledger_root_is_primary_default(self, tmp_path, monkeypatch):
        import settings
        monkeypatch.setattr(settings, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(ai, "LEDGER_ROOT", tmp_path)
        assert ai.invoking_tree(None) is None

    def test_refresh_hashes_same_sha_as_gate_when_primary_lags(self, tmp_repo, monkeypatch):
        import settings
        wt = TestWorktreePathScoping._make_fake_worktree(tmp_repo, "wt2")
        (wt / "project-history" / "auto-improvement.ndjson").write_text(
            json.dumps({"ts": "2026-09-30T00:00:00Z", "scope": "scoped", "kind": "drift",
                        "target": "y", "description": "worktree ahead of lagging primary",
                        "status": "s1-emergent"}) + "\n", encoding="utf-8")
        monkeypatch.setattr(settings, "REPO_ROOT", wt)
        monkeypatch.setattr(ai, "LEDGER_ROOT", tmp_repo)  # primary, no ledger
        tree = ai.invoking_tree(None)
        assert tree == str(wt)
        r = ai.refresh(force=True, worktree_path=tree)
        assert r["source_sha"] == ai.source_sha_for_root(wt)
        assert check_auto_improvement_cache_freshness(wt) == []


class TestFreshnessKeeper:
    def test_fresh_repo_no_issues(self, tmp_repo):
        # No ndjson present → keeper silently passes.
        issues = check_auto_improvement_cache_freshness(repo_root=tmp_repo)
        assert issues == []

    def test_cache_missing_when_ndjson_exists_flagged(self, tmp_repo, monkeypatch):
        # Disable Tier-2 auto-pull so the missing cache stays missing (else the
        # Tier-1 resolver would pull it from the prod mirror and create it).
        monkeypatch.setenv("NOCTUS_DISABLE_AUTO_CACHE_PULL", "1")
        # Write the ndjson directly (without the helper, so the cache isn't built).
        ai.LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        ai.LEDGER_PATH.write_text(
            json.dumps({
                "ts": "2026-05-26", "agent": "tl", "scope": "broad", "kind": "drift",
                "target": "*", "description": "x", "status": "s1-emergent", "source_ref": None,
            }) + "\n",
            encoding="utf-8",
        )
        issues = check_auto_improvement_cache_freshness(repo_root=tmp_repo)
        assert any(i["symbol"] == "auto-improvement-cache-missing" for i in issues)

    def test_clean_state_passes(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="X", agent="tl")
        ai.refresh(force=True)
        issues = check_auto_improvement_cache_freshness(repo_root=tmp_repo)
        assert issues == []


class TestLogResolveFields:
    def test_resolve_when_and_to_persisted(self, tmp_repo):
        r = ai.log_entry(
            scope="broad", kind="drift", target="t", description="d", agent="tl",
            status="s2-memory", resolve_when="keeper:check_x", resolve_to="s4-keeper",
        )
        assert r["ok"] is True
        e = json.loads(ai.LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert e["resolve_when"] == "keeper:check_x"
        assert e["resolve_to"] == "s4-keeper"

    def test_omitted_resolve_fields_absent(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="t", description="d", agent="tl")
        e = json.loads(ai.LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert "resolve_when" not in e and "resolve_to" not in e

    def test_invalid_resolve_to_rejected(self, tmp_repo):
        r = ai.log_entry(scope="broad", kind="improvement", target="t", description="d",
                         resolve_to="bogus")
        assert r["ok"] is False
        assert "resolve_to must be one of" in r["error"]

    def test_log_entry_eager_refreshes_mirror(self, tmp_repo):
        # 3-leg keeper-mirror contract: log_entry must leave the mirror cache
        # FRESH at the mutation point (not stale awaiting lazy/heal-on-contact
        # rebuild). Proof: a refresh() immediately after reports 'in-sync'
        # (no rebuild needed). If log_entry only appended (the old lazy path),
        # the cache would be stale → this refresh would report 'rebuilt'.
        ai.log_entry(scope="broad", kind="improvement", target="x", description="first")
        r = ai.refresh()
        assert r["status"] == "in-sync", f"expected eager-refreshed mirror, got {r}"
        # A second append also stays compliant immediately.
        ai.log_entry(scope="broad", kind="improvement", target="y", description="second")
        assert ai.refresh()["status"] == "in-sync"


class TestReconcile:
    def _seed_compliance(self, root: Path, *keeper_names: str) -> None:
        comp = root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
        comp.parent.mkdir(parents=True, exist_ok=True)
        comp.write_text("".join(f"def {n}(x):\n    return []\n" for n in keeper_names), encoding="utf-8")

    def test_keeper_predicate_closes_and_is_idempotent(self, tmp_repo):
        self._seed_compliance(tmp_repo, "check_embed_funnel_self_configures")
        ai.log_entry(scope="broad", kind="improvement", target="embed-funnel", description="d",
                     status="s2-memory", resolve_when="keeper:check_embed_funnel_self_configures",
                     resolve_to="s4-keeper")
        r1 = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r1["counts"]["reconciled"] == 1
        assert r1["reconciled"][0]["to"] == "s4-keeper"
        e = json.loads(ai.LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert e["status"] == "s4-keeper"
        assert e["resolved_ts"] and e["resolved_by"] == ["keeper:check_embed_funnel_self_configures"]
        # Idempotent: terminal entry never re-touched.
        r2 = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r2["counts"]["reconciled"] == 0

    def test_dry_run_does_not_mutate(self, tmp_repo):
        self._seed_compliance(tmp_repo, "check_k")
        ai.log_entry(scope="broad", kind="drift", target="t", description="d",
                     status="s2-memory", resolve_when="keeper:check_k")
        before = ai.LEDGER_PATH.read_text(encoding="utf-8")
        r = ai.reconcile(dry_run=True, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 1
        assert ai.LEDGER_PATH.read_text(encoding="utf-8") == before  # untouched

    def test_unmet_keeper_stays_open(self, tmp_repo):
        self._seed_compliance(tmp_repo, "check_present")
        ai.log_entry(scope="broad", kind="drift", target="t", description="d",
                     status="s2-memory", resolve_when="keeper:check_absent")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 0
        assert r["counts"]["still_open"] == 1

    def test_all_predicates_must_pass(self, tmp_repo):
        self._seed_compliance(tmp_repo, "check_k")
        (tmp_repo / "exists.txt").write_text("x", encoding="utf-8")
        # one met (keeper), one unmet (missing path) → AND fails → still open
        ai.log_entry(scope="broad", kind="drift", target="t", description="d", status="s2-memory",
                     resolve_when=["keeper:check_k", "path_exists:missing.txt"])
        assert ai.reconcile(dry_run=False, repo_root=tmp_repo)["counts"]["reconciled"] == 0
        # now both met
        ai.log_entry(scope="broad", kind="drift", target="t2", description="d2", status="s2-memory",
                     resolve_when=["keeper:check_k", "path_exists:exists.txt"])
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 1

    def test_grep_max_and_present(self, tmp_repo):
        kb = tmp_repo / "KB"
        kb.mkdir()
        (kb / "a.md").write_text("legacy term here", encoding="utf-8")
        # grep_max:0 fails (1 file has it); grep_max:1 passes
        ai.log_entry(scope="broad", kind="drift", target="g0", description="d", status="s2-memory",
                     resolve_when="grep_max:0:legacy term@KB")
        ai.log_entry(scope="broad", kind="drift", target="g1", description="d", status="s2-memory",
                     resolve_when="grep_max:1:legacy term@KB")
        ai.log_entry(scope="broad", kind="drift", target="gp", description="d", status="s2-memory",
                     resolve_when="grep_present:legacy term@KB")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        closed = {x["target"] for x in r["reconciled"]}
        assert closed == {"g1", "gp"}  # g0 stays open (count 1 > 0)

    def test_superseded_by(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="old-drift", description="orig",
                     status="s2-memory", resolve_when="superseded_by:embed-keeper")
        # a LATER terminal entry whose target carries the substring
        ai.log_entry(scope="broad", kind="improvement", target="embed-keeper landed",
                     description="done", status="s4-keeper")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert any(x["target"] == "old-drift" for x in r["reconciled"])

    def test_entry_without_handle_is_unhandled_not_touched(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="no-handle", description="d",
                     status="s2-memory")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 0
        assert any(u["target"] == "no-handle" for u in r["unhandled"])
        e = json.loads(ai.LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert e["status"] == "s2-memory"  # untouched

    def test_unknown_predicate_never_silently_closes(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t", description="d",
                     status="s2-memory", resolve_when="bogus_grammar:x")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 0  # unknown ⇒ unmet, loud not silent

    def test_malformed_line_preserved_through_reconcile(self, tmp_repo):
        self._seed_compliance(tmp_repo, "check_k")
        ai.log_entry(scope="broad", kind="drift", target="t", description="d",
                     status="s2-memory", resolve_when="keeper:check_k")
        with ai.LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write("not json\n")
        ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert "not json" in ai.LEDGER_PATH.read_text(encoding="utf-8")


class TestPromoteSharesRewriter:
    """codification_radar.promote now routes through ai._rewrite_ledger."""

    def test_promote_updates_and_counts(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="x",
                     status="s1-emergent")
        ai.refresh(force=True)
        rows = ai.query()
        r = cr.promote(rows, "s2-memory")
        assert r["ok"] and r["updated"] == 1 and r["no_match"] == 0
        # second promote = idempotent no-op
        rows2 = ai.query()
        r2 = cr.promote(rows2, "s2-memory")
        assert r2["updated"] == 0 and r2["no_match"] == 1

    def test_promote_preserves_malformed(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="x")
        with ai.LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write("garbage line\n")
        ai.refresh(force=True)
        cr.promote(ai.query(), "closed")
        assert "garbage line" in ai.LEDGER_PATH.read_text(encoding="utf-8")


class TestResolutionHandleKeeper:
    def test_s2_without_handle_flagged(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="lingering", description="d",
                     status="s2-memory")
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_repo)
        assert any(i["symbol"] == "open-drift-no-resolution-handle" for i in issues)

    def test_s3_without_handle_flagged(self, tmp_repo):
        # Residual-2: s3-kb / s3-codified are now gated too (they linger as radar
        # promotion candidates if they can't auto-promote).
        for st in ("s3-kb", "s3-codified"):
            ai.log_entry(scope="broad", kind="improvement", target=f"t-{st}", description="d", status=st)
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_repo)
        flagged = {i["issue"].split("`")[1] for i in issues}
        assert "t-s3-kb" in flagged and "t-s3-codified" in flagged

    def test_s3_with_handle_clean(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="ok", description="d",
                     status="s3-codified", resolve_when="keeper:check_k")
        assert check_open_drift_has_resolution_handle(repo_root=tmp_repo) == []

    def test_s2_with_handle_clean(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="ok", description="d",
                     status="s2-memory", resolve_when="keeper:check_k")
        assert check_open_drift_has_resolution_handle(repo_root=tmp_repo) == []

    def test_s1_without_handle_not_flagged(self, tmp_repo):
        # s1-emergent is too freshly-surfaced to demand a handle.
        ai.log_entry(scope="broad", kind="improvement", target="fresh", description="d",
                     status="s1-emergent")
        assert check_open_drift_has_resolution_handle(repo_root=tmp_repo) == []

    def test_no_ledger_silent_pass(self, tmp_repo):
        assert check_open_drift_has_resolution_handle(repo_root=tmp_repo) == []

    def test_legacy_alias_resolves(self):
        # Old s2-only name preserved (born s2-only, widened same day).
        assert check_s2_drift_has_resolution_handle is check_open_drift_has_resolution_handle


class TestReconcileS3AndIdempotency:
    def _seed_compliance(self, root, *names):
        comp = root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
        comp.parent.mkdir(parents=True, exist_ok=True)
        comp.write_text("".join(f"def {n}(x):\n    return []\n" for n in names), encoding="utf-8")

    def test_s3_auto_promotes_to_s4_when_keeper_lands(self, tmp_repo):
        self._seed_compliance(tmp_repo, "check_landed")
        ai.log_entry(scope="broad", kind="improvement", target="codified-x", description="d",
                     status="s3-codified", resolve_when="keeper:check_landed", resolve_to="s4-keeper")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 1
        assert r["reconciled"][0]["from"] == "s3-codified" and r["reconciled"][0]["to"] == "s4-keeper"

    def test_s3_stays_when_keeper_absent(self, tmp_repo):
        self._seed_compliance(tmp_repo, "check_other")
        ai.log_entry(scope="broad", kind="improvement", target="codified-y", description="d",
                     status="s3-codified", resolve_when="keeper:check_not_yet", resolve_to="s4-keeper")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 0 and r["counts"]["still_open"] == 1

    def test_idempotency_guard_skips_when_already_at_resolve_to(self, tmp_repo):
        # resolve_to == current status (non-terminal) → no re-stamp, no churn.
        (tmp_repo / "doc.md").write_text("x", encoding="utf-8")
        ai.log_entry(scope="broad", kind="improvement", target="already", description="d",
                     status="s3-codified", resolve_when="path_exists:doc.md", resolve_to="s3-codified")
        r = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert r["counts"]["reconciled"] == 0  # already there → skipped
        e = json.loads(ai.LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert "resolved_ts" not in e  # never stamped


class TestQueryAutoReconcileFilter:
    def _seed_compliance(self, root, *names):
        comp = root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
        comp.parent.mkdir(parents=True, exist_ok=True)
        comp.write_text("".join(f"def {n}(x):\n    return []\n" for n in names), encoding="utf-8")

    def test_open_only_excludes_resolved_entry(self, tmp_repo, monkeypatch):
        # The core fix: a landed-but-not-yet-closed entry is NOT surfaced as open,
        # WITHOUT anyone running reconcile first. Pin reconcile's tree to tmp_repo.
        self._seed_compliance(tmp_repo, "check_done")
        monkeypatch.setattr(ai, "REPO_ROOT", tmp_repo)
        ai.log_entry(scope="broad", kind="drift", target="landed", description="d",
                     status="s2-memory", resolve_when="keeper:check_done")
        ai.log_entry(scope="broad", kind="drift", target="still-pending", description="d",
                     status="s2-memory", resolve_when="keeper:check_missing")
        ai.refresh(force=True)
        targets = {r["target"] for r in ai.query(open_only=True)}
        assert "landed" not in targets       # resolve_when passes → auto-filtered
        assert "still-pending" in targets    # predicate unmet → still surfaced

    def test_skip_reconcile_returns_raw_open_set(self, tmp_repo, monkeypatch):
        self._seed_compliance(tmp_repo, "check_done")
        monkeypatch.setattr(ai, "REPO_ROOT", tmp_repo)
        ai.log_entry(scope="broad", kind="drift", target="landed", description="d",
                     status="s2-memory", resolve_when="keeper:check_done")
        ai.refresh(force=True)
        raw = {r["target"] for r in ai.query(open_only=True, skip_reconcile=True)}
        assert "landed" in raw  # raw not-closed set — the ledger's literal state

    def test_non_open_query_not_filtered(self, tmp_repo, monkeypatch):
        # A targeted (non-open_only) consult query is never reconcile-filtered.
        self._seed_compliance(tmp_repo, "check_done")
        monkeypatch.setattr(ai, "REPO_ROOT", tmp_repo)
        ai.log_entry(scope="broad", kind="drift", target="landed", description="d",
                     status="s2-memory", resolve_when="keeper:check_done")
        ai.refresh(force=True)
        assert len(ai.query(target="landed")) == 1


class TestLedgerStoreRealMode:
    """S3 #1 (2026-09-24): the writer publishes to origin/ledgers via the
    Real store, never to the dev copy; reads + rewrites dual-read."""

    @pytest.fixture
    def real(self, ledger_repo, tmp_path, monkeypatch):
        bare, clone, show = ledger_repo
        dev_copy = clone / "project-history" / "auto-improvement.ndjson"
        monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / "cache")
        monkeypatch.setattr(ai, "CACHE_PATH", tmp_path / "cache" / "auto-improvement.sqlite")
        monkeypatch.setattr(ai, "LEDGER_PATH", dev_copy)
        return dev_copy, show

    def test_log_publishes_to_ledgers_branch_not_dev(self, real):
        dev_copy, show = real
        r = ai.log_entry(scope="broad", kind="improvement", target="t/real", description="d1")
        assert r["ok"] and r["publish"]["status"] == "pushed", r
        assert not dev_copy.exists()                      # the dev copy is never written
        row = json.loads(show("auto-improvement.ndjson").strip())
        assert row["target"] == "t/real"
        assert [x["target"] for x in ai.query()] == ["t/real"]

    def test_dual_read_sees_stale_peer_dev_rows(self, real):
        dev_copy, show = real
        dev_copy.write_text(json.dumps({"ts": "2026-09-01T00:00:00Z", "scope": "broad",
                                        "kind": "drift", "target": "t/dev-only",
                                        "description": "old writer", "status": "s1-emergent"}) + "\n")
        ai.log_entry(scope="broad", kind="improvement", target="t/new", description="d2")
        assert {x["target"] for x in ai.query()} == {"t/dev-only", "t/new"}
        # the keeper and refresh agree on the merged sha
        assert ai.source_sha_for_root(dev_copy.parents[1]) == ai._source_sha()

    def test_promote_rewrites_branch_and_absorbs_dev_only_rows(self, real):
        dev_copy, show = real
        stale = {"ts": "2026-09-01T00:00:00Z", "scope": "broad", "kind": "drift",
                 "target": "t/dev-only", "description": "old writer", "status": "s1-emergent"}
        dev_copy.write_text(json.dumps(stale) + "\n")
        r = cr.promote(matches=[stale], target_status="s2-memory")
        assert r["ok"] and r["updated"] == 1, r
        branch = [json.loads(x) for x in show("auto-improvement.ndjson").splitlines()]
        assert branch[0]["status"] == "s2-memory"
        # the stale dev row does NOT undo the promotion on read (branch wins by key)
        assert [x["status"] for x in ai.query()] == ["s2-memory"]


# ── Learning-loop closure (2026-11) ──────────────────────────────────────────
from datetime import datetime, timedelta, timezone  # noqa: E402


def _row(ts, target="t", desc="d", status="s1-emergent", agent="backend-engineer", **kw):
    return {"ts": ts, "agent": agent, "scope": "scoped", "kind": "improvement",
            "target": target, "description": desc, "status": status, **kw}


def _write(ledger, rows):
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class TestDriftRequiresResolveWhen:
    def test_refused_without_resolve_when(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="drift", target="x", description="d")
        assert r["ok"] is False and r["refused"] == "drift_requires_resolve_when"
        assert not ai.LEDGER_PATH.exists() or ai.LEDGER_PATH.read_text() == ""

    def test_empty_list_refused(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="drift", target="x", description="d", resolve_when=[" "])
        assert r["refused"] == "drift_requires_resolve_when"

    def test_manual_escape_accepted(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="drift", target="x", description="d",
                         agent="backend-engineer", resolve_when="manual:engineer-footer triage")
        assert r["ok"] is True
        assert r["entry"]["resolve_when"] == "manual:engineer-footer triage"

    def test_manual_without_reason_refused(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="drift", target="x", description="d", resolve_when="manual:")
        assert r["refused"] == "manual_requires_reason"

    def test_improvement_needs_no_predicate(self, tmp_repo):
        assert ai.log_entry(scope="scoped", kind="improvement", target="x", description="d")["ok"]

    def test_manual_never_auto_closes(self, tmp_repo):
        ai.log_entry(scope="scoped", kind="drift", target="x", description="d", resolve_when="manual:why")
        rec = ai.reconcile(dry_run=True, repo_root=tmp_repo)
        assert rec["counts"]["reconciled"] == 0 and rec["counts"]["still_open"] == 1


class TestStaleS1Aging:
    NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)

    def _ts(self, days):
        return (self.NOW - timedelta(days=days)).isoformat()

    def test_boundary_13_vs_15_days(self, tmp_repo):
        _write(ai.LEDGER_PATH, [_row(self._ts(13), "young"), _row(self._ts(15), "old")])
        rec = ai.reconcile(dry_run=True, repo_root=tmp_repo, now=self.NOW)
        assert [s["target"] for s in rec["stale_s1"]] == ["old"]
        assert rec["stale_s1_count"] == 1
        assert rec["stale_s1"][0]["decide"] == "promote, close or keep"

    def test_clustered_rows_excluded_and_non_s1_ignored(self, tmp_repo):
        old, mid = _row(self._ts(30), "clustered"), _row(self._ts(30), "mem", status="s2-memory")
        _write(ai.LEDGER_PATH, [old, mid])
        rec = ai.reconcile(dry_run=True, repo_root=tmp_repo, now=self.NOW,
                           clustered_keys={ai._entry_key(old)})
        assert rec["stale_s1"] == []

    def test_aging_never_mutates_ledger(self, tmp_repo):
        _write(ai.LEDGER_PATH, [_row(self._ts(40))])
        before = ai.LEDGER_PATH.read_text()
        ai.reconcile(dry_run=False, repo_root=tmp_repo, now=self.NOW)
        assert ai.LEDGER_PATH.read_text() == before

    def test_summary_exposes_count(self, tmp_repo):
        _write(ai.LEDGER_PATH, [_row(self._ts(20)), _row(self._ts(1))])
        s = ai.summary(now=self.NOW)
        assert s["stale_s1"] == 1 and s["open"] == 2 and s["open_without_resolve_when"] == 2


class TestNewKinds:
    @pytest.mark.parametrize("kind", ["phase-learning", "finding"])
    def test_kind_with_source(self, tmp_repo, kind):
        r = ai.log_entry(scope="scoped", kind=kind, target="projects/x", description="learned",
                         source={"tool": "noctus.dev.findings", "ref": "projects/x#3"})
        assert r["ok"] and r["entry"]["source"] == {"tool": "noctus.dev.findings", "ref": "projects/x#3"}
        row = [x for x in ai.query() if x["kind"] == kind][0]
        assert row["source"]["ref"] == "projects/x#3"

    def test_bad_source_refused(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="finding", target="x", description="d", source={"tool": "t"})
        assert r["ok"] is False


class TestAgentFilter:
    def test_query_agent_filter(self, tmp_repo):
        ai.log_entry(scope="scoped", kind="improvement", target="a", description="1", agent="backend-engineer")
        ai.log_entry(scope="scoped", kind="improvement", target="b", description="2", agent="frontend-engineer")
        assert [r["target"] for r in ai.query(agent="frontend-engineer")] == ["b"]


class TestRadarGroupByAgent:
    def test_per_agent_clusters_and_l1_proposal(self, tmp_repo):
        from unittest.mock import patch
        rows = [
            _row("2026-11-01T00:00:00+00:00", "a", "Always scope the query by org. More text", agent="backend-engineer"),
            _row("2026-11-02T00:00:00+00:00", "b", "Scope every query by org id", agent="backend-engineer"),
            _row("2026-11-02T00:00:00+00:00", "c", "Scope the query by org too", agent="frontend-engineer"),
        ]
        _write(ai.LEDGER_PATH, rows)
        with patch("tools.noctus.dev.vectorize.embed_text", return_value={"ok": True, "vector": [1.0, 0.0]}):
            res = cr.cluster(group_by="agent")
        assert res["ok"] and res["group_by"] == "agent"
        assert len(res["clusters"]) == 1  # frontend has a single entry: no cluster
        c = res["clusters"][0]
        assert c["agent"] == "backend-engineer" and c["size"] == 2
        assert c["agent_file"] == ".claude/agents/backend-engineer.md"
        assert c["proposed_l1_rule"].startswith("- Scope every query by org id")

    def test_bad_group_by(self, tmp_repo):
        from unittest.mock import patch
        _write(ai.LEDGER_PATH, [_row("2026-11-01T00:00:00+00:00")])
        with patch("tools.noctus.dev.vectorize.embed_text", return_value={"ok": True, "vector": [1.0]}):
            assert cr.cluster(group_by="kind")["ok"] is False


class TestPromoteToAgentFile:
    def test_promote_sets_predicate_and_reconcile_closes(self, tmp_repo):
        _write(ai.LEDGER_PATH, [_row("2026-10-01T00:00:00+00:00", "KB § PATTERNS/x.md",
                                     "Never bind the client at import time. Details follow.")])
        ai.refresh(force=True)
        r = cr.promote(ai.query(), "s3-codified", target_agent="backend-engineer")
        assert r["ok"] and r["updated"] == 1
        row = json.loads(ai.LEDGER_PATH.read_text().strip())
        assert row["status"] == "s3-codified" and row["target_agent"] == "backend-engineer"
        assert row["draft_l1"] == "- Never bind the client at import time. → `KB § PATTERNS/x.md`"
        assert row["resolve_when"] == "grep_present:Never bind the client at import time@.claude/agents/backend-engineer.md"

        # Not applied yet → stays open.
        agents = tmp_repo / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "backend-engineer.md").write_text("# agent\n")
        assert ai.reconcile(dry_run=True, repo_root=tmp_repo)["counts"]["reconciled"] == 0
        # Tech-lead applies the line → reconcile closes it.
        (agents / "backend-engineer.md").write_text("# agent\n" + row["draft_l1"] + "\n")
        rec = ai.reconcile(dry_run=False, repo_root=tmp_repo)
        assert rec["counts"]["reconciled"] == 1
        assert json.loads(ai.LEDGER_PATH.read_text().strip())["status"] == "closed"

    def test_target_agent_requires_s3(self, tmp_repo):
        assert cr.promote([], "s2-memory", target_agent="backend-engineer")["ok"] is False
        assert cr.promote([], "s3-codified", target_agent="../evil")["ok"] is False


class TestBackfill:
    def test_proposes_superseded_by_and_path_exists_dry_run_default(self, tmp_repo):
        a = _row("2026-09-01T00:00:00+00:00", "mcp/x/foo.py", "old drift")
        b = _row("2026-10-01T00:00:00+00:00", "mcp/x/foo.py", "fixed", status="closed")
        c = _row("2026-09-02T00:00:00+00:00", "mcp/x/missing.py", "helper is missing here")
        d = _row("2026-09-03T00:00:00+00:00", "*", "no signal")
        _write(ai.LEDGER_PATH, [a, b, c, d])
        res = ai.propose_resolve_when(repo_root=tmp_repo)
        assert res["dry_run"] and res["applied"] == 0 and res["no_signal"] == 1
        assert {p["resolve_when"] for p in res["proposals"]} == {
            "superseded_by:mcp/x/foo.py", "path_exists:mcp/x/missing.py"}
        assert "resolve_when" not in json.loads(ai.LEDGER_PATH.read_text().splitlines()[0])
        res = ai.propose_resolve_when(apply=True, repo_root=tmp_repo)
        assert res["applied"] == 2
        assert json.loads(ai.LEDGER_PATH.read_text().splitlines()[0])["resolve_when"] == "superseded_by:mcp/x/foo.py"


class TestProposeResolveWhenCli:
    def test_flag_registered_and_dry_run_default(self, tmp_repo, capsys, monkeypatch):
        import cli
        _write(ai.LEDGER_PATH, [_row("2026-09-03T00:00:00+00:00", "*", "no signal")])
        monkeypatch.setattr("sys.argv", ["cli.py", "--auto-improvement-propose-resolve-when"])
        with pytest.raises(SystemExit) as e:
            cli.main()
        assert e.value.code == 0
        assert "DRY-RUN" in capsys.readouterr().out
        assert "resolve_when" not in json.loads(ai.LEDGER_PATH.read_text().splitlines()[0])
