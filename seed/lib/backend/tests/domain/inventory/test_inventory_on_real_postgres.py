"""The inventory DDL + row-locked RPCs on a REAL Postgres (PGlite, PG16/WASM), for both generator variants.

The mock PostgREST client cannot enforce CHECKs, unique indexes, triggers or row locks, and a parser cannot prove
plpgsql RUNS. Every rule the organ claims is exercised here: moving-average cost, fractional KG, issue at average
cost, all-or-none reserve, idempotent replays, commit/release state machine, count adjustments, transfers,
the append-only kardex, and -- the point of the organ -- that the LAST unit cannot be sold twice.

Concurrency note: PGlite is a single connection, so two truly simultaneous reserves cannot be issued. What is
proven instead is the part that makes concurrency safe: (1) the second reserve of the last unit is REFUSED by the
RPC, and (2) the balance's `CHECK (on_hand - reserved >= 0)` independently refuses any write that would oversell
(`UPDATE ... SET reserved = ...`), i.e. even a caller that bypassed the RPC's check cannot oversell. Serialisation
of real concurrent callers is `SELECT ... FOR UPDATE` on the balance row inside `lock_balance` (asserted below by
the function body containing the lock) -- the same mechanism the finance settle RPC relies on.
Skips (visibly) when `node` or the harness install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.inventory import InventoryConfig, inventory_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

VARIANTS = {"invi": True, "invn": False}  # schema -> with_items


def _prelude(schema: str, with_items: bool) -> str:
    items = "CREATE TABLE IF NOT EXISTS @S@.itm_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL);" if with_items else ""
    return f"""
CREATE SCHEMA IF NOT EXISTS {schema};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
{items.replace("@S@", schema)}
"""


def _base(with_items: bool) -> str:
    item_ins = "INSERT INTO @S@.itm_items(id, org_id) VALUES (i, o), (i2, o);" if with_items else ""
    return f"""
DO $$
DECLARE o uuid := gen_random_uuid(); w1 uuid := gen_random_uuid(); w2 uuid := gen_random_uuid();
        i uuid := gen_random_uuid(); i2 uuid := gen_random_uuid(); other uuid := gen_random_uuid();
        r jsonb; b record; b2 record; n numeric; t text;
BEGIN
  {item_ins}
  INSERT INTO @S@.inv_warehouses(id, org_id, name, code, is_default) VALUES (w1, o, 'Matriz', 'MTZ', true);
  INSERT INTO @S@.inv_warehouses(id, org_id, name, code) VALUES (w2, o, 'Filial', 'FIL');
  {{body}}
END $$;
"""


def rec(qty="10", cost=100, wh="w1", item="i", ref=None) -> str:
    extra = f", 'source_ref', '{ref}'" if ref else ""
    return f"jsonb_build_object('item_id', {item}, 'warehouse_id', {wh}, 'qty', '{qty}', 'unit_cost_cents', {cost}{extra})"


def row(qty="1", wh="w1", item="i", ref=None) -> str:
    extra = f", 'source_ref', '{ref}'" if ref else ""
    return f"jsonb_build_object('item_id', {item}, 'warehouse_id', {wh}, 'qty', '{qty}'{extra})"


def lines(*specs: tuple[str, str, str]) -> str:
    """(item, qty, warehouse-or-'') -> a jsonb array literal expression."""
    parts = []
    for item, qty, wh in specs:
        wh_part = f", 'warehouse_id', {wh}" if wh else ""
        parts.append(f"jsonb_build_object('item_id', {item}, 'qty', '{qty}'{wh_part})")
    return "jsonb_build_array(" + ", ".join(parts) + ")"


def bal(var: str = "b", wh: str = "w1", item: str = "i") -> str:
    return (f"SELECT on_hand, reserved, avg_cost_cents INTO {var} FROM @S@.inv_stock_balances "
            f"WHERE org_id = o AND item_id = {item} AND warehouse_id = {wh};")


def need(cond: str, msg: str) -> str:
    return f"IF NOT ({cond}) THEN RAISE EXCEPTION '{msg}: %', r; END IF;"


def s_(call: str) -> str:
    return call.replace("RPC.", "@S@.inv_")


SCENARIOS: dict[str, str] = {
    "receive recomputes the moving average cost": f"""
  r := @S@.inv_receive(o, {rec('10', 100)});
  r := @S@.inv_receive(o, {rec('10', 200)});
  {need("r->>'status' = 'ok'", 'status')}
  {bal()}
  {need("b.on_hand = 20 AND b.avg_cost_cents = 150", 'avg')}
  {need("(r->'moves'->0->>'avg_cost_after_cents')::bigint = 150 AND (r->'moves'->0->>'on_hand_after')::numeric = 20", 'kardex running balance')}""",
    "fractional KG quantities keep three decimals": f"""
  r := @S@.inv_receive(o, {rec('2.500', 1000)});
  r := @S@.inv_receive(o, {rec('1.500', 2000)});
  {bal()}
  {need("b.on_hand = 4.000 AND b.avg_cost_cents = 1375", 'fractional avg')}""",
    "issue leaves at the CURRENT average cost and never below zero": f"""
  r := @S@.inv_receive(o, {rec('10', 100)});
  r := @S@.inv_receive(o, {rec('10', 200)});
  r := @S@.inv_issue(o, {row('4')});
  {need("r->>'status' = 'ok' AND (r->'moves'->0->>'unit_cost_cents')::bigint = 150", 'issue cost')}
  {bal()}
  {need("b.on_hand = 16 AND b.avg_cost_cents = 150", 'after issue')}
  r := @S@.inv_issue(o, {row('17')});
  {need("r->>'code' = 'estoque_insuficiente'", 'overissue')}
  {bal()}
  {need("b.on_hand = 16", 'unchanged')}""",
    "issue cannot take units that are reserved": f"""
  r := @S@.inv_receive(o, {rec('5', 100)});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '4', ''))}, NULL, 'order');
  r := @S@.inv_issue(o, {row('2')});
  {need("r->>'code' = 'estoque_insuficiente'", 'issue past available')}
  r := @S@.inv_issue(o, {row('1')});
  {need("r->>'status' = 'ok'", 'issue the free unit')}""",
    "a source_ref makes receive idempotent": f"""
  r := @S@.inv_receive(o, {rec('10', 100, ref='NF-1')});
  r := @S@.inv_receive(o, {rec('10', 100, ref='NF-1')});
  {need("r->>'status' = 'replayed'", 'replay')}
  {bal()}
  {need("b.on_hand = 10", 'no double receipt')}""",
    "receive rejects bad input explicitly": f"""
  r := @S@.inv_receive(o, jsonb_build_object('item_id', i, 'warehouse_id', w1, 'qty', '1'));
  {need("r->>'code' = 'custo_invalido'", 'missing cost')}
  r := @S@.inv_receive(o, {rec('0', 100)});
  {need("r->>'code' = 'quantidade_invalida'", 'zero qty')}
  r := @S@.inv_receive(o, {rec('-1', 100)});
  {need("r->>'code' = 'quantidade_invalida'", 'negative qty')}""",
    "count adjustment books the signed delta and is a no-op when equal": f"""
  r := @S@.inv_receive(o, {rec('10', 100)});
  r := @S@.inv_adjust(o, jsonb_build_object('item_id', i, 'warehouse_id', w1, 'counted_qty', '7'));
  {need("(r->'moves'->0->>'qty')::numeric = -3 AND r->'moves'->0->>'kind' = 'adjust'", 'loss')}
  {bal()}
  {need("b.on_hand = 7 AND b.avg_cost_cents = 100", 'after count down')}
  r := @S@.inv_adjust(o, jsonb_build_object('item_id', i, 'warehouse_id', w1, 'counted_qty', '9'));
  {need("(r->'moves'->0->>'qty')::numeric = 2", 'gain')}
  r := @S@.inv_adjust(o, jsonb_build_object('item_id', i, 'warehouse_id', w1, 'counted_qty', '9'));
  {need("jsonb_array_length(r->'moves') = 0", 'no-op')}""",
    "a count below the reserved quantity is refused": f"""
  r := @S@.inv_receive(o, {rec('10', 100)});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '6', ''))}, NULL, 'order');
  r := @S@.inv_adjust(o, jsonb_build_object('item_id', i, 'warehouse_id', w1, 'counted_qty', '5'));
  {need("r->>'code' = 'abaixo_reservado'", 'below reserved')}
  r := @S@.inv_adjust(o, jsonb_build_object('item_id', i, 'warehouse_id', w1, 'counted_qty', '6'));
  {need("r->>'status' = 'ok'", 'count at reserved')}""",
    "a count into an empty balance books a gain at the given cost": f"""
  r := @S@.inv_adjust(o, jsonb_build_object('item_id', i, 'warehouse_id', w1, 'counted_qty', '3', 'unit_cost_cents', 250));
  {bal()}
  {need("b.on_hand = 3 AND b.avg_cost_cents = 250", 'opening via count')}""",
    "transfer moves stock at the origin's average cost, atomically, in two kardex rows": f"""
  r := @S@.inv_receive(o, {rec('10', 100)});
  r := @S@.inv_receive(o, {rec('10', 200)});
  r := @S@.inv_transfer(o, jsonb_build_object('item_id', i, 'from_warehouse_id', w1, 'to_warehouse_id', w2, 'qty', '5'));
  {need("jsonb_array_length(r->'moves') = 2 AND r->'moves'->0->>'transfer_group' = r->'moves'->1->>'transfer_group'", 'two rows')}
  {bal('b', 'w1')}
  {need("b.on_hand = 15 AND b.avg_cost_cents = 150", 'origin')}
  {bal('b2', 'w2')}
  {need("b2.on_hand = 5 AND b2.avg_cost_cents = 150", 'destination')}
  r := @S@.inv_transfer(o, jsonb_build_object('item_id', i, 'from_warehouse_id', w1, 'to_warehouse_id', w1, 'qty', '1'));
  {need("r->>'code' = 'transferencia_mesmo_deposito'", 'same wh')}
  r := @S@.inv_transfer(o, jsonb_build_object('item_id', i, 'from_warehouse_id', w1, 'to_warehouse_id', w2, 'qty', '99'));
  {need("r->>'code' = 'estoque_insuficiente'", 'insufficient')}
  {bal('b2', 'w2')}
  {need("b2.on_hand = 5", 'destination untouched by a refused transfer')}""",
    "a transfer blends into the destination's existing average": f"""
  r := @S@.inv_receive(o, {rec('10', 100)});
  r := @S@.inv_receive(o, {rec('10', 400, wh='w2')});
  r := @S@.inv_transfer(o, jsonb_build_object('item_id', i, 'from_warehouse_id', w1, 'to_warehouse_id', w2, 'qty', '10'));
  {bal('b2', 'w2')}
  {need("b2.on_hand = 20 AND b2.avg_cost_cents = 250", 'blended')}""",
    "OVERSELLING: the last unit cannot be reserved twice": f"""
  r := @S@.inv_receive(o, {rec('1', 5000)});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '1', ''))}, NULL, 'order');
  {need("r->>'status' = 'ok'", 'first reserve')}
  r := @S@.inv_reserve(o, 'ORD-2', {lines(('i', '1', ''))}, NULL, 'order');
  {need("r->>'status' = 'refused' AND r->>'code' = 'estoque_insuficiente'", 'second reserve of the last unit')}
  {bal()}
  {need("b.on_hand = 1 AND b.reserved = 1", 'one hold only')}
  SELECT count(*) INTO n FROM @S@.inv_stock_moves WHERE org_id = o AND source_ref = 'ORD-2';
  {need("n = 0", 'a refused reserve leaves no kardex row')}""",
    "OVERSELLING backstop: the balance CHECKs refuse any write that would oversell": f"""
  r := @S@.inv_receive(o, {rec('1', 5000)});
  BEGIN
    UPDATE @S@.inv_stock_balances SET reserved = 2 WHERE org_id = o AND item_id = i;
    RAISE EXCEPTION 'NOT ENFORCED: reserved above on_hand';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    UPDATE @S@.inv_stock_balances SET on_hand = -1 WHERE org_id = o AND item_id = i;
    RAISE EXCEPTION 'NOT ENFORCED: negative on_hand';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    UPDATE @S@.inv_stock_balances SET reserved = -1 WHERE org_id = o AND item_id = i;
    RAISE EXCEPTION 'NOT ENFORCED: negative reserved';
  EXCEPTION WHEN check_violation THEN NULL;
  END;""",
    "reserve is all-or-none across lines": f"""
  r := @S@.inv_receive(o, {rec('5', 100)});
  r := @S@.inv_receive(o, {rec('1', 100, item='i2')});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '2', ''), ('i2', '2', ''))}, NULL, 'order');
  {need("r->>'code' = 'estoque_insuficiente' AND r->>'item_id' = i2::text", 'second line refuses')}
  {bal()}
  {need("b.reserved = 0", 'first line rolled back')}
  SELECT count(*) INTO n FROM @S@.inv_stock_moves WHERE org_id = o AND source_ref = 'ORD-1';
  {need("n = 0", 'no kardex row survived')}""",
    "reserve is idempotent on order_ref and uses the default warehouse": f"""
  r := @S@.inv_receive(o, {rec('5', 100)});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '2', ''))}, NULL, 'order');
  {need("r->>'status' = 'ok' AND r->'moves'->0->>'warehouse_id' = w1::text", 'default warehouse')}
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '2', ''))}, NULL, 'order');
  {need("r->>'status' = 'replayed'", 'replay')}
  {bal()}
  {need("b.reserved = 2", 'held once')}""",
    "reserve without a default warehouse and without one on the line is refused": f"""
  UPDATE @S@.inv_warehouses SET is_default = false WHERE id = w1;
  r := @S@.inv_receive(o, {rec('5', 100)});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '2', ''))}, NULL, 'order');
  {need("r->>'code' = 'sem_deposito_padrao'", 'no default')}
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '2', 'w1'))}, NULL, 'order');
  {need("r->>'status' = 'ok'", 'explicit warehouse')}""",
    "commit turns the reservation into a stock-out at average cost, once": f"""
  r := @S@.inv_receive(o, {rec('10', 100)});
  r := @S@.inv_receive(o, {rec('10', 200)});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '3', ''))}, NULL, 'order');
  r := @S@.inv_commit(o, 'ORD-1', NULL, NULL, 'order');
  {need("r->>'status' = 'ok' AND r->'moves'->0->>'kind' = 'commit' AND (r->'moves'->0->>'unit_cost_cents')::bigint = 150", 'commit')}
  {bal()}
  {need("b.on_hand = 17 AND b.reserved = 0 AND b.avg_cost_cents = 150", 'after commit')}
  r := @S@.inv_commit(o, 'ORD-1', NULL, NULL, 'order');
  {need("r->>'status' = 'replayed'", 'commit replay')}
  {bal()}
  {need("b.on_hand = 17", 'no double stock-out')}
  r := @S@.inv_release(o, 'ORD-1', NULL, NULL, 'order');
  {need("r->>'code' = 'reserva_consumida'", 'release after commit')}""",
    "release frees the hold; commit after release is refused; nothing reserved is a no-op": f"""
  r := @S@.inv_receive(o, {rec('5', 100)});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '4', ''))}, NULL, 'order');
  r := @S@.inv_release(o, 'ORD-1', NULL, NULL, 'order');
  {need("r->>'status' = 'ok' AND r->'moves'->0->>'kind' = 'release'", 'release')}
  {bal()}
  {need("b.reserved = 0 AND b.on_hand = 5", 'freed')}
  r := @S@.inv_release(o, 'ORD-1', NULL, NULL, 'order');
  {need("r->>'status' = 'replayed'", 'release replay')}
  r := @S@.inv_commit(o, 'ORD-1', NULL, NULL, 'order');
  {need("r->>'code' = 'reserva_liberada'", 'commit after release')}
  r := @S@.inv_release(o, 'ORD-NEVER', NULL, NULL, 'order');
  {need("r->>'status' = 'ok' AND jsonb_array_length(r->'moves') = 0", 'release of nothing')}
  r := @S@.inv_commit(o, 'ORD-NEVER', NULL, NULL, 'order');
  {need("r->>'code' = 'sem_reserva'", 'commit of nothing')}""",
    "commit and release can target a subset of lines and refuse a divergent quantity": f"""
  r := @S@.inv_receive(o, {rec('5', 100)});
  r := @S@.inv_receive(o, {rec('5', 100, item='i2')});
  r := @S@.inv_reserve(o, 'ORD-1', {lines(('i', '2', ''), ('i2', '3', ''))}, NULL, 'order');
  r := @S@.inv_commit(o, 'ORD-1', {lines(('i', '9', ''))}, NULL, 'order');
  {need("r->>'code' = 'quantidade_divergente'", 'divergent qty')}
  r := @S@.inv_commit(o, 'ORD-1', {lines(('i', '2', ''))}, NULL, 'order');
  {need("jsonb_array_length(r->'moves') = 1", 'only line i')}
  {bal('b', 'w1', 'i2')}
  {need("b.reserved = 3 AND b.on_hand = 5", 'line i2 untouched')}""",
    "another org's warehouse is not usable": f"""
  r := @S@.inv_receive(gen_random_uuid(), {rec('1', 100)});
  {need("r->>'code' = 'deposito_invalido'", 'foreign warehouse')}
  r := @S@.inv_reserve(gen_random_uuid(), 'ORD-1', {lines(('i', '1', 'w1'))}, NULL, 'order');
  {need("r->>'code' = 'deposito_invalido'", 'foreign warehouse on reserve')}""",
    "the kardex is append-only (update, delete and truncate are refused)": f"""
  r := @S@.inv_receive(o, {rec('3', 100)});
  BEGIN UPDATE @S@.inv_stock_moves SET qty = 99 WHERE org_id = o; RAISE EXCEPTION 'NOT ENFORCED: update';
  EXCEPTION WHEN SQLSTATE 'IN002' THEN NULL; END;
  BEGIN DELETE FROM @S@.inv_stock_moves WHERE org_id = o; RAISE EXCEPTION 'NOT ENFORCED: delete';
  EXCEPTION WHEN SQLSTATE 'IN002' THEN NULL; END;
  BEGIN TRUNCATE @S@.inv_stock_moves; RAISE EXCEPTION 'NOT ENFORCED: truncate';
  EXCEPTION WHEN SQLSTATE 'IN002' THEN NULL; END;""",
    "kardex constraints: qty sign, idempotency key, transfer group, source_ref": f"""
  BEGIN
    INSERT INTO @S@.inv_stock_moves(org_id,item_id,warehouse_id,kind,qty,on_hand_after,reserved_after,avg_cost_after_cents)
      VALUES (o,i,w1,'in',-1,0,0,0);
    RAISE EXCEPTION 'NOT ENFORCED: negative in';
  EXCEPTION WHEN check_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.inv_stock_moves(org_id,item_id,warehouse_id,kind,qty,on_hand_after,reserved_after,avg_cost_after_cents)
      VALUES (o,i,w1,'adjust',0,0,0,0);
    RAISE EXCEPTION 'NOT ENFORCED: zero qty';
  EXCEPTION WHEN check_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.inv_stock_moves(org_id,item_id,warehouse_id,kind,qty,on_hand_after,reserved_after,avg_cost_after_cents)
      VALUES (o,i,w1,'transfer_in',1,0,0,0);
    RAISE EXCEPTION 'NOT ENFORCED: transfer without group';
  EXCEPTION WHEN check_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.inv_stock_moves(org_id,item_id,warehouse_id,kind,qty,source,source_ref,on_hand_after,reserved_after,avg_cost_after_cents)
      VALUES (o,i,w1,'in',1,'order','X',1,0,0);
    INSERT INTO @S@.inv_stock_moves(org_id,item_id,warehouse_id,kind,qty,source,source_ref,on_hand_after,reserved_after,avg_cost_after_cents)
      VALUES (o,i,w1,'in',1,'order','X',2,0,0);
    RAISE EXCEPTION 'NOT ENFORCED: duplicate idempotency key';
  EXCEPTION WHEN unique_violation THEN NULL; END;""",
    "warehouse constraints: one default, unique code (case-insensitive), no inactive default": f"""
  BEGIN
    INSERT INTO @S@.inv_warehouses(org_id, name, code, is_default) VALUES (o, 'X', 'X1', true);
    RAISE EXCEPTION 'NOT ENFORCED: second default';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.inv_warehouses(org_id, name, code) VALUES (o, 'X', 'mtz');
    RAISE EXCEPTION 'NOT ENFORCED: duplicate code';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.inv_warehouses(org_id, name, code, is_default, active) VALUES (gen_random_uuid(), 'X', 'X2', true, false);
    RAISE EXCEPTION 'NOT ENFORCED: inactive default';
  EXCEPTION WHEN check_violation THEN NULL; END;
  INSERT INTO @S@.inv_warehouses(org_id, name, code, is_default) VALUES (gen_random_uuid(), 'Other org', 'MTZ', true);""",
    "every secdef function pins search_path to pg_catalog first, locks the balance row, and is not callable by clients": """
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '@S@' AND p.proname LIKE 'inv\\_%' AND p.prosecdef
      AND p.proconfig::text LIKE '%search_path=pg_catalog, @S@, pg_temp%';
  IF n <> 9 THEN RAISE EXCEPTION 'search_path not pinned on % of 9 secdef functions', n; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '@S@' AND p.proname = 'inv_lock_balance' AND p.prosrc ILIKE '%FOR UPDATE%';
  IF n <> 1 THEN RAISE EXCEPTION 'lock_balance does not take FOR UPDATE'; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '@S@' AND p.proname LIKE 'inv\\_%' AND p.prosecdef
      AND (has_function_privilege('anon', p.oid, 'EXECUTE') OR has_function_privilege('authenticated', p.oid, 'EXECUTE'));
  IF n <> 0 THEN RAISE EXCEPTION '% secdef functions executable by client roles', n; END IF;""",
}

ITEMS_ONLY: dict[str, str] = {
    "an item that is not this org's is refused (the FK alone cannot see the org)": f"""
  r := @S@.inv_receive(o, {rec('1', 100, item='gen_random_uuid()')});
  {need("r->>'code' = 'item_invalido'", 'unknown item')}
  INSERT INTO @S@.itm_items(id, org_id) VALUES (other, gen_random_uuid());
  r := @S@.inv_receive(o, {rec('1', 100, item='other')});
  {need("r->>'code' = 'item_invalido'", 'foreign item')}""",
    "with items the balance carries an FK to itm_items": f"""
  BEGIN
    INSERT INTO @S@.inv_stock_balances(org_id, item_id, warehouse_id) VALUES (o, gen_random_uuid(), w1);
    RAISE EXCEPTION 'NOT ENFORCED: item FK';
  EXCEPTION WHEN foreign_key_violation THEN NULL; END;""",
}

NO_ITEMS_ONLY: dict[str, str] = {
    "without items the item id is an opaque uuid (no FK)": f"""
  r := @S@.inv_receive(o, {rec('1', 100, item='gen_random_uuid()')});
  {need("r->>'status' = 'ok'", 'opaque item')}""",
}


def _scenarios(with_items: bool) -> dict[str, str]:
    return {**SCENARIOS, **(ITEMS_ONLY if with_items else NO_ITEMS_ONLY)}


def _run(schema: str, with_items: bool) -> dict:
    cfg = InventoryConfig(schema=schema, with_items=with_items)
    migration = inventory_migration(cfg, schema)
    base = _base(with_items)
    steps = [
        {"product": schema, "file": "prelude", "sql": _prelude(schema, with_items), "mode": "file", "twice": False},
        {"product": schema, "file": "migration", "sql": migration, "mode": "file", "twice": True},
        *(
            {"product": schema, "file": f"scenario: {name}", "sql": base.replace("{body}", body).replace("@S@", schema), "mode": "file", "twice": False}
            for name, body in _scenarios(with_items).items()
        ),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=600,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


@pytest.fixture(scope="module", params=list(VARIANTS), ids=lambda s: f"with_items={VARIANTS[s]}")
def replay(request) -> tuple[str, dict]:
    schema = request.param
    return schema, _run(schema, VARIANTS[schema])


def test_migration_applies_twice(replay):
    _, steps = replay
    assert steps["migration"]["failures"] == [], steps["migration"]["failures"]


def _names() -> list[str]:
    return sorted({*SCENARIOS, *ITEMS_ONLY, *NO_ITEMS_ONLY})


@pytest.mark.parametrize("name", _names())
def test_scenario(replay, name):
    schema, steps = replay
    key = f"scenario: {name}"
    if key not in steps:
        pytest.skip("scenario applies to the other generator variant")
    assert steps[key]["failures"] == [], steps[key]["failures"]
