"""noctus.dev.projection_rebuild -- the scope / credential refusals, and a real rebuild on PGlite.

The real leg drives the tool's SQL through an executor that runs it on a live PGlite (the rendered event store
organ), so the dry-run plan and the begin/step/swap sequence are proven against Postgres, not a string fake.
"""
from __future__ import annotations

import uuid

import pytest

from tools.noctus.dev.migrate_product import FakeSqlExecutor
from tools.noctus.dev.projection_rebuild import projection_rebuild

S = "pr_tool"
ORG = str(uuid.UUID(int=0xA7))
LIVE = lambda: ["demo"]  # noqa: E731 -- the catalog seam (`deploy_verify._resolve_live_products` injection)


class _PgliteExecutor:
    def __init__(self, client):
        self.client = client
        self.executed: list[str] = []

    def execute(self, sql):
        self.executed.append(sql)
        try:
            return {"ok": True, "rows": self.client.query(sql), "error": None}
        except Exception as exc:  # noqa: BLE001 -- surfaced as the executor's error shape
            return {"ok": False, "rows": None, "error": str(exc)}


def test_refuses_a_product_outside_the_live_catalog():
    ex = FakeSqlExecutor()
    out = projection_rebuild("sleepy", "cnt", schema=S, executor=ex, live_products_fn=LIVE)
    assert out["status"] == "refused_catalog_scope" and ex.executed == []


def test_rejects_a_malformed_projection_name():
    out = projection_rebuild("demo", "Bad; DROP", schema=S, executor=FakeSqlExecutor(), live_products_fn=LIVE)
    assert out["status"] == "error" and "projection must match" in out["error"]


def test_unregistered_projection_is_refused():
    out = projection_rebuild("demo", "cnt", schema=S, executor=FakeSqlExecutor(), live_products_fn=LIVE)
    assert out["status"] == "refused" and "not registered" in out["error"]


@pytest.fixture(scope="module")
def db():
    from noctusai_lib.testing.pglite import PgliteClient, pglite_available

    if not pglite_available():
        pytest.skip("PGlite unavailable (needs `node` and mcp/noctusai/node/node_modules) -- did not run")
    from noctusai_lib.domain.event_store import EventStoreConfig, event_store_migration

    client = PgliteClient(S)
    client.exec(f"CREATE SCHEMA {S}")
    client.exec(event_store_migration(EventStoreConfig(S)))
    client.exec(f"""
CREATE TABLE {S}.counts (stream_id uuid PRIMARY KEY, n int NOT NULL);
CREATE FUNCTION {S}.count_h(p_events jsonb, p_target regclass) RETURNS void LANGUAGE plpgsql AS $$
DECLARE e jsonb; BEGIN
  FOR e IN SELECT * FROM jsonb_array_elements(p_events) LOOP
    EXECUTE format('INSERT INTO %s AS t (stream_id, n) VALUES ($1, 1) ON CONFLICT (stream_id) DO UPDATE SET n = t.n + 1',
                   p_target) USING (e->>'stream_id')::uuid;
  END LOOP; END $$;""")
    yield client
    client.close()


def test_dry_run_then_rebuild_on_postgres(db):
    reg = db.rpc("es_register_projection", {"p_projection": "cnt", "p_handler": "count_h", "p_target": "counts",
                                            "p_stream_types": ["sub"], "p_mode": "async"}).execute().data
    assert reg["status"] == "ok"
    sid = str(uuid.uuid4())
    db.rpc("es_append", {"p_org": ORG, "p_stream_type": "sub", "p_stream_id": sid, "p_expected_version": 0,
                         "p_events": [{"event_type": "x"}] * 5}).execute()
    db.rpc("es_run_projection", {"p_projection": "cnt"}).execute()
    db.exec(f"UPDATE {S}.counts SET n = 999")

    ex = _PgliteExecutor(db)
    plan = projection_rebuild("demo", "cnt", schema=S, batch=2, executor=ex, live_products_fn=LIVE)
    assert plan["status"] == "planned" and plan["plan"]["events_to_replay"] == 5 and plan["plan"]["estimated_steps"] == 3
    assert not [q for q in ex.executed if "es_rebuild" in q]  # a dry run never starts a rebuild
    assert db.query(f"SELECT n FROM {S}.counts")[0]["n"] == 999

    done = projection_rebuild("demo", "cnt", schema=S, batch=2, confirm=True, executor=ex, live_products_fn=LIVE)
    assert done["status"] == "rebuilt" and done["applied"] == 5 and done["rows"] == 1, done
    assert db.query(f"SELECT n FROM {S}.counts")[0]["n"] == 5
    assert db.query(f"SELECT to_regclass('{S}.counts__rebuild') IS NULL AS gone")[0]["gone"]
