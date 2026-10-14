"""The purchasing DDL + row-locked RPCs on a REAL Postgres (PGlite, PG16/WASM), next to the REAL parties, inventory and
finance(with_parties) migrations of the same schema (the cross-organ contract is proven, not mocked).

What a mock cannot show and this does: the order state machine, the number counter that a refused save does not burn, the
landed-cost proration (telescopes to EXACTLY freight + other - discount across partial receipts), over-receipt refusal,
idempotent receipts, composite org FKs, and that finance accepts `source='purchasing'` + a linked `party_id` while the
inventory kardex is idempotent on the receipt-line id.
Skips (visibly) when `node` or the harness install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.finance import FinanceConfig, finance_migration
from noctusai_lib.domain.inventory import InventoryConfig, inventory_migration
from noctusai_lib.domain.parties import PartiesConfig, parties_migration
from noctusai_lib.domain.purchasing import PurchasingConfig, purchasing_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

FULL, BARE = "purf", "purb"

PRELUDE = """
CREATE SCHEMA IF NOT EXISTS {s};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE TABLE IF NOT EXISTS {s}.itm_items (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL);
"""

BASE = """
DO $$
DECLARE o uuid := gen_random_uuid(); other uuid := gen_random_uuid(); p uuid := gen_random_uuid(); pf uuid := gen_random_uuid();
        w uuid := gen_random_uuid(); i1 uuid := gen_random_uuid(); i2 uuid := gen_random_uuid(); ifx uuid := gen_random_uuid();
        r jsonb; r2 jsonb; u uuid; oid uuid; oid2 uuid; l1 uuid; l2 uuid; rid uuid; rid2 uuid; n numeric; k bigint; k2 bigint; t text;
BEGIN
  INSERT INTO @S@.pty_parties(id, org_id, kind, legal_name) VALUES (p, o, 'PJ', 'Fornecedor Ltda'), (pf, other, 'PJ', 'Forasteiro');
  INSERT INTO @S@.inv_warehouses(id, org_id, name, code, is_default) VALUES (w, o, 'Matriz', 'MTZ', true);
  INSERT INTO @S@.itm_items(id, org_id) VALUES (i1, o), (i2, o), (ifx, other);
  {body}
END $$;
"""


def line(item: str = "i1", qty: str = "10", cost: int = 1000, desc: str = "Produto") -> str:
    return f"jsonb_build_object('item_id', {item}, 'description', '{desc}', 'qty', '{qty}', 'unit_cost_cents', {cost})"


def order(lines: list[str] | None = None, **over) -> str:
    """jsonb literal for `pur_save_order`; `over` values are raw SQL expressions."""
    lines = lines if lines is not None else [line("i1", "10", 1000), line("i2", "2.5", 333)]
    fields = {"party_id": "p", "supplier_name": "'Fornecedor Ltda'", "warehouse_id": "w", "freight_cents": "1000", "discount_cents": "500",
              "other_cents": "0", "installments_count": "1", "first_due_days": "30", "interval_days": "30", **over}
    parts = ", ".join(f"'{key}', {val}" for key, val in fields.items())
    return f"jsonb_build_object({parts}, 'lines', jsonb_build_array({', '.join(lines)}))"


def need(cond: str, msg: str) -> str:
    return f"IF NOT ({cond}) THEN RAISE EXCEPTION '{msg}: %', r; END IF;"


def save(var: str = "r", oid: str = "NULL", row: str | None = None) -> str:
    return f"{var} := @S@.pur_save_order(o, {oid}, {row or order()});"


def lines_of(oid: str) -> str:
    return (f"SELECT id INTO l1 FROM @S@.pur_order_lines WHERE order_id = {oid} AND line_no = 1;"
            f" SELECT id INTO l2 FROM @S@.pur_order_lines WHERE order_id = {oid} AND line_no = 2;")


def recv(lid: str, qty: str, key: str | None = None) -> str:
    extra = f", 'idempotency_key', '{key}'" if key else ""
    return f"jsonb_build_object('received_on', '2026-10-14', 'lines', jsonb_build_array(jsonb_build_object('order_line_id', {lid}, 'qty', '{qty}')){extra})"


def recv_all(l1: str = "l1", l2: str = "l2") -> str:
    return (f"jsonb_build_object('received_on', '2026-10-14', 'lines', jsonb_build_array("
            f"jsonb_build_object('order_line_id', {l1}, 'qty', '10'), jsonb_build_object('order_line_id', {l2}, 'qty', '2.5')))")


SETUP_APPROVED = f"""
  {save()}
  oid := (r->>'order_id')::uuid; {lines_of('oid')}
  r := @S@.pur_transition(o, oid, 'approve', NULL, NULL);
  {need("r->>'status' = 'ok'", 'approve')}"""

SCENARIOS: dict[str, str] = {
    "save computes line totals, goods, total and numbers orders sequentially per org": f"""
  {save()}
  {need("r->>'status' = 'ok'", 'save')}
  oid := (r->>'order_id')::uuid;
  SELECT goods_cents, total_cents, number, status INTO k, k2, n, t FROM @S@.pur_orders WHERE id = oid;
  {need("k = 10833 AND k2 = 11333 AND n = 1 AND t = 'draft'", 'totals (10000 + round(2.5*333)=833 half-up; +1000 freight -500 discount)')}
  {save()}
  SELECT number INTO n FROM @S@.pur_orders WHERE id = (r->>'order_id')::uuid;
  {need("n = 2", 'second number')}
  r := @S@.pur_save_order(other, NULL, {order(party_id='pf', warehouse_id='NULL', lines=[line('ifx')])});
  {need("r->>'code' = 'deposito_invalido'", 'foreign org has no warehouse yet')}""",
    "a refused save burns no number and leaves nothing behind": f"""
  r := @S@.pur_save_order(o, NULL, {order(lines=[])});
  {need("r->>'code' = 'sem_linhas'", 'no lines')}
  r := @S@.pur_save_order(o, NULL, {order(party_id='pf')});
  {need("r->>'code' = 'fornecedor_invalido'", 'foreign party')}
  r := @S@.pur_save_order(o, NULL, {order(lines=[line('ifx')])});
  {need("r->>'code' = 'item_invalido'", 'foreign item')}
  r := @S@.pur_save_order(o, NULL, {order(lines=["jsonb_build_object('description', 'x', 'qty', '1', 'unit_cost_cents', 100)"])});
  {need("r->>'code' = 'item_obrigatorio'", 'stock needs an item')}
  r := @S@.pur_save_order(o, NULL, {order(warehouse_id='NULL')});
  {need("r->>'code' = 'deposito_invalido'", 'warehouse required')}
  r := @S@.pur_save_order(o, NULL, {order(discount_cents='999999')});
  {need("r->>'code' = 'desconto_excede'", 'discount')}
  r := @S@.pur_save_order(o, NULL, {order(lines=[line('i1', '0')])});
  {need("r->>'code' = 'quantidade_invalida'", 'qty')}
  r := @S@.pur_save_order(o, NULL, {order(lines=[line('i1', '1', 0)])});
  {need("r->>'code' = 'pedido_sem_valor'", 'zero value')}
  r := @S@.pur_save_order(o, NULL, {order(installments_count='0')});
  {need("r->>'code' = 'parcelas_invalidas'", 'installments')}
  r := @S@.pur_save_order(o, NULL, {order(installments_count='3', interval_days='0')});
  {need("r->>'code' = 'prazo_invalido'", 'interval')}
  r := @S@.pur_save_order(o, NULL, {order(freight_cents='-1')});
  {need("r->>'code' = 'valor_invalido'", 'negative')}
  SELECT count(*) INTO n FROM @S@.pur_orders WHERE org_id = o;
  {need("n = 0", 'no order persisted by a refusal')}
  {save()}
  SELECT number INTO n FROM @S@.pur_orders WHERE id = (r->>'order_id')::uuid;
  {need("n = 1", 'the refusals burned no number')}""",
    "a draft is replaced as a set; a non-draft is not editable; an unknown order is refused": f"""
  {save()}
  oid := (r->>'order_id')::uuid;
  r := @S@.pur_save_order(o, oid, {order(lines=[line('i1', '4', 250)], freight_cents='0', discount_cents='0')});
  {need("r->>'status' = 'ok'", 'replace')}
  SELECT count(*), max(line_total_cents) INTO n, k FROM @S@.pur_order_lines WHERE order_id = oid;
  {need("n = 1 AND k = 1000", 'lines replaced')}
  SELECT total_cents INTO k FROM @S@.pur_orders WHERE id = oid;
  {need("k = 1000", 'total re-derived')}
  r := @S@.pur_transition(o, oid, 'approve', NULL, NULL);
  r := @S@.pur_save_order(o, oid, {order()});
  {need("r->>'code' = 'pedido_nao_editavel'", 'not editable')}
  r := @S@.pur_save_order(o, gen_random_uuid(), {order()});
  {need("r->>'code' = 'pedido_inexistente'", 'unknown')}
""",
    "state machine: approve -> send -> cancel, strict order, replays, org-scoped": f"""
  {save()}
  oid := (r->>'order_id')::uuid;
  r := @S@.pur_transition(o, oid, 'send', NULL, NULL);
  {need("r->>'code' = 'transicao_invalida'", 'send before approve')}
  r := @S@.pur_transition(o, oid, 'bogus', NULL, NULL);
  {need("r->>'code' = 'transicao_invalida'", 'unknown action')}
  r := @S@.pur_transition(other, oid, 'approve', NULL, NULL);
  {need("r->>'code' = 'pedido_inexistente'", 'foreign org')}
  r := @S@.pur_transition(o, oid, 'approve', gen_random_uuid(), NULL);
  {need("r->>'status' = 'ok'", 'approve')}
  SELECT status INTO t FROM @S@.pur_orders WHERE id = oid;
  {need("t = 'approved'", 'status')}
  {need("EXISTS (SELECT 1 FROM @S@.pur_orders WHERE id = oid AND approved_by IS NOT NULL AND approved_at IS NOT NULL)", 'approver recorded')}
  r := @S@.pur_transition(o, oid, 'approve', NULL, NULL);
  {need("r->>'status' = 'replayed'", 'approve replay')}
  r := @S@.pur_transition(o, oid, 'send', NULL, NULL);
  {need("r->>'status' = 'ok'", 'send')}
  r := @S@.pur_transition(o, oid, 'approve', NULL, NULL);
  {need("r->>'code' = 'transicao_invalida'", 'approve after send')}
  r := @S@.pur_transition(o, oid, 'cancel', NULL, 'mudou de ideia');
  {need("r->>'status' = 'ok'", 'cancel after send, before any receipt')}
  SELECT status INTO t FROM @S@.pur_orders WHERE id = oid;
  {need("t = 'cancelled'", 'cancelled')}
  {need("EXISTS (SELECT 1 FROM @S@.pur_orders WHERE id = oid AND cancel_reason = 'mudou de ideia' AND cancelled_at IS NOT NULL)", 'reason recorded')}
  r := @S@.pur_transition(o, oid, 'cancel', NULL, NULL);
  {need("r->>'status' = 'replayed'", 'cancel replay')}
  r := @S@.pur_transition(o, oid, 'send', NULL, NULL);
  {need("r->>'code' = 'transicao_invalida'", 'send a cancelled order')}""",
    "receiving needs an approved order and refuses draft / cancelled / received": f"""
  {save()}
  oid := (r->>'order_id')::uuid; {lines_of('oid')}
  r := @S@.pur_receive(o, oid, {recv_all()});
  {need("r->>'code' = 'pedido_nao_aprovado'", 'draft')}
  r := @S@.pur_transition(o, oid, 'cancel', NULL, NULL);
  r := @S@.pur_receive(o, oid, {recv_all()});
  {need("r->>'code' = 'pedido_cancelado'", 'cancelled')}
  {save()}
  oid := (r->>'order_id')::uuid; {lines_of('oid')}
  r := @S@.pur_transition(o, oid, 'approve', NULL, NULL);
  r := @S@.pur_receive(o, oid, {recv_all()});
  {need("r->>'status' = 'ok' AND r->>'order_status' = 'received'", 'full receipt')}
  r := @S@.pur_receive(o, oid, {recv('l1', '1')});
  {need("r->>'code' = 'pedido_ja_recebido'", 'already received')}
  r := @S@.pur_transition(o, oid, 'cancel', NULL, NULL);
  {need("r->>'code' = 'pedido_com_recebimento'", 'cancel after a receipt')}""",
    "one full receipt prorates freight - discount over the lines and adds up to the order total": f"""
  {SETUP_APPROVED}
  r := @S@.pur_receive(o, oid, {recv_all()});
  rid := (r->>'receipt_id')::uuid;
  SELECT goods_cents, adjustment_cents, total_cents, receipt_no INTO k, k2, n, t FROM @S@.pur_receipts WHERE id = rid;
  {need("k = 10833 AND k2 = 500 AND n = 11333", 'receipt totals = order totals')}
  SELECT landed_unit_cost_cents, adjustment_cents INTO k, k2 FROM @S@.pur_receipt_lines WHERE receipt_id = rid AND order_line_id = l1;
  {need("k = 1046 AND k2 = 462", 'line 1: (10000 + round(500*10000/10833)=462) / 10 = 1046')}
  SELECT landed_unit_cost_cents, adjustment_cents INTO k, k2 FROM @S@.pur_receipt_lines WHERE receipt_id = rid AND order_line_id = l2;
  {need("k = 348 AND k2 = 38", 'line 2 takes the remainder: (833 + 38) / 2.5 = 348')}
  SELECT status INTO t FROM @S@.pur_orders WHERE id = oid;
  {need("t = 'received'", 'order received')}""",
    "partial receipts: the shares telescope to EXACTLY freight + other - discount": f"""
  {SETUP_APPROVED}
  r := @S@.pur_receive(o, oid, {recv('l1', '6')});
  {need("r->>'order_status' = 'partially_received'", 'partial')}
  rid := (r->>'receipt_id')::uuid;
  r := @S@.pur_receive(o, oid, {recv_all()});
  {need("r->>'code' = 'recebimento_excede_pedido'", 'cannot receive 10 more of line 1')}
  r := @S@.pur_receive(o, oid, jsonb_build_object('lines', jsonb_build_array(
      jsonb_build_object('order_line_id', l1, 'qty', '4'), jsonb_build_object('order_line_id', l2, 'qty', '2.5'))));
  {need("r->>'status' = 'ok' AND r->>'order_status' = 'received'", 'second receipt completes')}
  rid2 := (r->>'receipt_id')::uuid;
  SELECT adjustment_cents, goods_cents, order_goods_before_cents, receipt_no INTO k, k2, n, t FROM @S@.pur_receipts WHERE id = rid;
  {need("k = 277 AND k2 = 6000 AND n = 0 AND t = '1'", 'first share = round(500*6000/10833)')}
  SELECT adjustment_cents, goods_cents, order_goods_before_cents, receipt_no INTO k, k2, n, t FROM @S@.pur_receipts WHERE id = rid2;
  {need("k = 223 AND k2 = 4833 AND n = 6000 AND t = '2'", 'second share is the remainder')}
  SELECT sum(adjustment_cents), sum(total_cents) INTO k, k2 FROM @S@.pur_receipts WHERE order_id = oid;
  {need("k = 500 AND k2 = 11333", 'sum of receipts = order adjustment and total, to the cent')}
  SELECT sum(adjustment_cents) INTO k FROM @S@.pur_receipt_lines WHERE receipt_id = rid2;
  {need("k = 223", 'line shares add up to the receipt share')}
  SELECT received_qty INTO n FROM @S@.pur_order_lines WHERE id = l1;
  {need("n = 10", 'received_qty')}""",
    "a negative adjustment (discount > freight) lowers the landed cost and never goes below zero": f"""
  {save(row=order(lines=[line('i1', '10', 1000)], freight_cents='0', discount_cents='3000'))}
  oid := (r->>'order_id')::uuid; {lines_of('oid')}
  r := @S@.pur_transition(o, oid, 'approve', NULL, NULL);
  r := @S@.pur_receive(o, oid, {recv('l1', '10')});
  rid := (r->>'receipt_id')::uuid;
  SELECT adjustment_cents, total_cents INTO k, k2 FROM @S@.pur_receipts WHERE id = rid;
  {need("k = -3000 AND k2 = 7000", 'discount reduces the AP amount')}
  SELECT landed_unit_cost_cents INTO k FROM @S@.pur_receipt_lines WHERE receipt_id = rid;
  {need("k = 700", 'landed unit = (10000 - 3000)/10')}""",
    "receipt idempotency key replays, and cannot be reused on another order": f"""
  {SETUP_APPROVED}
  r := @S@.pur_receive(o, oid, {recv('l1', '3', 'k-1')});
  rid := (r->>'receipt_id')::uuid;
  r := @S@.pur_receive(o, oid, {recv('l1', '3', 'k-1')});
  {need("r->>'status' = 'replayed' AND (r->>'receipt_id')::uuid = rid", 'replay')}
  SELECT count(*) INTO n FROM @S@.pur_receipts WHERE order_id = oid;
  {need("n = 1", 'no second receipt')}
  SELECT received_qty INTO n FROM @S@.pur_order_lines WHERE id = l1;
  {need("n = 3", 'quantity counted once')}
  {save(var='r2')}
  oid2 := (r2->>'order_id')::uuid; {lines_of('oid2')}
  r2 := @S@.pur_transition(o, oid2, 'approve', NULL, NULL);
  r := @S@.pur_receive(o, oid2, {recv('l1', '1', 'k-1')});
  {need("r->>'code' = 'chave_reutilizada'", 'key reuse')}""",
    "a line of another order / org is refused, duplicate lines in one receipt are summed": f"""
  {SETUP_APPROVED}
  r := @S@.pur_receive(o, oid, {recv('gen_random_uuid()', '1')});
  {need("r->>'code' = 'linha_invalida'", 'unknown line')}
  r := @S@.pur_receive(other, oid, {recv('l1', '1')});
  {need("r->>'code' = 'pedido_inexistente'", 'foreign org')}
  r := @S@.pur_receive(o, oid, jsonb_build_object('lines', jsonb_build_array(
      jsonb_build_object('order_line_id', l1, 'qty', '2'), jsonb_build_object('order_line_id', l1, 'qty', '3'))));
  {need("r->>'status' = 'ok'", 'duplicates')}
  SELECT qty INTO n FROM @S@.pur_receipt_lines WHERE receipt_id = (r->>'receipt_id')::uuid;
  {need("n = 5", 'summed into one receipt line')}
  r := @S@.pur_receive(o, oid, {recv('l1', '1')} || jsonb_build_object('lines', jsonb_build_array(jsonb_build_object('order_line_id', l1, 'qty', '0'))));
  {need("r->>'code' = 'quantidade_invalida'", 'zero qty')}""",
    "cross-organ: the landed cost goes to the kardex and the AP to finance with the party link, both idempotent": f"""
  {SETUP_APPROVED}
  r := @S@.pur_receive(o, oid, {recv_all()});
  rid := (r->>'receipt_id')::uuid;
  SELECT id INTO l1 FROM @S@.pur_receipt_lines WHERE receipt_id = rid AND order_line_id = (SELECT id FROM @S@.pur_order_lines WHERE order_id = oid AND line_no = 1);
  r2 := @S@.inv_receive(o, jsonb_build_object('item_id', i1, 'warehouse_id', w, 'qty', '10', 'unit_cost_cents', 1046,
        'source', 'purchasing', 'source_ref', l1::text));
  {need("r2->>'status' = 'ok'", 'stock in')}
  r2 := @S@.inv_receive(o, jsonb_build_object('item_id', i1, 'warehouse_id', w, 'qty', '10', 'unit_cost_cents', 1046,
        'source', 'purchasing', 'source_ref', l1::text));
  {need("r2->>'status' = 'replayed'", 'kardex replay on the receipt-line id')}
  SELECT on_hand, avg_cost_cents INTO n, k FROM @S@.inv_stock_balances WHERE org_id = o AND item_id = i1;
  {need("n = 10 AND k = 1046", 'stock at the landed cost, once')}
  INSERT INTO @S@.fin_entries(org_id, direction, description, competence_month, due_date, amount_cents, source, source_ref, party_id)
    VALUES (o, 'payable', 'Compra #1', '2026-10-01', '2026-11-13', 11333, 'purchasing', rid::text, p);
  BEGIN
    INSERT INTO @S@.fin_entries(org_id, direction, description, competence_month, due_date, amount_cents, source, source_ref)
      VALUES (o, 'payable', 'dup', '2026-10-01', '2026-11-13', 11333, 'purchasing', rid::text);
    RAISE EXCEPTION 'NOT ENFORCED: AP idempotency (org, source, source_ref)';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.fin_entries(org_id, direction, description, competence_month, due_date, amount_cents, party_id)
      VALUES (o, 'payable', 'cross-tenant link', '2026-10-01', '2026-11-13', 100, pf);
    RAISE EXCEPTION 'NOT ENFORCED: fin_entries.party_id composite FK';
  EXCEPTION WHEN foreign_key_violation THEN NULL; END;""",
    "the database refuses what the RPCs already refuse (constraints are the backstop)": f"""
  {SETUP_APPROVED}
  BEGIN
    UPDATE @S@.pur_order_lines SET received_qty = qty + 1 WHERE id = l1;
    RAISE EXCEPTION 'NOT ENFORCED: received_qty <= qty';
  EXCEPTION WHEN check_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.pur_orders(org_id, number, supplier_name, party_id) VALUES (o, 1, 'dup number', p);
    RAISE EXCEPTION 'NOT ENFORCED: unique (org_id, number)';
  EXCEPTION WHEN unique_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.pur_orders(org_id, number, supplier_name, party_id) VALUES (o, 99, 'foreign party', pf);
    RAISE EXCEPTION 'NOT ENFORCED: party composite FK';
  EXCEPTION WHEN foreign_key_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.pur_order_lines(org_id, order_id, line_no, description, qty, unit_cost_cents, line_total_cents)
      VALUES (other, oid, 9, 'cross-org line', 1, 1, 1);
    RAISE EXCEPTION 'NOT ENFORCED: order line composite FK';
  EXCEPTION WHEN foreign_key_violation THEN NULL; END;
  BEGIN
    INSERT INTO @S@.pur_settings(org_id, approval_threshold_cents) VALUES (o, -1);
    RAISE EXCEPTION 'NOT ENFORCED: threshold >= 0';
  EXCEPTION WHEN check_violation THEN NULL; END;""",
    "approval limit is judged inside the RPC under the order lock against the CURRENT total (a stale read cannot slip a raised total through)": f"""
  {save()}
  oid := (r->>'order_id')::uuid;
  r := @S@.pur_set_threshold(o, gen_random_uuid(), 20000);
  {need("r->>'status' = 'ok'", 'threshold set')}
  UPDATE @S@.pur_settings SET threshold_changed_at = now() - interval '11 minutes' WHERE org_id = o;
  -- the concurrent PUT that raised the total committed AFTER the Python pre-check read 11333 (< 20000)
  UPDATE @S@.pur_orders SET total_cents = 50000, goods_cents = 50000 WHERE id = oid;
  r := @S@.pur_transition(o, oid, 'approve', gen_random_uuid(), NULL, false);
  {need("r->>'code' = 'aprovacao_acima_do_limite'", 'non-approver over the limit is refused by the RPC')}
  SELECT status INTO t FROM @S@.pur_orders WHERE id = oid;
  {need("t = 'draft'", 'a refusal leaves the order untouched')}
  r := @S@.pur_transition(o, oid, 'approve', gen_random_uuid(), NULL);
  {need("r->>'code' = 'aprovacao_acima_do_limite'", 'the default is fail-closed (cannot exceed)')}
  r := @S@.pur_transition(o, oid, 'approve', gen_random_uuid(), NULL, true);
  {need("r->>'status' = 'ok'", 'an approver may exceed the limit once the cooldown is over')}""",
    "a threshold change is audit-logged, no-ops replay, and starts a cooldown on the LOWEST limit in force": f"""
  {save()}
  oid := (r->>'order_id')::uuid;
  u := gen_random_uuid();
  r := @S@.pur_set_threshold(o, u, 10000);
  {need("r->>'status' = 'ok'", 'first set')}
  r := @S@.pur_set_threshold(o, u, 10000);
  {need("r->>'status' = 'replayed'", 'same value is a no-op')}
  SELECT count(*) INTO n FROM @S@.pur_settings_log WHERE org_id = o AND kind = 'threshold' AND actor_id = u AND old_cents IS NULL AND new_cents = 10000;
  {need("n = 1", 'one audit row, with who / old / new')}
  -- raise within the window: the order (11333) is above the LOWEST limit in force (10000) -> blocked for everyone
  r := @S@.pur_set_threshold(o, u, 50000);
  r := @S@.pur_set_threshold(o, u, 90000);
  SELECT previous_threshold_cents INTO k FROM @S@.pur_settings WHERE org_id = o;
  {need("k = 10000", 'previous keeps the lowest threshold of the window')}
  r := @S@.pur_transition(o, oid, 'approve', gen_random_uuid(), NULL, true);
  {need("r->>'code' = 'limite_em_carencia'", 'raise + approve in the same breath is refused even for an approver')}
  SELECT count(*) INTO n FROM @S@.pur_settings_log WHERE org_id = o AND kind = 'threshold';
  {need("n = 3", 'every real change logged')}
  UPDATE @S@.pur_settings SET threshold_changed_at = now() - interval '11 minutes';
  r := @S@.pur_set_threshold(o, u, NULL);
  r := @S@.pur_transition(o, oid, 'approve', gen_random_uuid(), NULL, false);
  {need("r->>'status' = 'ok'", 'cleared limit; 11333 is under the lowest limit in the window (90000) so the cooldown does not block it')}
  r := @S@.pur_set_threshold(o, u, -5);
  {need("r->>'code' = 'valor_invalido'", 'negative threshold')}""",
    "the audit log is append-only; approver grants are org-scoped, idempotent and audited": f"""
  u := gen_random_uuid();
  r := @S@.pur_set_threshold(o, u, 100);
  BEGIN UPDATE @S@.pur_settings_log SET new_cents = 1; RAISE EXCEPTION 'NOT ENFORCED: log update';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN DELETE FROM @S@.pur_settings_log; RAISE EXCEPTION 'NOT ENFORCED: log delete';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN TRUNCATE @S@.pur_settings_log; RAISE EXCEPTION 'NOT ENFORCED: log truncate';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  r := @S@.pur_set_approver(o, gen_random_uuid(), u, true);
  {need("r->>'status' = 'ok'", 'grant')}
  r := @S@.pur_set_approver(o, gen_random_uuid(), u, true);
  {need("r->>'status' = 'replayed'", 'grant replay')}
  SELECT count(*) INTO n FROM @S@.pur_approvers WHERE user_id = u;
  {need("n = 1", 'one grant')}
  SELECT count(*) INTO n FROM @S@.pur_approvers WHERE org_id = other AND user_id = u;
  {need("n = 0", 'a grant in org A is nothing in org B')}
  r := @S@.pur_set_approver(other, gen_random_uuid(), u, true);
  SELECT count(*) INTO n FROM @S@.pur_approvers WHERE user_id = u;
  {need("n = 2", 'the same user can hold separate grants per org')}
  r := @S@.pur_set_approver(o, gen_random_uuid(), u, false);
  {need("r->>'status' = 'ok'", 'revoke')}
  r := @S@.pur_set_approver(o, gen_random_uuid(), u, false);
  {need("r->>'status' = 'replayed'", 'revoke replay')}
  SELECT count(*) INTO n FROM @S@.pur_approvers WHERE org_id = o AND user_id = u;
  {need("n = 0", 'revoked in A')}
  SELECT count(*) INTO n FROM @S@.pur_approvers WHERE org_id = other AND user_id = u;
  {need("n = 1", 'the revoke did not touch org B')}
  SELECT count(*) INTO n FROM @S@.pur_settings_log WHERE org_id = o AND kind IN ('approver_added', 'approver_removed') AND subject_user_id = u;
  {need("n = 2", 'grant + revoke audited (replays are not)')}
  r := @S@.pur_set_approver(o, NULL, NULL, true);
  {need("r->>'code' = 'usuario_invalido'", 'null user')}""",
    "every secdef function pins search_path to pg_catalog first, locks the order row, and is not callable by clients": """
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '@S@' AND p.proname LIKE 'pur\\_%' AND p.prosecdef
      AND p.proconfig::text LIKE '%search_path=pg_catalog, @S@, pg_temp%';
  IF n <> 5 THEN RAISE EXCEPTION 'search_path not pinned on % of 5 secdef functions', n; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace WHERE ns.nspname = '@S@' AND p.proname = 'pur_transition';
  IF n <> 1 THEN RAISE EXCEPTION 'pur_transition has % overloads (a legacy unguarded one must not survive)', n; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '@S@' AND p.proname IN ('pur_save_order', 'pur_transition', 'pur_receive', 'pur_set_threshold') AND p.prosrc ILIKE '%FOR UPDATE%';
  IF n <> 4 THEN RAISE EXCEPTION 'only % of 4 functions take FOR UPDATE', n; END IF;
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '@S@' AND p.proname LIKE 'pur\\_%' AND p.prosecdef
      AND (has_function_privilege('anon', p.oid, 'EXECUTE') OR has_function_privilege('authenticated', p.oid, 'EXECUTE'));
  IF n <> 0 THEN RAISE EXCEPTION '% secdef functions executable by client roles', n; END IF;""",
}

BARE_SCENARIOS: dict[str, str] = {
    "without the parties / items / inventory organs the same flow runs on free-text suppliers and item-less lines": """
  DECLARE oid uuid; l uuid; r jsonb; n numeric; k bigint;
  BEGIN
    r := @S@.pur_save_order(o, NULL, jsonb_build_object('supplier_name', 'Avulso', 'freight_cents', 100, 'lines', jsonb_build_array(
      jsonb_build_object('description', 'Sem cadastro', 'qty', '3', 'unit_cost_cents', 500))));
    IF r->>'status' <> 'ok' THEN RAISE EXCEPTION 'save: %', r; END IF;
    oid := (r->>'order_id')::uuid;
    r := @S@.pur_transition(o, oid, 'approve', NULL, NULL);
    SELECT id INTO l FROM @S@.pur_order_lines WHERE order_id = oid;
    r := @S@.pur_receive(o, oid, jsonb_build_object('lines', jsonb_build_array(jsonb_build_object('order_line_id', l, 'qty', '3'))));
    IF r->>'order_status' <> 'received' THEN RAISE EXCEPTION 'receive: %', r; END IF;
    SELECT total_cents INTO k FROM @S@.pur_receipts WHERE id = (r->>'receipt_id')::uuid;
    IF k <> 1600 THEN RAISE EXCEPTION 'total %', k; END IF;
  END;""",
}

BARE_BASE = "DO $$ DECLARE o uuid := gen_random_uuid(); BEGIN {body} END $$;"


def _step(schema: str, file: str, sql: str, twice: bool = False) -> dict:
    return {"product": schema, "file": file, "sql": sql, "mode": "file", "twice": twice}


def _run() -> dict:
    full = PurchasingConfig(schema=FULL)
    bare = PurchasingConfig(schema=BARE, with_parties=False, with_items=False, with_inventory=False)
    steps = [
        _step(FULL, "prelude", PRELUDE.format(s=FULL)),
        _step(FULL, "parties", parties_migration(PartiesConfig(schema=FULL), FULL), True),
        _step(FULL, "inventory", inventory_migration(InventoryConfig(schema=FULL), FULL), True),
        _step(FULL, "finance", finance_migration(FinanceConfig(schema=FULL, with_parties=True), FULL), True),
        _step(FULL, "migration", purchasing_migration(full, FULL), True),
        _step(BARE, "prelude", PRELUDE.format(s=BARE)),
        _step(BARE, "migration", purchasing_migration(bare, BARE), True),
        *(_step(FULL, f"scenario: {name}", BASE.replace("{body}", body).replace("@S@", FULL)) for name, body in SCENARIOS.items()),
        *(
            _step(BARE, f"scenario: {name}", BARE_BASE.replace("{body}", body).replace("@S@", BARE))
            for name, body in BARE_SCENARIOS.items()
        ),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=900,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


@pytest.fixture(scope="module")
def replay() -> dict:
    return _run()


@pytest.mark.parametrize("name", ["parties", "inventory", "finance", "migration"])
def test_chain_applies_twice(replay, name):
    assert replay[name]["failures"] == [], replay[name]["failures"]


@pytest.mark.parametrize("name", [*SCENARIOS, *BARE_SCENARIOS])
def test_scenario(replay, name):
    assert replay[f"scenario: {name}"]["failures"] == [], replay[f"scenario: {name}"]["failures"]
