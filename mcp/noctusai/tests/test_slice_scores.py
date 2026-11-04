"""Slice-score ledger, footer->auto_improvement wiring, and agent_metrics rollup."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import dispatch_token_log as dtl  # noqa: E402
from tools.noctus.team import agent_metrics as am  # noqa: E402

GOOD_Q = {"Q1": 4, "Q2": 3.5, "Q3": 3, "Q4": 3.5, "Q5": 4, "Q6": 3, "Q7": 4}
FOOTER = """done.
drift-found:
- BE payload lacks blueprint in app/routers/viral.py
- docs stale
scoped-improvement:
- add probe for compliance.py allowlist
"""


def _score(**over):
    base = {"model": "claude-sonnet-5-5", "planner_model": "claude-opus-5-5",
            "q": dict(GOOD_Q), "tokens": 100_000, "tool_uses": 10,
            "wall_s_measured": 600, "wall_s_self_reported": 1500, "first_pass": True}
    base.update(over)
    return base


@pytest.fixture
def ledgers(tmp_path, monkeypatch):
    monkeypatch.setattr(dtl, "_ledger_path", lambda: tmp_path / "dispatch-budget.ndjson")
    monkeypatch.setattr(dtl, "_slice_scores_path", lambda: tmp_path / "slice-scores.ndjson")
    return tmp_path


class _FakeAI:
    """Recording stand-in for the auto_improvement seam."""
    def __init__(self):
        self.calls = []

    def log_entry(self, **kw):
        self.calls.append(kw)
        return {"ok": True, "entry": {"ts": f"2026-11-04T00:00:0{len(self.calls)}+00:00"}}


class TestSchema:
    def test_weights_sum_to_one(self):
        assert sum(dtl.RUBRIC_V1["weights"].values()) == pytest.approx(1.0)

    def test_row_written_with_full_schema(self, ledgers):
        r = dtl.log_completion("s", "backend-engineer", 10, score=_score(branch="b", sha="abc"))
        assert r["ok"]
        row = json.loads((ledgers / "slice-scores.ndjson").read_text().splitlines()[0]) \
            if (ledgers / "slice-scores.ndjson").exists() else r["score_row"]
        for k in ("ts", "slug", "branch", "sha", "agent", "model", "planner_model", "rubric_version",
                  "q", "q_weighted", "tokens", "tool_uses", "wall_s_measured", "wall_s_self_reported",
                  "first_pass", "rework_commits", "rework_severity", "scope_changes",
                  "drifts", "improvements", "notes"):
            assert k in row

    @pytest.mark.parametrize("bad", [5, -0.1, "3", True])
    def test_q_out_of_range_rejected(self, ledgers, bad):
        q = dict(GOOD_Q, Q1=bad)
        assert dtl.log_completion("s", "a", 1, score=_score(q=q))["ok"] is False

    def test_empty_agent_or_model_rejected(self, ledgers):
        assert dtl.log_completion("s", " ", 1, score=_score())["ok"] is False
        assert dtl.log_completion("s", "a", 1, score=_score(model=""))["ok"] is False

    def test_unknown_criterion_rejected(self, ledgers):
        assert dtl.log_completion("s", "a", 1, score=_score(q={"Q9": 1}))["ok"] is False

    def test_legacy_call_unchanged(self, ledgers):
        r = dtl.log_completion("s", "a", 1.0)
        assert r["ok"] and "score_row" not in r


class TestQWeighted:
    def test_math(self):
        # .25*4 + .2*3.5 + .15*3 + .15*3.5 + .1*4 + .05*3 + .1*4
        assert dtl.compute_q_weighted(GOOD_Q) == pytest.approx(3.625)

    def test_null_when_any_missing(self):
        assert dtl.compute_q_weighted(dict(GOOD_Q, Q7=None)) is None
        assert dtl.compute_q_weighted({k: v for k, v in GOOD_Q.items() if k != "Q7"}) is None


class TestFooter:
    def test_parse(self):
        p = dtl.parse_footer(FOOTER)
        assert [d["text"] for d in p["drifts"]][0].startswith("BE payload")
        assert p["drifts"][0]["target"] == "app/routers/viral.py"
        assert p["drifts"][1]["target"] is None
        assert len(p["improvements"]) == 1

    def test_none_sentinel_yields_nothing(self):
        p = dtl.parse_footer("drift-found:\nnone\nscoped-improvement:\nnone\n")
        assert p == {"drifts": [], "improvements": []}

    def test_logs_each_line_and_stores_ts(self, ledgers):
        fake = _FakeAI()
        r = dtl.log_completion("s", "backend-engineer", 1, score=_score(), engineer_return=FOOTER,
                               ai_logger=fake.log_entry)
        assert r["ok"]
        assert len(fake.calls) == 3
        assert {c["kind"] for c in fake.calls} == {"drift", "improvement"}
        assert all(c["resolve_when"] == "manual:engineer-footer triage" for c in fake.calls)
        assert all(c["agent"] == "backend-engineer" for c in fake.calls)
        row = r["score_row"]
        assert row["drifts"][0]["ai_ts"] == "2026-11-04T00:00:01+00:00"
        assert row["improvements"][0]["ai_ts"] == "2026-11-04T00:00:03+00:00"

    def test_missing_footer_refused_not_raised(self, ledgers):
        r = dtl.log_completion("s", "a", 1, score=_score(), engineer_return="all good, no footer")
        assert r["ok"] is False and r["refused"] == "missing-footer"
        assert not (ledgers / "dispatch-budget.ndjson").exists()


def _row(agent, model, qw, **kw):
    r = {"ts": "2026-11-03T10:00:00+00:00", "agent": agent, "model": model, "q_weighted": qw,
         "tokens": 1_000_000, "first_pass": True, "rework_severity": {}, "drifts": []}
    r.update(kw)
    return r


class TestMetrics:
    def test_grouping_and_stats(self):
        rows = [
            _row("be", "claude-sonnet-5-5", 3.0, rework_severity={"major": 1, "minor": 1}, first_pass=False,
                 wall_s_self_reported=1500, wall_s_measured=600, drifts=[{"text": "x"}]),
            _row("be", "claude-sonnet-5-5", 4.0, drifts=[{"text": "x"}, {"text": "y"}]),
            _row("be", "claude-opus-5-5", 3.8),
        ]
        out = am.rollup(rows)
        g = {(x["agent"], x["model"]): x for x in out["groups"]}
        s = g[("be", "claude-sonnet-5-5")]
        assert s["n"] == 2 and s["mean_q_weighted"] == 3.5
        assert s["first_pass_yield"] == 0.5
        assert s["rework_rate"] == 1.5  # (2+1)/2
        assert s["self_estimate_error_ratio"] == 2.5
        assert s["top_drifts"][0] == {"text": "x", "count": 2}
        assert "90/10" in out["cost_note"]

    def test_cost_estimate(self):
        # 1M tokens: .9M in + .1M out
        assert am.estimate_cost_usd("claude-opus-5-5", 1_000_000) == pytest.approx(0.9 * 4 + 0.1 * 20)
        assert am.estimate_cost_usd("claude-sonnet-5-5", 1_000_000) == pytest.approx(0.9 * 2 + 0.1 * 10)
        assert am.estimate_cost_usd("mystery", 5) is None
        assert am.estimate_cost_usd("claude-opus-5-5", None) is None

    def test_week_bucket_and_agent_filter(self):
        rows = [_row("be", "m", 3.0), _row("be", "m", 3.0, ts="2026-11-10T10:00:00+00:00"),
                _row("fe", "m", 2.0)]
        out = am.rollup(rows, agent="be", by_week=True)
        assert [g["week"] for g in out["groups"]] == ["2026-W45", "2026-W46"]
        assert out["total_rows"] == 2


class TestSupersede:
    def test_latest_row_per_slug_sha_wins(self, tmp_path, monkeypatch):
        import settings
        from tools.noctus.dev._ledger_store import append_rows
        monkeypatch.setattr(settings, "LEDGER_ROOT", tmp_path)
        path = tmp_path / "project-history" / "slice-scores.ndjson"
        path.parent.mkdir()
        old = _row("fe", "m", None, slug="s", sha="x")
        new = _row("fe", "m", 3.7, slug="s", sha="x", ts="2026-11-04T00:00:00+00:00")
        append_rows(path.name, path, [old, new], message="t")
        rows = am.load_rows()
        assert len(rows) == 1 and rows[0]["q_weighted"] == 3.7
