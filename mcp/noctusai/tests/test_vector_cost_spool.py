"""The cost-ledger fold-into-commit contract (2026-08-11).

WHAT THIS PINS. Cost rows are appended as a side-effect of embedding work whose
timing we do not control — above all the pre-push refreshes, which run AFTER the
last commit and after the push refs are negotiated. When those rows went straight
into the git-TRACKED ledger, the tree went dirty at a moment when nothing could
commit it, so the pre-push hook swept them into a `chore(cost-log)` commit. That
commit could not join the push that created it, so it rode the NEXT push, moved
the branch tip, and cancelled the in-flight CI run for the sha that mattered
(`test.yml` sets `concurrency: cancel-in-progress`). Five CI runs died that way in
one session; `git log --grep=cost-log` showed 20+ commits of pure churn.

THE INVARIANT: the tracked ledger only ever changes inside a real commit.
  writes  → untracked spool (any time, harmless — untracked ≠ dirty tracked tree)
  drain   → pre-commit only  (folds the spool in, stages it, rides the commit)
  reads   → ledger + spool   (so an un-drained row is never missing from a report)

The hook-text tests below are deliberately coarse. They cannot prove the hooks
behave; they prove the two things that would silently undo this fix — a `git
commit` of the ledger reappearing in pre-push, or the drain going missing from
pre-commit. Both are one careless edit away, and neither shows up in any other
suite. → KB § PATTERNS/common/vector-cost-tracking.md § Fold-into-commit.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import vector_costs as vc  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
PRE_PUSH = REPO / "scripts" / "hooks" / "pre-push"
PRE_COMMIT = REPO / "scripts" / "hooks" / "pre-commit"


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Redirect both the ledger and the spool into a temp dir."""
    ledger = tmp_path / "project-history" / "vector-costs.ndjson"
    spool = tmp_path / "project-history" / ".vector-costs-spool.ndjson"
    ledger.parent.mkdir(parents=True)
    monkeypatch.setattr(vc, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vc, "SPOOL_PATH", spool)
    return ledger, spool


def _log(ns="kb-embeddings", tokens=100):
    return vc.log_refresh_batch(
        namespace=ns, model="text-embedding-3-small",
        doc_count=1, chunk_count=1, estimated_tokens=tokens,
    )


# ── writes go to the spool, never the tracked ledger ──────────────────────────

class TestWritesAreSpooled:
    def test_log_writes_spool_and_leaves_ledger_untouched(self, paths):
        ledger, spool = paths
        r = _log()
        assert r["ok"] is True
        assert r["spooled"] is True
        assert spool.exists(), "cost row must land in the spool"
        assert not ledger.exists(), (
            "log_refresh_batch must NEVER touch the tracked ledger — that is the "
            "whole point: a tracked file must not go dirty outside a commit"
        )

    def test_returned_path_is_the_spool(self, paths):
        _ledger, spool = paths
        assert _log()["path"] == str(spool)


# ── drain folds the spool into the ledger ─────────────────────────────────────

class TestDrainSpool:
    def test_drain_moves_rows_into_ledger_and_empties_spool(self, paths):
        ledger, spool = paths
        _log(tokens=100)
        _log(tokens=200)

        result = vc.drain_spool()

        assert result["ok"] is True
        assert result["drained"] == 2
        rows = [json.loads(ln) for ln in ledger.read_text().strip().splitlines()]
        assert [r["estimated_tokens"] for r in rows] == [100, 200], "write order preserved"
        assert not spool.exists(), "spool is emptied so rows are never folded in twice"

    def test_drain_appends_and_does_not_clobber_existing_ledger(self, paths):
        ledger, _spool = paths
        ledger.write_text(json.dumps({"ts": "2026-01-01T00:00:00+00:00",
                                      "namespace": "old", "estimated_cost_usd": 0.5}) + "\n")
        _log()

        vc.drain_spool()

        rows = [json.loads(ln) for ln in ledger.read_text().strip().splitlines()]
        assert len(rows) == 2
        assert rows[0]["namespace"] == "old", "the append-only history must survive a drain"

    def test_drain_is_a_noop_when_spool_absent(self, paths):
        ledger, _spool = paths
        result = vc.drain_spool()
        assert result["ok"] is True and result["drained"] == 0
        assert not ledger.exists(), "a no-op drain must not create an empty ledger"

    def test_drain_is_idempotent(self, paths):
        ledger, _spool = paths
        _log()
        vc.drain_spool()
        second = vc.drain_spool()
        assert second["drained"] == 0
        assert len(ledger.read_text().strip().splitlines()) == 1, "no duplicate rows"

    def test_drain_tolerates_a_spool_of_only_blank_lines(self, paths):
        ledger, spool = paths
        spool.write_text("\n\n  \n")
        result = vc.drain_spool()
        assert result["ok"] is True and result["drained"] == 0
        assert not ledger.exists()
        assert not spool.exists(), "a junk-only spool is cleared, not left to accrete"


# ── reads must see un-drained rows ────────────────────────────────────────────

class TestReadsSeeBothFiles:
    def test_total_counts_undrained_spool_rows(self, paths):
        """Deferring the ledger write must not silently under-report cost."""
        _log(tokens=1_000_000)
        t = vc.total()
        assert t["batch_count"] == 1
        assert t["estimated_tokens"] == 1_000_000

    def test_total_is_unchanged_by_draining(self, paths):
        _log(tokens=500)
        before = vc.total()
        vc.drain_spool()
        after = vc.total()
        assert before == after, "a drain relocates rows; it must not change the numbers"

    def test_report_merges_ledger_and_spool(self, paths):
        ledger, _spool = paths
        ledger.write_text(json.dumps({
            "ts": "2026-01-01T00:00:00+00:00", "namespace": "kb-embeddings",
            "estimated_tokens": 10, "estimated_cost_usd": 0.001, "doc_count": 1,
            "chunk_count": 1,
        }) + "\n")
        _log(ns="kb-embeddings", tokens=20)

        periods = vc.report(namespace="kb-embeddings")

        assert sum(p["batch_count"] for p in periods) == 2
        assert sum(p["estimated_tokens"] for p in periods) == 30


# ── the hooks themselves (the regression this whole file exists for) ──────────

class TestHookContract:
    def test_pre_push_makes_no_cost_log_commit(self):
        """🔴 A commit created in pre-push cancels that push's own CI run.

        It cannot join the push that created it (refs already negotiated), so it
        rides the NEXT push and moves the branch tip. Re-adding one here is the
        single edit that would silently restore the bug.
        """
        text = PRE_PUSH.read_text()
        offenders = [
            ln.strip() for ln in text.splitlines()
            # A real command, not the block comment explaining why it is gone.
            if not ln.lstrip().startswith("#")
            and re.search(r"\bgit\b.*\bcommit\b", ln)
        ]
        assert not offenders, (
            "pre-push must not create commits — found:\n  " + "\n  ".join(offenders)
        )

    def test_pre_push_does_not_reference_the_removed_escape_hatch(self):
        """NOCTUS_SKIP_COSTLOG_COMMIT only existed to disable the removed sweep."""
        live = [
            ln for ln in PRE_PUSH.read_text().splitlines()
            if not ln.lstrip().startswith("#") and "NOCTUS_SKIP_COSTLOG_COMMIT" in ln
        ]
        assert not live, "dead escape hatch left wired — it now controls nothing"

    def test_pre_commit_drains_the_spool_before_staging_the_ledger(self):
        """Order matters: draining after the `git add` would stage a stale ledger."""
        text = PRE_COMMIT.read_text()
        drain_at = text.find("--vector-costs-drain-spool")
        stage_at = text.find("git add -- project-history/vector-costs.ndjson")
        assert drain_at != -1, "pre-commit must drain the cost spool"
        assert stage_at != -1, "pre-commit must stage the ledger"
        assert drain_at < stage_at, "drain must run BEFORE the ledger is staged"

    def test_cli_exposes_the_drain_flag(self):
        """The hook shells out to this flag; a rename would silently no-op it."""
        assert "--vector-costs-drain-spool" in (REPO / "mcp" / "noctusai" / "cli.py").read_text()


# ── the spool must stay untracked ─────────────────────────────────────────────

class TestSpoolIsGitIgnored:
    def test_spool_path_is_ignored_by_git(self):
        """If the spool were tracked, every fix above would be undone at once."""
        rel = "project-history/.vector-costs-spool.ndjson"
        proc = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=REPO, capture_output=True,
        )
        assert proc.returncode == 0, f"{rel} MUST be gitignored (git check-ignore said no)"

    def test_spool_is_not_tracked(self):
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "project-history/.vector-costs-spool.ndjson"],
            cwd=REPO, capture_output=True,
        )
        assert proc.returncode != 0, "the spool must never be committed"
