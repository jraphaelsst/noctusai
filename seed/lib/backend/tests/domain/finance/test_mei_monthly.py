"""MEI Relatório Mensal de Receitas Brutas (E21): activity group x with/without nota fiscal, cash basis, honest warnings."""
from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from noctusai_lib.domain.finance import categories, dre_settings, mei, settlements

from .accountant_support import ah, ah_plain  # noqa: F401
from .conftest import mk_account, mk_entry

M = "month=2026-10-01"


def cat(s, name):
    return next(c for c in categories.list_categories(s) if c["name"] == name)


def received(s, acc, *, category, amount, on=date(2026, 10, 10), has_invoice=None, **over):
    e = mk_entry(s, direction="receivable", category_id=category["id"], amount_cents=amount, has_invoice=has_invoice, **over)
    settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": amount, "settled_on": on})
    return e


def set_mei(ah):
    assert ah.client.put("/api/finance/dre-settings", headers=ah.admin, json={"tax_regime": "mei"}).status_code == 200


def test_groups_split_by_activity_and_invoice(ah):
    set_mei(ah)
    s, acc = ah.s, mk_account(ah.s)
    received(s, acc, category=cat(s, "Vendas"), amount=100_00, has_invoice=True)
    received(s, acc, category=cat(s, "Vendas"), amount=40_00, has_invoice=False)
    received(s, acc, category=cat(s, "Serviços"), amount=300_00, has_invoice=True)
    received(s, acc, category=cat(s, "Serviços"), amount=50_00, has_invoice=False)
    d = ah.get(f"/reports/mei-monthly?{M}").json()["data"]
    assert d["applicable"] and d["tax_regime"] == "mei" and d["basis"] == "cash" and d["deadline"] == "2026-11-20"
    assert d["groups"]["comercio"] == {"without_invoice_cents": 40_00, "with_invoice_cents": 100_00, "total_cents": 140_00}
    assert d["groups"]["servicos"] == {"without_invoice_cents": 50_00, "with_invoice_cents": 300_00, "total_cents": 350_00}
    assert d["groups"]["industria"]["total_cents"] == 0
    assert d["total_cents"] == 490_00 and d["unassigned_cents"] == 0 and d["warnings"] == []
    assert d["fields"]["comercio"]["total_roman"] == "III" and d["grand_total"]["roman"] == "X"


def test_cash_basis_only_the_month_of_the_receipt_and_refunds_net(ah):
    set_mei(ah)
    s, acc = ah.s, mk_account(ah.s)
    e = received(s, acc, category=cat(s, "Vendas"), amount=100_00, has_invoice=False)
    received(s, acc, category=cat(s, "Vendas"), amount=999_00, on=date(2026, 9, 30), has_invoice=False)  # other month
    settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "kind": "refund", "amount_cents": 10_00, "settled_on": date(2026, 10, 20)})
    d = ah.get(f"/reports/mei-monthly?{M}").json()["data"]
    assert d["groups"]["comercio"]["total_cents"] == 90_00


def test_unknown_invoice_counts_as_sem_nota_but_is_never_silent(ah):
    set_mei(ah)
    s, acc = ah.s, mk_account(ah.s)
    received(s, acc, category=cat(s, "Vendas"), amount=70_00, has_invoice=None)
    d = ah.get(f"/reports/mei-monthly?{M}").json()["data"]
    assert d["groups"]["comercio"]["without_invoice_cents"] == 70_00 and d["unknown_invoice_cents"] == 70_00
    w = {x["code"]: x for x in d["warnings"]}
    assert w["nota_fiscal_nao_informada"]["severity"] == "warning" and w["nota_fiscal_nao_informada"]["details"]["cents"] == 70_00


def test_revenue_without_activity_is_not_guessed(ah):
    set_mei(ah)
    s, acc = ah.s, mk_account(ah.s)
    received(s, acc, category=cat(s, "Outras receitas"), amount=10_00)  # not even gross revenue: ignored entirely
    c = categories.create_category(s, {"name": "Aluguel de espaço", "direction": "income", "dre_line": "gross_revenue"})
    received(s, acc, category=c, amount=25_00, has_invoice=True)
    d = ah.get(f"/reports/mei-monthly?{M}").json()["data"]
    assert d["total_cents"] == 0 and d["unassigned_cents"] == 25_00
    w = {x["code"]: x for x in d["warnings"]}
    assert w["atividade_nao_definida"]["severity"] == "critical"
    # once the contador/owner names the activity the money lands in the model
    ah.client.patch(f"/api/finance/categories/{c['id']}", headers=ah.admin, json={"activity_kind": "servicos"})
    d = ah.get(f"/reports/mei-monthly?{M}").json()["data"]
    assert d["groups"]["servicos"]["with_invoice_cents"] == 25_00 and d["unassigned_cents"] == 0


def test_activity_is_inherited_from_the_parent(ah):
    set_mei(ah)
    s, acc = ah.s, mk_account(ah.s)
    parent = cat(s, "Vendas")
    child = categories.create_category(s, {"name": "Loja online", "direction": "income", "parent_id": parent["id"]})
    received(s, acc, category=child, amount=33_00, has_invoice=True)
    d = ah.get(f"/reports/mei-monthly?{M}").json()["data"]
    assert d["groups"]["comercio"]["with_invoice_cents"] == 33_00


def test_not_applicable_outside_mei(ah):
    d = ah.get(f"/reports/mei-monthly?{M}").json()["data"]  # regime still unknown
    assert d["applicable"] is False and [w["code"] for w in d["warnings"]] == ["relatorio_somente_mei"]
    ah.client.put("/api/finance/dre-settings", headers=ah.admin, json={"tax_regime": "simples"})
    assert ah.get(f"/reports/mei-monthly?{M}").json()["data"]["applicable"] is False


def test_org_scope(ah):
    set_mei(ah)
    received(ah.s_b, mk_account(ah.s_b), category=cat(ah.s_b, "Vendas"), amount=500_00, has_invoice=True)
    assert ah.get(f"/reports/mei-monthly?{M}").json()["data"]["total_cents"] == 0


def test_csv_and_pdf(ah):
    set_mei(ah)
    s, acc = ah.s, mk_account(ah.s)
    received(s, acc, category=cat(s, "Vendas"), amount=100_00, has_invoice=True)
    r = ah.get(f"/exports/mei-monthly.csv?{M}")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    by_item = {row[0]: row for row in rows[2:12]}
    assert by_item["II"][2] == "100.00" and by_item["III"][2] == "100.00" and by_item["X"][2] == "100.00"
    p = ah.get(f"/exports/mei-monthly.pdf?{M}")
    assert p.status_code == 200 and p.content.startswith(b"%PDF") and p.headers["content-type"] == "application/pdf"


def test_has_invoice_round_trips_through_the_entry_api(ah):
    body = {"direction": "receivable", "description": "Venda B2B", "due_date": "2026-10-20", "amount_cents": 1000, "has_invoice": True}
    r = ah.client.post("/api/finance/entries", headers=ah.admin, json=body)
    assert r.status_code == 201 and r.json()["data"][0]["has_invoice"] is True
    eid = r.json()["data"][0]["id"]
    r = ah.client.patch(f"/api/finance/entries/{eid}", headers=ah.admin, json={"has_invoice": False})
    assert r.json()["data"]["has_invoice"] is False
    assert ah.client.get(f"/api/finance/entries/{eid}", headers=ah.admin).json()["data"]["has_invoice"] is False


def test_booking_seam_accepts_has_invoice(ah):
    from noctusai_lib.domain.finance import make_finance_booking

    booking = make_finance_booking("supabase", db=ah.db, cfg=ah.s.cfg)
    eid = booking.book_receivable(
        ah.s.org_id, source="commerce_order", source_ref="o-1", description="Pedido 1", counterparty_name=None, counterparty_doc=None,
        amount_cents=1000, competence_month=date(2026, 10, 1), due_date=date(2026, 10, 5), has_invoice=True,
    )
    row = ah.db.table("fin_entries").select("*").eq("id", eid).execute().data[0]
    assert row["has_invoice"] is True


def test_gate_matrix(ah, ah_plain):
    for path in (f"/reports/mei-monthly?{M}", f"/exports/mei-monthly.csv?{M}", f"/exports/mei-monthly.pdf?{M}"):
        assert ah.client.get(f"/api/finance{path}").status_code == 401
        assert ah.get(path, ah.staff).status_code == 403
        assert ah.get(path, ah.accountant).status_code == 200
        assert ah_plain.get(path, ah_plain.accountant).status_code == 403
