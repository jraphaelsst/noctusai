"""The ERP link delta (`commerce_erp_migration`) on a REAL Postgres (PGlite, PG16/WASM).

Chain: base commerce -> items -> inventory -> money delta -> ERP link delta (applied TWICE: the chain-replay contract).
Then the database rules the quote / stock slices lean on: a product can only point at ITS org's item (composite FK), an
order made from a quote can exist once (`source_ref`), the channel is a closed vocabulary, a manual order needs no tender,
and the inventory RPCs hold / refuse / ship by the COMMERCE ORDER id (the last unit cannot be sold twice).
Skips visibly when `node` / the harness install is missing -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.commerce import CommerceConfig, commerce_migration
from noctusai_lib.domain.commerce.erp_sql import commerce_erp_migration
from noctusai_lib.domain.commerce.money_sql import commerce_money_migration
from noctusai_lib.domain.inventory import InventoryConfig, inventory_migration
from noctusai_lib.domain.items import ItemsConfig, items_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "comerp"

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
DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); c uuid := gen_random_uuid(); c2 uuid := gen_random_uuid();
        i uuid := gen_random_uuid(); i2 uuid := gen_random_uuid(); w uuid := gen_random_uuid();
        ord uuid := gen_random_uuid(); r jsonb; r2 jsonb; n int;
BEGIN
  INSERT INTO {SCHEMA}.itm_items(id, org_id, sku, name) VALUES (i, o, 'CAM-1', 'Camiseta'), (i2, o2, 'CAM-1', 'Camiseta de outro');
  INSERT INTO {SCHEMA}.commerce_customers(id, org_id, email) VALUES (c, o, 'a@b.c'), (c2, o2, 'd@e.f');
  {{body}}
END $$;
"""

_ORDER = (
    "INSERT INTO {s}.commerce_orders(id, org_id, token, customer_id, subtotal_cents, total_cents, channel, source_ref{extra_cols}) "
    "VALUES ({oid}, {org}, 'tok_' || gen_random_uuid()::text, {cust}, 100, 100, {channel}, {ref}{extra_vals})"
)


def order(oid="ord", org="o", cust="c", channel="'manual'", ref="NULL", extra_cols="", extra_vals="") -> str:
    return _ORDER.format(s=SCHEMA, oid=oid, org=org, cust=cust, channel=channel, ref=ref, extra_cols=extra_cols, extra_vals=extra_vals)


#: name -> PL/pgSQL that RAISEs when the rule does not hold.
SCENARIOS: dict[str, str] = {
    "a product links to its own org's item": f"""
  INSERT INTO {SCHEMA}.commerce_products(org_id, slug, title, product_type, fulfillment_type, item_id)
    VALUES (o, 'camiseta', 'Camiseta', 'physical', 'shipping', i);
  SELECT count(*) INTO n FROM {SCHEMA}.commerce_products WHERE item_id = i;
  IF n <> 1 THEN RAISE EXCEPTION 'product not linked'; END IF;""",
    "a product without an item still saves (digital products need none)": f"""
  INSERT INTO {SCHEMA}.commerce_products(org_id, slug, title, product_type, fulfillment_type)
    VALUES (o, 'ebook', 'Ebook', 'digital', 'digital_delivery');""",
    "a storefront order defaults its channel and may be created without tender or gateway": f"""
  INSERT INTO {SCHEMA}.commerce_orders(id, org_id, token, customer_id, subtotal_cents, total_cents)
    VALUES (ord, o, 'tok_' || gen_random_uuid()::text, c, 100, 100);
  SELECT count(*) INTO n FROM {SCHEMA}.commerce_orders WHERE id = ord AND channel = 'storefront' AND payment_method IS NULL AND gateway IS NULL;
  IF n <> 1 THEN RAISE EXCEPTION 'defaults wrong'; END IF;""",
    "the same source_ref is allowed in another org and repeated NULLs are allowed": f"""
  {order(oid="gen_random_uuid()", ref="'quote-1'")};
  {order(oid="gen_random_uuid()", org="o2", cust="c2", ref="'quote-1'")};
  {order(oid="gen_random_uuid()")};
  {order(oid="gen_random_uuid()")};""",
    "the inventory holds by the commerce order id and refuses the last unit twice": f"""
  INSERT INTO {SCHEMA}.inv_warehouses(id, org_id, name, code, is_default) VALUES (w, o, 'Matriz', 'MTZ', true);
  r := {SCHEMA}.inv_receive(o, jsonb_build_object('item_id', i, 'warehouse_id', w, 'qty', '1', 'unit_cost_cents', 1000));
  r := {SCHEMA}.inv_reserve(o, ord::text, jsonb_build_array(jsonb_build_object('item_id', i, 'qty', '1')), NULL, 'order');
  IF r->>'status' <> 'ok' THEN RAISE EXCEPTION 'reserve %', r; END IF;
  r2 := {SCHEMA}.inv_reserve(o, gen_random_uuid()::text, jsonb_build_array(jsonb_build_object('item_id', i, 'qty', '1')), NULL, 'order');
  IF r2->>'code' <> 'estoque_insuficiente' THEN RAISE EXCEPTION 'oversell not refused %', r2; END IF;
  r := {SCHEMA}.inv_reserve(o, ord::text, jsonb_build_array(jsonb_build_object('item_id', i, 'qty', '1')), NULL, 'order');
  IF r->>'status' <> 'replayed' THEN RAISE EXCEPTION 'reserve not idempotent %', r; END IF;
  r := {SCHEMA}.inv_commit(o, ord::text, NULL, NULL, 'order');
  r := {SCHEMA}.inv_commit(o, ord::text, NULL, NULL, 'order');
  IF r->>'status' <> 'replayed' THEN RAISE EXCEPTION 'commit not idempotent %', r; END IF;
  r := {SCHEMA}.inv_release(o, ord::text, NULL, NULL, 'order');
  IF r->>'code' <> 'reserva_consumida' THEN RAISE EXCEPTION 'release after commit must refuse %', r; END IF;""",
}

#: name -> (SQLSTATE condition, statement that MUST be refused).
RULES: dict[str, tuple[str, str]] = {
    "a product cannot point at another org's item": ("foreign_key_violation",
        f"INSERT INTO {SCHEMA}.commerce_products(org_id, slug, title, product_type, fulfillment_type, item_id) "
        "VALUES (o, 'x', 'X', 'physical', 'shipping', i2)"),
    "an order channel outside storefront | manual is refused": ("check_violation", order(channel="'telepathy'")),
    "one order per source record": ("unique_violation",
        f"{order(oid='gen_random_uuid()', ref=chr(39) + 'quote-9' + chr(39))}; {order(oid='gen_random_uuid()', ref=chr(39) + 'quote-9' + chr(39))}"),
    "a tender, when set, is still one of pix | boleto | credit_card": ("check_violation",
        order(extra_cols=", payment_method", extra_vals=", 'cash'")),
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
        {"product": SCHEMA, "file": "items", "sql": items_migration(ItemsConfig(schema=SCHEMA)), "mode": "file", "twice": True},
        {"product": SCHEMA, "file": "inventory", "sql": inventory_migration(InventoryConfig(schema=SCHEMA), SCHEMA), "mode": "file", "twice": True},
        {"product": SCHEMA, "file": "money", "sql": commerce_money_migration(cfg, SCHEMA), "mode": "file", "twice": True},
        {"product": SCHEMA, "file": "erp", "sql": commerce_erp_migration(cfg, SCHEMA), "mode": "file", "twice": True},
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


@pytest.mark.parametrize("step", ["base", "items", "inventory", "money", "erp"])
def test_the_chain_applies_and_every_delta_applies_twice(replay, step):
    assert replay[step]["failures"] == [], replay[step]["failures"]


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_link_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]


@pytest.mark.parametrize("name", list(RULES))
def test_database_rule_is_enforced(replay, name):
    assert replay[f"rule: {name}"]["failures"] == [], replay[f"rule: {name}"]["failures"]
