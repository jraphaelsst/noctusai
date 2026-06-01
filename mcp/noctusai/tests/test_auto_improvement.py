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
            agent="backend-engineer",
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
        r = ai.log_entry(scope="invalid", kind="drift", target="*", description="x")
        assert r["ok"] is False
        assert "scope must be one of" in r["error"]

    def test_invalid_kind_rejected(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="bogus", target="*", description="x")
        assert r["ok"] is False
        assert "kind must be one of" in r["error"]

    def test_invalid_status_rejected(self, tmp_repo):
        r = ai.log_entry(scope="scoped", kind="drift", target="*", description="x", status="bogus")
        assert r["ok"] is False
        assert "status must be one of" in r["error"]


class TestRefreshAndQuery:
    def test_refresh_populates_cache(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="A pattern", agent="tech-lead")
        ai.log_entry(scope="scoped", kind="drift", target=".claude/agents/x.md", description="B drift", agent="alpha")
        r = ai.refresh(force=True)
        assert r["status"] == "rebuilt"
        assert r["rows_written"] == 2

    def test_idempotent_short_circuit(self, tmp_repo):
        ai.log_entry(scope="broad", kind="improvement", target="*", description="X", agent="tech-lead")
        ai.refresh(force=True)
        r2 = ai.refresh()
        assert r2["status"] == "in-sync"

    def test_lazy_rebuild_on_sha_mismatch(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="first", agent="tl")
        ai.refresh(force=True)
        # Add a new entry — sha drifts; next query rebuilds.
        ai.log_entry(scope="broad", kind="drift", target="t2", description="second", agent="tl")
        rows = ai.query()
        assert len(rows) == 2

    def test_query_filters_by_target(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target=".claude/agents/a.md", description="x", agent="tl")
        ai.log_entry(scope="broad", kind="drift", target=".claude/agents/b.md", description="y", agent="tl")
        ai.log_entry(scope="broad", kind="drift", target="KB § PATTERNS/z.md", description="z", agent="tl")
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
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x", agent="tl", status="s1-emergent")
        ai.log_entry(scope="broad", kind="drift", target="t2", description="y", agent="tl", status="closed")
        ai.log_entry(scope="broad", kind="drift", target="t3", description="z", agent="tl", status="s4-keeper")
        ai.log_entry(scope="broad", kind="drift", target="t4", description="w", agent="tl", status="s3-codified")
        ai.refresh(force=True)
        targets = {r["target"] for r in ai.query(open_only=True, skip_reconcile=True)}
        assert targets == {"t1", "t4"}      # s1 + s3 surface
        assert "t2" not in targets          # closed — terminal
        assert "t3" not in targets          # s4-keeper — terminal (the fix)

    def test_query_filter_by_kind(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x", agent="tl")
        ai.log_entry(scope="broad", kind="improvement", target="t1", description="y", agent="tl")
        ai.refresh(force=True)
        assert len(ai.query(kind="drift")) == 1
        assert len(ai.query(kind="improvement")) == 1

    def test_malformed_ndjson_line_skipped(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x", agent="tl")
        # Write a malformed line directly.
        with ai.LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write("not valid json at all\n")
        ai.log_entry(scope="broad", kind="drift", target="t2", description="y", agent="tl")
        ai.refresh(force=True)
        rows = ai.query()
        # Two valid entries; the malformed line was silently skipped.
        targets = {r["target"] for r in rows}
        assert targets == {"t1", "t2"}


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
        ai.log_entry(scope="broad", kind="drift", target="t", description="d", agent="tl")
        e = json.loads(ai.LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert "resolve_when" not in e and "resolve_to" not in e

    def test_invalid_resolve_to_rejected(self, tmp_repo):
        r = ai.log_entry(scope="broad", kind="drift", target="t", description="d",
                         resolve_to="bogus")
        assert r["ok"] is False
        assert "resolve_to must be one of" in r["error"]


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
        ai.log_entry(scope="broad", kind="drift", target="no-handle", description="d",
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
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x",
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
        ai.log_entry(scope="broad", kind="drift", target="t1", description="x")
        with ai.LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write("garbage line\n")
        ai.refresh(force=True)
        cr.promote(ai.query(), "closed")
        assert "garbage line" in ai.LEDGER_PATH.read_text(encoding="utf-8")


class TestResolutionHandleKeeper:
    def test_s2_without_handle_flagged(self, tmp_repo):
        ai.log_entry(scope="broad", kind="drift", target="lingering", description="d",
                     status="s2-memory")
        issues = check_open_drift_has_resolution_handle(repo_root=tmp_repo)
        assert any(i["symbol"] == "open-drift-no-resolution-handle" for i in issues)

    def test_s3_without_handle_flagged(self, tmp_repo):
        # Residual-2: s3-kb / s3-codified are now gated too (they linger as radar
        # promotion candidates if they can't auto-promote).
        for st in ("s3-kb", "s3-codified"):
            ai.log_entry(scope="broad", kind="drift", target=f"t-{st}", description="d", status=st)
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
        ai.log_entry(scope="broad", kind="drift", target="fresh", description="d",
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
