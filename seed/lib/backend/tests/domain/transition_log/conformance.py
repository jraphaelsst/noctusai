"""ONE behaviour suite for every `TransitionLog` implementation (Fake and Real alike).

`test_conformance.py` runs it against `FakeTransitionLog` and against `SupabaseTransitionLog` over a live
PGlite (real Postgres, the rendered SQL) -- so the Fake is held to exactly what the database does.
Each case takes a `Harness`: the log under test, plus a way to insert a state row OUTSIDE the log (a legacy
entity) and to read the current state back.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

import pytest

from noctusai_lib.domain.transition_log import (
    KeyColumn,
    TransitionLog,
    TransitionLogConfig,
)

SCHEMA = "tlc"
ORG = str(uuid.UUID(int=0xA1))
OTHER_ORG = str(uuid.UUID(int=0xB2))

CARD = TransitionLogConfig(schema=SCHEMA, aggregate="card", state_table="cards", state_column="stage")
PARTICIPANT = TransitionLogConfig(
    schema=SCHEMA, aggregate="participant", state_table="participants", state_column="status",
    key=(KeyColumn("thread_id"), KeyColumn("agent_id", "text")),
    state_updated_at_column=None, state_created_at_column=None,
)
CONFIGS = {"card": CARD, "participant": PARTICIPANT}

#: The state tables the suite runs against (the Real's database; the Fake gets the same column sets).
STATE_DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE TABLE {SCHEMA}.cards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, title text NOT NULL DEFAULT '',
    stage text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE {SCHEMA}.participants (
    org_id uuid NOT NULL, thread_id uuid NOT NULL, agent_id text NOT NULL, status text NOT NULL,
    PRIMARY KEY (thread_id, agent_id));
"""
STATE_COLUMNS = {
    "card": ("id", "org_id", "title", "stage", "created_at", "updated_at"),
    "participant": ("org_id", "thread_id", "agent_id", "status"),
}
STATE_DEFAULTS = {"card": {"title": ""}, "participant": {}}


@dataclass
class Harness:
    name: str
    cfg: TransitionLogConfig
    log: TransitionLog
    insert_state: Callable[[str, dict], None]
    state_of: Callable[[str, dict], Optional[Any]]


def new_row(h: Harness, state: str, **extra: Any) -> dict:
    if h.name == "card":
        return {"id": str(uuid.uuid4()), "title": "Apto 302", "stage": state, **extra}
    return {"thread_id": str(uuid.uuid4()), "agent_id": "julia", "status": state, **extra}


def key_of(h: Harness, row_or_event: dict) -> dict:
    if h.name == "card":
        return {"entity_id": row_or_event.get("entity_id") or row_or_event["id"]}
    return {"thread_id": row_or_event["thread_id"], "agent_id": row_or_event["agent_id"]}


def _created(h: Harness, state: str = "lead", **kw: Any) -> tuple[dict, dict]:
    out = h.log.create(ORG, new_row(h, state), **kw)
    assert out.status == "ok", out
    return out.event, key_of(h, out.event)


# -- creation ----------------------------------------------------------------------------------------------------

def case_create_writes_state_and_seq1_created(h: Harness) -> None:
    ev, key = _created(h)
    assert (ev["seq"], ev["event_type"], ev["from_state"], ev["to_state"]) == (1, "created", None, "lead")
    assert set(ev) == set(h.cfg.event_columns)
    assert ev["org_id"] == ORG and ev["actor_kind"] == "user" and ev["data"] == {}
    assert h.state_of(ORG, key) == "lead"
    assert [e["id"] for e in h.log.history(ORG, key)] == [ev["id"]]


def case_create_replays_on_the_same_event_id(h: Harness) -> None:
    eid = str(uuid.uuid4())
    row = new_row(h, "lead")
    first = h.log.create(ORG, row, event_id=eid, data={"via": "form"})
    again = h.log.create(ORG, row, event_id=eid, data={"via": "form"})
    assert first.status == "ok" and again.status == "replayed"
    assert again.event["id"] == first.event["id"] == eid
    assert len(h.log.history(ORG, key_of(h, first.event))) == 1


def case_create_with_a_foreign_event_id_conflicts(h: Harness) -> None:
    ev, key = _created(h)
    tr = h.log.transition(ORG, key, from_state="lead", to_state="won")
    assert tr.status == "ok"
    out = h.log.create(ORG, new_row(h, "lead"), event_id=tr.event["id"])
    assert (out.status, out.code) == ("refused", "idempotency_conflict")
    other_org = h.log.create(OTHER_ORG, new_row(h, "lead"), event_id=ev["id"])
    assert (other_org.status, other_org.code) == ("refused", "idempotency_conflict")


def case_create_refuses_a_bad_row(h: Harness) -> None:
    state_col = h.cfg.state_column
    missing_state = {k: v for k, v in new_row(h, "lead").items() if k != state_col}
    assert h.log.create(ORG, missing_state).code == "invalid_row"
    assert h.log.create(ORG, new_row(h, "lead", no_such_column=1)).code == "invalid_row"


def case_create_refuses_a_duplicate_entity(h: Harness) -> None:
    row = new_row(h, "lead")
    assert h.log.create(ORG, row).status == "ok"
    out = h.log.create(ORG, row)
    assert (out.status, out.code) == ("refused", "duplicate")


def case_record_created_for_a_row_inserted_elsewhere(h: Harness) -> None:
    row = new_row(h, "lead")
    h.insert_state(ORG, row)
    key = key_of(h, row)
    out = h.log.record_created(ORG, key, actor_kind="system", data={"source": "import"})
    assert out.status == "ok" and out.event["seq"] == 1 and out.event["event_type"] == "created"
    assert out.event["actor_kind"] == "system" and out.event["data"] == {"source": "import"}
    again = h.log.record_created(ORG, key)
    assert (again.status, again.code) == ("refused", "history_exists")
    assert h.log.record_created(ORG, key_of(h, new_row(h, "x"))).code == "not_found"


# -- transitions ----------------------------------------------------------------------------------------------------

def case_transition_compare_and_set(h: Harness) -> None:
    ev, key = _created(h)
    out = h.log.transition(ORG, key, from_state="lead", to_state="visit", event_type="stage_moved",
                           data={"by": "kanban"}, actor_id=str(uuid.UUID(int=7)), actor_kind="agent")
    assert out.status == "ok"
    assert (out.event["seq"], out.event["from_state"], out.event["to_state"]) == (2, "lead", "visit")
    assert out.event["event_type"] == "stage_moved" and out.event["actor_kind"] == "agent"
    assert out.event["actor_id"] == str(uuid.UUID(int=7)) and out.event["data"] == {"by": "kanban"}
    assert h.state_of(ORG, key) == "visit"


def case_stale_from_state_is_refused_and_writes_nothing(h: Harness) -> None:
    ev, key = _created(h)
    assert h.log.transition(ORG, key, from_state="lead", to_state="visit").status == "ok"
    out = h.log.transition(ORG, key, from_state="lead", to_state="won")
    assert (out.status, out.code, out.current_state) == ("refused", "stale_state", "visit")
    assert h.state_of(ORG, key) == "visit"
    assert [e["seq"] for e in h.log.history(ORG, key)] == [1, 2]


def case_transition_replays_on_the_same_event_id(h: Harness) -> None:
    ev, key = _created(h)
    eid = str(uuid.uuid4())
    first = h.log.transition(ORG, key, from_state="lead", to_state="visit", event_id=eid)
    retry = h.log.transition(ORG, key, from_state="lead", to_state="visit", event_id=eid)  # the retried request
    assert first.status == "ok" and retry.status == "replayed" and retry.event["id"] == eid
    assert [e["seq"] for e in h.log.history(ORG, key)] == [1, 2]
    conflict = h.log.transition(ORG, key, from_state="visit", to_state="won", event_id=eid)
    assert (conflict.status, conflict.code) == ("refused", "idempotency_conflict")


def case_transition_on_a_missing_or_foreign_entity(h: Harness) -> None:
    ev, key = _created(h)
    assert h.log.transition(ORG, key_of(h, new_row(h, "x")), from_state="lead", to_state="won").code == "not_found"
    assert h.log.transition(OTHER_ORG, key, from_state="lead", to_state="won").code == "not_found"
    assert h.log.history(OTHER_ORG, key) == []


def case_input_refusals(h: Harness) -> None:
    ev, key = _created(h)
    t = h.log.transition
    assert t(ORG, key, from_state="lead", to_state="x", actor_kind="synthetic").code == "invalid_actor_kind"
    assert t(ORG, key, from_state="lead", to_state="x", actor_kind="robot").code == "invalid_actor_kind"
    assert t(ORG, key, from_state="lead", to_state="x", data=[1, 2]).code == "invalid_data"
    assert t(ORG, key, from_state="lead", to_state="x", event_type="Not Valid").code == "invalid_event_type"
    assert t(ORG, key, from_state="lead", to_state="x", event_type="created").code == "reserved_event_type"
    assert t(ORG, key, from_state="lead", to_state="x", event_type="imported_initial_state").code == "reserved_event_type"
    assert h.log.create(ORG, new_row(h, "lead"), actor_kind="synthetic").code == "invalid_actor_kind"
    assert h.state_of(ORG, key) == "lead" and len(h.log.history(ORG, key)) == 1


def case_malformed_keys_raise_before_any_io(h: Harness) -> None:
    with pytest.raises(ValueError):
        h.log.transition(ORG, {"nope": 1}, from_state="a", to_state="b")
    with pytest.raises(ValueError):
        h.log.history(ORG, {})
    with pytest.raises(ValueError):
        h.log.erase_subject(ORG, {"nope": 1}, reason="x")


def case_seq_is_contiguous_and_chains(h: Harness) -> None:
    ev, key = _created(h, "s0")
    for i in range(1, 6):
        assert h.log.transition(ORG, key, from_state=f"s{i - 1}", to_state=f"s{i}").status == "ok"
    hist = h.log.history(ORG, key)
    assert [e["seq"] for e in hist] == [1, 2, 3, 4, 5, 6]
    assert all(b["from_state"] == a["to_state"] for a, b in zip(hist, hist[1:]))
    assert h.state_of(ORG, key) == "s5"


# -- legacy entities: lazy first event + backfill ------------------------------------------------------------------

def case_first_transition_of_a_legacy_entity_logs_its_initial_state(h: Harness) -> None:
    row = new_row(h, "lead")
    h.insert_state(ORG, row)
    key = key_of(h, row)
    out = h.log.transition(ORG, key, from_state="lead", to_state="won")
    assert out.status == "ok" and out.event["seq"] == 2
    first, second = h.log.history(ORG, key)
    assert (first["seq"], first["event_type"], first["from_state"], first["to_state"]) == (1, "imported_initial_state", None, "lead")
    assert first["actor_kind"] == "synthetic" and first["data"]["synthetic"] is True
    assert second["id"] == out.event["id"]


def case_backfill_writes_one_synthetic_event_per_entity_without_history(h: Harness) -> None:
    org, other_org = str(uuid.uuid4()), str(uuid.uuid4())  # fresh orgs: the Real's database is shared by every case
    legacy = [new_row(h, "lead"), new_row(h, "won")]
    for row in legacy:
        h.insert_state(org, row)
    other = new_row(h, "lead")
    h.insert_state(other_org, other)
    had = h.log.create(org, new_row(h, "lead"))  # already has history: untouched
    assert h.log.backfill_initial_state(org) == 2
    assert h.log.backfill_initial_state(org) == 0  # idempotent
    for row in legacy:
        (ev,) = h.log.history(org, key_of(h, row))
        assert (ev["seq"], ev["event_type"], ev["to_state"]) == (1, "imported_initial_state", row[h.cfg.state_column])
        assert ev["actor_kind"] == "synthetic" and ev["data"] == {"synthetic": True, "source": "transition_log_backfill"}
        assert ev["from_state"] is None and ev["actor_id"] is None
    assert len(h.log.history(org, key_of(h, had.event))) == 1
    assert h.log.history(other_org, key_of(h, other)) == []
    assert h.log.backfill_initial_state() >= 1  # NULL org = every org
    assert [e["event_type"] for e in h.log.history(other_org, key_of(h, other))] == ["imported_initial_state"]


# -- erasure ------------------------------------------------------------------------------------------------------

def case_erase_subject_deletes_only_the_subject(h: Harness) -> None:
    ev, key = _created(h)
    h.log.transition(ORG, key, from_state="lead", to_state="won")
    keep_ev, keep_key = _created(h)
    assert h.log.erase_subject(OTHER_ORG, key, reason="LGPD art. 18 VI").deleted == 0
    out = h.log.erase_subject(ORG, key, reason="LGPD art. 18 VI", actor_id=str(uuid.UUID(int=9)))
    assert (out.status, out.deleted) == ("ok", 2)
    assert h.log.history(ORG, key) == []
    assert len(h.log.history(ORG, keep_key)) == 1
    assert h.log.erase_subject(ORG, key, reason="   ").code == "invalid_reason"


def case_erase_by_a_partial_key(h: Harness) -> None:
    if len(h.cfg.key) < 2:  # a single-column key has no partial subset: an empty subject is a caller bug
        with pytest.raises(ValueError):
            h.log.erase_subject(ORG, {}, reason="x")
        return
    thread = str(uuid.uuid4())
    for agent in ("julia", "monica"):
        assert h.log.create(ORG, {"thread_id": thread, "agent_id": agent, "status": "active"}).status == "ok"
    survivor_ev, survivor = _created(h)
    out = h.log.erase_subject(ORG, {"thread_id": thread}, reason="lead erased")
    assert out.deleted == 2
    assert h.log.history(ORG, {"thread_id": thread, "agent_id": "julia"}) == []
    assert len(h.log.history(ORG, survivor)) == 1


CASES: dict[str, Callable[[Harness], None]] = {
    name[len("case_"):]: fn for name, fn in sorted(globals().items()) if name.startswith("case_") and callable(fn)
}
