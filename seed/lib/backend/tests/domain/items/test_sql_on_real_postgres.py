"""The generated DDL on a REAL Postgres (PGlite, PG16/WASM) -- applied twice, then every DB-side rule exercised.

The mock PostgREST client cannot enforce unique indexes, CHECKs or FKs, and a parser cannot prove DDL RUNS.
This drives the toolkit's own migration-replay node harness (`mcp/noctusai/node`) with the generator's output:
the chain-replay contract is "a new migration applies whole, then again". Skips (visibly, with the reason) when
`node` or the harness install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.items import ItemsConfig, items_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "itx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""

_BASE = f"""
DO $$
DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); c uuid := gen_random_uuid(); c2 uuid := gen_random_uuid();
BEGIN
  INSERT INTO {SCHEMA}.itm_item_categories(id,org_id,name) VALUES (c,o,'Raiz');
  INSERT INTO {SCHEMA}.itm_item_categories(id,org_id,name) VALUES (c2,o2,'Outra org');
  INSERT INTO {SCHEMA}.itm_items(org_id,sku,name,category_id) VALUES (o,'ABC-1','Item',c);
  {{body}}
END $$;
"""

I = f"INSERT INTO {SCHEMA}.itm_items(org_id,sku,name"

#: name -> (SQLSTATE exception clause, statement that MUST be refused). A rule that is not enforced reaches
#: `RAISE EXCEPTION 'NOT ENFORCED'`, which no handler catches, so the step fails by name.
RULES: dict[str, tuple[str, str]] = {
    "sku unique per org, case-insensitive": ("unique_violation", f"{I}) VALUES (o,'abc-1','Dup')"),
    "item must reference a category of ITS OWN org": ("foreign_key_violation", f"{I},category_id) VALUES (o,'X-1','x',c2)"),
    "category parent must be in the same org": ("foreign_key_violation",
        f"INSERT INTO {SCHEMA}.itm_item_categories(org_id,name,parent_id) VALUES (o,'Filha',c2)"),
    "category name unique per parent (case-insensitive)": ("unique_violation",
        f"INSERT INTO {SCHEMA}.itm_item_categories(org_id,name) VALUES (o,'raiz')"),
    "a category in use cannot be deleted": ("foreign_key_violation", f"DELETE FROM {SCHEMA}.itm_item_categories WHERE id = c"),
    "item_type is closed": ("check_violation", f"{I},item_type) VALUES (o,'X-2','x','gadget')"),
    "unit is closed": ("check_violation", f"{I},unit) VALUES (o,'X-3','x','XX')"),
    "sku shape": ("check_violation", f"{I}) VALUES (o,'a b','x')"),
    "name not blank": ("check_violation", f"{I}) VALUES (o,'X-4','   ')"),
    "ncm is 8 digits": ("check_violation", f"{I},ncm) VALUES (o,'X-5','x','1234567')"),
    "cest is 7 digits": ("check_violation", f"{I},cest) VALUES (o,'X-6','x','12345678')"),
    "cfop first digit": ("check_violation", f"{I},cfop_default) VALUES (o,'X-7','x','4102')"),
    "origem 0..8": ("check_violation", f"{I},origem) VALUES (o,'X-8','x',9)"),
    "gtin length": ("check_violation", f"{I},gtin) VALUES (o,'X-9','x','123456789')"),
    "cost not negative": ("check_violation", f"{I},cost_cents) VALUES (o,'X-10','x',-1)"),
    "price not negative": ("check_violation", f"{I},price_cents) VALUES (o,'X-11','x',-1)"),
    "weight not negative": ("check_violation", f"{I},weight_g) VALUES (o,'X-12','x',-1)"),
    "dimension not negative": ("check_violation", f"{I},length_mm) VALUES (o,'X-13','x',-1)"),
}

#: Statements that MUST succeed (so a rule above is not refusing for an unrelated reason).
ALLOWED = {
    "same sku in ANOTHER org": f"{I}) VALUES (o2,'ABC-1','Outra org')",
    "fully fiscal item": f"{I},ncm,cest,cfop_default,origem,gtin,cost_cents,price_cents,weight_g) "
                         "VALUES (o,'FULL-1','x','73181500','0100100','5102',0,'7891000100103',1,2,3)",
    "same category name under another parent": f"INSERT INTO {SCHEMA}.itm_item_categories(org_id,name,parent_id) VALUES (o,'Raiz',c)",
}


def _rule_sql(clause: str, stmt: str) -> str:
    body = f"""BEGIN
    {stmt};
    RAISE EXCEPTION 'NOT ENFORCED';
  EXCEPTION WHEN {clause} THEN NULL;
  END;"""
    return _BASE.replace("{body}", body)


@pytest.fixture(scope="module")
def replay() -> dict:
    sql = items_migration(ItemsConfig(schema=SCHEMA))
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "items_migration", "sql": sql, "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"rule: {n}", "sql": _rule_sql(*r), "mode": "file", "twice": False} for n, r in RULES.items()),
        *({"product": SCHEMA, "file": f"allowed: {n}", "sql": _BASE.replace("{body}", f"{stmt};"), "mode": "file", "twice": False} for n, stmt in ALLOWED.items()),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:  # the harness could not MEASURE: say so, never read it as a pass
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_ddl_applies_twice_on_real_postgres(replay):
    step = replay["items_migration"]
    assert step["failures"] == [], step["failures"]


@pytest.mark.parametrize("rule", list(RULES))
def test_database_rule_is_enforced(replay, rule):
    step = replay[f"rule: {rule}"]
    assert step["failures"] == [], f"{rule}: {step['failures']}"


@pytest.mark.parametrize("name", list(ALLOWED))
def test_legitimate_statement_is_accepted(replay, name):
    step = replay[f"allowed: {name}"]
    assert step["failures"] == [], f"{name}: {step['failures']}"
