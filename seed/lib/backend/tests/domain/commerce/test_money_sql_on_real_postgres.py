"""The P4 money DDL + `commerce_create_refund` on a REAL Postgres (PGlite, PG16/WASM).

Base migration, then the money delta applied TWICE (the chain-replay contract), then the
refund RPC's rules exercised in SQL. A mock cannot prove a lock, a partial unique index or
that a PL/pgSQL body compiles. Skips visibly when `node` / the harness install is missing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.commerce import CommerceConfig, commerce_migration
from noctusai_lib.domain.commerce.money_sql import commerce_money_migration

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
DECLARE o uuid := gen_random_uuid(); c uuid := gen_random_uuid(); ord uuid := gen_random_uuid();
        ch uuid := gen_random_uuid(); r jsonb; r2 jsonb; rid uuid; n int;
        tok text := 'tok_' || gen_random_uuid()::text; gid text := 'pay_' || gen_random_uuid()::text;
BEGIN
  INSERT INTO {SCHEMA}.commerce_customers(id,org_id,email) VALUES (c,o,'a@b.c');
  INSERT INTO {SCHEMA}.commerce_orders(id,org_id,token,customer_id,status,subtotal_cents,total_cents,payment_method,gateway,gateway_charge_id,charge_attempts)
    VALUES (ord,o,tok,c,'paid',10000,10000,'pix','asaas',gid,1);
  INSERT INTO {SCHEMA}.commerce_order_charges(id,org_id,order_id,attempt,gateway,gateway_charge_id,payment_method,amount_cents,status)
    VALUES (ch,o,ord,1,'asaas',gid,'pix',10000,'paid');
  {{body}}
END $$;
"""

#: name -> PL/pgSQL that RAISEs when the rule does not hold.
SCENARIOS: dict[str, str] = {
    "refund creates a requested row and reports the balance": f"""
  r := {SCHEMA}.commerce_create_refund(o, ord, 3000, 'x', NULL, 'k1');
  IF r->>'status' <> 'created' OR (r->>'refundable_cents')::bigint <> 10000 THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "a second refund while one is requested is refused": f"""
  r := {SCHEMA}.commerce_create_refund(o, ord, 3000, 'x', NULL, 'k1');
  r2 := {SCHEMA}.commerce_create_refund(o, ord, 1000, 'y', NULL, 'k2');
  IF r2->>'code' <> 'estorno_em_andamento' THEN RAISE EXCEPTION 'bad %', r2; END IF;""",
    "the refundable balance excludes only failed refunds": f"""
  r := {SCHEMA}.commerce_create_refund(o, ord, 3000, 'x', NULL, 'k1');
  rid := (r->'refund'->>'id')::uuid;
  UPDATE {SCHEMA}.commerce_refunds SET status = 'done', done_at = now() WHERE id = rid;
  r2 := {SCHEMA}.commerce_create_refund(o, ord, 8000, 'y', NULL, 'k2');
  IF r2->>'code' <> 'valor_excede_saldo' OR (r2->>'refundable_cents')::bigint <> 7000 THEN RAISE EXCEPTION 'bad %', r2; END IF;
  UPDATE {SCHEMA}.commerce_refunds SET status = 'failed' WHERE id = rid;
  r2 := {SCHEMA}.commerce_create_refund(o, ord, 8000, 'y', NULL, 'k3');
  IF r2->>'status' <> 'created' THEN RAISE EXCEPTION 'failed refunds must not count: %', r2; END IF;""",
    "the same idempotency key replays the first refund": f"""
  r := {SCHEMA}.commerce_create_refund(o, ord, 3000, 'x', NULL, 'k1');
  r2 := {SCHEMA}.commerce_create_refund(o, ord, 3000, 'x', NULL, 'k1');
  IF r2->>'status' <> 'replayed' OR r2->'refund'->>'id' <> r->'refund'->>'id' THEN RAISE EXCEPTION 'bad %', r2; END IF;""",
    "no amount means the whole remaining balance": f"""
  r := {SCHEMA}.commerce_create_refund(o, ord, NULL, 'x', NULL, NULL);
  IF (r->'refund'->>'amount_cents')::bigint <> 10000 THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "an unpaid order is not refundable": f"""
  UPDATE {SCHEMA}.commerce_orders SET status = 'expired' WHERE id = ord;
  r := {SCHEMA}.commerce_create_refund(o, ord, 1000, 'x', NULL, NULL);
  IF r->>'code' <> 'pedido_nao_reembolsavel' THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "an installment order is refundable through the RPC and reports its parcelamento id": f"""
  UPDATE {SCHEMA}.commerce_order_charges SET installment_count = 6, gateway_installment_id = 'ins_1' WHERE id = ch;
  r := {SCHEMA}.commerce_create_refund(o, ord, 1000, 'x', NULL, NULL);
  IF r->>'status' <> 'created' OR r->'charge'->>'gateway_installment_id' <> 'ins_1'
     OR (r->'charge'->>'installment_count')::int <> 6 THEN RAISE EXCEPTION 'bad %', r; END IF;""",
    "the refund RPC pins search_path to pg_catalog first": f"""
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '{SCHEMA}' AND p.proname = 'commerce_create_refund' AND p.prosecdef
      AND p.proconfig::text LIKE '%search_path=pg_catalog, {SCHEMA}, pg_temp%';
  IF n <> 1 THEN RAISE EXCEPTION 'search_path not pinned'; END IF;""",
    "another org cannot refund this order": f"""
  r := {SCHEMA}.commerce_create_refund(gen_random_uuid(), ord, 1000, 'x', NULL, NULL);
  IF r->>'code' <> 'pedido_nao_encontrado' THEN RAISE EXCEPTION 'bad %', r; END IF;""",
}

#: name -> (SQLSTATE condition, statement that MUST be refused).
RULES: dict[str, tuple[str, str]] = {
    "two requested refunds on one order": ("unique_violation",
        f"INSERT INTO {SCHEMA}.commerce_refunds(org_id,order_id,charge_id,amount_cents) VALUES (o,ord,ch,1); "
        f"INSERT INTO {SCHEMA}.commerce_refunds(org_id,order_id,charge_id,amount_cents) VALUES (o,ord,ch,2)"),
    "refund amount must be positive": ("check_violation",
        f"INSERT INTO {SCHEMA}.commerce_refunds(org_id,order_id,charge_id,amount_cents) VALUES (o,ord,ch,0)"),
    "a done refund needs done_at": ("check_violation",
        f"INSERT INTO {SCHEMA}.commerce_refunds(org_id,order_id,charge_id,amount_cents,status) VALUES (o,ord,ch,5,'done')"),
    "gateway refund id unique per org": ("unique_violation",
        f"INSERT INTO {SCHEMA}.commerce_refunds(org_id,order_id,charge_id,amount_cents,status,done_at,gateway_refund_id) VALUES (o,ord,ch,5,'done',now(),'re_1'); "
        f"INSERT INTO {SCHEMA}.commerce_refunds(org_id,order_id,charge_id,amount_cents,status,done_at,gateway_refund_id) VALUES (o,ord,ch,5,'done',now(),'re_1')"),
    "one charge row per order attempt": ("unique_violation",
        f"INSERT INTO {SCHEMA}.commerce_order_charges(org_id,order_id,attempt,gateway,gateway_charge_id,payment_method,amount_cents) VALUES (o,ord,1,'asaas','pay_2','pix',5)"),
    "one row per gateway charge id": ("unique_violation",
        f"INSERT INTO {SCHEMA}.commerce_order_charges(org_id,order_id,attempt,gateway,gateway_charge_id,payment_method,amount_cents) VALUES (o,ord,2,'asaas',gid,'pix',5)"),
    "one reminder per order and kind": ("unique_violation",
        f"INSERT INTO {SCHEMA}.commerce_order_reminders(org_id,order_id,kind) VALUES (o,ord,'before_expiry'); "
        f"INSERT INTO {SCHEMA}.commerce_order_reminders(org_id,order_id,kind) VALUES (o,ord,'before_expiry')"),
    "disputed is a legal order status": ("check_violation",
        f"UPDATE {SCHEMA}.commerce_orders SET status = 'nonsense' WHERE id = ord"),
    "interest-free cannot exceed the maximum": ("check_violation",
        f"INSERT INTO {SCHEMA}.commerce_store_profiles(org_id,legal_name,trade_name,cnpj,tax_regime,installments_max,installments_interest_free) "
        "VALUES (o,'a','b','1','simples',2,5)"),
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
    cfg = CommerceConfig(schema=SCHEMA)
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "base", "sql": commerce_migration(cfg, SCHEMA), "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "money", "sql": commerce_money_migration(cfg, SCHEMA), "mode": "file", "twice": True},
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


def test_base_then_money_delta_applies_and_the_delta_applies_twice(replay):
    assert replay["base"]["failures"] == [], replay["base"]["failures"]
    assert replay["money"]["failures"] == [], replay["money"]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_refund_rpc_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


@pytest.mark.parametrize("name", list(RULES))
def test_database_rule_is_enforced(replay, name):
    assert replay[f"rule: {name}"]["failures"] == [], replay[f"rule: {name}"]["failures"]
