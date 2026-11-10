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
    worker = Worker(repo, worker_id="w", handlers={"transcricao": _noop}, poll_interval_seconds=0.01,
                    idle_sleep=_no_sleep, breaker=b, held_poll_seconds=0.01)

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
    b, store, alerter, clock = make_breaker()
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
    assert json.loads(store.data["noctus:breaker:prod-x:rearm:worker:a"])["by"] == "ana", "the re-arm marker is left"


def test_parked_worker_resumes_after_rearm():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=0.0)
    b.trip("worker:transcricao", reason="runaway")
    repo = RunawayRepo(b, clock)
    worker = Worker(repo, worker_id="w", handlers={"transcricao": _noop}, poll_interval_seconds=0.01,
                    idle_sleep=_no_sleep, breaker=b, held_poll_seconds=0.01)

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
    assert "noctus:breaker:prod-x:rearm:worker:a" not in store.data, "the marker is consumed"


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
    n = 200_000
    t0 = time.perf_counter()
    for _ in range(n):
        b.record_call("http")
    per_call_us = (time.perf_counter() - t0) / n * 1e6
    assert store.calls == 0, "counting must be in-memory: no Redis, no network per call"
    assert per_call_us < 20, f"{per_call_us:.2f} us per counted call"
    print(f"\nper-call overhead: {per_call_us:.2f} us")


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
    b.configure(slug="t", store=InMemoryBreakerStore(), alerter=RecordingAlerter(), config=BreakerConfig())
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
    b, store, alerter, clock = make_breaker()
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


class BusyRepo(FakeJobRepository):
    async def claim_next(self, *a, **kw):
        get_breaker  # noqa: B018 -- the breaker under test is passed to the Worker; claims are productive here
        self.breaker.record_call()
        return await super().claim_next(*a, **kw)


def test_busy_productive_worker_never_trips_its_loop_and_there_are_no_credits():
    b, store, alerter, clock = make_breaker()
    repo = BusyRepo()
    repo.breaker = b

    async def noop(job):
        for _ in range(10):
            b.record_call()

    worker = Worker(repo, worker_id="w", handlers={"t": noop}, breaker=b, idle_sleep=_no_sleep,
                    poll_interval_seconds=0.001)

    async def drive():
        for _ in range(500):  # a backlog drain: 500 jobs, ~11 calls each, back to back
            await repo.enqueue(type="t", payload={})
        for _ in range(500):
            assert await worker.run_once() is True

    asyncio.run(drive())
    assert b.hold_reason("worker:t") is None and not store.data
    assert not hasattr(b, "credit"), "the credit scheme is deleted"


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
    rows = [json.loads(r) for r in store.audit]
    assert [r["op"] for r in rows] == ["trip", "rearm"] and rows[1]["claimed_by"] == "ana" and rows[1]["reason"] == "fixed"
    assert BREAKER_AUDIT_KEY == "noctus:breaker:audit"
    for i in range(1200):
        store.append_audit(BREAKER_AUDIT_KEY, str(i), 1000)
    assert len(store.audit) == 1000


# --- startup is its own source; unattributed still catches stray loops (coordinator review 2026-11-10) -------------


def test_startup_and_unattributed_are_alert_only_never_held():
    b, store, alerter, clock = make_breaker()
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


def test_P3_7_budget_env_above_the_ceiling_is_rejected_and_defaults_apply(caplog):
    from noctusai_lib.primitives.supabase_breaker import MAX_BUDGET_CALLS

    cfg = BreakerConfig.from_env({"NOCTUS_BREAKER_BUDGETS": json.dumps({"worker:a": [[300, MAX_BUDGET_CALLS + 1]]})})
    assert cfg.overrides == {}
    ok = BreakerConfig.from_env({"NOCTUS_BREAKER_BUDGETS": json.dumps({"worker:a": [[300, MAX_BUDGET_CALLS]]})})
    assert ok.overrides["worker:a"][0].max_calls == MAX_BUDGET_CALLS


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
        await asyncio.sleep(0.15)
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
