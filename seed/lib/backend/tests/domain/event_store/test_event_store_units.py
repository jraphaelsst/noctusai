"""Upcasting, the jobs-worker projection handler and the rebuild helper (backend-independent; Fake store)."""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.domain.event_store import (
    PROJECTION_JOB_TYPE,
    FakeEventStore,
    NewEvent,
    UpcastError,
    Upcasters,
    assert_every_stored_type_handled,
    load_stream,
    projection_job_handler,
    rebuild_projection,
    unhandled_stored_types,
)
from noctusai_lib.domain.jobs import FakeJobRepository, Worker

ORG = str(uuid.UUID(int=7))


def _count(events, table):
    for e in events:
        if e.event_type == "boom":
            raise RuntimeError("boom")
        table[e.stream_id] = table.get(e.stream_id, 0) + 1


def _store_with_projection(mode="async"):
    store = FakeEventStore()
    store.create_table("counts")
    assert store.register_projection("cnt", handler=_count, target="counts", stream_types=["sub"], mode=mode) is None
    return store


# -- upcasting -------------------------------------------------------------------------------------------------


def _up():
    return (Upcasters()
            .register("priced", 1, lambda d: {"cents": d["reais"] * 100})
            .register("priced", 2, lambda d: {**d, "currency": "BRL"}))


def test_upcast_chain_runs_to_current_and_never_rewrites_the_log():
    store, sid = FakeEventStore(), str(uuid.uuid4())
    store.append(ORG, "sub", sid, [NewEvent("priced", {"reais": 3}, schema_version=1),
                                   NewEvent("priced", {"cents": 5}, schema_version=2),
                                   NewEvent("priced", {"cents": 7, "currency": "USD"}, schema_version=3)])
    up = _up()
    assert up.current_version("priced") == 3 and up.current_version("other") == 1
    got = load_stream(store, ORG, "sub", sid, upcasters=up).events
    assert [(e.schema_version, e.data) for e in got] == [
        (3, {"cents": 300, "currency": "BRL"}), (3, {"cents": 5, "currency": "BRL"}), (3, {"cents": 7, "currency": "USD"})]
    assert [e.schema_version for e in store.load(ORG, "sub", sid).events] == [1, 2, 3]
    assert store.load(ORG, "sub", sid).events[0].data == {"reais": 3}


def test_upcast_refuses_a_gap_and_a_future_version():
    store, sid = FakeEventStore(), str(uuid.uuid4())
    store.append(ORG, "sub", sid, [NewEvent("priced", {"cents": 1}, schema_version=4)])
    with pytest.raises(UpcastError, match="priced v4"):
        load_stream(store, ORG, "sub", sid, upcasters=_up())
    gappy = Upcasters().register("x", 2, lambda d: d)  # v1 -> v2 missing
    assert gappy.chain_gap("x", 1) == 1 and gappy.chain_gap("x", 2) is None
    with pytest.raises(ValueError):
        _up().register("priced", 1, lambda d: d)  # double registration


def test_every_stored_type_needs_a_handler_and_a_complete_chain():
    store = FakeEventStore()
    store.append(ORG, "sub", str(uuid.uuid4()), [NewEvent("priced", {"reais": 1}), NewEvent("renamed"),
                                                 NewEvent("legacy", schema_version=2)])
    problems = unhandled_stored_types(store.stored_event_types(), handled={"priced", "renamed", "legacy"}, upcasters=_up())
    assert problems == ["legacy v2 (1 stored): no upcaster from v2 to current v1"]
    assert unhandled_stored_types(store.stored_event_types(), handled={"priced"}, upcasters=_up()) == [
        "legacy v2 (1 stored): no handler", "renamed v1 (1 stored): no handler"]
    with pytest.raises(AssertionError, match="no handler"):
        assert_every_stored_type_handled(store, handled={"priced", "legacy"}, upcasters=_up())
    up = _up().register("legacy", 1, lambda d: d)
    assert_every_stored_type_handled(store, handled={"priced", "renamed", "legacy"}, upcasters=up)


# -- the jobs-worker handler ----------------------------------------------------------------------------------


async def _run_job(store, payload, **kw):
    repo = FakeJobRepository()
    await repo.enqueue(type=PROJECTION_JOB_TYPE, payload=payload, max_retries=0)
    worker = Worker(repo, worker_id="w1", handlers={PROJECTION_JOB_TYPE: projection_job_handler(store, **kw)})
    assert await worker.run_once()
    return await repo.queue_stats()


@pytest.mark.asyncio
async def test_job_drains_the_projection_in_batches_exactly_once():
    store, sid = _store_with_projection(), str(uuid.uuid4())
    store.append(ORG, "sub", sid, [NewEvent("x") for _ in range(5)])
    stats = await _run_job(store, {"projection": "cnt"}, batch=2)
    assert store.read_model("counts") == {sid: 5}
    assert stats.dead_letter == 0
    await _run_job(store, {"projection": "cnt"}, batch=2)  # a second job finds nothing new
    assert store.read_model("counts") == {sid: 5}


@pytest.mark.asyncio
async def test_job_dead_letters_a_refusal_and_fails_a_broken_batch():
    store = _store_with_projection(mode="sync")
    assert (await _run_job(store, {"projection": "cnt"})).dead_letter == 1     # not_async: retrying cannot help
    assert (await _run_job(store, {})).dead_letter == 1                         # no projection name
    store = _store_with_projection()
    store.append(ORG, "sub", str(uuid.uuid4()), [NewEvent("boom")])
    stats = await _run_job(store, {"projection": "cnt"})                        # error -> raises -> the job retries
    assert stats.dead_letter == 0 and stats.pending == 1 and "boom" in (stats.last_error or "")
    assert store.checkpoints["cnt"].last_error == "boom" and store.read_model("counts") == {}


# -- rebuild helper -------------------------------------------------------------------------------------------


def test_rebuild_stops_at_max_steps_without_swapping():
    store, sid = _store_with_projection(), str(uuid.uuid4())
    store.append(ORG, "sub", sid, [NewEvent("x") for _ in range(5)])
    store.run_projection("cnt")
    store.tables["counts"][sid] = 999
    out = rebuild_projection(store, "cnt", batch=1, max_steps=2)
    assert out.status == "refused" and out.code == "max_steps" and out.steps == 2
    assert store.read_model("counts") == {sid: 999}  # the live read model was not touched
    assert rebuild_projection(store, "cnt", batch=1).rows == 1 and store.read_model("counts") == {sid: 5}
