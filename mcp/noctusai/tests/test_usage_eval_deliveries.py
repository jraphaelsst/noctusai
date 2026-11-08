"""noctus.dev.usage_eval action=sync_deliveries — dedup, join, models, cost, ambiente, origem, missing table."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.noctus.dev import usage_eval as ue

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def _score(slug="s1", agent="backend-engineer", ts="2026-11-04T19:52:00+00:00", model="claude-sonnet-5-5",
           tokens=100_000, **kw):
    return {"ts": ts, "slug": slug, "branch": f"feat/{slug}", "sha": "abc", "agent": agent, "model": model,
            "planner_model": "claude-opus-5-5", "q": {"Q1": 4.0}, "q_weighted": 3.5, "tokens": tokens,
            "tool_uses": 5, "wall_s_measured": 60, "wall_s_self_reported": 90, "first_pass": True,
            "rework_commits": 0, **kw}


def _budget(slug="s1", agent="backend-engineer", ts="2026-11-04T19:55:00+00:00", **kw):
    return {"ts": ts, "slug": slug, "agent": agent, "duration_minutes": 12.0, "estimated_tokens": None,
            "outcome": "landed", "notes": "n", **kw}


def _nd(rows) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def _build(scores=(), budgets=(), **kw):
    return ue.build_deliveries(_nd(scores), _nd(budgets), amb="local", now=NOW, **kw)


def test_dedup_is_idempotent_on_line_hash_and_natural_key() -> None:
    s = _score()
    same_key_other_body = _score(q_weighted=1.0)  # same (slug, agent, ts), different hash
    rows, stats = _build([s, s, same_key_other_body])
    assert len(rows) == 1 and stats["duplicates"] == 2
    again, _ = _build([s, s, same_key_other_body])
    assert again == rows  # same input => same rows (hash included)


def test_budget_joins_score_within_15_minutes_only() -> None:
    rows, stats = _build([_score()], [_budget(ts="2026-11-04T20:06:00+00:00")])  # +14 min
    assert len(rows) == 1 and stats["matched"] == 1
    assert rows[0]["duration_minutes"] == 12.0 and rows[0]["outcome"] == "landed"
    rows, stats = _build([_score()], [_budget(ts="2026-11-04T20:08:00+00:00")])  # +16 min
    assert len(rows) == 2 and stats["unmatched_budget"] == 1 and stats["unmatched_score"] == 1
    orphan = next(r for r in rows if r["q_weighted"] is None)  # unmatched budget keeps null scores
    assert orphan["q"] is None and orphan["outcome"] == "landed" and orphan["tokens"] is None
    scored = next(r for r in rows if r["q_weighted"] is not None)
    assert scored["duration_minutes"] is None and scored["outcome"] is None


def test_join_requires_same_slug_and_agent_and_each_budget_used_once() -> None:
    _, stats = _build([_score(), _score(ts="2026-11-04T19:53:00+00:00")], [_budget(), _budget(agent="x")])
    assert stats["matched"] == 1 and stats["unmatched_score"] == 1 and stats["unmatched_budget"] == 1


def test_unknown_model_kept_raw_and_counted() -> None:
    rows, stats = _build([_score(model="gpt-mystery-9"), _score(slug="s2", model="claude-opus-5-5-2026-09-08")])
    by = {r["slug"]: r for r in rows}
    assert by["s1"]["model"] == "gpt-mystery-9" and stats["unknown_model"] == 1
    assert by["s1"]["cost_usd"] is None  # unpriced model => no invented cost
    assert by["s2"]["model"] == "claude-opus-5-5"  # pinned snapshot canonicalised


def test_null_tokens_give_null_cost_and_priced_tokens_get_an_estimate() -> None:
    rows, _ = _build([_score(tokens=None), _score(slug="s2", tokens=1_000_000)])
    by = {r["slug"]: r for r in rows}
    assert by["s1"]["tokens"] is None and by["s1"]["cost_usd"] is None and by["s1"]["cost_is_estimate"] is None
    # sonnet 5.5: $2 in / $10 out per MTok, 90/10 split => 0.9*2 + 0.1*10 = 2.8
    assert by["s2"]["cost_usd"] == pytest.approx(2.8)
    assert by["s2"]["cost_is_estimate"] is True and by["s2"]["price_version"].startswith("catalog:")


def test_budget_tokens_fill_only_when_the_score_has_none() -> None:
    rows, _ = _build([_score(tokens=None)], [_budget(total_tokens=500, input_tokens=400, output_tokens=100)])
    assert rows[0]["tokens"] == 500


def test_window_filters_by_ts() -> None:
    rows, stats = _build([_score(), _score(slug="late", ts="2026-11-06T00:00:00+00:00")],
                         since=datetime(2026, 11, 5, tzinfo=timezone.utc))
    assert [r["slug"] for r in rows] == ["late"] and stats["out_of_window"] == 1


def test_ambiente_derivation_order() -> None:
    fleet = {"noctus-core"}
    assert ue.ambiente({"NOC_AMBIENTE": "prod", "CI": "true"}, "x", fleet) == "prod"  # explicit wins over CI
    assert ue.ambiente({"CI": "true"}, "noctus-core", fleet) == "ci"  # CI wins over the fleet host
    assert ue.ambiente({"GITHUB_ACTIONS": "true"}, "x", fleet) == "ci"
    assert ue.ambiente({}, "noctus-core", fleet) == "prod"
    assert ue.ambiente({}, "laptop", fleet) == "local"
    with pytest.raises(ValueError):
        ue.ambiente({"NOC_AMBIENTE": "staging"}, "x", fleet)


def test_fleet_hosts_are_derived_from_the_compose_file(tmp_path: Path) -> None:
    c = tmp_path / "c.yml"
    c.write_text("services:\n  core:\n    container_name: noctus-core\n  w:\n    hostname: Box.example\n")
    assert ue.fleet_hosts(c, env={"NOCTUS_VPS_HOST": "vps1.example.com"}) == {"noctus-core", "box", "vps1"}
    assert ue.fleet_hosts(tmp_path / "missing.yml", env={}) == set()


def test_origem_is_desconhecido_unless_readable() -> None:
    assert ue.origem_of() == "desconhecido"
    assert ue.origem_of({"entrypoint": "cli", "userType": "external"}) == "desconhecido"
    assert ue.origem_of({"auth_mode": "assinatura"}) == "assinatura"
    rows, _ = _build([_score()])
    assert rows[0]["origem"] == "desconhecido"


class _Table:
    def __init__(self, client, name):
        self.c, self.name = client, name

    def select(self, *_a):
        self.op = "select"
        return self

    def limit(self, _n):
        return self

    def upsert(self, rows, on_conflict):
        self.op, self.rows, self.conflict = "upsert", rows, on_conflict
        return self

    def execute(self):
        if self.c.missing and self.name == ue.DELIVERIES_TABLE:
            err = RuntimeError("Could not find the table 'public.dev_deliveries' in the schema cache")
            err.code = "PGRST205"  # type: ignore[attr-defined]
            raise err
        if self.op == "upsert":
            self.c.writes.append((self.name, self.conflict, self.rows))


class _Client:
    def __init__(self, missing=False):
        self.missing, self.writes = missing, []

    def table(self, name):
        return _Table(self, name)


LEDGERS = (_nd([_score()]), _nd([_budget()]), [])
KW = {"env": {}, "hostname": "laptop", "fleet": set()}


def test_dry_run_needs_no_table_and_no_client() -> None:
    out = ue.sync_deliveries(dry_run=True, ledgers=LEDGERS, **KW)
    assert out["dry_run"] and out["rows"] == 1 and out["written"] == 0 and out["ambiente"] == "local"


def test_real_run_on_missing_table_fails_loudly_and_writes_nothing() -> None:
    c = _Client(missing=True)
    with pytest.raises(ue.DeliveriesSchemaError, match="migration 111"):
        ue.sync_deliveries(client=c, ledgers=LEDGERS, **KW)
    assert c.writes == []


def test_real_run_upserts_on_the_natural_key_and_is_repeatable() -> None:
    c = _Client()
    a = ue.sync_deliveries(client=c, ledgers=LEDGERS, **KW)
    b = ue.sync_deliveries(client=c, ledgers=LEDGERS, **KW)
    assert a["written"] == b["written"] == 1
    assert c.writes[0][1] == "slug,agent,ts"
    strip = lambda w: [{k: v for k, v in r.items() if k != "ingested_at"} for r in w[2]]  # noqa: E731
    assert strip(c.writes[0]) == strip(c.writes[1])
