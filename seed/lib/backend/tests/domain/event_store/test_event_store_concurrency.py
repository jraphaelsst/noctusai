"""Two-connection proofs on a REAL Postgres server (PGlite is one connection and cannot show them).

* `read_all` never skips a late-committing writer -- in BOTH orderings (early position + late commit; early xid +
  late position) -- because it only returns events with `tx_id < pg_snapshot_xmin(pg_current_snapshot())` and
  pages by the `(tx_id, global_position)` pair;
* two concurrent appends at the same expected version: the second waits on the stream lock, then answers
  `conflict` (never two events at one version);
* a second concurrent async-projection runner answers `busy` (checkpoint row `FOR UPDATE SKIP LOCKED`), and the
  read model ends exactly-once.

Server: `noctusai_lib.testing.pgserver.disposable_postgres` (NOCTUS_TEST_PG_DSN, or initdb from local / CI
Postgres binaries). Skips VISIBLY when neither exists -- a skip is not a pass.
"""
from __future__ import annotations

import json
import threading
import uuid

import pytest

from noctusai_lib.domain.event_store import EventStoreConfig, event_store_migration
from noctusai_lib.testing.pgserver import SUPABASE_ROLE_STUBS, disposable_postgres

psycopg2 = pytest.importorskip("psycopg2")

S = "es_conc"
ORG = str(uuid.UUID(int=0xC1))
START = ("0", 0)


@pytest.fixture(scope="module")
def dsn():
    with disposable_postgres() as found:
        if found is None:
            pytest.skip("no Postgres server (set NOCTUS_TEST_PG_DSN or install initdb/pg_ctl) -- "
                        "the two-connection proofs did not run")
        setup = psycopg2.connect(found)
        setup.autocommit = True
        with setup.cursor() as c:
            c.execute(f"DROP SCHEMA IF EXISTS {S} CASCADE")
            c.execute(SUPABASE_ROLE_STUBS)
            c.execute(f"CREATE SCHEMA {S}")
            c.execute(event_store_migration(EventStoreConfig(S)))
            c.execute(f"""
CREATE TABLE {S}.counts (stream_id uuid PRIMARY KEY, n int NOT NULL);
CREATE FUNCTION {S}.count_h(p_events jsonb, p_target regclass) RETURNS void LANGUAGE plpgsql AS $$
DECLARE e jsonb; BEGIN
  FOR e IN SELECT * FROM jsonb_array_elements(p_events) LOOP
    EXECUTE format('INSERT INTO %s AS t (stream_id, n) VALUES ($1, 1) ON CONFLICT (stream_id) DO UPDATE SET n = t.n + 1',
                   p_target) USING (e->>'stream_id')::uuid;
  END LOOP; END $$;""")
        setup.close()
        yield found


def _conn(dsn, autocommit=False):
    c = psycopg2.connect(dsn)
    c.autocommit = autocommit
    return c


def _one(conn, sql, *args):
    with conn.cursor() as c:
        c.execute(sql, args)
        return c.fetchone()[0]


def _append(conn, stream_type, sid, expected=-1):
    return _one(conn, f"SELECT {S}.es_append(%s, %s, %s, %s, %s::jsonb)",
                ORG, stream_type, sid, expected, json.dumps([{"event_type": "happened"}]))


def _read_all(conn, after, stream_type):
    return _one(conn, f"SELECT {S}.es_read_all(%s::xid8, %s, 500, ARRAY[%s]::text[])", after[0], after[1], stream_type)


def _drain(reader, stream_type, cursor=START):
    """A reader that keeps a (tx_id, position) cursor -- exactly what a projection does."""
    seen = []
    while True:
        out = _read_all(reader, cursor, stream_type)
        if not out["events"]:
            return seen, cursor
        seen += [e["global_position"] for e in out["events"]]
        cursor = (str(out["next"]["tx_id"]), out["next"]["position"])


def test_late_commit_with_an_earlier_position_is_never_skipped(dsn):
    st = f"lc_{uuid.uuid4().hex[:8]}"
    a, b, reader = _conn(dsn), _conn(dsn, True), _conn(dsn, True)
    try:
        slow = _append(a, st, str(uuid.uuid4()))["positions"][0]   # the LOWER position, transaction left open
        fast = _append(b, st, str(uuid.uuid4()))["positions"][0]   # a higher position, committed first
        assert slow < fast
        seen, cursor = _drain(reader, st)
        assert seen == []  # the committed fast event is not settled while an older writer is open
        a.commit()
        more, _ = _drain(reader, st, cursor)
        assert sorted(seen + more) == [slow, fast]  # nothing skipped
    finally:
        for c in (a, b, reader):
            c.close()


def test_early_xid_with_a_later_position_is_never_skipped(dsn):
    st = f"lx_{uuid.uuid4().hex[:8]}"
    a, b, reader = _conn(dsn), _conn(dsn, True), _conn(dsn, True)
    try:
        _one(a, "SELECT pg_current_xact_id()::text")                # A takes the OLDER xid first
        first = _append(b, st, str(uuid.uuid4()))["positions"][0]   # B: lower position, newer xid, commits
        late = _append(a, st, str(uuid.uuid4()))["positions"][0]    # A: higher position, older xid
        assert late > first
        assert _drain(reader, st)[0] == []  # B not settled while A is open
        a.commit()
        seen, _ = _drain(reader, st)
        # settled order is (tx_id, position): A's event first although its position is higher; none skipped
        assert seen == [late, first]
    finally:
        for c in (a, b, reader):
            c.close()


def test_concurrent_appends_at_one_version_conflict_after_the_lock(dsn):
    st, sid = f"cv_{uuid.uuid4().hex[:8]}", str(uuid.uuid4())
    a, b = _conn(dsn), _conn(dsn, True)
    result = {}
    try:
        assert _append(a, st, sid, expected=0)["status"] == "ok"   # holds the stream row lock
        t = threading.Thread(target=lambda: result.update(out=_append(b, st, sid, expected=0)))
        t.start()
        t.join(0.5)
        assert t.is_alive()  # B waits on the stream lock instead of reading a stale version
        a.commit()
        t.join(10)
        assert result["out"] == {"status": "conflict", "current_version": 1}
    finally:
        a.close()
        b.close()


def test_second_async_runner_is_busy_and_the_read_model_is_exactly_once(dsn):
    st, sid, proj = f"pj_{uuid.uuid4().hex[:8]}", str(uuid.uuid4()), f"p_{uuid.uuid4().hex[:8]}"
    admin = _conn(dsn, True)
    try:
        reg = _one(admin, f"SELECT {S}.es_register_projection(%s, 'count_h', 'counts', ARRAY[%s], 'async')", proj, st)
        assert reg["status"] == "ok"
        for _ in range(3):
            _append(admin, st, sid)
        w1, w2 = _conn(dsn), _conn(dsn, True)
        try:
            run1 = _one(w1, f"SELECT {S}.es_run_projection(%s, 500)", proj)   # holds the checkpoint row lock
            assert run1["status"] == "ok" and run1["applied"] == 3
            assert _one(w2, f"SELECT {S}.es_run_projection(%s, 500)", proj)["status"] == "busy"
            w1.commit()
            assert _one(w2, f"SELECT {S}.es_run_projection(%s, 500)", proj)["status"] == "idle"
        finally:
            w1.close()
            w2.close()
        assert _one(admin, f"SELECT n FROM {S}.counts WHERE stream_id = %s", sid) == 3
    finally:
        admin.close()
