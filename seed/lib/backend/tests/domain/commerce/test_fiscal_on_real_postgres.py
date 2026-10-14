"""The fiscal DDL on a REAL Postgres (PGlite, PG16/WASM): applied after the commerce migration, twice,
then every DB-side rule exercised -- the regime CHECK above all (D37 as a database invariant).

Same harness as finance's `test_sql_on_real_postgres.py`. Skips (visibly) when `node` or the harness
install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.commerce import CommerceConfig, commerce_migration
from noctusai_lib.domain.commerce.fiscal_sql import commerce_fiscal_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "comx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""

_BASE = f"""
DO $$
DECLARE o uuid := gen_random_uuid(); c uuid := gen_random_uuid(); ord uuid := gen_random_uuid(); inv uuid := gen_random_uuid();
BEGIN
  INSERT INTO {SCHEMA}.commerce_store_profiles(org_id,legal_name,trade_name,cnpj,tax_regime) VALUES (o,'L','L','11222333000181','lucro_presumido');
  INSERT INTO {SCHEMA}.commerce_customers(id,org_id,email) VALUES (c,o,'a@b.c');
  INSERT INTO {SCHEMA}.commerce_orders(id,org_id,token,customer_id,subtotal_cents,total_cents,payment_method,gateway)
    VALUES (ord,o,gen_random_uuid()::text,c,100,100,'pix','asaas');
  INSERT INTO {SCHEMA}.commerce_invoices(id,org_id,order_id,kind,ref) VALUES (inv,o,ord,'nfse','abc12345-ord-nfse-1');
  {{body}}
END $$;
"""

#: name -> (SQLSTATE clause, statement that MUST be refused).
RULES: dict[str, tuple[str, str]] = {
    "mei cannot hold municipal (update)": ("check_violation",
        f"UPDATE {SCHEMA}.commerce_store_profiles SET tax_regime='mei', nfse_mode='municipal' WHERE org_id=o"),
    "simples cannot hold municipal (insert)": ("check_violation",
        f"INSERT INTO {SCHEMA}.commerce_store_profiles(org_id,legal_name,trade_name,cnpj,tax_regime,nfse_mode) "
        "VALUES (gen_random_uuid(),'L','L','11222333000181','simples','municipal')"),
    "a regime change to simples while municipal is refused": ("check_violation",
        f"UPDATE {SCHEMA}.commerce_store_profiles SET nfse_mode='municipal' WHERE org_id=o; "
        f"UPDATE {SCHEMA}.commerce_store_profiles SET tax_regime='simples' WHERE org_id=o"),
    "nfse_mode vocabulary": ("check_violation", f"UPDATE {SCHEMA}.commerce_store_profiles SET nfse_mode='federal' WHERE org_id=o"),
    "municipio_ibge has 7 digits": ("check_violation", f"UPDATE {SCHEMA}.commerce_store_profiles SET municipio_ibge='123' WHERE org_id=o"),
    "ref unique per org": ("unique_violation",
        f"INSERT INTO {SCHEMA}.commerce_invoices(org_id,order_id,kind,seq,ref) VALUES (o,ord,'nfe',1,'abc12345-ord-nfse-1')"),
    "one seq per order+kind": ("unique_violation",
        f"INSERT INTO {SCHEMA}.commerce_invoices(org_id,order_id,kind,seq,ref) VALUES (o,ord,'nfse',1,'other-ref')"),
    "kind vocabulary": ("check_violation", f"INSERT INTO {SCHEMA}.commerce_invoices(org_id,order_id,kind,ref) VALUES (o,ord,'nfce','r2')"),
    "status vocabulary": ("check_violation", f"UPDATE {SCHEMA}.commerce_invoices SET status='done' WHERE id=inv"),
    "ref shape (no path characters)": ("check_violation", f"INSERT INTO {SCHEMA}.commerce_invoices(org_id,order_id,kind,seq,ref) VALUES (o,ord,'nfe',1,'../x')"),
    "ref length cap 64": ("check_violation", f"INSERT INTO {SCHEMA}.commerce_invoices(org_id,order_id,kind,seq,ref) VALUES (o,ord,'nfe',1,'{'a' * 65}')"),
    "invoice needs a real order": ("foreign_key_violation",
        f"INSERT INTO {SCHEMA}.commerce_invoices(org_id,order_id,kind,ref) VALUES (o,gen_random_uuid(),'nfe','r3')"),
    "seq starts at 1": ("check_violation", f"UPDATE {SCHEMA}.commerce_invoices SET seq=0 WHERE id=inv"),
}

#: statements that MUST succeed (positive controls: the CHECK is not simply rejecting everything).
ALLOWED: dict[str, str] = {
    "lucro_presumido may hold municipal": f"UPDATE {SCHEMA}.commerce_store_profiles SET nfse_mode='municipal' WHERE org_id=o",
    "simples with nacional": f"UPDATE {SCHEMA}.commerce_store_profiles SET tax_regime='simples', nfse_mode='nacional' WHERE org_id=o",
    "simples with NULL mode (put_profile never sets it)": f"UPDATE {SCHEMA}.commerce_store_profiles SET tax_regime='mei', nfse_mode=NULL WHERE org_id=o",
    "re-issue after rejection is seq 2": f"INSERT INTO {SCHEMA}.commerce_invoices(org_id,order_id,kind,seq,ref) VALUES (o,ord,'nfse',2,'abc12345-ord-nfse-2')",
    "valid ibge": f"UPDATE {SCHEMA}.commerce_store_profiles SET municipio_ibge='3548500' WHERE org_id=o",
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
    cfg = CommerceConfig(schema=SCHEMA)
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "commerce_migration", "sql": commerce_migration(cfg, SCHEMA), "mode": "file", "twice": True},
        {"product": SCHEMA, "file": "commerce_fiscal_migration", "sql": commerce_fiscal_migration(cfg, SCHEMA), "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"rule: {n}", "sql": _rule_sql(*r), "mode": "file", "twice": False} for n, r in RULES.items()),
        *({"product": SCHEMA, "file": f"allowed: {n}", "sql": _BASE.replace("{body}", stmt + ";"), "mode": "file", "twice": False} for n, stmt in ALLOWED.items()),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)], input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:  # the harness could not MEASURE: say so, never read it as a pass
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_commerce_then_fiscal_apply_twice_on_real_postgres(replay):
    assert replay["commerce_migration"]["failures"] == [], replay["commerce_migration"]["failures"]
    assert replay["commerce_fiscal_migration"]["failures"] == [], replay["commerce_fiscal_migration"]["failures"]


@pytest.mark.parametrize("rule", list(RULES))
def test_database_rule_is_enforced(replay, rule):
    assert replay[f"rule: {rule}"]["failures"] == [], f"{rule}: {replay[f'rule: {rule}']['failures']}"


@pytest.mark.parametrize("name", list(ALLOWED))
def test_valid_statement_is_accepted(replay, name):
    assert replay[f"allowed: {name}"]["failures"] == [], f"{name}: {replay[f'allowed: {name}']['failures']}"
