"""Receiving: the RPC verdict, then the two idempotent posting legs (stock through the inventory port, AP through finance).

The ports are the REAL `SupabaseStockPort` / `SupabaseFinanceBooking` over the schema-validated mock (the stock RPC is the
mock's canned seam, so move arithmetic is inventory's own real-PG suite); the Fakes count calls where a test needs to.
"""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import FakeFinanceBooking, NoopFinanceBooking, make_finance_booking
from noctusai_lib.domain.finance._common import Scope as FinScope
from noctusai_lib.domain.inventory import FakeStockPort, NoopStockPort, make_stock_port
from noctusai_lib.domain.purchasing import PurchasingConfig, receipts
from noctusai_lib.domain.purchasing._common import Scope
from noctusai_lib.primitives.exceptions import AppException

from .conftest import (
    CFG, FIN_CFG, INV_CFG, ITEM, ITEM2, ORDER, ORG_A, ORG_B, PARTY, WH1, build_harness,
    seed_line, seed_order, seed_receipt, seed_receipt_line,
)

L1, L2 = "77777777-7777-4777-8777-777777777771", "77777777-7777-4777-8777-777777777772"
R1, RL1, RL2 = "88888888-8888-4888-8888-888888888881", "99999999-9999-4999-8999-999999999991", "99999999-9999-4999-8999-999999999992"
URL = f"/api/purchasing/orders/{ORDER}/receipts"
BODY = {"received_on": "2026-10-14", "idempotency_key": "k1", "lines": [{"order_line_id": L1, "qty": "10"}]}


def ports(h):
    return dict(
        stock_factory=lambda db: make_stock_port("supabase", db=db, cfg=INV_CFG),
        booking_factory=lambda db: make_finance_booking("supabase", db=db, cfg=FIN_CFG),
    )


def wired(**order_over):
    """A harness whose router posts through the real Supabase ports, with an approved order + one received line staged."""
    h = build_harness(**ports(None))
    h.db.table("pty_parties").insert({"id": PARTY, "org_id": ORG_A, "kind": "PJ", "doc": "11222333000181", "legal_name": "Fornecedor Ltda", "is_active": True}).execute()
    seed_order(h.db, party_id=PARTY, total=100_000, **order_over)
    seed_line(h.db, L1)
    seed_receipt(h.db, R1)
    seed_receipt_line(h.db, RL1, R1, L1, landed=10_000)
    h.db.set_rpc_data("pur_receive", {"status": "ok", "receipt_id": R1, "order_status": "received"})
    h.db.set_rpc_data("inv_receive", {"status": "ok", "moves": [{"id": "m1", "kind": "in"}]})
    return h


def fin_rows(h):
    return FinScope(h.db, FIN_CFG, ORG_A).rows("entries")


def test_receive_posts_stock_at_the_landed_cost_and_the_ap_entry_with_the_party_link():
    h = wired()
    r = h.client.post(URL, json=BODY, headers=h.admin)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["replayed"] is False and data["order_status"] == "received" and data["posting_error"] is None and data["posted"] is True
    assert data["stock_posted_at"] and data["finance_posted_at"] and len(data["lines"]) == 1

    name, params = [c for c in h.db.rpc_calls if c[0] == "inv_receive"][-1]
    row = params["p_row"]
    assert row["item_id"] == ITEM and row["warehouse_id"] == WH1 and row["qty"] == "10.000" and row["unit_cost_cents"] == 10_000
    assert row["source"] == "purchasing" and row["source_ref"] == RL1 and params["p_org_id"] == ORG_A

    [entry] = fin_rows(h)
    assert entry["direction"] == "payable" and entry["source"] == "purchasing" and entry["source_ref"] == R1
    assert entry["amount_cents"] == 100_000 and entry["party_id"] == PARTY
    assert entry["counterparty_name"] == "Fornecedor Ltda" and entry["counterparty_doc"] == "11222333000181"  # snapshots
    assert entry["due_date"] == "2026-11-13" and entry["competence_month"] == "2026-10-01"
    assert entry["description"] == "Compra #1 - recebimento 1" and entry["status"] == "open"
    cat = FinScope(h.db, FIN_CFG, ORG_A).find("categories", entry["category_id"])
    assert cat["name"] == "Mercadorias / insumos para revenda" and cat["direction"] == "expense"


def test_the_rpc_payload_carries_the_actor_and_decimal_quantities_as_strings():
    h = wired()
    h.client.post(URL, json={**BODY, "lines": [{"order_line_id": L1, "qty": "2.500"}], "note": "NF 123"}, headers=h.admin)
    name, params = h.db.rpc_calls[0]
    assert name == "pur_receive" and params["p_order_id"] == ORDER and params["p_org"] == ORG_A
    assert params["p_row"]["lines"] == [{"order_line_id": L1, "qty": "2.500"}] and params["p_row"]["created_by"]
    assert params["p_row"]["idempotency_key"] == "k1" and params["p_row"]["note"] == "NF 123"


def test_the_installments_follow_the_payment_terms_with_per_installment_idempotency_keys():
    h = wired(installments_count=3, first_due_days=30, interval_days=15)
    h.client.post(URL, json=BODY, headers=h.admin)
    rows = sorted(fin_rows(h), key=lambda e: e["source_ref"])
    assert [e["source_ref"] for e in rows] == [f"{R1}:1", f"{R1}:2", f"{R1}:3"]
    assert [e["amount_cents"] for e in rows] == [33_333, 33_333, 33_334]  # the last absorbs the remainder
    assert [e["due_date"] for e in rows] == ["2026-11-13", "2026-11-28", "2026-12-13"]
    assert rows[0]["description"].endswith("(1/3)") and all(e["party_id"] == PARTY for e in rows)
    assert sum(e["amount_cents"] for e in rows) == 100_000


def test_a_receipt_total_smaller_than_the_installments_never_books_a_zero_cent_installment(purchasing_schema_cache):
    h = wired(installments_count=12)
    h.db.table("pur_receipts").update({"total_cents": 5}).eq("id", R1).execute()
    h.client.post(URL, json=BODY, headers=h.admin)
    rows = fin_rows(h)
    assert len(rows) == 5 and all(e["amount_cents"] == 1 for e in rows)


def test_a_free_receipt_books_no_ap_but_is_marked_posted():
    h = wired()
    h.db.table("pur_receipts").update({"total_cents": 0, "goods_cents": 0}).eq("id", R1).execute()
    data = h.client.post(URL, json=BODY, headers=h.admin).json()["data"]
    assert fin_rows(h) == [] and data["finance_posted_at"] and data["posted"] is True


def test_posting_is_idempotent_a_second_post_moves_and_books_nothing_more():
    h = wired()
    h.client.post(URL, json=BODY, headers=h.admin)
    calls = len([c for c in h.db.rpc_calls if c[0] == "inv_receive"])
    again = h.client.post(f"/api/purchasing/receipts/{R1}/post", headers=h.admin)
    assert again.status_code == 200 and again.json()["data"]["posted"] is True
    assert len([c for c in h.db.rpc_calls if c[0] == "inv_receive"]) == calls and len(fin_rows(h)) == 1


def test_a_finance_leg_retry_after_a_lost_marker_finds_the_existing_entries_by_source_ref():
    h = wired(installments_count=2)
    h.client.post(URL, json=BODY, headers=h.admin)
    h.db.table("pur_receipts").update({"finance_posted_at": None}).eq("id", R1).execute()
    h.client.post(f"/api/purchasing/receipts/{R1}/post", headers=h.admin)
    assert len(fin_rows(h)) == 2


def test_a_replayed_receive_verdict_is_flagged_and_posts_only_what_is_missing():
    h = wired()
    h.client.post(URL, json=BODY, headers=h.admin)
    h.db.set_rpc_data("pur_receive", {"status": "replayed", "receipt_id": R1, "order_status": "received"})
    data = h.client.post(URL, json=BODY, headers=h.admin).json()["data"]
    assert data["replayed"] is True and len(fin_rows(h)) == 1


class _BrokenBooking(NoopFinanceBooking):
    def book_payable(self, org_id, **_):
        raise AppException("categoria_inativa", "A categoria está inativa.", 422)


def test_a_domain_failure_in_the_finance_leg_is_recorded_and_the_retry_completes_it(purchasing_schema_cache):
    h = wired()
    s = Scope(h.db, CFG, ORG_A)
    broken = receipts.post_receipt(s, R1, user_id="u", stock=make_stock_port("supabase", db=h.db, cfg=INV_CFG), booking=_BrokenBooking())
    assert broken["posting_error"] == "categoria_inativa: A categoria está inativa."
    assert broken["stock_posted_at"] and broken.get("finance_posted_at") is None and broken["posted"] is False
    persisted = receipts.get_receipt(s, R1)
    assert persisted["posting_error"] == broken["posting_error"]
    pending = h.client.get("/api/purchasing/receipts?pending=true", headers=h.as_("user"))
    assert pending.status_code == 200 and [r["id"] for r in pending.json()["data"]] == [R1]

    fixed = h.client.post(f"/api/purchasing/receipts/{R1}/post", headers=h.admin).json()["data"]
    assert fixed["posting_error"] is None and fixed["posted"] is True and len(fin_rows(h)) == 1
    stock_calls = [c for c in h.db.rpc_calls if c[0] == "inv_receive"]
    assert len(stock_calls) == 1  # the stock leg was not redone


class _BrokenStock(NoopStockPort):
    def receive_stock(self, org_id, **_):
        raise AppException("deposito_inativo", "O depósito está inativo.", 422)


def test_a_stock_failure_stops_before_the_ap_so_a_payable_never_exists_without_its_goods(purchasing_schema_cache):
    h = wired()
    s = Scope(h.db, CFG, ORG_A)
    out = receipts.post_receipt(s, R1, user_id="u", stock=_BrokenStock(), booking=make_finance_booking("supabase", db=h.db, cfg=FIN_CFG))
    assert out["posting_error"].startswith("deposito_inativo") and out.get("stock_posted_at") is None and fin_rows(h) == []


def test_with_fakes_each_line_is_one_idempotent_stock_move_and_one_entry_per_installment(purchasing_schema_cache):
    h = wired()
    seed_line(h.db, L2, item=ITEM2, no=2, qty="2.500", cost=400)
    seed_receipt_line(h.db, RL2, R1, L2, qty="2.500", cost=400, landed=420)
    stock, booking = FakeStockPort(), FakeFinanceBooking()
    s = Scope(h.db, CFG, ORG_A)
    receipts.post_receipt(s, R1, user_id="u", stock=stock, booking=booking)
    assert sorted(m["item_id"] for m in stock.moves) == sorted([ITEM, ITEM2])
    assert {m["source_ref"] for m in stock.moves} == {RL1, RL2}
    assert {m["unit_cost_cents"] for m in stock.moves} == {10_000, 420}
    assert list(booking.entries) == [(ORG_A, "purchasing", R1)]
    assert booking.entries[(ORG_A, "purchasing", R1)]["category_hint"] == "Mercadorias / insumos para revenda"


def test_without_inventory_the_stock_leg_is_a_marked_no_op(purchasing_schema_cache):
    h = build_harness(PurchasingConfig(schema=CFG.schema, with_inventory=False), booking_factory=lambda db: make_finance_booking("supabase", db=db, cfg=FIN_CFG))
    seed_order(h.db, warehouse_id=None)
    seed_line(h.db, L1, item=None)
    seed_receipt(h.db, R1)
    seed_receipt_line(h.db, RL1, R1, L1)
    h.db.set_rpc_data("pur_receive", {"status": "ok", "receipt_id": R1, "order_status": "received"})
    data = h.client.post(URL, json=BODY, headers=h.admin).json()["data"]
    assert data["posted"] is True and not [c for c in h.db.rpc_calls if c[0].startswith("inv_")] and len(fin_rows(h)) == 1


def test_the_default_ports_are_noop_so_a_host_without_finance_or_inventory_just_marks_posted(purchasing_schema_cache):
    h = build_harness()
    seed_order(h.db)
    seed_line(h.db, L1)
    seed_receipt(h.db, R1)
    seed_receipt_line(h.db, RL1, R1, L1)
    h.db.set_rpc_data("pur_receive", {"status": "ok", "receipt_id": R1, "order_status": "received"})
    data = h.client.post(URL, json=BODY, headers=h.admin).json()["data"]
    assert data["posted"] is True and fin_rows(h) == []


@pytest.mark.parametrize(
    "code,status",
    [("pedido_nao_aprovado", 409), ("pedido_cancelado", 409), ("pedido_ja_recebido", 409), ("recebimento_excede_pedido", 409),
     ("linha_invalida", 422), ("quantidade_invalida", 422), ("chave_reutilizada", 409), ("pedido_inexistente", 404)],
)
def test_receive_refusals_map_to_http_and_post_nothing(code, status):
    h = wired()
    h.db.set_rpc_data("pur_receive", {"status": "refused", "code": code})
    r = h.client.post(URL, json=BODY, headers=h.admin)
    assert r.status_code == status and not [c for c in h.db.rpc_calls if c[0] == "inv_receive"] and fin_rows(h) == []


@pytest.mark.parametrize("body", [{"lines": []}, {"lines": [{"order_line_id": L1, "qty": "0"}]}, {"lines": [{"order_line_id": "x", "qty": "1"}]},
                                  {**BODY, "idempotency_key": ""}, {**BODY, "extra": 1}])
def test_bad_receipt_bodies_are_422(body):
    h = wired()
    assert h.client.post(URL, json=body, headers=h.admin).status_code == 422 and h.db.rpc_calls == []


def test_receipts_of_another_org_are_invisible_and_cannot_be_posted():
    h = wired()
    assert h.client.get(f"/api/purchasing/receipts/{R1}", headers=h.as_("org-b-admin")).status_code == 404
    assert h.client.post(f"/api/purchasing/receipts/{R1}/post", headers=h.as_("org-b-admin")).status_code == 404
    assert h.client.get("/api/purchasing/receipts", headers=h.as_("org-b-admin")).json()["data"] == []
    assert [r["id"] for r in h.client.get("/api/purchasing/receipts", headers=h.as_("user")).json()["data"]] == [R1]
    assert [r["id"] for r in h.client.get(f"/api/purchasing/receipts?order_id={ORDER}", headers=h.as_("user")).json()["data"]] == [R1]


def test_the_order_detail_nests_its_receipts_with_their_lines():
    h = wired()
    data = h.client.get(f"/api/purchasing/orders/{ORDER}", headers=h.as_("user")).json()["data"]
    assert [r["id"] for r in data["receipts"]] == [R1] and data["receipts"][0]["lines"][0]["id"] == RL1


def test_the_entries_party_link_requires_the_finance_host_to_mount_parties(purchasing_schema_cache):
    from noctusai_lib.domain.finance import FinanceConfig

    h = wired()
    plain = FinanceConfig(schema=CFG.schema)  # no with_parties: party_id is silently NOT written (column absent)
    s = Scope(h.db, CFG, ORG_A)
    receipts.post_receipt(s, R1, user_id="u", stock=NoopStockPort(), booking=make_finance_booking("supabase", db=h.db, cfg=plain))
    [entry] = fin_rows(h)
    assert entry.get("party_id") is None and entry["counterparty_name"] == "Fornecedor Ltda"
