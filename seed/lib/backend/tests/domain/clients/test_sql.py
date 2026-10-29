"""The generated DDL: shape (offline) and, when the PGlite harness is available, on a REAL Postgres -- applied
twice, its guards refusing, and the declared guard probes refusing exactly as `verify_db_guards` will run them."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.clients import CLIENTS_MIGRATION_HEADER, clients_guard_probes, clients_migration, clients_table_ddl

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "clientsx"


def test_ddl_shape():
    sql = clients_table_ddl(SCHEMA)
    for table in ("clients", "client_schedules", "client_sessions", "client_payments"):
        assert f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{table}" in sql
        assert f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert re.search(r"org_id\s+UUID NOT NULL", sql)
    # status / session status / method are DATA: no CHECK may freeze them
    assert "CHECK (status" not in sql and "CHECK (method" not in sql
    # the person's document is never readable through a direct authenticated path
    assert f"REVOKE ALL ON {SCHEMA}.clients FROM PUBLIC, anon, authenticated" in sql
    assert f"GRANT SELECT ON {SCHEMA}.clients TO authenticated" not in sql
    assert f"GRANT SELECT ON {SCHEMA}.client_sessions TO authenticated" in sql
    # materialization's ON CONFLICT target must be a plain (non-partial) unique index
    assert f"uq_client_sessions_slot ON {SCHEMA}.client_sessions (schedule_id, starts_at);" in sql


def test_migration_has_header_and_rejects_empty_schema():
    assert clients_migration(SCHEMA).startswith(CLIENTS_MIGRATION_HEADER)
    with pytest.raises(ValueError):
        clients_migration(" ")


def test_every_unique_guard_is_declared_as_a_probe():
    declared = sorted(p.guard_name for p in clients_guard_probes(SCHEMA))
    emitted = sorted(re.findall(r"CREATE UNIQUE INDEX IF NOT EXISTS (\w+)", clients_table_ddl(SCHEMA)))
    assert declared == emitted == ["uq_client_sessions_slot", "uq_clients_lead"]


_REAL = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""


def _probe_sql(probe) -> str:
    return f"""DO $$ DECLARE v_org uuid := gen_random_uuid(); {probe.declare}
BEGIN
  BEGIN
    {probe.body}
    RAISE EXCEPTION 'NOT ENFORCED: {probe.permitted}';
  EXCEPTION WHEN unique_violation THEN
    IF position('{probe.refusal_fragment}' in SQLERRM) = 0 THEN RAISE EXCEPTION 'wrong guard: %', SQLERRM; END IF;
  END;
END $$;"""


ONE_OFFS = f"""DO $$ DECLARE o uuid := gen_random_uuid(); c uuid := gen_random_uuid();
BEGIN
  INSERT INTO {SCHEMA}.clients (id, org_id, name, status) VALUES (c, o, 'a', 'ativo');
  -- one-off sessions (NULL schedule_id) at the same instant never conflict
  INSERT INTO {SCHEMA}.client_sessions (org_id, client_id, starts_at, duration_min, status) VALUES (o, c, '2030-01-07 13:00+00', 50, 'agendada');
  INSERT INTO {SCHEMA}.client_sessions (org_id, client_id, starts_at, duration_min, status) VALUES (o, c, '2030-01-07 13:00+00', 50, 'agendada');
  -- clients without a lead never conflict
  INSERT INTO {SCHEMA}.clients (org_id, name, status) VALUES (o, 'b', 'ativo'), (o, 'c', 'ativo');
END $$;"""


@_REAL
def test_ddl_applies_twice_and_the_guards_refuse():
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "clients_migration", "sql": clients_migration(SCHEMA), "mode": "file", "twice": True},
        {"product": SCHEMA, "file": "one-offs coexist", "sql": ONE_OFFS, "mode": "file", "twice": False},
        *(
            {"product": SCHEMA, "file": f"probe: {p.guard_name}", "sql": _probe_sql(p), "mode": "file", "twice": False}
            for p in clients_guard_probes(SCHEMA)
        ),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)], input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    failed = {s["file"]: s["failures"] for s in out["steps"] if s["failures"]}
    assert not failed, failed
