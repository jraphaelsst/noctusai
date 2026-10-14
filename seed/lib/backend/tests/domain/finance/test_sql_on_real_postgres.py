"""The generated DDL on a REAL Postgres (PGlite, PG16/WASM) -- applied twice, then every DB-side rule exercised.

The mock PostgREST client cannot enforce unique indexes, CHECKs or FKs, and a parser cannot prove DDL
RUNS. This drives the toolkit's own migration-replay node harness (`mcp/noctusai/node`) with the
generator's output: the chain-replay contract is "a new migration applies whole, then again".
Skips (visibly, with the reason) when `node` or the harness install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.finance import FinanceConfig, finance_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "finx"

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
DECLARE r uuid := gen_random_uuid(); o uuid := gen_random_uuid(); a uuid := gen_random_uuid();
        e uuid := gen_random_uuid(); s uuid := gen_random_uuid(); l uuid := gen_random_uuid();
BEGIN
  INSERT INTO {SCHEMA}.fin_accounts(id,org_id,name,kind,gateway) VALUES (a,o,'Asaas','gateway','asaas');
  INSERT INTO {SCHEMA}.fin_entries(id,org_id,direction,description,competence_month,due_date,amount_cents,source,source_ref)
    VALUES (e,o,'receivable','x','2026-10-01','2026-10-10',1000,'commerce_order','ord1');
  INSERT INTO {SCHEMA}.fin_settlements(id,org_id,entry_id,account_id,kind,settled_on,amount_cents,external_ref)
    VALUES (s,o,e,a,'payment','2026-10-10',1000,'pay_1');
  INSERT INTO {SCHEMA}.fin_ledger(id,org_id,account_id,occurred_on,direction,amount_cents,origin,settlement_id)
    VALUES (l,o,a,'2026-10-10','in',1000,'settlement',s);
  {{body}}
END $$;
"""

#: name -> (SQLSTATE exception clause, statement that MUST be refused). A rule that is not enforced
#: reaches `RAISE EXCEPTION 'NOT ENFORCED'`, which no handler catches, so the step fails by name.
RULES: dict[str, tuple[str, str]] = {
    "one gateway account per org+gateway": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_accounts(org_id,name,kind,gateway) VALUES (o,'Dup','gateway','asaas')"),
    "gateway account needs a gateway": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_accounts(org_id,name,kind) VALUES (o,'x','gateway')"),
    "entry source_ref unique per org+source": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents,source,source_ref) "
        "VALUES (o,'receivable','x','2026-10-01','2026-10-10',1000,'commerce_order','ord1')"),
    "competence_month is day 1": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents) "
        "VALUES (o,'receivable','x','2026-10-05','2026-10-10',1000)"),
    "amount must be positive": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents) "
        "VALUES (o,'receivable','x','2026-10-01','2026-10-10',0)"),
    "settled cannot exceed amount": ("check_violation", f"UPDATE {SCHEMA}.fin_entries SET settled_cents = 2000 WHERE id = e"),
    "installment numbering is all-or-none": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents,installment_n) "
        "VALUES (o,'payable','x','2026-10-01','2026-10-10',10,1)"),
    "settlement external_ref unique per org+kind": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_settlements(org_id,entry_id,account_id,kind,settled_on,amount_cents,external_ref) "
        "VALUES (o,e,a,'payment','2026-10-10',10,'pay_1')"),
    "settlement amount must be positive": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_settlements(org_id,entry_id,account_id,kind,settled_on,amount_cents) VALUES (o,e,a,'payment','2026-10-10',0)"),
    "a reversal needs its reason": ("check_violation", f"UPDATE {SCHEMA}.fin_settlements SET reversed_at = now() WHERE id = s"),
    "one ledger row per settlement+origin": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin,settlement_id) "
        "VALUES (o,a,'2026-10-10','in',1000,'settlement',s)"),
    "a ledger row is reversed at most once": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin,settlement_id,reverses_id) "
        "VALUES (o,a,'2026-10-11','out',1000,'settlement',s,l); "
        f"INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin,settlement_id,reverses_id) "
        "VALUES (o,a,'2026-10-11','out',1000,'settlement',s,l)"),
    "settlement ledger row needs its settlement": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin) VALUES (o,a,'2026-10-11','out',5,'settlement')"),
    "transfer needs its group": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin) VALUES (o,a,'2026-10-11','out',5,'transfer')"),
    "ledger amount must be positive": ("check_violation",
        f"INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin,settlement_id) VALUES (o,a,'2026-10-11','out',0,'fee',s)"),
    "category name unique per parent (case-insensitive)": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_categories(org_id,name,direction) VALUES (o,'A','income'); "
        f"INSERT INTO {SCHEMA}.fin_categories(org_id,name,direction) VALUES (o,'a','income')"),
    "cost center code unique per org": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_cost_centers(org_id,code,name) VALUES (o,'ADM','a'); "
        f"INSERT INTO {SCHEMA}.fin_cost_centers(org_id,code,name) VALUES (o,'ADM','b')"),
    "recurrence generation unique per due date": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_recurrences(id,org_id,template,frequency,next_date) VALUES (r,o,'{{}}','monthly','2026-11-01'); "
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents,recurrence_id) "
        "VALUES (o,'payable','x','2026-11-01','2026-11-05',10,r); "
        f"INSERT INTO {SCHEMA}.fin_entries(org_id,direction,description,competence_month,due_date,amount_cents,recurrence_id) "
        "VALUES (o,'payable','y','2026-11-01','2026-11-05',10,r)"),
    "statement sha256 unique per account": ("unique_violation",
        f"INSERT INTO {SCHEMA}.fin_statement_imports(org_id,account_id,format,filename,sha256) VALUES (o,a,'ofx','a.ofx','h'); "
        f"INSERT INTO {SCHEMA}.fin_statement_imports(org_id,account_id,format,filename,sha256) VALUES (o,a,'ofx','b.ofx','h')"),
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
    sql = finance_migration(FinanceConfig(schema=SCHEMA), SCHEMA)
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "finance_migration", "sql": sql, "mode": "file", "twice": True},
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
    step = replay["finance_migration"]
    assert step["failures"] == [], step["failures"]


@pytest.mark.parametrize("rule", list(RULES))
def test_database_rule_is_enforced(replay, rule):
    step = replay[f"rule: {rule}"]
    assert step["failures"] == [], f"{rule}: {step['failures']}"
