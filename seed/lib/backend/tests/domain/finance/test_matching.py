"""Reconciliation: link to an unreconciled ledger row FIRST, settle only a still-open entry, never double-book."""
from __future__ import annotations

from datetime import date

from noctusai_lib.domain.finance import make_finance_booking

from .conftest import CFG, ORG_A, mk_account, mk_entry
from .recon_support import ofx1, rh  # noqa: F401

P = "/api/finance"


def upload_one(rh, acc, amount="100.00", day="20261010", fitid="F1"):
    rh.upload(acc["id"], f"{fitid}.ofx", ofx1((day, amount, fitid, "PIX")))
    return [l for l in rh.s.rows("statement_lines") if l["fitid"] == fitid][0]


def match(rh, line, entry, headers=None):
    return rh.client.post(f"{P}/statement-lines/{line['id']}/match", headers=headers or rh.admin, json={"entry_id": entry["id"]})


def test_open_entry_gets_a_settlement_and_the_ledger_row_is_linked(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    line = upload_one(rh, acc)
    r = match(rh, line, e)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["created_settlement"] is True and d["entry"]["status"] == "paid"
    sts = rh.s.rows("settlements")
    assert len(sts) == 1 and sts[0]["statement_line_id"] == line["id"] and sts[0]["account_id"] == acc["id"]
    after = rh.s.get("statement_lines", line["id"], what="x")
    assert after["match_status"] == "matched" and after["ledger_id"] == d["ledger_id"]


def test_money_already_booked_is_linked_not_booked_again(rh):
    """The commerce bridge settled the entry on this account; the bank line must only point at that ledger row."""
    acc = mk_account(rh.s)
    booking = make_finance_booking("supabase", db=rh.db, cfg=CFG)
    eid = booking.book_receivable(ORG_A, source="commerce_order", source_ref="o1", description="Pedido", counterparty_name="Ana",
                                  counterparty_doc=None, amount_cents=10000, competence_month=date(2026, 10, 1), due_date=date(2026, 10, 10))
    booking.book_settlement(ORG_A, source="commerce_order", source_ref="o1", kind="payment", external_ref="pay_1",
                            amount_cents=10000, settled_on=date(2026, 10, 10), account_hint=f"account:{acc['id']}")
    ledger_before = rh.s.rows("ledger")
    line = upload_one(rh, acc)
    assert line["suggested_entry_id"] == eid and line["match_status"] == "suggested"  # a PAID entry is still suggested
    r = match(rh, line, {"id": eid})
    d = r.json()["data"]
    assert r.status_code == 200 and d["created_settlement"] is False
    assert len(rh.s.rows("settlements")) == 1 and rh.s.rows("ledger") == ledger_before
    assert d["ledger_id"] == ledger_before[0]["id"]


def test_ledger_id_is_unique_per_line(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    l1 = upload_one(rh, acc, fitid="F1")
    l2 = upload_one(rh, acc, fitid="F2")
    assert match(rh, l1, e).status_code == 200
    again = match(rh, l2, e)  # entry is paid and its only ledger row is consumed
    assert again.status_code == 409 and again.json()["error"]["code"] == "lancamento_ja_baixado"
    assert len(rh.s.rows("settlements")) == 1


def test_rematching_a_matched_line_is_409(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    line = upload_one(rh, acc)
    match(rh, line, e)
    r = match(rh, line, e)
    assert r.status_code == 409 and r.json()["error"]["code"] == "linha_ja_conciliada"
    assert len(rh.s.rows("settlements")) == 1


def test_partial_open_entry_is_settled_for_the_line_amount(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    line = upload_one(rh, acc, amount="40.00")
    d = match(rh, line, e).json()["data"]
    assert d["entry"]["status"] == "partial" and d["entry"]["settled_cents"] == 4000


def test_line_larger_than_the_open_balance_is_refused(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    r = match(rh, upload_one(rh, acc, amount="150.00"), e)
    assert r.status_code == 422 and r.json()["error"]["code"] == "baixa_excede_saldo"
    assert rh.s.rows("settlements") == []


def test_direction_mismatch_is_refused(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, direction="payable", due_date="2026-10-10", amount_cents=10000)
    r = match(rh, upload_one(rh, acc, amount="100.00"), e)
    assert r.status_code == 422 and r.json()["error"]["code"] == "direcao_divergente"


def test_payable_paid_by_a_debit_line(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, direction="payable", due_date="2026-10-10", amount_cents=10000)
    d = match(rh, upload_one(rh, acc, amount="-100.00"), e).json()["data"]
    assert d["entry"]["status"] == "paid" and rh.s.rows("ledger")[0]["direction"] == "out"


def test_cancelled_entry_and_foreign_entry(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    rh.client.post(f"{P}/entries/{e['id']}/cancel", headers=rh.admin)
    line = upload_one(rh, acc)
    assert match(rh, line, e).status_code == 409
    foreign = mk_entry(rh.s_b, due_date="2026-10-10", amount_cents=10000)
    assert match(rh, line, foreign).status_code == 404


def test_line_of_another_org_is_404(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s_b, due_date="2026-10-10", amount_cents=10000)
    line = upload_one(rh, acc)
    assert match(rh, line, e, rh.admin_b).status_code == 404
    assert rh.client.post(f"{P}/statement-lines/{line['id']}/ignore", headers=rh.admin_b).status_code == 404


def test_ignore_then_match_is_refused_and_ignore_is_idempotent(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    line = upload_one(rh, acc)
    assert rh.client.post(f"{P}/statement-lines/{line['id']}/ignore", headers=rh.admin).json()["data"]["match_status"] == "ignored"
    assert rh.client.post(f"{P}/statement-lines/{line['id']}/ignore", headers=rh.admin).status_code == 200
    r = match(rh, line, e)
    assert r.status_code == 409 and r.json()["error"]["code"] == "linha_ignorada"


def test_matched_line_cannot_be_ignored(rh):
    acc = mk_account(rh.s)
    e = mk_entry(rh.s, due_date="2026-10-10", amount_cents=10000)
    line = upload_one(rh, acc)
    match(rh, line, e)
    assert rh.client.post(f"{P}/statement-lines/{line['id']}/ignore", headers=rh.admin).status_code == 409
