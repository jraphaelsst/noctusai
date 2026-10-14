"""Cash flow (realized + projected), receivables aging (the DRE: test_dre.py)."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import reports, settlements
from noctusai_lib.domain.finance.errors import FinanceError

from .conftest import VALID_CNPJ, VALID_CPF, mk_account, mk_entry


def pay(s, e, acc, amount, on, **kw):
    return settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": amount, "settled_on": on, **kw})


# ── cash flow ──


def test_cashflow_realized_projected_and_balances(s):
    acc = mk_account(s, opening_balance_cents=1000, opening_date="2026-01-01")
    r1 = mk_entry(s, direction="receivable", due_date="2026-02-10", amount_cents=5000)
    p1 = mk_entry(s, direction="payable", due_date="2026-02-12", amount_cents=2000)
    mk_entry(s, direction="receivable", due_date="2026-03-05", amount_cents=7000)  # projected only
    paid_early = mk_entry(s, direction="receivable", due_date="2026-01-20", amount_cents=300)
    pay(s, paid_early, acc, 300, "2026-01-20")  # before the period: opening
    pay(s, r1, acc, 3000, "2026-02-11", fee_cents=100)  # partial: 2000 still projected
    pay(s, p1, acc, 2000, "2026-02-13")
    cf = reports.cashflow(s, date(2026, 2, 1), date(2026, 3, 31))
    assert cf["opening_balance_cents"] == 1000 + 300
    feb, mar = cf["buckets"]
    assert (feb["month"], mar["month"]) == ("2026-02", "2026-03")
    assert (feb["realized_in_cents"], feb["realized_out_cents"]) == (3000, 2000 + 100)
    assert (feb["projected_in_cents"], feb["projected_out_cents"]) == (2000, 0)  # remaining of the partial
    assert (mar["projected_in_cents"], mar["realized_in_cents"]) == (7000, 0)
    assert cf["closing_realized_balance_cents"] == 1300 + 3000 - 2100
    assert cf["closing_projected_balance_cents"] == cf["closing_realized_balance_cents"] + 2000 + 7000


def test_cashflow_reversal_nets_out_and_transfers_wash_in_the_aggregate(s):
    a, b = mk_account(s, "A"), mk_account(s, "B")
    e = mk_entry(s, due_date="2026-02-10", amount_cents=1000)
    st = pay(s, e, a, 1000, "2026-02-10")["settlement"]
    settlements.create_transfer(s, {"from_account_id": a["id"], "to_account_id": b["id"], "amount_cents": 400, "occurred_on": "2026-02-11"})
    agg = reports.cashflow(s, date(2026, 2, 1), date(2026, 2, 28))["buckets"][0]
    assert (agg["realized_in_cents"], agg["realized_out_cents"]) == (1000, 0)  # transfer is invisible in aggregate
    per_account = reports.cashflow(s, date(2026, 2, 1), date(2026, 2, 28), account_id=a["id"])["buckets"][0]
    assert (per_account["realized_in_cents"], per_account["realized_out_cents"]) == (1000, 400)
    settlements.reverse_settlement(s, st["id"], "x")  # reversal books today's date, outside the window
    assert reports.cashflow(s, date(2026, 2, 1), date(2026, 2, 28))["buckets"][0]["realized_in_cents"] == 1000


def test_cashflow_range_rules_and_org_scope(s, s_b):
    with pytest.raises(FinanceError):
        reports.cashflow(s, date(2026, 3, 1), date(2026, 2, 1))
    with pytest.raises(FinanceError) as err:
        reports.cashflow(s, date(2020, 1, 1), date(2026, 1, 1))
    assert err.value.code == "periodo_grande_demais"
    foreign = mk_account(s_b)
    with pytest.raises(FinanceError):
        reports.cashflow(s, date(2026, 1, 1), date(2026, 2, 1), account_id=foreign["id"])
    mk_entry(s_b, due_date="2026-01-10", amount_cents=999)
    assert reports.cashflow(s, date(2026, 1, 1), date(2026, 1, 31))["totals"]["projected_in_cents"] == 0


# ── DRE ── (the structured statement is covered in test_dre.py; only the legacy import path is pinned here)


def test_reports_dre_keeps_its_import_path_and_answers_the_structured_statement(s):
    out = reports.dre(s, date(2026, 1, 1), date(2026, 3, 31))
    assert out["months"] == ["2026-01", "2026-02", "2026-03"] and out["view"] == "statement"
    assert [i["key"] for i in out["statement"]][-1] == "net_result"


# ── aging ──


def test_aging_buckets_group_by_counterparty_and_use_the_remaining_amount(s):
    on = date(2026, 6, 30)
    mk_entry(s, counterparty_name="Ana", counterparty_doc=VALID_CPF, amount_cents=1000, due_date="2026-06-20")  # 10d
    mk_entry(s, counterparty_name="Ana", counterparty_doc=VALID_CPF, amount_cents=2000, due_date="2026-05-01")  # 60d
    e3 = mk_entry(s, counterparty_name="Bia Ltda", counterparty_doc=VALID_CNPJ, amount_cents=5000, due_date="2026-03-01")  # 121d
    pay(s, e3, mk_account(s), 1500, "2026-03-02")  # remaining 3500
    mk_entry(s, counterparty_name="Futuro", amount_cents=9999, due_date="2026-07-15")  # not due
    mk_entry(s, direction="payable", counterparty_name="Fornecedor", amount_cents=9999, due_date="2026-01-01")  # payables never age
    out = reports.aging(s, as_of=on, is_admin=True)
    by = {c["counterparty_name"]: c for c in out["counterparties"]}
    assert set(by) == {"Ana", "Bia Ltda"}
    assert by["Ana"]["buckets"] == {"d1_30": 1000, "d31_60": 2000, "d61_90": 0, "d90_plus": 0}
    assert by["Bia Ltda"]["buckets"]["d90_plus"] == 3500 and by["Bia Ltda"]["total_cents"] == 3500
    assert out["counterparties"][0]["counterparty_name"] == "Bia Ltda"  # biggest debt first
    assert out["totals"]["total_cents"] == 6500
    assert by["Ana"]["oldest_due_date"] == "2026-05-01" and by["Ana"]["entries"] == 2


def test_aging_masks_the_doc_for_non_admins(s):
    mk_entry(s, counterparty_name="Ana", counterparty_doc=VALID_CPF, due_date="2026-01-01")
    staff = reports.aging(s, as_of=date(2026, 6, 1), is_admin=False)["counterparties"][0]["counterparty_doc"]
    admin = reports.aging(s, as_of=date(2026, 6, 1), is_admin=True)["counterparties"][0]["counterparty_doc"]
    assert staff == "***.982.247-**" and admin == VALID_CPF


def test_aging_bucket_edges():
    assert [reports._bucket_of(d) for d in (1, 30, 31, 60, 61, 90, 91, 400)] == [
        "d1_30", "d1_30", "d31_60", "d31_60", "d61_90", "d61_90", "d90_plus", "d90_plus",
    ]


def test_aging_org_scope(s, s_b):
    mk_entry(s_b, counterparty_name="Outra", due_date="2026-01-01")
    assert reports.aging(s, as_of=date(2026, 6, 1))["counterparties"] == []
