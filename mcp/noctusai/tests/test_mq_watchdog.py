"""`noctus.dev.mq_watchdog` — the OFF-HOST merge-queue watchdog.

WHY: four merge-queue failures reached nobody (2026-11-05 drain crash loop, 11-06 second
crash loop, 11-07 silent ejections, 11-08 a 3.5 h bisect with no steward alive). These tests
pin what decides whether the owner is told: a first run is a silent baseline, every entry
that leaves is reported LANDED/EJECTED, the first red candidate batch is reported once, a
drain failure is reported once, a stall alerts with reminders and recovers, a blind
watchdog says so, and an undelivered FAILURE is retried next run. No network, no monkeypatch.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import mq_watchdog as w  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
T0 = 1_800_000_000.0
TH = w.thresholds({})


def _snap(*entries):
    return {"status": "ok", "entries": [{"slug": s, "sha": sha, "ref": f"mq/{s}--{sha[:7]}",
                                         "verdict": {"state": st}} for s, sha, st in entries]}


def _status(table):
    return lambda sha: table.get(sha, {"state": "queued"})


def _step(state, snap, *, status=None, drain=(), tests=(), now=T0, err=None):
    return w.evaluate(state, snap, err, status or _status({}), list(drain), list(tests), now, TH)


def _baselined(snap, now=T0, **kw):
    st, ev = _step(w.fresh_state(), snap, now=now, **kw)
    assert not any(ev.values()), ev  # first run never alerts
    return st


A = ("seed-a", "a" * 40, "pending")
B = ("seed-b", "b" * 40, "queued")


def test_first_run_is_a_silent_baseline_even_with_red_history():
    red = {"id": 1, "status": "completed", "conclusion": "failure", "head_branch": "mq-candidate/9-1"}
    st, ev = _step(w.fresh_state(), _snap(A), tests=[red])
    assert not any(ev.values())
    assert st["baseline"] and "1" in st["seen_runs"]


def test_left_entries_report_landed_and_ejected():
    st = _baselined(_snap(A, B))
    status = _status({"a" * 40: {"state": "landed", "dev_sha": "deadbeef1"},
                      "b" * 40: {"state": "ejected", "description": "ci_red: MCP Toolkit Tests", "url": "u"}})
    st, ev = _step(st, _snap(), status=status, now=T0 + 600)
    assert ev["landed"] == [{"slug": "seed-a", "sha": "a" * 9, "dev_sha": "deadbeef1"}]
    assert ev["ejected"][0]["slug"] == "seed-b" and "ci_red" in ev["ejected"][0]["why"]
    assert w.has_failure(ev)
    subject, body = w.compose(ev, 0)
    assert "1 landed" in subject and "1 EJECTED" in subject
    assert "EJECTED seed-b" in body and "LANDED seed-a" in body


def test_unreadable_final_verdict_retries_then_reports_unknown():
    st = _baselined(_snap(A))
    for i in range(int(TH["MQW_LEFT_RETRIES"]) - 1):
        st, ev = _step(st, _snap(), status=_status({"a" * 40: {"state": "unavailable"}}), now=T0 + 60 * (i + 1))
        assert not ev["unknown"] and "a" * 40 in st["leaving"]
    st, ev = _step(st, _snap(), status=_status({"a" * 40: {"state": "unavailable"}}), now=T0 + 3600)
    assert ev["unknown"][0]["slug"] == "seed-a" and not st["leaving"]


def test_red_candidate_batch_reported_once_and_green_ignored():
    st = _baselined(_snap(A))
    red = {"id": 42, "status": "completed", "conclusion": "failure", "head_branch": "mq-candidate/7-5", "html_url": "r"}
    green = {"id": 43, "status": "completed", "conclusion": "success", "head_branch": "mq-candidate/7-6"}
    other = {"id": 44, "status": "completed", "conclusion": "failure", "head_branch": "feat/x"}
    st, ev = _step(st, _snap(A), tests=[red, green, other], now=T0 + 600)
    assert [x["run"] for x in ev["batch_red"]] == ["42"]
    st, ev = _step(st, _snap(A), tests=[red, green, other], now=T0 + 1200)
    assert not ev["batch_red"]


def test_drain_failure_reported_once_cancelled_ignored():
    st = _baselined(_snap(A))
    runs = [{"id": 7, "status": "completed", "conclusion": "failure", "html_url": "d"},
            {"id": 8, "status": "completed", "conclusion": "cancelled"}]
    st, ev = _step(st, _snap(A), drain=runs, now=T0 + 600)
    assert [x["run"] for x in ev["drain_failed"]] == ["7"]
    st, ev = _step(st, _snap(A), drain=runs, now=T0 + 1200)
    assert not ev["drain_failed"]


def test_stall_alerts_reminds_and_recovers():
    st = _baselined(_snap(A))
    st, ev = _step(st, _snap(A), now=T0 + 89 * 60)
    assert not ev["stall"]
    st, ev = _step(st, _snap(A), now=T0 + 91 * 60)
    assert ev["stall"] and "nothing has left the queue for 91 min" in ev["stall"][0]
    st, ev = _step(st, _snap(A), now=T0 + 100 * 60)
    assert not ev["stall"]  # deduped until the reminder interval
    st, ev = _step(st, _snap(A), now=T0 + (91 + 120) * 60)
    assert ev["stall"]  # reminder
    st, ev = _step(st, _snap(), status=_status({"a" * 40: {"state": "landed", "dev_sha": "1"}}), now=T0 + 220 * 60)
    assert ev["landed"] and ev["recovered"] and st["stall_alerted_at"] is None


def test_long_running_drain_is_a_stall_even_while_entries_wait_briefly():
    st = _baselined(_snap(A))
    started = "2027-01-15T08:00:00Z"
    now = w._epoch(started) + 151 * 60
    st["last_progress_at"] = now - 60  # something left a minute ago
    st, ev = _step(st, _snap(A), drain=[{"id": 9, "status": "in_progress", "run_started_at": started,
                                          "html_url": "x"}], now=now)
    assert ev["stall"] and "drain run 9 in progress for 151 min" in ev["stall"][0]


def test_empty_queue_never_stalls():
    st = _baselined(_snap())
    st, ev = _step(st, _snap(), now=T0 + 10 * 3600)
    assert not ev["stall"]


def test_blind_after_n_runs_then_recovers():
    st = _baselined(_snap(A))
    for i in range(int(TH["MQW_BLIND_RUNS"]) - 1):
        st, ev = _step(st, None, err="gh: EOF", now=T0 + 600 * (i + 1))
        assert not ev["blind"]
    st, ev = _step(st, None, err="gh: EOF", now=T0 + 3600)
    assert ev["blind"] and "gh: EOF" in ev["blind"][0]["error"]
    st, ev = _step(st, None, err="gh: EOF", now=T0 + 4200)
    assert not ev["blind"]  # once
    st, ev = _step(st, _snap(A), now=T0 + 4800)
    assert ev["recovered"]


def test_nothing_happened_composes_nothing():
    st = _baselined(_snap(A))
    _, ev = _step(st, _snap(A), now=T0 + 600)
    assert w.compose(ev, 1) is None


# ── run(): delivery routing + undelivered-failure retry ───────────────────────
def _run(tmp_path, snaps, statuses=None, senders=None, now=T0):
    it = iter(snaps)
    return w.run(tmp_path / "s.json", send=True, env={"GITHUB_REPOSITORY": "o/r"},
                 snapshot_fn=lambda: next(it), status_fn=_status(statuses or {}),
                 runs_fn=lambda wf: [], senders=senders if senders is not None else {}, clock=lambda: now)


def test_success_only_goes_to_whatsapp_only(tmp_path):
    calls = []
    senders = {"whatsapp": lambda s, b: (calls.append("wa") or True, "ok"),
               "email": lambda s, b: (calls.append("em") or True, "ok")}
    _run(tmp_path, [_snap(A)], senders=senders)
    rep = _run(tmp_path, [_snap()], {"a" * 40: {"state": "landed", "dev_sha": "1"}}, senders, now=T0 + 600)
    assert rep["sent"] and calls == ["wa"]


def test_failure_goes_to_every_channel(tmp_path):
    calls = []
    senders = {"whatsapp": lambda s, b: (calls.append("wa") or True, "ok"),
               "email": lambda s, b: (calls.append("em") or True, "ok")}
    _run(tmp_path, [_snap(A)], senders=senders)
    _run(tmp_path, [_snap()], {"a" * 40: {"state": "ejected", "description": "x"}}, senders, now=T0 + 600)
    assert calls == ["wa", "em"]


def test_undelivered_failure_exits_1_and_is_retried(tmp_path):
    _run(tmp_path, [_snap(A)])
    ej = {"a" * 40: {"state": "ejected", "description": "ci_red"}}
    rep = _run(tmp_path, [_snap()], ej, senders={}, now=T0 + 600)
    assert rep["exit_code"] == 1 and rep["events"]["ejected"]
    ok = {"whatsapp": lambda s, b: (True, "ok")}
    rep = _run(tmp_path, [_snap()], ej, senders=ok, now=T0 + 1200)
    assert rep["exit_code"] == 0 and rep["events"]["ejected"]  # still reported: never lost


def test_corrupt_state_starts_fresh_loudly(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    rep = w.run(p, env={"GITHUB_REPOSITORY": "o/r"}, snapshot_fn=lambda: _snap(A), status_fn=_status({}),
                runs_fn=lambda wf: [], clock=lambda: T0)
    assert rep["baseline_only"] and any("unreadable" in x for x in rep["warnings"])
    assert json.loads(p.read_text())["baseline"] is True


def test_bad_threshold_is_a_config_error():
    try:
        w.thresholds({"MQW_STALL_MIN": "soon"})
    except ValueError as exc:
        assert "MQW_STALL_MIN" in str(exc)
    else:
        raise AssertionError("expected ValueError")


# ── wiring ────────────────────────────────────────────────────────────────────
def test_module_imports_under_bare_stdlib():
    code = ("import sys; sys.path.insert(0, sys.argv[1]);"
            "from tools.noctus.dev import mq_watchdog as w; print(w.STATE_VERSION)")
    out = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(REPO / "mcp" / "noctusai")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "1"


def test_registered_cli_wired_and_workflow_present():
    init = (REPO / "mcp/noctusai/tools/noctus/dev/__init__.py").read_text()
    cli = (REPO / "mcp/noctusai/cli.py").read_text()
    wf = (REPO / ".github/workflows/merge-queue-watchdog.yml").read_text()
    assert "mq_watchdog.register(server)" in init
    assert "--mq-watchdog" in cli
    assert "tools.noctus.dev.mq_watchdog" in wf and "--send" in wf and "cron:" in wf
