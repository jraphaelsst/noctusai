"""steward_feed: the handed-run registry + the watch hooks, with Fakes at the seams (no module function is patched)."""
from __future__ import annotations

from typing import Any

from tools.noctus.dev import merge_queue as mq
from tools.noctus.dev import steward_feed as sf
from tools.noctus.dev.ci_verdict import FakeGithubClient, make_run

SHA = "a" * 40


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def build(tmp_path, *, enqueue=None, landed=None, superseded=None, rate=4000, clock=None):
    gh = FakeGithubClient(rate=rate)
    lines: list[str] = []
    beats: list[int] = []
    enq: list[tuple[str, str]] = []

    def do_enqueue(slug: str, ref: str) -> dict[str, Any]:
        enq.append((slug, ref))
        return (enqueue or (lambda s, r: {"status": "queued", "exit_code": 0, "class": "nested"}))(slug, ref)

    feed = sf.StewardFeed(sf.HandedRuns(tmp_path / "reg.ndjson"), gh, enqueue_fn=do_enqueue,
                          landed_fn=landed or (lambda s: {"status": "landed", "dev_sha": "d" * 40}),
                          heartbeat_fn=lambda: beats.append(1) or {"ok": True},
                          superseded_fn=superseded or (lambda sha: None), emit=lines.append,
                          clock=clock or Clock())
    return feed, gh, lines, beats, enq


def test_green_run_heartbeats_then_enqueues_and_prints_one_line_each(tmp_path):
    feed, gh, lines, beats, enq = build(tmp_path)
    gh.runs["7"] = make_run(7, SHA, conclusion="success")
    feed.reg.register("alpha", "7", SHA)
    feed.tick()
    assert lines == [f"RUN alpha 7 -> success {SHA[:9]} rate_remaining=4000", "ENQ alpha -> queued"]
    assert beats == [1] and enq == [("alpha", "gh-run:7")]
    assert feed.idle()


def test_pending_run_waits_and_is_polled_no_faster_than_120s(tmp_path):
    clock = Clock()
    feed, gh, lines, _b, _e = build(tmp_path, clock=clock)
    gh.runs["7"] = make_run(7, SHA, status="in_progress")
    feed.reg.register("alpha", "7", SHA)
    feed.tick()
    clock.t = 60
    feed.tick()
    assert gh.polls == ["7"] and lines == []
    clock.t = 121
    feed.tick()
    assert gh.polls == ["7", "7"] and not feed.idle()


def test_red_run_carries_failing_jobs_and_first_failed_line_from_one_log_fetch(tmp_path):
    feed, gh, lines, _b, enq = build(tmp_path)
    gh.runs["7"] = make_run(7, SHA, conclusion="failure")
    gh.logs["7"] = ("Product Backend Tests (x)\tRun pytest\t2026-11-16T10:00:00.1Z collecting\n"
                    "Product Backend Tests (x)\tRun pytest\t2026-11-16T10:00:01.2Z FAILED tests/test_a.py::t - boom\n"
                    "Lint\tRuff\t2026-11-16T10:00:02.3Z error: bad\n")
    feed.reg.register("alpha", "7", SHA)
    feed.tick()
    assert enq == []
    assert lines == [f"RUN alpha 7 -> failure {SHA[:9]} rate_remaining=4000 "
                     "jobs=Product Backend Tests (x),Lint first='FAILED tests/test_a.py::t - boom'"]


def test_run_that_tested_another_sha_is_refused_not_enqueued(tmp_path):
    feed, gh, lines, _b, enq = build(tmp_path)
    gh.runs["7"] = make_run(7, "b" * 40, conclusion="success")
    feed.reg.register("alpha", "7", SHA)
    feed.tick()
    assert enq == [] and "refused: tested bbbbbbbbb, registered aaaaaaaaa" in lines[0]


def test_after_orders_enqueues(tmp_path):
    feed, gh, lines, _b, enq = build(tmp_path)
    gh.runs["1"] = make_run(1, SHA, conclusion="success")
    gh.runs["2"] = make_run(2, "c" * 40, conclusion="success")
    feed.reg.register("second", "2", "c" * 40, after="first")
    feed.reg.register("first", "1", SHA)
    feed.tick()
    assert [s for s, _r in enq] == ["first"] and "2" not in gh.polls  # `second` is not polled while `first` is open
    feed.tick()
    assert [s for s, _r in enq] == ["first", "second"]


def test_enqueue_outcomes_are_single_top_level_lines(tmp_path):
    feed, gh, lines, _b, _e = build(tmp_path, enqueue=lambda s, r: {
        "status": "needs_resync", "failing": [{"name": "migration_numbers", "class": "x"}]})
    gh.runs["7"] = make_run(7, SHA, conclusion="success")
    feed.reg.register("alpha", "7", SHA)
    feed.tick()
    assert lines[1] == "ENQ alpha -> needs_resync:migration_numbers"
    feed2, gh2, lines2, _b2, _e2 = build(tmp_path / "x", enqueue=lambda s, r: {"status": "blocked", "refused": "refusal_recurrence"})
    gh2.runs["7"] = make_run(7, SHA, conclusion="success")
    feed2.reg.register("alpha", "7", SHA)
    feed2.tick()
    assert lines2[1] == "ENQ alpha -> refused:refusal_recurrence"


def test_low_quota_backs_off_to_300s(tmp_path):
    clock = Clock()
    feed, gh, lines, _b, _e = build(tmp_path, rate=120, clock=clock)
    gh.runs["7"] = make_run(7, SHA, status="queued")
    feed.reg.register("alpha", "7", SHA)
    feed.tick()
    assert feed.interval() == 300.0
    clock.t = 200
    feed.tick()
    assert gh.polls == ["7"]  # 200s < 300s back-off gap
    gh.runs["7"] = make_run(7, SHA, conclusion="success")
    clock.t = 301
    feed.tick()
    assert "rate_remaining=120" in lines[0]


def test_landed_is_recorded_by_the_feed_and_conflict_ejection_already_on_dev_is_superseded(tmp_path):
    feed, _gh, lines, _b, _e = build(tmp_path, superseded=lambda sha: "patch-equivalent")
    feed.on_left("alpha", SHA, {"state": "landed", "dev_sha": "d" * 40})
    feed.on_left("beta", "c" * 40, {"state": "ejected", "description": "merge conflict in x.py"})
    feed.on_left("gamma", "e" * 40, {"state": "ejected", "description": "Tests & Build red"})
    assert lines == [f"LANDED-RECORDED alpha {'d' * 40}",
                     "MQ-SUPERSEDED beta ccccccccc -> superseded (patch-equivalent): already on dev, nothing to re-enqueue"]


def test_watch_exits_idle_when_queue_empty_and_nothing_pending(tmp_path):
    feed, _gh, _l, _b, _e = build(tmp_path)
    out: list[str] = []
    mq.watch(lambda: {"status": "ok", "entries": []}, lambda s: {}, sleep=lambda s: None, emit=out.append,
             tick_fn=feed.tick, on_left=feed.on_left, idle_fn=feed.idle, interval_fn=feed.interval)
    assert out == ["MQ-IDLE queue empty and no handed run pending"]


def test_watch_keeps_running_while_a_run_is_pending(tmp_path):
    feed, gh, _l, _b, _e = build(tmp_path)
    gh.runs["7"] = make_run(7, SHA, status="in_progress")
    feed.reg.register("alpha", "7", SHA)
    out: list[str] = []
    mq.watch(lambda: {"status": "ok", "entries": []}, lambda s: {}, sleep=lambda s: None, emit=out.append,
             max_polls=3, tick_fn=feed.tick, idle_fn=feed.idle)
    assert "MQ-IDLE queue empty and no handed run pending" not in out


def test_registry_reregister_restarts_and_done_is_folded(tmp_path):
    reg = sf.HandedRuns(tmp_path / "r.ndjson")
    reg.register("a", "1", SHA)
    reg.mark_done("a", "enqueued")
    assert reg.pending() == []
    reg.register("a", "2", SHA)
    assert [p["run"] for p in reg.pending()] == ["2"]


def test_on_left_hook_error_is_reported_not_fatal():
    out: list[str] = []

    def boom(*a):
        raise RuntimeError("x")
    seq = iter([{"status": "ok", "entries": [{"slug": "a", "sha": SHA, "verdict": {"state": "queued"}}]},
                {"status": "ok", "entries": []}])
    mq.watch(lambda: next(seq), lambda s: {"state": "landed", "dev_sha": "d"}, sleep=lambda s: None, emit=out.append,
             max_polls=2, on_left=boom)
    assert any(x.startswith("MQ-WATCH-ERROR on_left") for x in out)
