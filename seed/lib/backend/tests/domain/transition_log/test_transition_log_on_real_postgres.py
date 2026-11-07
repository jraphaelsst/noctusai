"""The rendered guard + erasure path on a REAL Postgres (PGlite, PG16/WASM).

The conformance suite proves the RPC behaviour (compare-and-set, replay, seq, lazy first event, backfill)
through the Real adapter; this file proves what no adapter call can reach: that a direct UPDATE / DELETE /
TRUNCATE of the events table is refused even for the table owner, that the ONE erasure function deletes
under its transaction-local flag and logs it, that the flag never outlives the function, that the erasure
log is itself append-only, that no events FK cascades, and the privilege posture of every function.
Skips (visibly) when node / the PGlite install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.domain.transition_log import ERASURES_TABLE, transition_log_migration

from . import pglite_client
from .conformance import CARD, PARTICIPANT, SCHEMA, STATE_DDL

ORG = str(uuid.UUID(int=0xC3))


@pytest.fixture(scope="module")
def db():
    if not pglite_client.available():
        pytest.skip("PGlite unavailable (needs `node` and mcp/noctusai/node/node_modules)")
    client = pglite_client.PgliteClient(SCHEMA)
    client.exec(STATE_DDL)
    sql = transition_log_migration(CARD) + transition_log_migration(PARTICIPANT, header=False)
    client.exec(sql)
    client.exec(sql)  # forward-only + idempotent: a second apply is a no-op, never an error
    yield client
    client.close()


def _card(db) -> str:
    out = db.rpc(CARD.rpc("create"), {"p_org": ORG, "p_row": {"title": "x", "stage": "lead"}}).execute().data
    assert out["status"] == "ok", out
    return out["event"]["entity_id"]


@pytest.mark.parametrize("stmt", [
    "UPDATE {s}.card_events SET data = '{{\"x\": 1}}'::jsonb WHERE entity_id = '{e}'",
    "UPDATE {s}.card_events SET to_state = 'won' WHERE entity_id = '{e}'",
    "DELETE FROM {s}.card_events WHERE entity_id = '{e}'",
    "TRUNCATE {s}.card_events",
])
def test_direct_mutation_of_history_is_refused(db, stmt):
    e = _card(db)
    with pytest.raises(pglite_client.PgliteError, match="card_events is append-only") as err:
        db.exec(stmt.format(s=SCHEMA, e=e))
    assert err.value.code == "TL001"
    assert db.query(f"SELECT count(*)::int AS n FROM {SCHEMA}.card_events WHERE entity_id = '{e}'")[0]["n"] == 1


def test_a_caller_cannot_borrow_the_erasure_flag_of_another_aggregate(db):
    e = _card(db)
    with pytest.raises(pglite_client.PgliteError, match="append-only"):
        db.exec(f"BEGIN; SELECT set_config('{PARTICIPANT.erase_guc}', 'on', true); "
                f"DELETE FROM {SCHEMA}.card_events WHERE entity_id = '{e}'; COMMIT;")
    db.exec("ROLLBACK")


def test_erasure_deletes_the_subject_under_its_flag_and_logs_it(db):
    e = _card(db)
    db.rpc(CARD.rpc("transition"), {"p_org": ORG, "p_key": {"entity_id": e}, "p_from": "lead", "p_to": "won"}).execute()
    keep = _card(db)
    out = db.rpc(CARD.rpc("erase_subject"), {"p_org": ORG, "p_subject": {"entity_id": e},
                                             "p_reason": "LGPD art. 18 VI", "p_actor_id": str(uuid.UUID(int=5))}).execute().data
    assert out == {"status": "ok", "deleted": 2}
    assert db.query(f"SELECT count(*)::int AS n FROM {SCHEMA}.card_events WHERE entity_id = '{e}'")[0]["n"] == 0
    assert db.query(f"SELECT count(*)::int AS n FROM {SCHEMA}.card_events WHERE entity_id = '{keep}'")[0]["n"] == 1
    (log,) = db.query(f"SELECT aggregate, subject, events_deleted, reason FROM {SCHEMA}.{ERASURES_TABLE} "
                      f"WHERE subject->>'entity_id' = '{e}'")
    assert log == {"aggregate": "card", "subject": {"entity_id": e}, "events_deleted": 2, "reason": "LGPD art. 18 VI"}
    # the flag is transaction-local AND switched off before the function returns
    rows = db.query(f"SELECT {SCHEMA}.{CARD.rpc('erase_subject')}('{ORG}', '{{\"entity_id\": \"{keep}\"}}'::jsonb, 'r', NULL) AS r, "
                    f"current_setting('{CARD.erase_guc}', true) AS flag")
    assert rows[0]["r"]["deleted"] == 1 and rows[0]["flag"] in ("off", "", None)
    # erasure lets the product delete the state row afterwards (no history left, no cascade needed)
    db.exec(f"DELETE FROM {SCHEMA}.cards WHERE id = '{e}'")


def test_no_cascade_a_state_row_with_history_cannot_be_deleted(db):
    e = _card(db)
    with pytest.raises(pglite_client.PgliteError, match="card_events_entity_fk"):
        db.exec(f"DELETE FROM {SCHEMA}.cards WHERE id = '{e}'")
    fk = db.query(f"SELECT confdeltype, condeferrable FROM pg_constraint WHERE conname = 'card_events_entity_fk'")[0]
    assert fk == {"confdeltype": "a", "condeferrable": True}  # NO ACTION, deferrable for the guard probes


def test_the_erasure_log_is_append_only(db):
    db.exec(f"INSERT INTO {SCHEMA}.{ERASURES_TABLE} (org_id, aggregate, subject, events_deleted, reason) "
            f"VALUES ('{ORG}', 'card', '{{}}'::jsonb, 0, 'probe')")
    for stmt in (f"UPDATE {SCHEMA}.{ERASURES_TABLE} SET reason = 'x'", f"DELETE FROM {SCHEMA}.{ERASURES_TABLE}",
                 f"TRUNCATE {SCHEMA}.{ERASURES_TABLE}"):
        with pytest.raises(pglite_client.PgliteError, match=f"{ERASURES_TABLE} is append-only"):
            db.exec(stmt)


def test_the_checks_backstop_direct_inserts(db):
    e = _card(db)
    ins = (f"INSERT INTO {SCHEMA}.card_events (org_id, entity_id, seq, from_state, to_state, event_type, data, actor_kind) "
           f"VALUES ('{ORG}', '{e}', {{seq}}, {{frm}}, 'x', '{{typ}}', {{data}}, '{{kind}}')")
    bad = {
        "card_events_creation_first": dict(seq=1, frm="'lead'", typ="transitioned", data="'{}'", kind="user"),
        "card_events_seq_positive": dict(seq=0, frm="'lead'", typ="transitioned", data="'{}'", kind="user"),
        "card_events_event_type_shape": dict(seq=9, frm="'lead'", typ="Moved", data="'{}'", kind="user"),
        "card_events_data_object": dict(seq=9, frm="'lead'", typ="moved", data="'[1]'", kind="user"),
        "card_events_actor_kind": dict(seq=9, frm="'lead'", typ="moved", data="'{}'", kind="robot"),
        "uq_card_events_entity_seq": dict(seq=1, frm="NULL", typ="created", data="'{}'", kind="user"),
    }
    for constraint, values in bad.items():
        with pytest.raises(pglite_client.PgliteError, match=constraint):
            db.exec(ins.format(**values))


def test_function_posture(db):
    rows = db.query(f"""
        SELECT p.proname, p.prosecdef, p.proconfig::text AS cfg,
               has_function_privilege('anon', p.oid, 'EXECUTE') AS anon,
               has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authed,
               has_function_privilege('service_role', p.oid, 'EXECUTE') AS svc
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = '{SCHEMA}' AND p.proname LIKE 'card\\_%' AND p.prokind = 'f'
           AND p.prorettype <> 'trigger'::regtype""")
    assert {r["proname"] for r in rows} == {CARD.rpc(n) for n in ("create", "record_created", "transition", "history",
                                                                   "erase_subject", "backfill_initial_state")}
    for r in rows:
        assert r["prosecdef"] and f"search_path=pg_catalog, {SCHEMA}, pg_temp" in r["cfg"], r
        assert not r["anon"] and not r["authed"] and r["svc"], r
    tier = db.query(f"SELECT obj_description('{SCHEMA}.card_events'::regclass, 'pg_class') AS t")[0]["t"]
    assert tier == "tier:org"
    assert not db.query(f"SELECT has_table_privilege('authenticated', '{SCHEMA}.card_events', 'SELECT') AS x")[0]["x"]


def test_transition_locks_the_state_row(db):
    body = db.query(f"SELECT prosrc FROM pg_proc WHERE proname = '{CARD.rpc('transition')}'")[0]["prosrc"]
    assert "FOR UPDATE" in body  # concurrent transitions serialise on the state row (PGlite is single-connection)
