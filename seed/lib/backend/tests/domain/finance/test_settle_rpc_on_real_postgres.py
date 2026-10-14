"""The row-locked settle / reverse RPCs on a REAL Postgres (PGlite): the rules the Python mirror in the tests claims."""
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
SCHEMA = "finr"

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
DECLARE o uuid := gen_random_uuid(); a uuid := gen_random_uuid(); e uuid := gen_random_uuid();
        r jsonb; r2 jsonb; sid uuid; n int;
BEGIN
  INSERT INTO {SCHEMA}.fin_accounts(id,org_id,name,kind) VALUES (a,o,'Banco','checking');
  INSERT INTO {SCHEMA}.fin_entries(id,org_id,direction,description,competence_month,due_date,amount_cents)
    VALUES (e,o,'receivable','x','2026-10-01','2026-10-10',1000);
  {{body}}
END $$;
"""

def _row(kind: str, amount: int, ref: str = "NULL") -> str:
    return (f"jsonb_build_object('id', gen_random_uuid(), 'org_id', o, 'entry_id', e, 'account_id', a, 'kind', '{kind}', "
            f"'settled_on', '2026-10-10', 'amount_cents', {amount}, 'fee_cents', 0, 'created_at', now())")

SCENARIOS = {
    "a settlement inside the balance is inserted": f"""
  r := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('payment', 700)});
  IF r->>'status' <> 'ok' THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "the second settlement past the balance is refused (balance from the ROWS)": f"""
  r := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('payment', 700)});
  r2 := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('payment', 700)});
  IF r2->>'code' <> 'baixa_excede_saldo' THEN RAISE EXCEPTION 'bad %', r2; END IF;
  SELECT count(*) INTO n FROM {SCHEMA}.fin_settlements WHERE entry_id = e;
  IF n <> 1 THEN RAISE EXCEPTION 'overpaid: % rows', n; END IF;""",
    "a refund above what was paid is refused": f"""
  r := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('refund', 100)});
  IF r->>'code' <> 'estorno_excede_pago' THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "a cancelled entry refuses": f"""
  UPDATE {SCHEMA}.fin_entries SET status = 'cancelled' WHERE id = e;
  r := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('payment', 100)});
  IF r->>'code' <> 'lancamento_cancelado' THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "another org's entry is not found": f"""
  r := {SCHEMA}.fin_settle_entry_locked(gen_random_uuid(), e, {_row('payment', 100)});
  IF r->>'status' <> 'not_found' THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "reverse stamps the settlement and books the opposite ledger rows once": f"""
  r := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('payment', 700)});
  sid := (r->'settlement'->>'id')::uuid;
  INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin,settlement_id)
    VALUES (o,a,'2026-10-10','in',700,'settlement',sid);
  r2 := {SCHEMA}.fin_reverse_settlement_locked(o, sid, 'engano', NULL, '2026-10-11');
  IF r2->>'status' <> 'ok' THEN RAISE EXCEPTION 'bad %', r2; END IF;
  SELECT count(*) INTO n FROM {SCHEMA}.fin_ledger WHERE settlement_id = sid AND reverses_id IS NOT NULL AND direction = 'out';
  IF n <> 1 THEN RAISE EXCEPTION 'opposite rows: %', n; END IF;
  r2 := {SCHEMA}.fin_reverse_settlement_locked(o, sid, 'engano', NULL, '2026-10-11');
  IF r2->>'status' <> 'already_reversed' THEN RAISE EXCEPTION 'bad %', r2; END IF;""",
    "a payment cannot be reversed while a refund rests on it": f"""
  r := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('payment', 700)});
  sid := (r->'settlement'->>'id')::uuid;
  r2 := {SCHEMA}.fin_settle_entry_locked(o, e, {_row('refund', 700)});
  IF r2->>'status' <> 'ok' THEN RAISE EXCEPTION 'bad %', r2; END IF;
  r2 := {SCHEMA}.fin_reverse_settlement_locked(o, sid, 'engano', NULL, '2026-10-11');
  IF r2->>'code' <> 'baixa_com_estorno' THEN RAISE EXCEPTION 'bad %', r2; END IF;""",
}


@pytest.fixture(scope="module")
def replay() -> dict:
    sql = finance_migration(FinanceConfig(schema=SCHEMA), SCHEMA)
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "migration", "sql": sql, "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"scenario: {n}", "sql": _BASE.replace("{body}", b), "mode": "file", "twice": False} for n, b in SCENARIOS.items()),
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


def test_migration_with_the_rpcs_applies_twice(replay):
    assert replay["migration"]["failures"] == [], replay["migration"]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_rpc_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]
