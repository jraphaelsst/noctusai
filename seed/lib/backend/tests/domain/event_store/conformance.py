"""ONE behaviour suite for every `EventStore` / `CheckpointStore` pair (Fake and Real alike).

`test_conformance.py` runs it against the Fakes and against the Real adapters over a live PGlite (real Postgres,
the rendered SQL) -- so the Fake is held to exactly what the database does. Every case uses its own stream type
and projection names, so cases sharing one database never see each other's events.

A `Harness` gives a case the stores plus one backend-shaped helper: `install_counter(...)` registers a projection
that counts events per stream into a read model (a SQL function + table for the Real, a Python callable + dict for
the Fake), failing on any event of type `boom`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

import pytest

from noctusai_lib.domain.event_store import (
    ANY_VERSION,
    ConcurrencyConflict,
    Cursor,
    NewEvent,
    Upcasters,
    execute,
    rebuild_projection,
)
from noctusai_lib.domain.event_store.projections import ExternalProjectionRunner

ORG = str(uuid.UUID(int=0xE1))
OTHER_ORG = str(uuid.UUID(int=0xE2))


@dataclass
class Harness:
    name: str
    store: Any
    checkpoints: Any
    #: (projection, mode, target, stream_types) -> registration refusal code or None
    install_counter: Callable[[str, str, str, list], Optional[str]]
    #: target -> {stream_id: count}
    counts: Callable[[str], dict]
    #: target -> overwrite every count with 999 (a drifted read model)
    corrupt: Callable[[str], None]
    #: target -> does the table exist
    table_exists: Callable[[str], bool]


def _u(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _sid() -> str:
    return str(uuid.uuid4())


def ev(event_type: str = "happened", event_id: Optional[str] = None, **data) -> NewEvent:
    return NewEvent(event_type, data, event_id=event_id)


# -- append / load -------------------------------------------------------------------------------------------


def case_append_new_stream_versions_and_positions(h: Harness):
    st, sid = _u("st"), _sid()
    out = h.store.append(ORG, st, sid, [ev("created", n=1), ev("renamed", n=2)], expected_version=0)
    assert out.status == "ok" and out.version == 2 and len(out.positions) == 2 and out.positions[0] < out.positions[1]
    loaded = h.store.load(ORG, st, sid)
    assert loaded.version == 2
    assert [(e.version, e.event_type, e.data) for e in loaded.events] == [(1, "created", {"n": 1}), (2, "renamed", {"n": 2})]
    assert [e.global_position for e in loaded.events] == list(out.positions)
    assert all(e.org_id == ORG and e.stream_id == sid and e.schema_version == 1 for e in loaded.events)
    assert [e.version for e in h.store.load(ORG, st, sid, from_version=2).events] == [2]


def case_expected_version_conflict(h: Harness):
    st, sid = _u("st"), _sid()
    assert h.store.append(ORG, st, sid, [ev()], expected_version=0).status == "ok"
    out = h.store.append(ORG, st, sid, [ev()], expected_version=0)
    assert out.status == "conflict" and out.current_version == 1
    assert h.store.load(ORG, st, sid).version == 1  # nothing appended
    assert h.store.append(ORG, st, sid, [ev()], expected_version=1).version == 2
    assert h.store.append(ORG, st, sid, [ev()], expected_version=ANY_VERSION).version == 3
    new = h.store.append(ORG, _u("st"), _sid(), [ev()], expected_version=5)
    assert new.status == "conflict" and new.current_version == 0


def case_conflict_and_refusal_leave_no_stream_behind(h: Harness):
    st, sid = _u("st"), _sid()
    assert h.store.append(ORG, st, sid, [ev()], expected_version=3).status == "conflict"
    # the conflicting first append left no stream row: version 0 and expected_version=0 still succeeds
    assert h.store.load(ORG, st, sid).version == 0
    assert h.store.append(ORG, st, sid, [ev()], expected_version=0).status == "ok"


def case_idempotent_append_replays(h: Harness):
    st, sid = _u("st"), _sid()
    ids = [_sid(), _sid()]
    first = h.store.append(ORG, st, sid, [ev("a", ids[0]), ev("b", ids[1])], expected_version=0)
    again = h.store.append(ORG, st, sid, [ev("a", ids[0]), ev("b", ids[1])], expected_version=0)
    assert again.status == "replayed" and again.version == 2 and again.positions == first.positions
    assert h.store.load(ORG, st, sid).version == 2
    # half-replayed batch, another stream, another type: never silently appended
    assert h.store.append(ORG, st, sid, [ev("a", ids[0]), ev("c", _sid())]).code == "idempotency_conflict"
    assert h.store.append(ORG, st, _sid(), [ev("a", ids[0])]).code == "idempotency_conflict"
    assert h.store.append(ORG, st, sid, [ev("zzz", ids[0]), ev("b", ids[1])]).code == "idempotency_conflict"
    assert h.store.append(ORG, st, sid, [ev("a", ids[0]), ev("a", ids[0])]).code == "duplicate_event_id"
    assert h.store.load(ORG, st, sid).version == 2


def case_org_isolation(h: Harness):
    st, sid = _u("st"), _sid()
    h.store.append(ORG, st, sid, [ev()], expected_version=0)
    assert h.store.append(OTHER_ORG, st, sid, [ev()]).code == "org_mismatch"
    other = h.store.load(OTHER_ORG, st, sid)
    assert other.version == 0 and other.events == ()  # indistinguishable from a missing stream


def case_input_refusals(h: Harness):
    st, sid = _u("st"), _sid()
    assert h.store.append(ORG, st, sid, []).code == "empty"
    assert h.store.append(ORG, "Bad Type", sid, [ev()]).code == "invalid_stream_type"
    assert h.store.append(ORG, st, sid, [NewEvent("Not.A Type")]).code == "invalid_event_type"
    assert h.store.append(ORG, st, sid, [NewEvent("x", data=[1])]).code == "invalid_data"  # type: ignore[arg-type]
    assert h.store.append(ORG, st, sid, [NewEvent("x", metadata={"email": "a@b"})]).code == "invalid_metadata"
    assert h.store.append(ORG, st, sid, [NewEvent("x", schema_version=0)]).code == "invalid_schema_version"
    assert h.store.append(ORG, st, sid, [ev()], expected_version=-2).code == "invalid_expected_version"
    ok = h.store.append(ORG, st, sid, [NewEvent("x", metadata={"actor_id": ORG, "correlation_id": _sid(), "source": "t"})])
    assert ok.status == "ok"
    with pytest.raises(ValueError):
        h.store.append(ORG, st, "not-a-uuid", [ev()])


def case_occurred_at_and_schema_version_round_trip(h: Harness):
    st, sid = _u("st"), _sid()
    h.store.append(ORG, st, sid, [NewEvent("x", {"k": "v"}, schema_version=3, occurred_at="2026-01-02T03:04:05+00:00")])
    (e,) = h.store.load(ORG, st, sid).events
    assert e.schema_version == 3 and e.occurred_at.startswith("2026-01-02T03:04:05")


# -- read_all ------------------------------------------------------------------------------------------------


def case_read_all_pages_in_order_with_a_cursor(h: Harness):
    st, other = _u("st"), _u("st")
    s1, s2 = _sid(), _sid()
    h.store.append(ORG, st, s1, [ev("a"), ev("b")])
    h.store.append(ORG, other, _sid(), [ev("noise")])
    h.store.append(OTHER_ORG, st, s2, [ev("c")])  # read_all is cross-org: projections are platform-level
    first = h.store.read_all(Cursor(), limit=2, stream_types=[st])
    assert [e.event_type for e in first.events] == ["a", "b"] and first.next == first.events[-1].cursor
    rest = h.store.read_all(first.next, limit=10, stream_types=[st])
    assert [e.event_type for e in rest.events] == ["c"]
    end = h.store.read_all(rest.next, limit=10, stream_types=[st])
    assert end.events == () and end.next == rest.next
    cursors = [e.cursor for e in first.events + rest.events]
    assert cursors == sorted(cursors)


def case_stored_event_types(h: Harness):
    st = _u("st")
    h.store.append(ORG, st, _sid(), [NewEvent("es_conf_typed", schema_version=2), NewEvent("es_conf_typed", schema_version=2)])
    assert h.store.stored_event_types()[("es_conf_typed", 2)] >= 2


# -- projections ---------------------------------------------------------------------------------------------


def case_sync_projection_runs_inside_the_append(h: Harness):
    st, proj, table = _u("st"), _u("p"), _u("t")
    assert h.install_counter(proj, "sync", table, [st]) is None
    sid = _sid()
    h.store.append(ORG, st, sid, [ev(), ev()])
    assert h.counts(table) == {sid: 2}
    out = h.store.append(ORG, st, sid, [ev(), ev("boom")])
    assert out.status == "refused" and out.code == "projection_failed" and out.projection == proj
    # the failing hook rolled the whole append back: no events, no version bump, no partial read model
    assert h.store.load(ORG, st, sid).version == 2 and h.counts(table) == {sid: 2}
    assert h.store.run_projection(proj).code == "not_async"


def case_async_projection_moves_read_model_and_checkpoint_together(h: Harness):
    st, proj, table = _u("st"), _u("p"), _u("t")
    assert h.install_counter(proj, "async", table, [st]) is None
    a, b = _sid(), _sid()
    h.store.append(ORG, st, a, [ev(), ev()])
    h.store.append(ORG, _u("st"), _sid(), [ev("boom")])  # another stream type: never reaches this projection
    run = h.store.run_projection(proj, limit=10)
    assert run.status == "ok" and run.applied == 2 and h.counts(table) == {a: 2}
    assert h.checkpoints.get(proj).cursor == run.cursor
    assert h.store.run_projection(proj).status == "idle" and h.counts(table) == {a: 2}  # exactly once
    h.store.append(ORG, st, b, [ev(), ev("boom")])
    failed = h.store.run_projection(proj, limit=10)
    assert failed.status == "error" and failed.cursor == run.cursor
    cp = h.checkpoints.get(proj)
    assert cp.cursor == run.cursor and cp.last_error  # checkpoint did not move, error recorded
    assert h.counts(table) == {a: 2}  # and the batch's partial writes were rolled back
    assert h.store.run_projection(_u("nope")).code == "unknown_projection"


def case_async_projection_batches(h: Harness):
    st, proj, table = _u("st"), _u("p"), _u("t")
    h.install_counter(proj, "async", table, [st])
    sid = _sid()
    h.store.append(ORG, st, sid, [ev() for _ in range(5)])
    assert [h.store.run_projection(proj, limit=2).applied for _ in range(4)] == [2, 2, 1, 0]
    assert h.counts(table) == {sid: 5}


def case_registration_refusals(h: Harness):
    st, table = _u("st"), _u("t")
    assert h.install_counter(_u("p"), "sometimes", table, [st]) == "invalid_mode"
    assert h.install_counter("Bad Name", "async", table, [st]) == "invalid_projection"
    assert h.install_counter(_u("p"), "async", table, []) == "invalid_stream_types"


def _rebuild(h: Harness, mode: str):
    st, proj, table = _u("st"), _u("p"), _u("t")
    h.install_counter(proj, mode, table, [st])
    a, b = _sid(), _sid()
    h.store.append(ORG, st, a, [ev(), ev(), ev()])
    h.store.append(ORG, st, b, [ev()])
    if mode == "async":
        h.store.run_projection(proj)
    assert h.counts(table) == {a: 3, b: 1}
    h.corrupt(table)
    assert h.counts(table) == {a: 999, b: 999}
    out = rebuild_projection(h.store, proj, batch=2)
    assert out.status == "ok" and out.rows == 2 and out.steps >= 2
    assert h.counts(table) == {a: 3, b: 1}
    assert not h.table_exists(f"{table}__rebuild")
    if mode == "async":
        assert h.checkpoints.get(proj).cursor == out.cursor
        assert h.store.run_projection(proj).status == "idle"
    h.store.append(ORG, st, a, [ev()])
    if mode == "async":
        h.store.run_projection(proj)
    assert h.counts(table) == {a: 4, b: 1}  # the swapped read model keeps projecting


def case_rebuild_async(h: Harness):
    _rebuild(h, "async")


def case_rebuild_sync(h: Harness):
    _rebuild(h, "sync")


def case_rebuild_refusals(h: Harness):
    assert rebuild_projection(h.store, _u("nope")).code == "unknown_projection"
    st, proj, table = _u("st"), _u("p"), _u("t")
    h.install_counter(proj, "async", table, [st])
    assert h.store.rebuild_step(proj).code == "not_rebuilding"
    assert h.store.rebuild_swap(proj).code == "not_rebuilding"


# -- checkpoints ---------------------------------------------------------------------------------------------


def case_checkpoint_compare_and_set(h: Harness):
    name = _u("cp")
    assert h.checkpoints.get(name).cursor == Cursor()
    assert h.checkpoints.advance(name, expected=Cursor(), to=Cursor(5, 7)) == "ok"
    assert h.checkpoints.advance(name, expected=Cursor(), to=Cursor(6, 1)) == "conflict"
    assert h.checkpoints.get(name).cursor == Cursor(5, 7)
    with pytest.raises(ValueError):
        h.checkpoints.advance(name, expected=Cursor(5, 7), to=Cursor(5, 7))
    h.checkpoints.record_error(name, "downstream 503")
    cp = h.checkpoints.get(name)
    assert cp.last_error == "downstream 503" and cp.cursor == Cursor(5, 7)
    h.checkpoints.reset(name)
    assert h.checkpoints.get(name).cursor == Cursor() and h.checkpoints.get(name).last_error is None


def case_external_runner_is_at_least_once_with_cas(h: Harness):
    st, name = _u("st"), _u("ext")
    sid = _sid()
    h.store.append(ORG, st, sid, [ev(), ev("boom"), ev()])
    seen: list[str] = []

    def handler(events):
        if any(e.event_type == "boom" for e in events) and not seen:
            seen.append("failed-once")
            raise RuntimeError("downstream down")
        seen.extend(e.event_id for e in events)

    runner = ExternalProjectionRunner(h.store, h.checkpoints, name, handler, stream_types=[st])
    first = runner.run_once(limit=10)
    assert first.status == "error" and h.checkpoints.get(name).last_error == "downstream down"
    assert h.checkpoints.get(name).cursor == Cursor()
    second = runner.run_once(limit=10)
    assert second.status == "ok" and second.applied == 3 and len(seen) == 4
    assert runner.run_once().status == "idle"


# -- execute -------------------------------------------------------------------------------------------------


def _evolve(state, e):
    return (state or 0) + e.data.get("n", 1)


def case_execute_folds_decides_appends(h: Harness):
    st, sid = _u("st"), _sid()
    h.store.append(ORG, st, sid, [ev(n=2), ev(n=3)])
    res = execute(h.store, ORG, st, sid, lambda s: [ev("added", n=s)], evolve=_evolve, initial=0)
    assert res.outcome.status == "ok" and res.state == 5 and res.attempts == 1
    assert h.store.load(ORG, st, sid).events[-1].data == {"n": 5}
    nothing = execute(h.store, ORG, st, sid, lambda s: [], evolve=_evolve, initial=0)
    assert nothing.outcome is None and nothing.state == 10


def case_execute_redecides_on_conflict_never_blind_reappends(h: Harness):
    st, sid = _u("st"), _sid()
    h.store.append(ORG, st, sid, [ev(n=1)])
    decided_on: list[int] = []

    def decide(state):
        decided_on.append(state)
        if len(decided_on) == 1:  # a concurrent writer lands between our load and our append
            h.store.append(ORG, st, sid, [ev(n=10)])
        return [ev("added", n=state)]

    res = execute(h.store, ORG, st, sid, decide, evolve=_evolve, initial=0)
    assert decided_on == [1, 11] and res.attempts == 2 and res.outcome.status == "ok"
    assert [e.data["n"] for e in h.store.load(ORG, st, sid).events] == [1, 10, 11]


def case_execute_gives_up_with_concurrency_conflict(h: Harness):
    st, sid = _u("st"), _sid()

    def always_raced(state):
        h.store.append(ORG, st, sid, [ev()])
        return [ev()]

    with pytest.raises(ConcurrencyConflict) as err:
        execute(h.store, ORG, st, sid, always_raced, evolve=_evolve, initial=0, max_attempts=3)
    assert err.value.attempts == 3 and err.value.current_version == 3


def case_execute_folds_upcast_events(h: Harness):
    st, sid = _u("st"), _sid()
    h.store.append(ORG, st, sid, [NewEvent("priced", {"cents": 100}, schema_version=1)])
    up = Upcasters().register("priced", 1, lambda d: {"amount": {"cents": d["cents"], "currency": "BRL"}})
    seen = []
    execute(h.store, ORG, st, sid, lambda s: seen.append(s) or [], evolve=lambda s, e: (e.schema_version, e.data),
            initial=None, upcasters=up)
    assert seen == [(2, {"amount": {"cents": 100, "currency": "BRL"}})]
    (stored,) = h.store.load(ORG, st, sid).events
    assert stored.schema_version == 1 and stored.data == {"cents": 100}  # the log itself is never rewritten


CASES = {name[len("case_"):]: fn for name, fn in globals().items() if name.startswith("case_")}
