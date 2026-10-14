"""The generated DDL on a REAL Postgres (PGlite, PG16/WASM) -- applied twice, then every DB-side rule exercised.

The mock PostgREST client cannot enforce unique indexes, CHECKs or FKs. This drives the toolkit's own
migration-replay node harness (`mcp/noctusai/node`): parties + finance first (the organs contracts links to),
then `contracts_migration` whole and AGAIN. Skips (visibly, with the reason) when `node` or the harness install is
unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.contracts import ContractsConfig, contracts_migration
from noctusai_lib.domain.finance import FinanceConfig, finance_migration
from noctusai_lib.domain.parties import PartiesConfig, parties_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "ctrx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

CFG = ContractsConfig(schema=SCHEMA, with_parties=True, with_items=True)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE TABLE IF NOT EXISTS {SCHEMA}.itm_items (id UUID PRIMARY KEY, org_id UUID NOT NULL, name TEXT, UNIQUE (org_id, id));
"""

_BASE = f"""
DO $$
DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); p uuid := gen_random_uuid(); it uuid := gen_random_uuid();
        c uuid := gen_random_uuid();
BEGIN
  INSERT INTO {SCHEMA}.pty_parties(id,org_id,kind,legal_name) VALUES (p,o,'PF','Ana');
  INSERT INTO {SCHEMA}.itm_items(id,org_id,name) VALUES (it,o,'Serviço');
  INSERT INTO {SCHEMA}.ctr_contracts(id,org_id,title,party_id,billing_model,amount_cents,first_due_date)
    VALUES (c,o,'Contrato',p,'recurring',1000,'2026-11-10');
  {{body}}
END $$;
"""

_CT = f"INSERT INTO {SCHEMA}.ctr_contracts(org_id,title,billing_model,amount_cents"
RULES: dict[str, tuple[str, str]] = {
    "status is one of five": ("check_violation", f"{_CT},status) VALUES (o,'x','one_time',1,'paused')"),
    "billing model is one of four": ("check_violation", f"{_CT}) VALUES (o,'x','weekly',1)"),
    "amount cannot be negative": ("check_violation", f"{_CT}) VALUES (o,'x','one_time',-1)"),
    "title not blank": ("check_violation", f"{_CT}) VALUES (o,'   ','one_time',1)"),
    "end before start": ("check_violation", f"{_CT},start_date,end_date) VALUES (o,'x','one_time',1,'2026-02-01','2026-01-01')"),
    "due day within 1..31": ("check_violation", f"{_CT},due_day) VALUES (o,'x','one_time',1,32)"),
    "number unique per org (case-insensitive)": ("unique_violation",
        f"{_CT},number) VALUES (o,'a','one_time',1,'CT-1'); {_CT},number) VALUES (o,'b','one_time',1,'ct-1')"),
    "quote unique per org": ("unique_violation",
        f"{_CT},source_quote_id) VALUES (o,'a','one_time',1,'Q1'); {_CT},source_quote_id) VALUES (o,'b','one_time',1,'Q1')"),
    "a contract cannot name a party of another org": ("foreign_key_violation",
        f"INSERT INTO {SCHEMA}.ctr_contracts(org_id,title,party_id,billing_model,amount_cents) VALUES (o2,'x',p,'one_time',1)"),
    "a line cannot name an item of another org": ("foreign_key_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_lines(org_id,contract_id,item_id,description,unit_price_cents) VALUES (o,c,gen_random_uuid(),'x',1)"),
    "a line cannot name a contract of another org": ("foreign_key_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_lines(org_id,contract_id,description,unit_price_cents) VALUES (o2,c,'x',1)"),
    "line quantity at least 1": ("check_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_lines(org_id,contract_id,description,quantity,unit_price_cents) VALUES (o,c,'x',0,1)"),
    "version number unique per contract": ("unique_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_versions(org_id,contract_id,version_n,kind) VALUES (o,c,1,'initial'); "
        f"INSERT INTO {SCHEMA}.ctr_contract_versions(org_id,contract_id,version_n,kind) VALUES (o,c,1,'amendment')"),
    "billing is unique per contract+period+kind (the idempotency floor)": ("unique_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_billings(org_id,contract_id,period_key,source_ref,amount_cents,due_date) VALUES (o,c,'k','r',1,'2026-11-10'); "
        f"INSERT INTO {SCHEMA}.ctr_contract_billings(org_id,contract_id,period_key,source_ref,amount_cents,due_date) VALUES (o,c,'k','r',1,'2026-11-10')"),
    "usage period must be the first of a month": ("check_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_usage(org_id,contract_id,period_month,minutes) VALUES (o,c,'2026-11-15',60)"),
    "usage minutes positive": ("check_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_usage(org_id,contract_id,period_month,minutes) VALUES (o,c,'2026-11-01',0)"),
    "finance now admits source='contracts'": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents,source,source_ref) "
        "VALUES (o,'receivable','x','2026-11-01','2026-11-10',1,'contracts','c:1'); RAISE check_violation USING MESSAGE = 'admitted'"),
    "finance still refuses an unknown source": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents,source) "
        "VALUES (o,'receivable','x','2026-11-01','2026-11-10',1,'nope')"),
    "deleting a contract cascades its children": ("check_violation",
        f"INSERT INTO {SCHEMA}.ctr_contract_lines(org_id,contract_id,description,unit_price_cents) VALUES (o,c,'x',1); "
        f"DELETE FROM {SCHEMA}.ctr_contracts WHERE id = c; "
        f"IF EXISTS (SELECT 1 FROM {SCHEMA}.ctr_contract_lines WHERE contract_id = c) THEN RAISE EXCEPTION 'cascade missing'; END IF; "
        "RAISE check_violation USING MESSAGE = 'cascade ok'"),
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
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "parties", "sql": parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA), "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "finance", "sql": finance_migration(FinanceConfig(schema=SCHEMA), SCHEMA), "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "contracts_migration", "sql": contracts_migration(CFG, SCHEMA), "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"rule: {name}", "sql": _rule_sql(*rule), "mode": "file", "twice": False} for name, rule in RULES.items()),
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
    for name in ("parties", "finance", "contracts_migration"):
        assert replay[name]["failures"] == [], (name, replay[name]["failures"])


@pytest.mark.parametrize("rule", list(RULES))
def test_database_rule_is_enforced(replay, rule):
    step = replay[f"rule: {rule}"]
    assert step["failures"] == [], f"{rule}: {step['failures']}"
