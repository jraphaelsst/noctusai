"""`noctus.dev.method_trial` — trials stored in the auto-improvement ledger."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import auto_improvement as ai  # noqa: E402
from tools.noctus.dev import codification_radar as cr  # noqa: E402
from tools.noctus.dev import method_trial as mt  # noqa: E402

METRICS = [{"name": "tokens", "how": "count tokens", "target": "<5k"},
           {"name": "rework", "how": "re-edits", "target": None}]
HYP = "using the skill reduces rework on migrations"
WHY = "measured twice, the skill held up on both migrations"


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / ".claude" / "cache")
    monkeypatch.setattr(ai, "CACHE_PATH", tmp_path / ".claude" / "cache" / "auto-improvement.sqlite")
    monkeypatch.setattr(ai, "LEDGER_PATH", tmp_path / "project-history" / "auto-improvement.ndjson")
    return tmp_path


def _open(slug="t-one", **kw):
    args = dict(slug=slug, target="skill:noc-x", hypothesis=HYP, metrics=METRICS)
    args.update(kw)
    return mt.open_trial(**args)


def _rows(tmp_repo):
    p = ai.LEDGER_PATH
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


class TestLifecycle:
    def test_open_observe_verdict_status(self, tmp_repo):
        r = _open()
        assert r["ok"]
        head = _rows(tmp_repo)[0]
        assert head["kind"] == "trial" and head["status"] == "s1-emergent"
        assert head["scope"] == "broad" and head["source_ref"] == "trial:t-one"
        assert head["trial"]["verdict"] == "pending" and head["trial"]["hypothesis"] == HYP

        o = mt.observe(slug="t-one", signal="measure", text="ran it", metric="tokens",
                       value=4200, evidence="commit abc")
        assert o["ok"]
        orow = _rows(tmp_repo)[1]
        assert orow["kind"] == "trial-obs" and orow["status"] == "closed"
        assert orow["trial"]["value"] == 4200
        mt.observe(slug="t-one", signal="friction", text="slow")

        st = mt.status(slug="t-one")["trials"][0]
        assert st["observations"]["measure"]["count"] == 1
        assert st["observations"]["friction"]["count"] == 1
        assert st["metric_values"] == {"tokens": [4200], "rework": []}
        assert st["verdict"] == "pending" and st["stale"] is False

        v = mt.verdict(slug="t-one", verdict="adopt", reasoning=WHY, changes=["a.md"])
        assert v["ok"] and "codify_log stage s3 for skill:noc-x" in v["next_steps"]
        assert _rows(tmp_repo)[-1]["kind"] == "trial-verdict"
        assert mt.status(slug="t-one")["trials"][0]["verdict"] == "adopt"

    @pytest.mark.parametrize("verdict,needle", [
        ("refine", "open nxt-1"), ("discard", "remove/rewrite"), ("extend", "widened")])
    def test_next_steps(self, tmp_repo, verdict, needle):
        _open()
        v = mt.verdict(slug="t-one", verdict=verdict, reasoning=WHY, followup_slug="nxt-1")
        assert needle in v["next_steps"]

    def test_run_dispatch_and_missing_args(self, tmp_repo):
        assert mt.run("open", slug="x")["ok"] is False
        assert mt.run("bogus")["ok"] is False
        assert mt.run("open", slug="t-one", target="x", hypothesis=HYP, metrics=METRICS)["ok"]
        assert mt.run("status")["count"] == 1


class TestRefusals:
    def test_duplicate_open_slug(self, tmp_repo):
        assert _open()["ok"]
        r = _open()
        assert not r["ok"] and "already open" in r["error"]

    def test_bad_open_inputs(self, tmp_repo):
        assert not _open(slug="Bad Slug")["ok"]
        assert not _open(hypothesis="short")["ok"]
        assert not _open(metrics=[])["ok"]
        assert not _open(metrics=[{"name": "a", "how": "x"}, {"name": "a", "how": "y"}])["ok"]

    def test_observe_unknown_and_closed(self, tmp_repo):
        assert not mt.observe(slug="nope", signal="note", text="x")["ok"]
        _open()
        mt.verdict(slug="t-one", verdict="discard", reasoning=WHY)
        r = mt.observe(slug="t-one", signal="note", text="late")
        assert not r["ok"] and "already has a verdict" in r["error"]
        assert not mt.verdict(slug="t-one", verdict="adopt", reasoning=WHY)["ok"]
        assert not _open()["ok"]  # verdicted slug cannot be reused

    def test_metric_and_signal_validation(self, tmp_repo):
        _open()
        r = mt.observe(slug="t-one", signal="measure", text="x", metric="bogus")
        assert not r["ok"] and "tokens" in r["error"]
        assert not mt.observe(slug="t-one", signal="weird", text="x")["ok"]
        assert not mt.verdict(slug="t-one", verdict="maybe", reasoning=WHY)["ok"]
        assert not mt.verdict(slug="t-one", verdict="adopt", reasoning="too short")["ok"]


class TestViews:
    def test_open_only_excludes_verdicted(self, tmp_repo):
        _open("a-one"); _open("b-two")
        mt.verdict(slug="a-one", verdict="adopt", reasoning=WHY)
        assert [t["slug"] for t in mt.status()["trials"]] == ["b-two"]
        assert {t["slug"] for t in mt.status(open_only=False)["trials"]} == {"a-one", "b-two"}

    def test_query_and_radar_ignore_obs_and_verdict(self, tmp_repo, monkeypatch):
        _open("a-one"); _open("b-two")
        mt.observe(slug="b-two", signal="note", text="n")
        mt.verdict(slug="a-one", verdict="adopt", reasoning=WHY)
        rows = ai.query(open_only=True, skip_reconcile=True)
        assert [(r["kind"], r["source_ref"]) for r in rows] == [("trial", "trial:b-two")]
        assert isinstance(rows[0]["trial"], dict)
        # radar skips trial heads entirely: nothing to embed.
        called = []
        monkeypatch.setattr("tools.noctus.dev.vectorize.embed_text",
                            lambda *a, **k: called.append(1) or {"ok": False})
        out = cr.cluster()
        assert out["ok"] and out["clusters"] == [] and not called

    def test_reconcile_leaves_trials_alone(self, tmp_repo):
        _open()
        rec = ai.reconcile(dry_run=True)
        assert rec["counts"] == {"reconciled": 0, "still_open": 0, "unhandled": 0}

    def test_stale_flag(self, tmp_repo):
        _open()
        later = datetime.now(timezone.utc) + timedelta(days=15)
        assert mt.status(now=later)["trials"][0]["stale"] is True
        mt.observe(slug="t-one", signal="note", text="recent")
        row_ts = datetime.fromisoformat(_rows(tmp_repo)[-1]["ts"])
        # a fresh observation (<7d before "now") clears staleness even when old
        assert mt.status(now=row_ts + timedelta(days=3))["trials"][0]["stale"] is False
        young = datetime.now(timezone.utc) + timedelta(days=3)
        assert mt.status(now=young)["trials"][0]["stale"] is False

    def test_report_counts(self, tmp_repo):
        for s in ("a-one", "b-two", "c-three", "d-four", "e-five"):
            _open(s)
        mt.verdict(slug="a-one", verdict="adopt", reasoning=WHY)
        mt.verdict(slug="b-two", verdict="refine", reasoning=WHY)
        mt.verdict(slug="c-three", verdict="discard", reasoning=WHY)
        mt.observe(slug="e-five", signal="note", text="n")
        rep = mt.report()
        assert rep["counts"] == {"open": 2, "adopt": 1, "refine": 1, "discard": 1, "extend": 0}
        assert {t["slug"] for t in rep["open_trials"]} == {"d-four", "e-five"}
        assert next(t for t in rep["open_trials"] if t["slug"] == "e-five")["observation_count"] == 1
        assert len(rep["last_verdicts"]) == 3
        future = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        assert mt.report(since=future)["counts"]["open"] == 0
        assert not mt.report(since="garbage")["ok"]


class TestBackCompat:
    def test_legacy_rows_without_trial_load(self, tmp_repo):
        ai.LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        ai.LEDGER_PATH.write_text(json.dumps({
            "ts": "2026-01-01T00:00:00+00:00", "agent": "x", "scope": "scoped", "kind": "drift",
            "target": "t", "description": "old", "status": "s1-emergent", "source_ref": None}) + "\n")
        _open()
        rows = ai.query(skip_reconcile=True)
        assert {r["kind"] for r in rows} == {"drift", "trial"}
        assert next(r for r in rows if r["kind"] == "drift")["trial"] is None
        assert mt.status()["count"] == 1

    def test_old_cache_schema_gets_trial_column(self, tmp_repo):
        import sqlite3
        ai.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(ai.CACHE_PATH)
        c.execute("CREATE TABLE auto_improvement (rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT,"
                  " ts TEXT NOT NULL, agent TEXT, scope TEXT NOT NULL, kind TEXT NOT NULL,"
                  " target TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL,"
                  " source_ref TEXT, cached_at TEXT NOT NULL)")
        c.commit(); c.close()
        assert _open()["ok"]
        assert mt.status()["count"] == 1
