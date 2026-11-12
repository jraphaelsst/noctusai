"""Supabase request breaker — count per source, trip a runaway BACKGROUND source, alert once, persist, re-arm by a human.

KB § PATTERNS/backend/supabase-request-breaker.md · incident KB § PATTERNS/backend/polling-request-budget.md
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from noctusai_lib.domain.jobs import FakeJobRepository, Worker
from noctusai_lib.integrations.http_pool import TimingTransport
from noctusai_lib.primitives.supabase_breaker import (
    BREAKER_AUDIT_KEY,
    BREAKER_FLEET_KEY,
    BREAKER_SOURCE_RE,
    Breaker,
    BreakerOpen,
    JobBudgetExceeded,
    job_scope,
    BreakerConfig,
    InMemoryBreakerStore,
    RecordingAlerter,
    get_breaker,
    reset_breaker_for_tests,
    source_scope,
)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def make_breaker(**kw) -> tuple[Breaker, InMemoryBreakerStore, RecordingAlerter, Clock]:
    store, alerter, clock = InMemoryBreakerStore(), RecordingAlerter(), Clock()
    b = Breaker(slug="prod-x", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, **kw)
    return b, store, alerter, clock


class RunawayRepo(FakeJobRepository):
    """Every claim is one Supabase REST call (what the real repo's `rpc/claim_next_job` is), on an EMPTY queue."""

    def __init__(self, breaker: Breaker, clock: Clock) -> None:
        super().__init__()
        self.breaker, self.clock, self.claims = breaker, clock, 0

    async def claim_next(self, *a, **kw):
        self.claims += 1
        self.breaker.record_call()  # under the Worker's alert-only claim scope; the Worker bills EMPTY polls to the loop  # the transport hook, against THIS breaker
        self.clock.advance(0.1)  # 10 calls / s: a 1 s idle poll x10 workers
        return None


async def _no_sleep(delay, stop_event):  # a runaway: the idle sleep returns at once
    await asyncio.sleep(0)


async def _noop(job):
    return None


@pytest.fixture(autouse=True)
def _fresh_singleton():
    reset_breaker_for_tests()
    yield
    reset_breaker_for_tests()


def test_runaway_worker_trips_within_window_loop_stops_key_written_one_alert():
    b, store, alerter, clock = make_breaker()
    repo = RunawayRepo(b, clock)
    worker = Worker(repo, worker_id="w", handlers={"transcricao": _noop}, poll_interval_seconds=1.0,
                    idle_sleep=_no_sleep, breaker=b, held_poll_seconds=0.01, clock=clock)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        await asyncio.sleep(0.3)
        claims_when_stopped = repo.claims
        await asyncio.sleep(0.2)
        assert repo.claims == claims_when_stopped, "a tripped worker must make NO further Supabase calls"
        stop.set()
        await asyncio.wait_for(task, 2)
        return claims_when_stopped

    claims = asyncio.run(drive())
    assert claims <= 330, f"tripped late: {claims} calls (budget 300 / 5 min)"
    key = "noctus:breaker:prod-x:worker:transcricao"
    assert key in store.data, "trip must be persisted (no TTL) in Redis"
    state = json.loads(store.data[key])
    assert state["by"] == "auto" and state["window"] == 300 and state["rate"] > 1
    assert len(alerter.sent) == 1, "exactly ONE alert per trip, not one per call"
    assert "TRIPPED" in alerter.sent[0][0]


def test_http_over_threshold_alerts_never_stops():
    b, store, alerter, clock = make_breaker(config=BreakerConfig(daily_quota=10**9))  # isolate from the aggregate
    for _ in range(7000):
        b.record_call("http")
        clock.advance(0.01)
    assert b.hold_reason("http") is None
    assert not b.status()["held"]
    assert len(alerter.sent) == 1 and "traffic high" in alerter.sent[0][0] and "http" in alerter.sent[0][0]
    assert store.data == {}
    with pytest.raises(ValueError):
        b.trip("http", reason="x")


def test_held_source_does_not_start_on_boot():
    b, store, alerter, clock = make_breaker()
    store.data["noctus:breaker:prod-x:worker:transcricao"] = json.dumps({"reason": "runaway", "by": "auto"})
    repo = RunawayRepo(b, clock)
    worker = Worker(repo, worker_id="w", handlers={"transcricao": _noop}, idle_sleep=_no_sleep, breaker=b,
                    held_poll_seconds=0.01)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        await asyncio.sleep(0.15)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(drive())
    assert repo.claims == 0, "a held source must not claim a single job on boot"


def test_fleet_key_stops_every_background_source_but_not_http():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=0.0)
    store.data[BREAKER_FLEET_KEY] = json.dumps({"reason": "402 storm", "by": "watcher"})
    for src in ("worker:a", "scheduler:nightly", "worker:b,c"):
        assert b.check_sync(src, force=True)["scope"] == "fleet"
    assert b.check_sync("http", force=True) is None  # the APIs keep serving


def test_rearm_restarts_source_and_requires_a_reason():
    b, store, alerter, clock = make_breaker()
    b.trip("worker:a", reason="runaway", rate=5, window=300)
    assert b.hold_reason("worker:a") and "noctus:breaker:prod-x:worker:a" in store.data
    for bad in ({"by": "ana", "reason": ""}, {"by": "", "reason": "fixed"}):
        with pytest.raises(ValueError):
            b.rearm("worker:a", **bad)
    assert b.hold_reason("worker:a"), "a refused re-arm changes nothing"
    out = b.rearm("worker:a", by="ana", reason="idle backoff deployed, verified")
    assert out["ok"] and b.hold_reason("worker:a") is None
    assert "noctus:breaker:prod-x:worker:a" not in store.data
    assert "noctus:breaker:prod-x:rearm:worker:a" not in store.data, "rearm:* is READ-ONLY for a product identity"
    row = json.loads(store.audits["noctus:breaker:prod-x:audit"][-1])
    assert row["op"] == "rearm" and row["tripped_at"] and row["key"] == "noctus:breaker:prod-x:worker:a"


def test_parked_worker_resumes_after_rearm():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=0.0)
    b.trip("worker:transcricao", reason="runaway")
    repo = RunawayRepo(b, clock)
    worker = Worker(repo, worker_id="w", handlers={"transcricao": _noop}, poll_interval_seconds=1.0,
                    idle_sleep=_no_sleep, breaker=b, held_poll_seconds=0.01, clock=clock)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        await asyncio.sleep(0.1)
        assert repo.claims == 0
        await asyncio.to_thread(b.rearm, "worker:transcricao", by="ana", reason="fixed and verified")
        await asyncio.sleep(0.1)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(drive())
    assert repo.claims > 0, "after a human re-arm the source restarts"


def test_rearm_from_another_process_releases_only_with_the_matching_marker():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=1.0)
    b.trip("worker:a", reason="runaway")
    trip_ts = b._trips["worker:a"].tripped_at
    clock.advance(10)
    key = "noctus:breaker:prod-x:worker:a"
    del store.data[key]  # the MCP tool: SET marker (with the trip's tripped_at) then DEL the key
    store.data["noctus:breaker:prod-x:rearm:worker:a"] = json.dumps({"tripped_at": trip_ts, "by": "ops:ana"})
    b.check_sync("worker:a", force=True)
    assert b.hold_reason("worker:a") is None
    assert "noctus:breaker:prod-x:rearm:worker:a" in store.data, "markers expire by TTL; products never delete them"


def test_P2_4_a_vanished_key_without_a_marker_never_releases_the_hold_it_is_rewritten_and_alerted():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=1.0)
    b.trip("worker:a", reason="runaway")
    clock.advance(10)
    store.data.clear()  # a Redis flush / eviction / tampering: NO re-arm marker
    b.check_sync("worker:a", force=True)
    assert b.hold_reason("worker:a") is not None, "a persisted hold is never silently released"
    assert "noctus:breaker:prod-x:worker:a" in store.data, "the key is rewritten"
    assert any("VANISHED" in s for s, _ in alerter.sent)
    # a marker for a DIFFERENT trip does not release it either
    clock.advance(10)
    del store.data["noctus:breaker:prod-x:worker:a"]
    store.data["noctus:breaker:prod-x:rearm:worker:a"] = json.dumps({"tripped_at": "1999-01-01T00:00:00+00:00"})
    b.check_sync("worker:a", force=True)
    assert b.hold_reason("worker:a") is not None


def test_redis_down_trips_in_process_and_alerts_and_fleet_read_fails_open():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=0.0)
    store.down = True
    b.trip("worker:a", reason="runaway", rate=3, window=300)
    assert b.hold_reason("worker:a") is not None and b.hold_reason("worker:a")["persisted"] is False
    assert len(alerter.sent) == 1 and "NOT persisted" in alerter.sent[0][1]
    assert b.check_sync("worker:other", force=True) is None  # fail OPEN
    assert any("BLIND" in s for s, _ in alerter.sent), "an unreadable fleet key must alert loudly"
    assert b.status()["store_down"] is True


def test_failed_alert_is_kept_and_retried_not_swallowed():
    b, store, alerter, clock = make_breaker()
    alerter.fail = True
    b.trip("worker:a", reason="runaway")
    assert alerter.sent == [] and len(b.pending_alerts) == 1
    alerter.fail = False
    assert b.flush_pending_alerts() == 0 and len(alerter.sent) == 1
    b.flush_pending_alerts()
    assert len(alerter.sent) == 1, "no duplicate after the retry succeeded"


def test_source_attribution_follows_threads_and_the_transport_counts_rest_only():
    b = get_breaker()
    b.configure(slug="t", config=BreakerConfig())
    inner = httpx.MockTransport(lambda req: httpx.Response(200, json=[]))
    client = httpx.Client(transport=TimingTransport(inner), base_url="https://x.supabase.co")

    async def drive():
        with source_scope("worker:z"):
            await asyncio.to_thread(client.get, "/rest/v1/jobs")
            await asyncio.to_thread(client.get, "/auth/v1/user")  # not REST: not counted
        await asyncio.to_thread(client.get, "/rest/v1/jobs")

    asyncio.run(drive())
    assert b.count("worker:z", 60) == 1
    assert b.count("unattributed", 60) == 1, "outside any scope a call is UNATTRIBUTED, never silently user traffic"


def test_count_overhead_is_negligible_and_never_touches_the_network():
    b, store, alerter, clock = make_breaker()
    n, best = 40_000, None
    for _ in range(5):  # best of 5: a loaded CI machine must not turn a scheduler hiccup into a failure
        t0 = time.perf_counter()
        for _ in range(n):
            b.record_call("http")
        per_call_us = (time.perf_counter() - t0) / n * 1e6
        best = per_call_us if best is None else min(best, per_call_us)
    assert store.calls == 0, "counting must be in-memory: no Redis, no network per call"
    assert best < 20, f"{best:.2f} us per counted call"
    print(f"\nper-call overhead: {best:.2f} us")


def test_scheduler_job_held_does_not_run_and_writes_no_ledger():
    from noctusai_lib.api import scheduler as sch

    sch.reset_for_testing()
    ledger: list = []

    class Obs:
        def record(self, run):
            ledger.append(run)

        def register_jobs(self, specs):
            pass

    sch.set_run_observer(Obs())
    ran: list[int] = []

    async def job():
        ran.append(1)

    wrapped = sch._instrument("nightly", job)
    b = get_breaker()
    b.configure(slug="t", store=InMemoryBreakerStore(), alerter=RecordingAlerter())
    asyncio.run(wrapped())
    assert ran == [1] and len(ledger) == 1
    b.trip("scheduler:nightly", reason="runaway")
    asyncio.run(wrapped())
    assert ran == [1] and len(ledger) == 1, "a held scheduler job neither runs nor writes a ledger row"
    b.rearm("scheduler:nightly", by="ana", reason="fixed")
    asyncio.run(wrapped())
    assert ran == [1, 1]
    sch.reset_for_testing()


# --- security review 2026-11-10 (F4 / F5 / design risk / F10) ------------------------------------------------------


def _transport_client():
    inner = httpx.MockTransport(lambda req: httpx.Response(200, json=[]))
    return httpx.Client(transport=TimingTransport(inner), base_url="https://x.supabase.co"), inner


def test_F4_a_handler_looping_1000_calls_is_stopped_at_the_per_job_cap_not_the_type():
    b = get_breaker()
    b.configure(slug="t", store=InMemoryBreakerStore(), alerter=RecordingAlerter(),
                config=BreakerConfig(job_cap_enforce=True))
    b._sync_io = True
    reached = []
    inner = httpx.MockTransport(lambda req: (reached.append(1), httpx.Response(200, json=[]))[1])
    client = httpx.Client(transport=TimingTransport(inner), base_url="https://x.supabase.co")
    refused = 0
    with source_scope("job:transcricao"), job_scope(300):
        for _ in range(1000):
            try:
                client.get("/rest/v1/jobs")
            except JobBudgetExceeded:
                refused += 1
    assert len(reached) == 300, f"{len(reached)} calls left the process (per-job cap 300)"
    assert refused == 700
    assert b.hold_reason("worker:transcricao") is None, "a runaway JOB never holds the type or other tenants"
    with source_scope("http"):
        client.get("/rest/v1/jobs")  # user traffic is never refused


def test_worker_dead_letters_a_job_over_its_call_cap_with_a_reason_and_keeps_serving():
    b, store, alerter, clock = make_breaker(config=BreakerConfig(job_cap_enforce=True))
    repo = FakeJobRepository()

    async def hog(job):
        for _ in range(50):
            b.record_call()
            b.guard()

    worker = Worker(repo, worker_id="w", handlers={"t": hog}, breaker=b, idle_sleep=_no_sleep, job_call_cap=10)

    async def drive():
        await repo.enqueue(type="t", payload={})
        await worker.run_once()

    asyncio.run(drive())
    (job,) = repo._jobs.values()
    assert job.status.value == "dead_letter" and "call cap" in (job.last_error or "")
    assert b.hold_reason("worker:t") is None


def test_F5_unscoped_calls_alert_but_are_never_held():
    b, store, alerter, clock = make_breaker()
    for _ in range(301):
        b.record_call()  # no scope: a lifespan create_task loop / bare Thread
    assert b.hold_reason("unattributed") is None, "request-path / unnamed work can never be refused"
    assert len(alerter.sent) == 1 and "unattributed" in alerter.sent[0][0]
    b.guard("unattributed")  # does not raise


def test_F5_request_middleware_sets_http_explicitly():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from noctusai_lib.api.supabase_source import SupabaseSourceMiddleware
    from noctusai_lib.primitives.supabase_breaker import current_source

    app = FastAPI()
    app.add_middleware(SupabaseSourceMiddleware)

    @app.get("/x")
    def _x():  # a threadpool handler: the context is copied into the worker thread
        return {"source": current_source()}

    assert TestClient(app).get("/x").json() == {"source": "http"}
    assert current_source() == "unattributed"


def test_job_of_a_held_type_is_released_not_failed_or_dead_lettered():
    b, store, alerter, clock = make_breaker()
    repo = FakeJobRepository()

    async def handler(job):
        b.guard("worker:t")  # what the transport does on the job's first Supabase call

    worker = Worker(repo, worker_id="w", handlers={"t": handler}, breaker=b, held_poll_seconds=0.01,
                    idle_sleep=_no_sleep)

    async def drive():
        await repo.enqueue(type="t", payload={})
        b.trip("worker:t", reason="burning")
        await worker.run_once()

    asyncio.run(drive())
    states = {j.status.value for j in repo._jobs.values()}
    assert states == {"pending"}, f"a breaker release must go back to PENDING (never failed/dead-letter), got {states}"


def test_F10_rearm_and_manual_trip_write_a_capped_audit_row():
    b, store, alerter, clock = make_breaker()
    b.trip("worker:a", reason="manual stop", by="ana")
    b.rearm("worker:a", by="ana", reason="fixed")
    rows = [json.loads(r) for r in store.audits["noctus:breaker:prod-x:audit"]]
    assert [r["op"] for r in rows] == ["trip", "rearm"] and rows[1]["claimed_by"] == "ana" and rows[1]["reason"] == "fixed"
    assert BREAKER_AUDIT_KEY == "noctus:breaker:audit"
    for i in range(1200):
        store.append_audit(BREAKER_AUDIT_KEY, str(i), 1000)
    assert len(store.audits[BREAKER_AUDIT_KEY]) == 1000 and len(store.audits["noctus:breaker:prod-x:audit"]) == 2, \
        "audit lists are keyed, like Redis"


# --- startup is its own source; unattributed still catches stray loops (coordinator review 2026-11-10) -------------


def test_startup_and_unattributed_are_alert_only_never_held():
    b, store, alerter, clock = make_breaker(config=BreakerConfig(daily_quota=10**9))
    for _ in range(1400):  # a heavy boot: recovery sweeps (the seed's own boot is ~2 calls)
        b.record_call("startup")
    assert not alerter.sent
    for _ in range(200):
        b.record_call("startup")  # 1,600 in 60 s: past the startup alert threshold
    assert b.hold_reason("startup") is None and len(alerter.sent) == 1
    clock.advance(5)
    for _ in range(301):
        b.record_call()
    assert b.hold_reason("unattributed") is None and b.hold_reason("startup") is None
    assert any("unattributed" in s for s, _ in alerter.sent)
    for src in ("startup", "unattributed", "http", "bg:conversation-worker", "job:t", "egress:storage"):
        with pytest.raises(ValueError):
            b.trip(src, reason="x")
        b.guard(src)


def test_scheduler_registry_thread_is_attributed_not_unattributed():
    from noctusai_lib.api import scheduler as sch
    from noctusai_lib.primitives.supabase_breaker import current_source

    sch.reset_for_testing()
    seen: list[str] = []

    class Obs:
        def record(self, run):
            pass

        def register_jobs(self, specs):
            seen.append(current_source())

    async def job():
        return None

    sch.set_run_observer(Obs())
    sch.register("j", job, hours=1)
    sch._publish_job_registry()
    import time as _t

    for _ in range(50):
        if seen:
            break
        _t.sleep(0.05)
    assert seen == ["bg:scheduler-registry"]
    sch.reset_for_testing()


# --- round 4: alert-only catch-alls, spawn_background, config clamp, reason regex, degraded, egress ------------------


def test_only_named_owned_loops_are_holdable():
    from noctusai_lib.primitives.supabase_breaker import is_holdable

    assert is_holdable("worker:t") and is_holdable("scheduler:nightly")
    for src in ("http", "startup", "unattributed", "bg:x", "job:t", "claim:t", "egress:auth", "gate:x"):
        assert not is_holdable(src)
    assert BREAKER_SOURCE_RE.match("worker:a,b") and BREAKER_SOURCE_RE.match("scheduler:nightly")
    for bad in ("fleet", "http", "startup", "unattributed", "worker:", "worker:a b", "worker:" + "x" * 101):
        assert not BREAKER_SOURCE_RE.match(bad)


def test_fleet_key_holds_worker_loops_and_scheduler_ticks_only():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=0.0)
    store.data[BREAKER_FLEET_KEY] = json.dumps({"reason": "402 storm", "by": "offhost-watchdog"})
    b.refresh()
    assert b.hold_reason("worker:a") and b.hold_reason("scheduler:x")
    for src in ("http", "startup", "unattributed", "bg:conversation-worker", "job:t"):
        assert b.hold_reason(src) is None
        b.guard(src)


def test_spawn_background_sets_an_explicit_alert_only_source_for_tasks_and_threads():
    from noctusai_lib.primitives.background import run_in_thread, spawn_background
    from noctusai_lib.primitives.supabase_breaker import current_source

    seen: list[str] = []

    async def coro():
        seen.append(current_source())
        await asyncio.to_thread(lambda: seen.append(current_source()))  # to_thread copies the scoped context

    async def drive():
        task = spawn_background("conversation-worker", coro())
        await task
        t = run_in_thread("pos-aceite", lambda: seen.append(current_source()))
        t.join(2)
        t2 = spawn_background("sync-fn", lambda: seen.append(current_source()))
        t2.join(2)

    asyncio.run(drive())
    assert seen == ["bg:conversation-worker", "bg:conversation-worker", "bg:pos-aceite", "bg:sync-fn"]


def test_P3_7_per_source_ceiling_is_derived_from_the_quota_as_a_rate_per_hour():
    ceiling = BreakerConfig().source_hour_ceiling()
    assert ceiling == int(500_000 * 0.5 / 24)

    def cfg(rules, **env):
        return BreakerConfig.from_env({"NOCTUS_BREAKER_BUDGETS": json.dumps({"worker:a": rules}), **env})

    assert cfg([[3600, ceiling + 1]]).overrides == {}
    assert cfg([[300, ceiling // 12 + 1]]).overrides == {}
    assert cfg([[60, ceiling // 60 + 1]]).overrides == {}
    assert cfg([[3600, ceiling]]).overrides["worker:a"][0].max_calls == ceiling
    assert cfg([[300, ceiling // 12]]).overrides["worker:a"][0].window_s == 300


def test_P2_3_env_cannot_loosen_the_safety_nets():
    from noctusai_lib.primitives.supabase_breaker import DEFAULT_DAILY_QUOTA

    huge = BreakerConfig.from_env({"NOCTUS_SUPABASE_DAILY_QUOTA": str(10**9)})
    assert huge.daily_quota == 2 * DEFAULT_DAILY_QUOTA and any("clamped" in w for w in huge.warnings)
    above = BreakerConfig.from_env({"NOCTUS_SUPABASE_DAILY_QUOTA": str(DEFAULT_DAILY_QUOTA + 1)})
    assert above.daily_quota == DEFAULT_DAILY_QUOTA + 1 and any("above the default" in w for w in above.warnings)
    assert BreakerConfig().warnings == []
    nets = BreakerConfig.from_env({"NOCTUS_BREAKER_BUDGETS": json.dumps(
        {"*": [[3600, 10**6]], "http": [[300, 10**6]], "startup": [[60, 10**6]], "unattributed": [[300, 10**6]],
         "worker:ok": [[3600, 100]]})})
    assert set(nets.overrides) == {"worker:ok"} and sum("safety net" in w for w in nets.warnings) == 4
    assert BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": "0.01"}).min_idle_poll_s == 1.0


def test_P2_3_config_warnings_are_alerted_once_when_the_breaker_is_configured():
    b, store, alerter, clock = make_breaker(config=BreakerConfig.from_env({"NOCTUS_SUPABASE_DAILY_QUOTA": "900000"}))
    b.announce_config_warnings()
    b.announce_config_warnings()
    assert len(alerter.sent) == 1 and "CONFIG" in alerter.sent[0][0]


def test_P3_5_reason_must_be_printable_text():
    b, store, alerter, clock = make_breaker()
    for bad in ("line\nbreak", "esc\x1b[31m", "nul\x00", "tab\t", "x" * 301):
        with pytest.raises(ValueError):
            b.trip("worker:a", reason=bad, by="ana")
        with pytest.raises(ValueError):
            b.rearm("worker:a", by="ana", reason=bad)


def test_P3_1_degraded_breaker_alerts_once_and_is_reported():
    b, store, alerter, clock = make_breaker()
    b.set_degraded("no REDIS_URL")
    b.set_degraded("no REDIS_URL")
    assert b.degraded == "no REDIS_URL" and b.status()["degraded"] == "no REDIS_URL"
    assert len(alerter.sent) == 1 and "DEGRADED" in alerter.sent[0][0]


def test_P3_6_non_rest_egress_is_counted_alert_only():
    b = get_breaker()
    b.configure(slug="t", config=BreakerConfig())
    inner = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    client = httpx.Client(transport=TimingTransport(inner), base_url="https://x.supabase.co")
    client.get("/storage/v1/object/x")
    client.get("/auth/v1/user")
    client.get("/functions/v1/f")
    assert b.count("egress:storage", 60) == b.count("egress:auth", 60) == b.count("egress:functions", 60) == 1
    assert b.count("unattributed", 60) == 0


def test_refresh_loop_ticks_once_per_interval_and_stops():
    from noctusai_lib.primitives.supabase_breaker import refresh_loop

    b = get_breaker()
    store = InMemoryBreakerStore()
    b.configure(slug="t", store=store, alerter=RecordingAlerter())

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(refresh_loop(stop, interval_s=0.02))
        for _ in range(250):  # wait for 3 ticks (up to 5 s): independent of machine load
            if store.calls >= 3:
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(drive())
    assert store.calls >= 3


def test_P1_2_the_source_middleware_is_outermost_and_the_audit_flush_has_its_own_source():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.middleware.base import BaseHTTPMiddleware

    from noctusai_lib.api.audit.sink import FakeAuditSink
    from noctusai_lib.api.supabase_source import SupabaseSourceMiddleware
    from noctusai_lib.primitives.supabase_breaker import current_source

    seen: dict[str, str] = {}

    class Inner(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            seen["inner"] = current_source()
            return await call_next(request)

    app = FastAPI()
    app.add_middleware(Inner)
    app.add_middleware(SupabaseSourceMiddleware)  # added LAST => outermost

    @app.post("/x")
    def _x():
        return {}

    c = TestClient(app)
    for _ in range(400):  # 400 anonymous POSTs
        c.post("/x")
    assert seen["inner"] == "http"
    b = get_breaker()
    assert b.status()["held"] == {} and b.hold_reason("http") is None
    assert FakeAuditSink is not None  # the real flush loop's explicit source is asserted below


def test_P1_2_audit_flush_task_runs_under_its_own_explicit_source():
    import inspect

    from noctusai_lib.api.audit import sink

    assert 'source_scope("bg:audit-flush")' in inspect.getsource(sink.RealAuditSink._flush_loop)


def test_configure_app_adds_the_source_middleware_last_so_it_is_outermost():
    import inspect

    from noctusai_lib.api import app_factory

    src = inspect.getsource(app_factory)
    adds = [i for i in range(len(src)) if src.startswith("app.add_middleware(", i)]
    last = src.rfind("app.add_middleware(")
    assert src[last:last + 60].startswith("app.add_middleware(SupabaseSourceMiddleware"), "must be the LAST add_middleware"
    assert adds


# --- round 5: cadence billing (P1-A), aggregate (P1-B), observe-mode job cap (P2-A), swallow-proof cap (P2-B) --------


def _cadence_worker(b, clock, repo, handler=_noop, **kw):
    return Worker(repo, worker_id="w", handlers={"t": handler}, breaker=b, poll_interval_seconds=1.0,
                  held_poll_seconds=0.01, clock=clock, **kw)


@pytest.mark.parametrize("step,jobs", [(1.0, 400), (0.5, 600)])  # 1 job/s for 400 s; 2 jobs/s for 300 s
def test_P1_A_steady_job_arrivals_never_hold_the_worker(step, jobs):
    b, store, alerter, clock = make_breaker()
    repo = FakeJobRepository()
    n = {"jobs": 0}

    async def idle_sleep(delay, stop):  # a producer in the same process enqueues jobs: each enqueue WAKES the worker
        clock.advance(step)
        await repo.enqueue(type="t", payload={})
        n["jobs"] += 1
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        if n["jobs"] >= jobs:
            stop.set()

    worker = _cadence_worker(b, clock, repo, idle_sleep=idle_sleep)

    async def drive():
        stop = asyncio.Event()
        await repo.enqueue(type="t", payload={})
        await asyncio.wait_for(worker.run_forever(stop_event=stop), 20)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is None, "job arrival volume must never park a Worker"
    assert b.count("worker:t", 3600) == 0, "every empty poll followed work or a wake: all free"
    assert not store.data


def test_P1_A_a_claim_loop_with_no_sleep_still_trips():
    b, store, alerter, clock = make_breaker()
    repo = RunawayRepo(b, clock)
    worker = _cadence_worker(b, clock, repo, idle_sleep=_no_sleep)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        for _ in range(250):  # wait for the trip (up to 5 s) instead of a fixed sleep: machine-load independent
            if b.hold_reason("worker:t") is not None:
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is not None and repo.claims <= 310


def test_P1_A_claim_errors_with_the_error_backoff_for_10_minutes_never_hold():
    b, store, alerter, clock = make_breaker()

    class DownRepo(FakeJobRepository):
        calls = 0

        async def claim_next(self, *a, **kw):
            DownRepo.calls += 1
            b.record_call()  # each failed claim still makes a Supabase call
            raise ConnectionError("supabase outage")

    async def idle_sleep(delay, stop):
        clock.advance(delay)  # the loop's own backoff is what advances time
        if clock() - 1000.0 >= 600:
            stop.set()

    worker = _cadence_worker(b, clock, DownRepo(), idle_sleep=idle_sleep)

    async def drive():
        stop = asyncio.Event()
        await asyncio.wait_for(worker.run_forever(stop_event=stop), 20)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is None, "an outage must never trip every Worker fleet-wide"
    assert DownRepo.calls < 60, f"error backoff must bound the retries ({DownRepo.calls} claims in 10 min)"


def test_P1_1_billing_rules_free_after_work_ramp_allowance_floor_reset_and_wake_cap():
    b, store, alerter, clock = make_breaker()
    worker = _cadence_worker(b, clock, FakeJobRepository())
    worker._last_poll_calls = 1  # the poll made one Supabase call (a claim)
    worker._bill_empty_poll(b)  # boot: free
    for _ in range(Worker.RAMP_FREE):  # the backoff ramp's allowance: sub-floor gaps, free
        clock.advance(1.0)
        worker._bill_empty_poll(b)
    assert b.count("worker:t", 3600) == 0
    clock.advance(1.0)
    worker._bill_empty_poll(b)  # past the allowance, still polling every 1 s (< 10 s floor): billed
    assert b.count("worker:t", 3600) == 1
    worker._poll_free = True  # a job was processed
    clock.advance(1.0)
    worker._bill_empty_poll(b)
    assert b.count("worker:t", 3600) == 1
    clock.advance(10.0)  # honouring the platform floor: free, and the ramp starts over
    worker._bill_empty_poll(b)
    clock.advance(1.0)
    worker._bill_empty_poll(b)
    assert b.count("worker:t", 3600) == 1
    # wake-followed empty polls: free up to the cap per 5 minutes, then billed
    for _ in range(b._config.max_free_wake_polls + 3):
        worker._woke_before_poll = True
        clock.advance(0.5)
        worker._bill_empty_poll(b)
    assert b.count("worker:t", 3600) == 1 + 3, "30 free wake-followed polls, then billed"


def test_P1_A_a_future_dated_enqueue_does_not_wake_the_worker():
    from datetime import datetime, timedelta, timezone

    from noctusai_lib.domain.jobs import wake

    async def drive():
        w = wake.register(asyncio.get_running_loop(), ["t"])
        repo = FakeJobRepository()
        await repo.enqueue(type="t", payload={}, scheduled_for=datetime.now(timezone.utc) + timedelta(hours=1))
        await asyncio.sleep(0.01)
        future_woke = w.event.is_set()
        await repo.enqueue(type="t", payload={})
        await asyncio.sleep(0.01)
        now_woke = w.event.is_set()
        wake.unregister(w)
        return future_woke, now_woke

    assert asyncio.run(drive()) == (False, True)


def test_P1_B_the_incident_shape_spread_over_several_loops_raises_the_aggregate_alert():
    b, store, alerter, clock = make_breaker()
    sources = ["bg:a", "job:b", "worker-x", "bg:c", "job:d", "bg:e"]  # each ~1,900/h: UNDER every per-source threshold
    total = 11_400
    for i in range(total):
        b.record_call(sources[i % 6])
        clock.advance(3600 / total)
    subjects = [s for s, _ in alerter.sent]
    assert any("*" in s for s in subjects), subjects
    assert not any(src in s for s in subjects for src in sources if src != "*"), "no per-source alert: only the aggregate"
    body = next(body for s, body in alerter.sent if "*" in s)
    assert "quota" in body and "projected daily" in body


def test_P1_B_alert_only_defaults_are_2000_per_hour_and_the_daily_quota_is_configurable():
    from noctusai_lib.primitives.supabase_breaker import DEFAULT_ALERT_RULES, DEFAULT_DAILY_QUOTA

    assert DEFAULT_ALERT_RULES[-1].max_calls == 2000 and DEFAULT_ALERT_RULES[-1].window_s == 3600
    cfg = BreakerConfig.from_env({"NOCTUS_SUPABASE_DAILY_QUOTA": "100000", "NOCTUS_BREAKER_AGGREGATE_SHARE": "0.25"})
    assert cfg.daily_quota == 100000 and cfg.aggregate_share == 0.25 and DEFAULT_DAILY_QUOTA == 500_000
    assert BreakerConfig.from_env({"NOCTUS_BREAKER_AGGREGATE_SHARE": "7"}).aggregate_share == 0.5


def test_P1_B_the_fleet_key_refuses_bg_only_on_explicit_opt_in():
    for opt_in, held in ((False, False), (True, True)):
        b, store, alerter, clock = make_breaker(config=BreakerConfig(fleet_holds_bg=opt_in), fleet_ttl_s=0.0)
        store.data[BREAKER_FLEET_KEY] = json.dumps({"reason": "402", "by": "offhost-watchdog"})
        b.refresh()
        assert b.is_open("bg:x") is held
        assert b.is_open("http") is False and b.is_open("startup") is False


def test_P2_A_the_per_job_cap_is_observe_mode_by_default_alert_at_cap_dead_letter_at_the_ceiling():
    b, store, alerter, clock = make_breaker()
    with job_scope(100) as budget:
        for _ in range(150):
            b.record_call("job:t")
            b.guard("job:t")  # past the cap, below the hard ceiling: NOT refused
    assert budget.hard == 20_000 and not budget.over
    assert sum("job-cap" in s for s, _ in alerter.sent) == 1, "one alert, at the cap"
    b2, *_ = make_breaker(config=BreakerConfig(job_cap_enforce=True))
    assert b2.job_hard_limit(100) == 100 and b.job_hard_limit(100) == 20_000


def test_P2_A_per_type_caps_map():
    b, store, alerter, clock = make_breaker(config=BreakerConfig(job_cap_enforce=True))
    repo = FakeJobRepository()
    seen = {}

    async def h(job):
        seen[job.type] = True
        for _ in range(30):
            b.record_call()
            b.guard()

    w = Worker(repo, worker_id="w", handlers={"small": h, "big": h}, breaker=b, idle_sleep=_no_sleep,
               job_call_cap=1000, job_call_caps={"small": 10})

    async def drive():
        await repo.enqueue(type="small", payload={})
        await repo.enqueue(type="big", payload={})
        await w.run_once()
        await w.run_once()

    asyncio.run(drive())
    states = {j.type: j.status.value for j in repo._jobs.values()}
    assert states == {"small": "dead_letter", "big": "completed"}


def test_P2_B_a_handler_that_swallows_the_cap_exception_is_still_dead_lettered():
    for variant in ("except_jobbudget", "except_exception"):
        b, store, alerter, clock = make_breaker(config=BreakerConfig(job_cap_enforce=True))
        repo = FakeJobRepository()

        async def sneaky(job, variant=variant):
            for _ in range(30):
                try:
                    b.record_call()
                    b.guard()
                except JobBudgetExceeded:
                    if variant == "except_jobbudget":
                        pass  # swallowed, handler returns normally
                except Exception:
                    pass

        w = Worker(repo, worker_id="w", handlers={"t": sneaky}, breaker=b, idle_sleep=_no_sleep, job_call_cap=10)

        async def drive():
            await repo.enqueue(type="t", payload={})
            await w.run_once()

        asyncio.run(drive())
        (job,) = repo._jobs.values()
        assert job.status.value == "dead_letter", variant


def test_P2_B_spawned_work_does_not_inherit_the_per_job_budget_or_tally():
    from noctusai_lib.primitives.background import run_in_thread, spawn_background
    from noctusai_lib.primitives.supabase_breaker import _JOB, _TALLY, call_tally

    seen = []

    async def drive():
        with job_scope(5), call_tally():
            async def coro():
                seen.append((_JOB.get(), _TALLY.get()))

            await spawn_background("c", coro())
            t = run_in_thread("t", lambda: seen.append((_JOB.get(), _TALLY.get())))
            t.join(2)

    asyncio.run(drive())
    assert seen == [(None, None), (None, None)]


def test_P3_2_marker_survives_a_deploy_overlap_without_false_vanished_alerts():
    store, alerter, clock = InMemoryBreakerStore(), RecordingAlerter(), Clock()
    mk = lambda: Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, fleet_ttl_s=1.0)
    a, b = mk(), mk()  # old container (a) and new container (b) of the same product
    a.trip("worker:t", reason="runaway")
    clock.advance(30)
    b.trip("worker:t", reason="runaway again")  # b's own trip overwrites the key with ITS tripped_at
    clock.advance(30)
    key_ts = json.loads(store.data["noctus:breaker:p:worker:t"])["tripped_at"]
    for br in (a, b):
        br.check_sync("worker:t", force=True)
    # the MCP re-arm: marker (TTL, never deleted by a product) carrying the PERSISTED key's tripped_at, then DEL
    store.data["noctus:breaker:p:rearm:worker:t"] = json.dumps({"tripped_at": key_ts, "by": "ops:ana"})
    del store.data["noctus:breaker:p:worker:t"]
    clock.advance(30)
    for br in (a, b):
        br.check_sync("worker:t", force=True)
    assert a.hold_reason("worker:t") is None and b.hold_reason("worker:t") is None
    assert not any("VANISHED" in s for s, _ in alerter.sent)
    assert "noctus:breaker:p:rearm:worker:t" in store.data, "markers expire by TTL; products never delete them"


def test_P3_3_an_in_memory_only_trip_is_repersisted_when_redis_recovers():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=0.0)
    store.down = True
    b.trip("worker:a", reason="runaway")
    assert not b._trips["worker:a"].persisted
    store.down = False
    b.check_sync("worker:a", force=True)
    assert b._trips["worker:a"].persisted and "noctus:breaker:prod-x:worker:a" in store.data


def test_P3_5_the_seed_app_wraps_the_whole_stack_so_product_middleware_added_later_runs_inside_http():
    from fastapi.testclient import TestClient
    from starlette.middleware.base import BaseHTTPMiddleware

    from noctusai_lib.api.supabase_source import SeedFastAPI
    from noctusai_lib.primitives.supabase_breaker import current_source

    seen = []

    class ProductTokenAudit(BaseHTTPMiddleware):  # a product adds this AFTER create_product_app
        async def dispatch(self, request, call_next):
            seen.append(current_source())
            return await call_next(request)

    app = SeedFastAPI()
    app.add_middleware(ProductTokenAudit)

    @app.get("/x")
    def _x():
        return {}

    TestClient(app).get("/x")
    assert seen == ["http"]


def test_round6_a_route_rearm_in_one_process_releases_the_others_via_the_audit_row_without_a_marker():
    store, alerter, clock = InMemoryBreakerStore(), RecordingAlerter(), Clock()
    mk = lambda: Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, fleet_ttl_s=1.0)
    a, b = mk(), mk()
    a.trip("worker:t", reason="runaway")
    clock.advance(30)
    b.check_sync("worker:t", force=True)  # b observes the persisted key as a remote hold... then both hold
    b.trip("worker:t", reason="runaway")  # (b trips on its own too: two local holds on one key)
    clock.advance(30)
    a.rearm("worker:t", by="ana", reason="fixed and verified")  # the platform-admin route path: DEL + audit row, NO marker
    assert not any(k.startswith("noctus:breaker:p:rearm:") for k in store.data)
    clock.advance(30)
    b.check_sync("worker:t", force=True)
    assert b.hold_reason("worker:t") is None, "the audit row (matching tripped_at) releases the other process"
    assert not any("VANISHED" in s for s, _ in alerter.sent)


def test_round6_an_audit_row_for_a_different_trip_does_not_release_a_vanished_hold():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=1.0)
    b.trip("worker:t", reason="runaway")
    clock.advance(30)
    store.audits.setdefault("noctus:breaker:prod-x:audit", []).append(json.dumps({"op": "rearm", "key": "noctus:breaker:prod-x:worker:t",
                                   "tripped_at": "1999-01-01T00:00:00+00:00"}))
    store.data.clear()
    b.check_sync("worker:t", force=True)
    assert b.hold_reason("worker:t") is not None and any("VANISHED" in s for s, _ in alerter.sent)


# --- round 7 P1-1: a REAL Worker configuration (default idle sleep) against the PLATFORM floor -----------------------


class StepClock:
    """Each read advances 1.0 s: every poll of the Worker is 1 s after the previous one, as with poll=max_idle=1."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        self.t += 1.0
        return self.t


class CountingRepo(FakeJobRepository):
    """Every claim is one Supabase REST call, and the repo counts them (F7): a fake that makes none is never billed."""

    def __init__(self, breaker: Breaker) -> None:
        super().__init__()
        self.breaker, self.claims = breaker, 0

    async def claim_next(self, *a, **kw):
        self.claims += 1
        self.breaker.record_call()  # what the transport does, under the Worker's alert-only claim scope
        return await super().claim_next(*a, **kw)


class VirtualClock:
    """ONE clock shared by the Worker and the breaker, advanced by (faithful) sleeps."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def _virtual_sleep(clock, until=None, on_sleep=None, step=None):
    """A faithful sleeper: the loop's idle delay really passes on the shared clock (or `step` when a producer wakes it)."""

    async def sleep(delay, stop):
        clock.advance(delay if step is None else min(delay, step))
        if on_sleep is not None:
            await on_sleep()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        if until is not None and clock() >= until:
            stop.set()

    return sleep


def _real_worker(b, repo, clock, **kw):
    # the DEFAULT idle sleep (no injected sleeper). The real sleep is shortened to 1 ms; the clock models 1 s per poll.
    return Worker(repo, worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=0.001,
                  max_idle_interval_seconds=0.001, held_poll_seconds=0.01, clock=clock, **kw)


def test_P1_1_a_real_worker_with_poll_equal_max_idle_of_1s_and_the_default_sleep_TRIPS():
    b, store, alerter, clock = make_breaker()
    worker = _real_worker(b, CountingRepo(b), StepClock())

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        for _ in range(500):  # wait for the trip (up to 10 s), independent of machine load
            if b.hold_reason("worker:t") is not None:
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, 3)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is not None, "a loop polling every 1 s with no backoff MUST be stopped"
    assert "noctus:breaker:prod-x:worker:t" in store.data


def test_P1_1_a_producer_that_keeps_waking_an_empty_loop_cannot_launder_it():
    from noctusai_lib.domain.jobs import wake

    b, store, alerter, clock = make_breaker()
    worker = _real_worker(b, CountingRepo(b), StepClock())

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))

        async def spam():  # enqueues that never leave anything claimable: pure wake traffic
            while not stop.is_set():
                wake.notify_enqueued("t")
                await asyncio.sleep(0.001)

        sp = asyncio.create_task(spam())
        for _ in range(500):
            if b.hold_reason("worker:t") is not None:
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, 3)
        await sp

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is not None, "wake-followed empty polls are free only up to the per-window cap"


def test_P1_1_a_worker_idling_at_the_floor_or_slower_is_never_billed():
    b, store, alerter, clock = make_breaker()

    class Slow:
        t = 0.0

        def __call__(self):
            Slow.t += 30.0  # the default max_idle: 30 s between polls
            return Slow.t

    worker = _real_worker(b, FakeJobRepository(), Slow())

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        await asyncio.sleep(0.3)
        stop.set()
        await asyncio.wait_for(task, 3)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is None and b.count("worker:t", 3600) == 0


def test_P1_1_in_a_deploy_context_a_max_idle_below_the_floor_is_clamped_loudly(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "production")
    b, *_ = make_breaker()
    with caplog.at_level("WARNING"):
        w = Worker(FakeJobRepository(), worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=1.0,
                   max_idle_interval_seconds=1.0)
    assert w._max_idle_interval == b._config.min_idle_poll_s == 10.0
    assert "clamped to the floor" in caplog.text
    monkeypatch.delenv("APP_ENV")
    w2 = Worker(FakeJobRepository(), worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=1.0,
                max_idle_interval_seconds=1.0)
    assert w2._max_idle_interval == 1.0, "outside a deploy the declared value stands (and is billed against the floor)"


# --- round 7: P2-1 route re-arm from a remote-only holder, P2-2 degraded, P3 clamps / lookback ------------------------


def test_P2_1_a_rearm_from_a_breaker_holding_the_trip_only_remotely_releases_a_peer_that_holds_it_locally():
    store, alerter, clock = InMemoryBreakerStore(), RecordingAlerter(), Clock()
    mk = lambda: Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, fleet_ttl_s=1.0)
    holder, server = mk(), mk()  # `server` serves the platform-admin route; `holder` runs the Worker that tripped
    holder.trip("worker:t", reason="runaway")
    clock.advance(30)
    server.check_sync("worker:t", force=True)  # the serving process sees only a REMOTE hold: no local trip at all
    assert "worker:t" not in server._trips and server.hold_reason("worker:t") is not None
    server.rearm("worker:t", by="ana", reason="fixed and verified")
    row = json.loads(store.audits["noctus:breaker:p:audit"][-1])
    assert row["tripped_at"], "the nonce comes from the PERSISTED key, not from a local trip the server never had"
    clock.advance(30)
    holder.check_sync("worker:t", force=True)
    assert holder.hold_reason("worker:t") is None, "the route's re-arm must not be reverted by the holder"
    assert not any("VANISHED" in s for s, _ in alerter.sent)
    assert any("RELEASED by an audit row" in s for s, _ in alerter.sent), "every audit-row release is announced"


def test_P2_1_the_audit_row_is_written_BEFORE_the_delete_and_is_mandatory():
    class NoAudit(InMemoryBreakerStore):
        def append_audit(self, key, value, cap):
            raise ConnectionError("audit list unwritable")

    store, alerter, clock = NoAudit(), RecordingAlerter(), Clock()
    b = Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True)
    b.trip("worker:t", reason="runaway")
    with pytest.raises(ConnectionError):
        b.rearm("worker:t", by="ana", reason="fixed")
    assert "noctus:breaker:p:worker:t" in store.data, "no audit row => the key is NOT deleted"
    assert b.hold_reason("worker:t") is not None


def test_P2_2_a_credentials_refusal_is_degraded_configuration_not_a_transient_outage():
    class NoPermissionError(Exception):  # the redis-py class name
        pass

    class Denied(InMemoryBreakerStore):
        def mget(self, keys):
            raise NoPermissionError("this user has no permissions to run the 'mget' command")

        def get(self, key):
            raise NoPermissionError("NOPERM")

        def set(self, key, value, ttl=None):
            raise NoPermissionError("NOPERM")

    store, alerter, clock = Denied(), RecordingAlerter(), Clock()
    b = Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, fleet_ttl_s=0.0)
    b.refresh()
    assert b.degraded and "configuration, not an outage" in b.degraded
    assert not any("BLIND" in s for s, _ in alerter.sent) and any("DEGRADED" in s for s, _ in alerter.sent)
    b2 = Breaker(slug="p", store=Denied(), alerter=RecordingAlerter(), clock=clock, wall=clock, sync_io=True)
    b2.trip("worker:t", reason="runaway")
    assert b2.degraded and "NOT persisted" in b2.degraded


def test_P2_2_the_boot_probe_degrades_on_failure_and_passes_on_a_healthy_store():
    ok, _, a_ok, clock = make_breaker()
    assert ok.probe() is True and ok.degraded is None
    store = InMemoryBreakerStore()
    store.down = True
    b = Breaker(slug="p", store=store, alerter=RecordingAlerter(), clock=clock, wall=clock, sync_io=True)
    assert b.probe() is False and "unreachable at boot" in b.degraded


def test_P3_2_cap_and_hard_are_clamped_to_the_ceiling():
    from noctusai_lib.primitives.supabase_breaker import MAX_BUDGET_CALLS

    with job_scope(10**9, hard=10**9) as budget:
        assert budget.cap == MAX_BUDGET_CALLS and budget.hard == MAX_BUDGET_CALLS
    b, *_ = make_breaker(config=BreakerConfig(job_cap_enforce=True))
    assert b.job_hard_limit(10**9) == MAX_BUDGET_CALLS


def test_P3_5_the_audit_lookback_scans_the_whole_capped_list_filtered_by_key():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=1.0)
    b.trip("worker:t", reason="runaway")
    ts = b._trips["worker:t"].tripped_at
    audit_key = "noctus:breaker:prod-x:audit"
    store.audits[audit_key] = [json.dumps({"op": "rearm", "key": "noctus:breaker:prod-x:worker:t", "tripped_at": ts})]
    store.audits[audit_key] += [json.dumps({"op": "trip", "key": "noctus:breaker:prod-x:worker:z"}) for _ in range(500)]
    clock.advance(30)
    del store.data["noctus:breaker:prod-x:worker:t"]
    b.check_sync("worker:t", force=True)  # the matching row is 500 rows deep: the old 30-row window would miss it
    assert b.hold_reason("worker:t") is None


# --- round 8: REAL deploy configuration, one shared virtual clock, a repo that counts its calls --------------------------


def _deploy_world(monkeypatch, **cfg_kw):
    monkeypatch.setenv("APP_ENV", "production")
    clock = VirtualClock()
    store, alerter = InMemoryBreakerStore(), RecordingAlerter()
    b = Breaker(slug="prod-x", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, **cfg_kw)
    return b, store, alerter, clock


def test_F2_a_gate_closed_worker_with_enqueues_every_2s_for_an_hour_is_never_held(monkeypatch):
    b, store, alerter, clock = _deploy_world(monkeypatch)
    repo = CountingRepo(b)

    gate_reads = {"n": 0}

    async def gate():  # a paused Worker: the claim gate answers False, no claim is attempted
        gate_reads["n"] += 1
        return False

    async def producer():
        await repo.enqueue(type="t", payload={})  # an enqueue every 2 s wakes the (paused) Worker

    worker = Worker(repo, worker_id="w", handlers={"t": _noop}, breaker=b, claim_gate=gate, poll_interval_seconds=1.0,
                    held_poll_seconds=0.01, clock=clock,
                    idle_sleep=_virtual_sleep(clock, until=1000.0 + 3600, on_sleep=producer))

    async def drive():
        stop = asyncio.Event()
        await asyncio.wait_for(worker.run_forever(stop_event=stop), 60)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is None, "a PAUSED worker must never trip the breaker under ordinary enqueue load"
    assert repo.claims == 0 and b.count("worker:t", 3600) == 0, "no claim was attempted, so nothing was billed"
    assert gate_reads["n"] < 200, f"{gate_reads['n']} gate reads in an hour: a paused Worker must back off, not hot-loop"


def test_F2_a_real_deploy_worker_with_idle_backoff_multiplier_1_trips(monkeypatch):
    b, store, alerter, clock = _deploy_world(monkeypatch)
    repo = CountingRepo(b)
    worker = Worker(repo, worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=1.0,
                    idle_backoff_multiplier=1.0, held_poll_seconds=0.01, clock=clock,
                    idle_sleep=_virtual_sleep(clock, until=1000.0 + 3600))

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        for _ in range(500):
            if b.hold_reason("worker:t") is not None:
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is not None, "no backoff (multiplier 1.0) polls every 1 s: MUST be held"
    # on ONE shared clock, exactly 1 billed poll/s is 300 per 5 min (not > 300): the hourly rule (2,000) trips it at ~33 min
    assert 2000 < repo.claims < 2100, f"{repo.claims} claims before the hold"


def test_F2_deploy_clamp_makes_a_max_idle_of_1s_a_ramp_to_the_floor_and_run_forever_is_never_billed(monkeypatch):
    b, store, alerter, clock = _deploy_world(monkeypatch)
    repo = CountingRepo(b)
    worker = Worker(repo, worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=1.0,
                    max_idle_interval_seconds=1.0, held_poll_seconds=0.01, clock=clock,
                    idle_sleep=_virtual_sleep(clock, until=1000.0 + 3600))
    assert worker._max_idle_interval == 10.0, "a max_idle below the floor is clamped in a deploy context"

    async def drive():
        stop = asyncio.Event()
        await asyncio.wait_for(worker.run_forever(stop_event=stop), 60)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is None and b.count("worker:t", 3600) == 0
    assert 300 < repo.claims < 400, f"{repo.claims} polls in an hour at the clamped 10 s idle"


def test_F1_the_idle_poll_floor_is_finite_bounded_and_clamped_in_a_deploy_context(monkeypatch):
    for bad in ("nan", "inf", "-inf"):
        cfg = BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": bad})
        assert cfg.min_idle_poll_s == 10.0 and any("finite" in w for w in cfg.warnings), bad
    assert BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": "9999"}).min_idle_poll_s == 60.0
    deploy = BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": "1", "APP_ENV": "production"})
    assert deploy.min_idle_poll_s == 10.0 and any("below the default" in w and "clamped" in w for w in deploy.warnings)
    dev = BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": "1"})
    assert dev.min_idle_poll_s == 1.0 and any("below the default" in w for w in dev.warnings)


def test_F1_floor_1_in_a_deploy_cannot_let_a_1s_loop_escape(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    cfg = BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": "1", "APP_ENV": "production"})
    clock = VirtualClock()
    b = Breaker(slug="p", store=InMemoryBreakerStore(), alerter=RecordingAlerter(), clock=clock, wall=clock,
                sync_io=True, config=cfg)
    repo = CountingRepo(b)
    worker = Worker(repo, worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=1.0,
                    idle_backoff_multiplier=1.0, clock=clock, held_poll_seconds=0.01,
                    idle_sleep=_virtual_sleep(clock, until=1000.0 + 3600))

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        for _ in range(500):
            if b.hold_reason("worker:t") is not None:
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is not None


def test_F8_the_error_backoff_sleep_ignores_the_job_waker():
    from noctusai_lib.domain.jobs import wake

    b, store, alerter, clock = make_breaker()

    class Down(FakeJobRepository):
        claims = 0

        async def claim_next(self, *a, **kw):
            Down.claims += 1
            raise ConnectionError("outage")

    worker = Worker(Down(), worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=0.2,
                    max_idle_interval_seconds=0.2, held_poll_seconds=0.01, clock=clock)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))

        async def spam():  # a producer waking the job waker continuously during the outage
            while not stop.is_set():
                wake.notify_enqueued("t")
                await asyncio.sleep(0.001)

        sp = asyncio.create_task(spam())
        await asyncio.sleep(0.6)
        stop.set()
        await asyncio.wait_for(task, 3)
        await sp

    asyncio.run(drive())
    assert Down.claims <= 5, f"{Down.claims} claims in 0.6 s: the waker cut the error backoff short"


def test_F9_reschedule_later_is_clamped_to_the_floor():
    from datetime import datetime, timezone

    from noctusai_lib.domain.jobs.repo import RescheduleLater

    b, store, alerter, clock = make_breaker()
    repo = FakeJobRepository()

    async def hot(job):
        raise RescheduleLater(0.0)

    w = Worker(repo, worker_id="w", handlers={"t": hot}, breaker=b, idle_sleep=_no_sleep)

    async def drive():
        await repo.enqueue(type="t", payload={})
        await w.run_once()

    asyncio.run(drive())
    (job,) = repo._jobs.values()
    delta = (job.scheduled_for - datetime.now(timezone.utc)).total_seconds()
    assert delta > 8.0, f"rescheduled only {delta:.1f}s ahead: a handler could spin the claim loop"


def test_F3_the_persisted_key_read_in_rearm_is_load_bearing_an_error_raises_before_audit_and_del():
    class NoGet(InMemoryBreakerStore):
        broken = False

        def get(self, key):
            if NoGet.broken:
                raise ConnectionError("redis read failed")
            return super().get(key)

    store, alerter, clock = NoGet(), RecordingAlerter(), Clock()
    b = Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True)
    b.trip("worker:t", reason="runaway")
    NoGet.broken = True
    with pytest.raises(ConnectionError):
        b.rearm("worker:t", by="ana", reason="fixed")
    NoGet.broken = False
    assert "noctus:breaker:p:worker:t" in store.data and not store.audits.get("noctus:breaker:p:audit")
    assert b.hold_reason("worker:t") is not None


def test_F4_a_failed_del_after_the_row_writes_a_compensating_rearm_aborted_and_the_newest_row_wins():
    class NoDel(InMemoryBreakerStore):
        def delete(self, key):
            raise ConnectionError("DEL failed")

    store, alerter, clock = NoDel(), RecordingAlerter(), Clock()
    mk = lambda: Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, fleet_ttl_s=1.0)
    a, peer = mk(), mk()
    a.trip("worker:t", reason="runaway")
    with pytest.raises(ConnectionError):
        a.rearm("worker:t", by="ana", reason="fixed")
    ops = [json.loads(r)["op"] for r in store.audits["noctus:breaker:p:audit"]]
    assert ops == ["rearm", "rearm_aborted"]
    # a peer holds the same trip; its key vanishes (eviction): the NEWEST row for key+nonce says aborted -> no release
    peer._trips["worker:t"] = a._trips["worker:t"]
    clock.advance(30)
    del store.data["noctus:breaker:p:worker:t"]
    peer.check_sync("worker:t", force=True)
    assert peer.hold_reason("worker:t") is not None and any("VANISHED" in s for s, _ in alerter.sent)


def test_F5_a_transient_degraded_state_clears_on_the_first_good_refresh_a_config_refusal_does_not():
    store, alerter, clock = InMemoryBreakerStore(), RecordingAlerter(), Clock()
    b = Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True, fleet_ttl_s=0.0)
    store.down = True
    assert b.probe() is False and b.degraded
    store.down = False
    b.refresh()
    assert b.degraded is None, "unreachable-at-boot is transient: the first successful refresh clears it"
    b.set_degraded("the breaker Redis refused this service's credentials/ACL (config)")
    b.refresh()
    assert b.degraded is not None, "a configuration refusal stays sticky"


def test_F10_a_budget_override_looser_than_the_default_is_alerted():
    cfg = BreakerConfig.from_env({"NOCTUS_BREAKER_BUDGETS": json.dumps({"worker:a": [[3600, 5000]],
                                                                         "worker:tight": [[3600, 100]]})})
    assert set(cfg.overrides) == {"worker:a", "worker:tight"}
    assert any("worker:a" in w and "LOOSER" in w for w in cfg.warnings)
    assert not any("worker:tight" in w for w in cfg.warnings)
    b, store, alerter, clock = make_breaker(config=cfg)
    b.announce_config_warnings()
    assert any("LOOSER" in body for _, body in alerter.sent)


# --- round 9: a wake must not reopen the laundering hole -----------------------------------------------------------------


@pytest.mark.parametrize("poll_interval", [1.0, 0.25])
def test_P2_1_a_wake_every_third_poll_with_nothing_claimable_cannot_launder_a_loop_for_an_hour(monkeypatch, poll_interval):
    from noctusai_lib.domain.jobs import wake

    b, store, alerter, clock = _deploy_world(monkeypatch)
    repo = CountingRepo(b)
    n = {"sleeps": 0}

    async def sleep(delay, stop):
        n["sleeps"] += 1
        wake_now = n["sleeps"] % 3 == 0  # every third sleep is CUT SHORT by a wake with nothing claimable behind it
        clock.advance(min(delay, 0.5) if wake_now else delay)
        if wake_now:
            wake.notify_enqueued("t")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        if clock() >= 1000.0 + 3600:
            stop.set()

    worker = Worker(repo, worker_id="w", handlers={"t": _noop}, breaker=b, poll_interval_seconds=poll_interval,
                    held_poll_seconds=0.01, clock=clock, idle_sleep=sleep)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        for _ in range(500):
            if b.hold_reason("worker:t") is not None:
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is not None, "a wake, then 1 s and 2 s polls, then a wake: MUST end held"


def test_P3_1_a_paused_worker_ignores_job_wakes_and_backs_off_a_bounded_number_of_gate_reads():
    from noctusai_lib.domain.jobs import wake

    b, store, alerter, clock = make_breaker()
    reads = {"n": 0}

    async def gate():
        reads["n"] += 1
        return False

    worker = Worker(FakeJobRepository(), worker_id="w", handlers={"t": _noop}, breaker=b, claim_gate=gate,
                    poll_interval_seconds=0.05, max_idle_interval_seconds=0.2, held_poll_seconds=0.01, clock=clock)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))

        async def spam():  # an enqueue stream waking the job waker every ms
            while not stop.is_set():
                wake.notify_enqueued("t")
                await asyncio.sleep(0.001)

        sp = asyncio.create_task(spam())
        await asyncio.sleep(0.8)
        stop.set()
        await asyncio.wait_for(task, 3)
        await sp

    asyncio.run(drive())
    assert reads["n"] <= 10, f"{reads['n']} gate reads in 0.8 s: wakes must not turn a paused Worker into a hot loop"


def test_P3_2_the_deploy_check_in_from_env_reads_the_passed_environment_not_os_environ(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")  # the PROCESS is a deploy ...
    dev_cfg = BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": "1"})  # ... but the env being judged is not
    assert dev_cfg.min_idle_poll_s == 1.0 and not any("clamped to the default" in w for w in dev_cfg.warnings)
    prod_cfg = BreakerConfig.from_env({"NOCTUS_MIN_IDLE_POLL_S": "1", "APP_ENV": "production"})
    assert prod_cfg.min_idle_poll_s == 10.0


def test_P3_3_the_looser_override_warning_compares_each_window_to_the_default_rule_of_the_same_window():
    cfg = BreakerConfig.from_env({"NOCTUS_BREAKER_BUDGETS": json.dumps({"worker:a": [[300, 800], [3600, 1000]]})})
    assert any("LOOSER" in w and "300s=800" in w and "3600s" not in w for w in cfg.warnings), cfg.warnings
    tight = BreakerConfig.from_env({"NOCTUS_BREAKER_BUDGETS": json.dumps({"worker:b": [[300, 100], [3600, 1000]]})})
    assert not any("LOOSER" in w for w in tight.warnings)


# --- scheduler billing: a run is billed only when it is a cadence violation that cost real Supabase calls ---------------


def _scheduler_world(job_calls_per_run):
    from noctusai_lib.api import scheduler as sch
    from noctusai_lib.primitives.supabase_breaker import install_breaker

    sch.reset_for_testing()
    clock = VirtualClock()
    store, alerter = InMemoryBreakerStore(), RecordingAlerter()
    b = install_breaker(Breaker(slug="p", store=store, alerter=alerter, clock=clock, wall=clock, sync_io=True))

    async def job():
        for _ in range(job_calls_per_run):
            b.record_call()  # the transport's count, under the run's `job:scheduler:<name>` source and tally

    return sch, b, clock, job


def test_scheduler_a_1s_job_that_an_idlegate_skips_makes_no_calls_and_is_never_held_for_an_hour():
    sch, b, clock, job = _scheduler_world(0)
    wrapped = sch._instrument("gated", job)

    async def drive():
        for _ in range(3600):
            clock.advance(1.0)
            await wrapped()

    asyncio.run(drive())
    assert b.hold_reason("scheduler:gated") is None and b.count("scheduler:gated", 3600) == 0
    sch.reset_for_testing()


def test_scheduler_a_1s_job_that_makes_a_supabase_call_per_run_IS_held():
    sch, b, clock, job = _scheduler_world(1)
    wrapped = sch._instrument("hot", job)

    async def drive():
        for _ in range(3600):
            clock.advance(1.0)
            await wrapped()

    asyncio.run(drive())
    assert b.hold_reason("scheduler:hot") is not None, "1 call/s from a 1 s job is the incident shape"
    sch.reset_for_testing()


def test_scheduler_a_nightly_job_with_thousands_of_calls_per_run_is_never_billed():
    sch, b, clock, job = _scheduler_world(5000)
    wrapped = sch._instrument("nightly", job)

    async def drive():
        for _ in range(5):
            clock.advance(86_400.0)
            await wrapped()

    asyncio.run(drive())
    assert b.hold_reason("scheduler:nightly") is None and b.count("scheduler:nightly", 3600) == 0
    sch.reset_for_testing()
