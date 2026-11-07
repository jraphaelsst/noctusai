"""Fake and Real run the SAME conformance suite (`conformance.py`); the Real on a live PGlite with the rendered SQL."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.event_store import (
    CheckpointStore,
    EventStore,
    EventStoreConfig,
    FakeEventStore,
    RealSupabaseEventStore,
    event_store_migration,
    make_checkpoint_store,
    make_event_store,
)
from noctusai_lib.testing.pglite import PgliteClient, pglite_available

from .conformance import CASES, Harness

SCHEMA = "es_conf"

# A projection handler: counts events per stream into the target; any `boom` event fails the batch.
COUNTER_FN = f"""
CREATE FUNCTION {SCHEMA}.es_conf_count(p_events jsonb, p_target regclass) RETURNS void
LANGUAGE plpgsql SET search_path = pg_catalog, {SCHEMA}, pg_temp AS $$
DECLARE e jsonb;
BEGIN
  FOR e IN SELECT * FROM jsonb_array_elements(p_events) LOOP
    IF e->>'event_type' = 'boom' THEN RAISE EXCEPTION 'boom event'; END IF;
    EXECUTE format('INSERT INTO %s AS t (stream_id, n) VALUES ($1, 1) '
                   'ON CONFLICT (stream_id) DO UPDATE SET n = t.n + 1', p_target)
      USING (e->>'stream_id')::uuid;
  END LOOP;
END $$;
"""


@pytest.fixture(scope="module")
def pglite():
    if not pglite_available():
        pytest.skip("PGlite unavailable (needs `node` and mcp/noctusai/node/node_modules) -- the Real leg did not run")
    client = PgliteClient(SCHEMA)
    client.exec(f"CREATE SCHEMA {SCHEMA}")
    client.exec(event_store_migration(EventStoreConfig(SCHEMA)))
    client.exec(COUNTER_FN)
    yield client
    client.close()


def _count(events, table):
    for e in events:
        if e.event_type == "boom":
            raise RuntimeError("boom event")
        table[e.stream_id] = table.get(e.stream_id, 0) + 1


def _fake() -> Harness:
    store = make_event_store("fake")
    assert isinstance(store, FakeEventStore)
    cps = make_checkpoint_store("fake", store=store)

    def install(name, mode, target, types):
        store.create_table(target)
        return store.register_projection(name, handler=_count, target=target, stream_types=types, mode=mode)

    def corrupt(target):
        for k in store.tables[target]:
            store.tables[target][k] = 999

    return Harness("fake", store, cps, install, lambda t: store.read_model(t), corrupt, lambda t: t in store.tables)


def _real(client) -> Harness:
    store = make_event_store("supabase", client=client)
    assert isinstance(store, RealSupabaseEventStore)
    cps = make_checkpoint_store("supabase", client=client)

    def install(name, mode, target, types):
        client.exec(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{target} (stream_id uuid PRIMARY KEY, n int NOT NULL)")
        return store.register_projection(name, handler="es_conf_count", target=target, stream_types=types, mode=mode)

    def counts(target):
        return {r["stream_id"]: r["n"] for r in client.query(f"SELECT stream_id::text, n FROM {SCHEMA}.{target}")}

    def exists(target):
        return client.query("SELECT to_regclass($1) IS NOT NULL AS e", [f"{SCHEMA}.{target}"])[0]["e"]

    return Harness("real", store, cps, install, counts,
                   lambda t: client.exec(f"UPDATE {SCHEMA}.{t} SET n = 999"), exists)


def test_factories_satisfy_the_protocols():
    assert isinstance(make_event_store("fake"), EventStore)
    assert isinstance(make_checkpoint_store("fake"), CheckpointStore)
    with pytest.raises(ValueError):
        make_event_store("supabase")
    with pytest.raises(ValueError):
        make_event_store("nope")  # type: ignore[arg-type]


@pytest.mark.parametrize("case", sorted(CASES))
def test_fake(case):
    CASES[case](_fake())


@pytest.mark.parametrize("case", sorted(CASES))
def test_real_on_pglite(case, pglite):
    CASES[case](_real(pglite))
