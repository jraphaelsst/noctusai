"""The generated DDL: shape (offline) and, when the PGlite harness is available, on a REAL Postgres."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.leads import LEADS_MIGRATION_HEADER, leads_guard_probes, leads_migration, leads_table_ddl

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "leadsx"


def test_ddl_shape():
    sql = leads_table_ddl(SCHEMA)
    assert re.search(r"org_id\s+UUID NOT NULL", sql) and re.search(r"position\s+NUMERIC", sql)
    for col in ("whatsapp_connection_id", "whatsapp_chat_id", "first_contact_at", "last_message_preview", "tags", "created_by"):
        assert col in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql and "service_role_bypass" in sql
    assert "UNIQUE INDEX IF NOT EXISTS uq_leads_chat" in sql and "WHERE whatsapp_connection_id IS NOT NULL" in sql
    # stage / origin are DATA: no CHECK may freeze them
    assert "CHECK (stage" not in sql and "CHECK (origin" not in sql


def test_migration_has_header_and_rejects_empty_schema():
    assert leads_migration(SCHEMA).startswith(LEADS_MIGRATION_HEADER)
    with pytest.raises(ValueError):
        leads_migration(" ")


def test_every_unique_guard_is_declared_as_a_probe():
    assert [p.guard_name for p in leads_guard_probes(SCHEMA)] == ["uq_leads_chat"]


_REAL = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""


def _rule(clause: str, stmt: str) -> str:
    return f"""DO $$ DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); c uuid := gen_random_uuid();
BEGIN
  INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage,whatsapp_connection_id,whatsapp_chat_id) VALUES (o,'a','whatsapp','lead',c,'chat-1');
  BEGIN
    {stmt};
    RAISE EXCEPTION 'NOT ENFORCED';
  EXCEPTION WHEN {clause} THEN NULL;
  END;
END $$;"""


RULES = {
    "one lead per chat": ("unique_violation", f"INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage,whatsapp_connection_id,whatsapp_chat_id) VALUES (o,'dup','whatsapp','lead',c,'chat-1')"),
    "same chat in another org is allowed": ("unique_violation", f"INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage,whatsapp_connection_id,whatsapp_chat_id) VALUES (o2,'ok','whatsapp','lead',c,'chat-1'); INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage,whatsapp_connection_id,whatsapp_chat_id) VALUES (o2,'dup','whatsapp','lead',c,'chat-1')"),
    "manual leads may repeat (no chat)": ("unique_violation", f"INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage) VALUES (o,'m1','outro','lead'); INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage) VALUES (o,'m2','outro','lead'); RAISE unique_violation USING MESSAGE='ok'"),
    "name not blank": ("check_violation", f"INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage) VALUES (o,'  ','outro','lead')"),
    "position keeps fractions": ("check_violation", f"INSERT INTO {SCHEMA}.leads(org_id,name,origin,stage,position) VALUES (o,'f','outro','lead',1.5); IF (SELECT position FROM {SCHEMA}.leads WHERE name='f') <> 1.5 THEN RAISE EXCEPTION 'rounded'; END IF; RAISE check_violation USING MESSAGE='ok'"),
}


@_REAL
def test_ddl_applies_twice_and_the_database_rules_hold():
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "leads_migration", "sql": leads_migration(SCHEMA), "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"rule: {n}", "sql": _rule(*r), "mode": "file", "twice": False} for n, r in RULES.items()),
    ]
    proc = subprocess.run(["node", str(HARNESS)], input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}), capture_output=True, text=True, cwd=NODE_DIR, timeout=300)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    failed = {s["file"]: s["failures"] for s in out["steps"] if s["failures"]}
    assert not failed, failed
