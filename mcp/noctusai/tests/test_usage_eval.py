"""noctus.dev.usage_eval — transcript dedupe, chars, OS/jobs parsing, windows, compare, sync payloads."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.noctus.dev import usage_eval as ue

T0 = datetime(2026, 11, 4, 3, 45, tzinfo=timezone.utc)
T1 = datetime(2026, 11, 4, 5, 45, tzinfo=timezone.utc)


def _w(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _assistant(ts: str, mid: str, block: dict, usage: dict | None = None, session: str = "s1",
               model: str = "claude-opus-5-5") -> dict:
    return {"type": "assistant", "timestamp": ts, "sessionId": session,
            "message": {"id": mid, "model": model, "content": [block],
                        "usage": usage or {"input_tokens": 10, "output_tokens": 100, "cache_read_input_tokens": 1000,
                                           "cache_creation_input_tokens": 50,
                                           "output_tokens_details": {"thinking_tokens": 40}}}}


@pytest.fixture
def claude_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    proj = root / "-repo"
    _w(proj / "s1.jsonl", [
        {"type": "user", "timestamp": "2026-11-04T03:50:00Z", "sessionId": "s1", "message": {"content": "hello"}},
        # one request = three entries with the SAME message id + usage: usage counts once, chars/tool calls sum
        _assistant("2026-11-04T03:50:05Z", "m1", {"type": "thinking", "thinking": "abcd"}),
        _assistant("2026-11-04T03:50:05Z", "m1", {"type": "text", "text": "hi there"}),
        _assistant("2026-11-04T03:50:05Z", "m1", {"type": "tool_use", "name": "Bash", "input": {"c": "ls"}}),
        {"type": "user", "timestamp": "2026-11-04T03:50:06Z", "sessionId": "s1",
         "message": {"content": [{"type": "tool_result", "content": "file1\nfile2"}]}},
        {"type": "user", "timestamp": "2026-11-04T03:50:07Z", "sessionId": "s1", "isMeta": True,
         "message": {"content": "meta ignored"}},
        # outside the window
        _assistant("2026-11-04T06:00:00Z", "m2", {"type": "text", "text": "later"}),
        # synthetic entries are not API calls
        _assistant("2026-11-04T03:51:00Z", "m3", {"type": "text", "text": "x"}, model="<synthetic>"),
    ])
    _w(proj / "s1" / "subagents" / "agent-abc.jsonl", [
        _assistant("2026-11-04T04:01:00Z", "m9", {"type": "text", "text": "sub"}),
    ])
    return root


@pytest.fixture
def hw_log(tmp_path: Path) -> Path:
    p = tmp_path / "hw.ndjson"
    m = {"cpu_idle_pct": 60.0, "reclaimable_mb": 2000, "swapout_per_s": 0.0, "load_1m": 20.0,
         "cpu_cores": 8, "claude_sessions": 9}
    _w(p, [
        {"ts": "2026-11-04T03:50:00+00:00", "event": "sample", "host": "h", "overloaded": False, "busy_slots": 0, "metrics": m},
        {"ts": "2026-11-04T03:51:00+00:00", "event": "sample", "host": "h", "overloaded": True, "busy_slots": 1,
         "metrics": {**m, "cpu_idle_pct": 10.0, "reclaimable_mb": 900}},
        {"ts": "2026-11-04T03:52:00+00:00", "event": "ran", "host": "h", "job": "pytest:agents", "admitted": True,
         "waited_s": 12.0, "duration_s": 100.0, "children_peak_rss_mb": 800.0, "exit_code": 1, "phase": "build", "metrics": m},
        {"ts": "2026-11-04T03:53:00+00:00", "event": "not_admitted", "host": "h", "job": "vitest:sw", "admitted": False,
         "waited_s": 1800.0, "metrics": m},
        {"ts": "2026-11-04T09:00:00+00:00", "event": "sample", "host": "h", "metrics": m},
    ])
    return p


def test_usage_counted_once_per_message_id_and_chars_summed(claude_root: Path) -> None:
    rows = ue.scan_claude(T0, T1, claude_root)
    main = [r for r in rows if not r.agent_id]
    c = {k: sum(r.counts[k] for r in main) for k in ue._COUNTERS}
    assert c["requests"] == 1
    assert (c["input_tokens"], c["output_tokens"], c["thinking_tokens"]) == (10, 100, 40)
    assert (c["cache_read_tokens"], c["cache_write_tokens"]) == (1000, 50)
    assert c["tool_calls"] == 1
    assert c["output_chars"] == len("abcd") + len("hi there") + len(json.dumps({"c": "ls"}))
    assert c["prompt_chars"] == len("hello")            # isMeta excluded
    assert c["tool_result_chars"] == len("file1\nfile2")
    assert all(r.model == "claude-opus-5-5" for r in main)  # never "<synthetic>"


def test_subagent_rows_carry_agent_id(claude_root: Path) -> None:
    sub = [r for r in ue.scan_claude(T0, T1, claude_root) if r.agent_id]
    assert [(r.agent_id, r.counts["requests"]) for r in sub] == [("abc", 1)]


def test_buckets_are_five_minutes() -> None:
    assert ue.bucket_of(datetime(2026, 11, 4, 3, 54, 59, tzinfo=timezone.utc)) == datetime(2026, 11, 4, 3, 50, tzinfo=timezone.utc)


def test_cost_comes_from_the_seed_rate_card(claude_root: Path) -> None:
    from noctusai_lib.integrations.llm.usage import estimate_cost_usd

    row = next(r for r in ue.scan_claude(T0, T1, claude_root) if not r.agent_id and r.counts["requests"])
    expected = estimate_cost_usd(provider="anthropic", model="claude-opus-5-5", prompt_tokens=10, completion_tokens=100,
                                 cache_read_input_tokens=1000, cache_creation_input_tokens=50)
    assert row.cost_usd == pytest.approx(expected)
    assert row.price_version != "unpriced"


def test_hw_samples_and_jobs_in_window(hw_log: Path) -> None:
    samples, jobs = ue.scan_hw(T0, T1, hw_log)
    assert len(samples) == 2
    assert [(j["kind"], j["target"], j["event"]) for j in jobs] == [("pytest", "agents", "ran"), ("vitest", "sw", "not_admitted")]


def test_window_report_and_compare(claude_root: Path, hw_log: Path) -> None:
    a = ue.window_report(T0, T1, claude_root=claude_root, hw_log=hw_log)
    assert a["jobs"]["ran"] == 1 and a["jobs"]["failed"] == 1 and a["jobs"]["not_admitted"] == 1
    assert a["os"]["overloaded_pct"] == 50.0 and a["os"]["reclaimable_mb_min"] == 900
    assert a["claude"]["sessions_active"] == 1 and a["claude"]["agents_active"] == 1
    b = ue.window_report(T1, datetime(2026, 11, 4, 7, 45, tzinfo=timezone.utc), claude_root=claude_root, hw_log=hw_log)
    cmp = ue.compare(a, b)
    row = next(m for m in cmp["metrics"] if m["metric"] == "jobs.ran_per_h")
    assert row["a"] == 0.5 and row["b"] == 0.0 and row["delta"] == -0.5
    assert next(m for m in cmp["metrics"] if m["metric"] == "os.overloaded_pct")["b"] is None  # unmeasured ≠ 0


def test_missing_hw_log_is_reported_not_silent(claude_root: Path, tmp_path: Path) -> None:
    r = ue.window_report(T0, T1, claude_root=claude_root, hw_log=tmp_path / "nope.ndjson")
    assert r["os"]["samples"] == 0 and r["os"]["source"].startswith("missing:")


class _FakeTable:
    def __init__(self, sink: dict, name: str) -> None:
        self.sink, self.name = sink, name

    def upsert(self, rows, on_conflict: str):
        self.sink.setdefault(self.name, []).append((on_conflict, rows if isinstance(rows, list) else [rows]))
        return self

    def execute(self):
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.sink: dict = {}

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self.sink, name)


def test_sync_upserts_on_the_natural_keys(claude_root: Path, hw_log: Path) -> None:
    fake = _FakeClient()
    out = ue.sync(T0, T1, client=fake, claude_root=claude_root, hw_log=hw_log)
    assert out["written"] == {"dev_telemetry_claude": 2, "dev_telemetry_os": 2, "dev_telemetry_jobs": 2}
    conflict, rows = fake.sink["dev_telemetry_claude"][0]
    assert conflict == "host,bucket,session_id,agent_id,model"
    assert all("text" not in k for r in rows for k in r)  # counts only, never text
    assert fake.sink["dev_telemetry_jobs"][0][0] == "host,ts,job,event"


def test_window_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        ue.usage_eval("report", since="2026-11-04T06:00:00Z", until="2026-11-04T05:00:00Z")
