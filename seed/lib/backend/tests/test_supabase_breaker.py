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
        self.breaker.record_call("worker:transcricao:loop")  # the transport hook, against THIS breaker
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
    key = "noctus:breaker:prod-x:worker:transcricao:loop"
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
    assert len(alerter.sent) == 1 and "http traffic high" in alerter.sent[0][0]
    assert store.data == {}
    with pytest.raises(ValueError):
        b.trip("http", reason="x")


def test_held_source_does_not_start_on_boot():
    b, store, alerter, clock = make_breaker()
    store.data["noctus:breaker:prod-x:worker:transcricao:loop"] = json.dumps({"reason": "runaway", "by": "auto"})
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
    assert out["ok"] and b.hold_reason("worker:a") is None and store.data == {}


def test_parked_worker_resumes_after_rearm():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=0.0)
    b.trip("worker:transcricao:loop", reason="runaway")
    repo = RunawayRepo(b, clock)
    worker = Worker(repo, worker_id="w", handlers={"transcricao": _noop}, poll_interval_seconds=0.01,
                    idle_sleep=_no_sleep, breaker=b, held_poll_seconds=0.01)

    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop_event=stop))
        await asyncio.sleep(0.1)
        assert repo.claims == 0
        await asyncio.to_thread(b.rearm, "worker:transcricao:loop", by="ana", reason="fixed and verified")
        await asyncio.sleep(0.1)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(drive())
    assert repo.claims > 0, "after a human re-arm the source restarts"


def test_rearm_from_another_process_releases_the_local_trip():
    b, store, alerter, clock = make_breaker(fleet_ttl_s=1.0)
    b.trip("worker:a", reason="runaway")
    clock.advance(10)
    store.data.clear()  # the MCP tool deleted the key
    b.check_sync("worker:a", force=True)
    assert b.hold_reason("worker:a") is None


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


def test_F4_handler_looping_1000_calls_under_a_tripped_source_makes_at_most_budget_plus_one():
    b = get_breaker()
    b.configure(slug="t", store=InMemoryBreakerStore(), alerter=RecordingAlerter(), config=BreakerConfig())
    b._sync_io = True
    reached = []
    inner = httpx.MockTransport(lambda req: (reached.append(1), httpx.Response(200, json=[]))[1])
    client = httpx.Client(transport=TimingTransport(inner), base_url="https://x.supabase.co")
    refused = 0
    with source_scope("worker:transcricao"):
        for _ in range(1000):
            try:
                client.get("/rest/v1/jobs")
            except BreakerOpen:
                refused += 1
    assert len(reached) <= 301, f"{len(reached)} calls left the process (budget 300/5min, so <= budget+1)"
    assert refused >= 699 and b.hold_reason("worker:transcricao") is not None
    with source_scope("http"):
        client.get("/rest/v1/jobs")  # user traffic is never refused


def test_F5_unscoped_calls_are_budgeted_and_trippable_http_is_explicit():
    b, store, alerter, clock = make_breaker()
    for _ in range(301):
        b.record_call()  # no scope: a lifespan create_task loop / bare Thread
    assert b.hold_reason("unattributed") is not None, "an unscoped runaway loop must be stoppable"
    assert b.hold_reason("http") is None
    assert BREAKER_SOURCE_RE.match("unattributed")


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


def test_productive_worker_is_not_tripped_but_a_call_burner_is():
    b, store, alerter, clock = make_breaker()
    # a backlog drain: 50 jobs, each spends 150 calls and FINISHES -> earns 200 headroom per job
    for _ in range(50):
        for _ in range(150):
            b.record_call("worker:t")
        b.credit("worker:t", 200)
    assert b.hold_reason("worker:t") is None
    # a handler burning calls without finishing a job: trips at the base budget
    for _ in range(301):
        b.record_call("worker:burner")
    assert b.hold_reason("worker:burner") is not None


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
    assert [r["op"] for r in rows] == ["trip", "rearm"] and rows[1]["by"] == "ana" and rows[1]["reason"] == "fixed"
    assert BREAKER_AUDIT_KEY == "noctus:breaker:audit"
    for i in range(1200):
        store.append_audit(BREAKER_AUDIT_KEY, str(i), 1000)
    assert len(store.audit) == 1000
