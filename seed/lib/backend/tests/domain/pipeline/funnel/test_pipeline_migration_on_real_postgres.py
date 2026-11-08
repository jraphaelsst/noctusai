"""`pipeline_migration` on a REAL Postgres (PGlite, PG16/WASM) -- the Real leg of the funnel's Fake+Real contract.

The route suite runs against `MockSupabaseClient` with its columns validated against THIS migration's emitted
schema; here the same DDL is applied for real (twice: forward-only + idempotent) and the database rules the
organ leans on are exercised: append-only history, service-role-only grants, one stage per role, slug shape,
the card columns (numeric position survives a midpoint). Route-level coverage against a live PostgREST is not
available offline; this is the strongest Real check the repo's harness allows.
Skips visibly when `node` / the harness install is missing -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.pipeline import PipelineConfig, pipeline_migration

ROOT = Path(__file__).resolve().parents[7]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "funil"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

CFG = PipelineConfig(
    pipeline="crm", card_table="cards", value_field="valor", entity_label="card", entity_kind="card", cliente_field=None
)
PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE TABLE {SCHEMA}.cards (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, titulo text, valor numeric);
"""

_BASE = f"""
DO $$
DECLARE o uuid := gen_random_uuid(); s1 uuid := gen_random_uuid(); s2 uuid := gen_random_uuid();
        c uuid := gen_random_uuid(); m uuid := gen_random_uuid(); n int; t text;
BEGIN
  INSERT INTO {SCHEMA}.pipeline_stages(id, org_id, pipeline, slug, label, posicao, papel)
    VALUES (s1, o, 'crm', 'entrada', 'Entrada', 0, NULL), (s2, o, 'crm', 'ganho', 'Ganho', 1, 'final');
  INSERT INTO {SCHEMA}.cards(id, org_id, titulo, valor) VALUES (c, o, 'Ana', 10);
  UPDATE {SCHEMA}.cards SET etapa_id = s1 WHERE id = c;
  INSERT INTO {SCHEMA}.pipeline_movimentos(id, org_id, pipeline, entidade_id, de_etapa_id, para_etapa_id)
    VALUES (m, o, 'crm', c, NULL, s1);
  {{body}}
END $$;
"""

SCENARIOS: dict[str, str] = {
    "a card defaults to open at position 0 and a midpoint survives (numeric, not integer)": f"""
  SELECT count(*) INTO n FROM {SCHEMA}.cards WHERE id = c AND status = 'aberto' AND kanban_pos = 0;
  IF n <> 1 THEN RAISE EXCEPTION 'card defaults wrong'; END IF;
  UPDATE {SCHEMA}.cards SET kanban_pos = 1.5 WHERE id = c;
  SELECT count(*) INTO n FROM {SCHEMA}.cards WHERE id = c AND kanban_pos = 1.5;
  IF n <> 1 THEN RAISE EXCEPTION 'midpoint rounded away'; END IF;""",
    "the browser roles hold no privilege on either table; service_role holds all": f"""
  FOREACH t IN ARRAY ARRAY['pipeline_stages', 'pipeline_movimentos'] LOOP
    IF has_table_privilege('anon', '{SCHEMA}.' || t, 'SELECT')
       OR has_table_privilege('authenticated', '{SCHEMA}.' || t, 'SELECT')
       OR has_table_privilege('authenticated', '{SCHEMA}.' || t, 'INSERT') THEN
      RAISE EXCEPTION 'browser role can reach %', t;
    END IF;
    IF NOT has_table_privilege('service_role', '{SCHEMA}.' || t, 'INSERT') THEN
      RAISE EXCEPTION 'service_role lost % ', t;
    END IF;
  END LOOP;""",
}

#: name -> (SQLSTATE condition, statement) that must be REFUSED.
RULES: dict[str, tuple[str, str]] = {
    "history is append-only: UPDATE refused": ("raise_exception", f"UPDATE {SCHEMA}.pipeline_movimentos SET motivo = 'x' WHERE id = m"),
    "history is append-only: DELETE refused": ("raise_exception", f"DELETE FROM {SCHEMA}.pipeline_movimentos WHERE id = m"),
    "one stage per role per pipeline per org": (
        "unique_violation",
        f"INSERT INTO {SCHEMA}.pipeline_stages(org_id, pipeline, slug, label, posicao, papel) VALUES (o, 'crm', 'outro', 'Outro', 2, 'final')",
    ),
    "a slug is machine-shaped": (
        "check_violation",
        f"INSERT INTO {SCHEMA}.pipeline_stages(org_id, pipeline, slug, label) VALUES (o, 'crm', 'Com Espaco', 'X')",
    ),
    "a history row must name a real destination stage": (
        "foreign_key_violation",
        f"INSERT INTO {SCHEMA}.pipeline_movimentos(org_id, pipeline, entidade_id, para_etapa_id) VALUES (o, 'crm', c, gen_random_uuid())",
    ),
}


def _sql(body: str) -> str:
    return _BASE.replace("{body}", body)


def _rule_sql(clause: str, stmt: str) -> str:
    return _sql(f"""BEGIN
    {stmt};
    RAISE EXCEPTION 'NOT ENFORCED';
  EXCEPTION WHEN {clause} THEN NULL;
  END;""")


@pytest.fixture(scope="module")
def replay() -> dict:
    migration = pipeline_migration(CFG, SCHEMA)
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "pipeline", "sql": migration, "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"scenario: {n}", "sql": _sql(b), "mode": "file", "twice": False} for n, b in SCENARIOS.items()),
        *({"product": SCHEMA, "file": f"rule: {n}", "sql": _rule_sql(*r), "mode": "file", "twice": False} for n, r in RULES.items()),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_the_migration_applies_and_applies_twice(replay):
    assert replay["pipeline"]["failures"] == [], replay["pipeline"]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


@pytest.mark.parametrize("name", list(RULES))
def test_database_rule_is_enforced(replay, name):
    assert replay[f"rule: {name}"]["failures"] == [], replay[f"rule: {name}"]["failures"]
