"""`noctus.dev.latency_report` — fast-responses gate. Fixture log lines only; the VPS is never called."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import latency_report as lr  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def _line(method, route, dur, status=200):
    return f"2026-10-22 10:00:00 INFO noctusai.request_timing req_timing method={method} route={route} status={status} dur_ms={dur}"


def _runner(lines):
    return lambda cmd: (0, "\n".join(lines), "")


def _many(method, route, durs):
    return [_line(method, route, d) for d in durs]


def test_ok_when_all_inside_budget():
    logs = _many("GET", "/api/me/access", [50] * 10) + _many("GET", "/api/items", [100] * 10)
    r = lr.latency_report("orbity", run_remote=_runner(logs))
    assert r["status"] == "ok" and r["exit_code"] == 0
    assert {x["class"] for x in r["routes"]} == {"shell", "read"}


def test_over_budget_uses_p95_and_class():
    # shell budget 150: p95 of 19x100 + 1x900 -> 900? nearest-rank p95 of 20 = 19th value = 100 -> ok; 3 slow of 20 -> over
    logs = _many("GET", "/api/me/access", [100] * 17 + [400] * 3)
    r = lr.latency_report("orbity", run_remote=_runner(logs))
    assert r["status"] == "over_budget" and r["exit_code"] == 1
    assert r["over_budget"][0]["route"] == "/api/me/access" and r["over_budget"][0]["budget_p95_ms"] == 150


def test_writes_get_write_budget():
    logs = _many("POST", "/api/items", [450] * 10)
    assert lr.latency_report("p", run_remote=_runner(logs))["status"] == "ok"
    logs = _many("POST", "/api/items", [550] * 10)
    assert lr.latency_report("p", run_remote=_runner(logs))["status"] == "over_budget"


def test_no_data_is_inconclusive_never_ok():
    r = lr.latency_report("orbity", run_remote=_runner(["unrelated line"]))
    assert r["status"] == "inconclusive" and r["ok"] is False and r["exit_code"] == 1


def test_thin_routes_alone_cannot_make_ok():
    r = lr.latency_report("orbity", run_remote=_runner(_many("GET", "/api/x", [10, 10])))
    assert r["status"] == "inconclusive" and r["thin"]


def test_health_and_unmatched_ignored():
    logs = _many("GET", "/api/health", [9999] * 10) + _many("GET", "<unmatched>", [9999] * 10)
    assert lr.latency_report("p", run_remote=_runner(logs))["status"] == "inconclusive"


def test_override_needs_and_carries_reason(tmp_path):
    b = json.loads((ROOT / "deploy/fleet/latency-budgets.json").read_text())
    b["overrides"] = [{"method": "GET", "route": "/api/export", "p95_ms": 2000, "reason": "streams a CSV"}]
    p = tmp_path / "b.json"
    p.write_text(json.dumps(b))
    logs = _many("GET", "/api/export", [1500] * 10)
    r = lr.latency_report("p", budgets_path=str(p), run_remote=_runner(logs))
    assert r["status"] == "ok" and r["routes"][0]["override_reason"] == "streams a CSV"


def test_percentile_nearest_rank():
    assert lr.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert lr.percentile([1, 2, 3, 4], 50) == 2


def test_log_fetch_failure_is_inconclusive():
    r = lr.latency_report("ghost", run_remote=lambda cmd: (1, "", "no such container"))
    assert r["status"] == "inconclusive" and r["exit_code"] == 1


def test_budgets_file_overrides_all_have_reasons():
    for ov in json.loads((ROOT / "deploy/fleet/latency-budgets.json").read_text())["overrides"]:
        assert ov.get("reason")


class TestWiring:
    def test_cli_and_registration_and_ship_skill(self):
        assert "--latency-report" in (ROOT / "mcp/noctusai/cli.py").read_text()
        assert "latency_report.register(server)" in (ROOT / "mcp/noctusai/tools/noctus/dev/__init__.py").read_text()
        assert "latency_report" in (ROOT / ".claude/skills/noc-ship/SKILL.md").read_text()


# --------------------------------------------------------------------------- concurrency fields (2026-10-23)
def _line_new(route, dur, **extra):
    tail = " ".join(f"{k}={v}" for k, v in extra.items())
    return _line("GET", route, dur) + " " + tail


def test_parse_old_and_new_lines_together():
    rows = lr.parse_lines([_line("GET", "/a", 10.0),
                           _line_new("/a", 20.0, inflight=3, inflight_peak=5, blk_n=2, blk_ms=11.5, blkq_ms=4.0, lag_ms=7.1)])
    assert "inflight" not in rows[0] and rows[0]["dur_ms"] == 10.0
    assert rows[1]["inflight_peak"] == 5.0 and rows[1]["blkq_ms"] == 4.0 and rows[1]["lag_ms"] == 7.1


def test_report_concurrency_percentiles_present_only_when_emitted():
    old = _many("GET", "/api/old", [50] * 6)
    new = [_line_new("/api/new", 50, inflight=i, inflight_peak=i + 1, blkq_ms=i * 2) for i in range(1, 7)]
    r = lr.latency_report("orbity", run_remote=_runner(old + new))
    by = {x["route"]: x for x in r["routes"]}
    assert "concurrency" not in by["/api/old"]
    c = by["/api/new"]["concurrency"]
    assert c["inflight_peak"]["p50"] == 4.0 and c["blkq_ms"]["p95"] == 12.0
    assert "lag_ms" not in c  # absent => omitted, never 0


def test_db_call_fields_parsed_and_reported():
    line = _line_new("/api/db", 50, inflight=1, db_n=7, db_ms=300.5, db_max_ms=90.0, db_new=2, db_conn_ms=80.0) + " db_svc=rest:7:300.5"
    row = lr.parse_lines([line])[0]
    assert row["db_n"] == 7.0 and row["db_ms"] == 300.5 and row["db_max_ms"] == 90.0
    assert row["db_new"] == 2.0 and row["db_conn_ms"] == 80.0
    r = lr.latency_report("orbity", run_remote=_runner([line.replace("dur_ms=50", "dur_ms=%d" % (50 + i)) for i in range(6)]))
    c = {x["route"]: x for x in r["routes"]}["/api/db"]["concurrency"]
    assert c["db_n"]["p50"] == 7.0 and c["db_conn_ms"]["p95"] == 80.0
