"""The rendered SQL's posture on a REAL Postgres (PGlite, PG16/WASM): what no adapter call can reach.

Direct UPDATE / DELETE / TRUNCATE / INSERT of the log are refused even for the owner; the migration applies twice
(forward-only, idempotent); RLS is on for every table; no foreign key ever cascades a delete INTO es_events;
EXECUTE is revoked from PUBLIC / anon / authenticated on every function and granted to service_role on the
RPCs only; LGPD -- `pii` / `subject_id` stay NULL. Skips (visibly) when node / PGlite is unavailable.
"""
from __future__ import annotations

import uuid

import pytest

from noctusai_lib.domain.event_store import (
    APPEND_ONLY_SQLSTATE,
    MIGRATION_HEADER,
    RPC_NAMES,
    EventStoreConfig,
    event_store_migration,
)
from noctusai_lib.domain.sql_templates import truncate_guard_sql
from noctusai_lib.testing.pglite import PgliteClient, PgliteError, pglite_available

S = "es_post"
ORG = str(uuid.UUID(int=0xD1))
TABLES = ("es_streams", "es_events", "es_projections", "es_checkpoints")


@pytest.fixture(scope="module")
def db():
    if not pglite_available():
        pytest.skip("PGlite unavailable (needs `node` and mcp/noctusai/node/node_modules) -- did not run")
    client = PgliteClient(S)
    client.exec(f"CREATE SCHEMA {S}")
    sql = event_store_migration(EventStoreConfig(S))
    client.exec(sql)
    client.exec(sql)  # forward-only + idempotent
    yield client
    client.close()


def _stream(db) -> str:
    sid = str(uuid.uuid4())
    out = db.rpc("es_append", {"p_org": ORG, "p_stream_type": "post", "p_stream_id": sid, "p_expected_version": 0,
                               "p_events": [{"event_type": "made"}]}).execute().data
    assert out["status"] == "ok", out
    return sid


def test_header_marks_the_file_as_generated():
    assert event_store_migration(EventStoreConfig("x")).startswith(MIGRATION_HEADER)


@pytest.mark.parametrize("stmt", [
    "UPDATE {s}.es_events SET data = '{{\"x\": 1}}'::jsonb WHERE stream_id = '{sid}'",
    "DELETE FROM {s}.es_events WHERE stream_id = '{sid}'",
    "TRUNCATE {s}.es_events CASCADE",
    "INSERT INTO {s}.es_events (event_id, org_id, stream_type, stream_id, version, event_type) "
    "VALUES (gen_random_uuid(), '{org}', 'post', '{sid}', 2, 'forged')",
    "UPDATE {s}.es_streams SET version = 9 WHERE stream_id = '{sid}'",
    "DELETE FROM {s}.es_streams WHERE stream_id = '{sid}'",
    "TRUNCATE {s}.es_streams CASCADE",
])
def test_direct_writes_to_the_log_are_refused(db, stmt):
    sid = _stream(db)
    with pytest.raises(PgliteError) as err:
        db.exec(stmt.format(s=S, sid=sid, org=ORG))
    assert err.value.code == APPEND_ONLY_SQLSTATE
    assert db.query(f"SELECT count(*)::int AS n FROM {S}.es_events WHERE stream_id = $1", [sid])[0]["n"] == 1


def test_the_append_flag_never_outlives_es_append(db):
    _stream(db)
    rows = db.query(f"SELECT current_setting('{EventStoreConfig(S).append_guc}', true) AS flag")
    assert rows[0]["flag"] in ("off", "", None)


def test_rls_is_on_for_every_table(db):
    rows = db.query("SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = $1::regnamespace "
                    "AND relkind = 'r'", [S])
    assert {r["relname"]: r["relrowsecurity"] for r in rows if r["relname"] in TABLES} == {t: True for t in TABLES}


def test_no_foreign_key_cascades_into_the_log(db):
    rows = db.query("SELECT conname, confdeltype FROM pg_constraint WHERE contype = 'f' AND conrelid = $1::regclass",
                    [f"{S}.es_events"])
    assert rows and all(r["confdeltype"] != "c" for r in rows)


def test_execute_privileges(db):
    rows = db.query("""
        SELECT p.proname,
               has_function_privilege('anon', p.oid, 'EXECUTE') AS anon,
               has_function_privilege('authenticated', p.oid, 'EXECUTE') AS auth,
               has_function_privilege('service_role', p.oid, 'EXECUTE') AS svc,
               p.prosecdef AS definer, p.prorettype = 'trigger'::regtype AS is_trigger,
               coalesce(array_to_string(p.proconfig, ','), '') AS config
        FROM pg_proc p WHERE p.pronamespace = $1::regnamespace""", [S])
    by = {r["proname"]: r for r in rows}
    assert set(RPC_NAMES) <= set(by)
    for name, r in by.items():
        assert not r["anon"] and not r["auth"], f"{name} executable by an API role"
        if not r["is_trigger"]:  # a trigger function cannot be called directly; the guard helper grants it anyway
            assert r["svc"] == (name in RPC_NAMES), f"{name}: service_role grant must match RPC_NAMES"
        if r["definer"]:
            assert "search_path=" in r["config"], f"{name}: SECURITY DEFINER without a pinned search_path"
    for name in RPC_NAMES:
        assert by[name]["definer"], f"{name} must be SECURITY DEFINER"


def test_events_never_carry_personal_data_columns(db):
    sid = _stream(db)
    (row,) = db.query(f"SELECT pii, subject_id FROM {S}.es_events WHERE stream_id = $1", [sid])
    assert row == {"pii": None, "subject_id": None}
    out = db.rpc("es_append", {"p_org": ORG, "p_stream_type": "post", "p_stream_id": sid, "p_expected_version": -1,
                               "p_events": [{"event_type": "made", "pii": {"name": "x"}}]}).execute().data
    assert out == {"status": "refused", "code": "pii_disabled"}


def test_read_all_returns_only_settled_events_in_cursor_order(db):
    sid = _stream(db)
    out = db.rpc("es_read_all", {"p_stream_types": ["post"]}).execute().data
    cursors = [(int(e["tx_id"]), e["global_position"]) for e in out["events"]]
    assert cursors == sorted(cursors) and any(e["stream_id"] == sid for e in out["events"])


def test_truncate_guard_helper_renders_a_statement_trigger_that_refuses(db):
    db.exec(f"CREATE TABLE {S}.tg_probe (id int); ALTER TABLE {S}.tg_probe ENABLE ROW LEVEL SECURITY;")
    sql = truncate_guard_sql(schema=S, table="tg_probe", errcode="TG001")
    db.exec(sql)
    db.exec(sql)  # idempotent
    with pytest.raises(PgliteError, match="tg_probe") as err:
        db.exec(f"TRUNCATE {S}.tg_probe")
    assert err.value.code == "TG001"
