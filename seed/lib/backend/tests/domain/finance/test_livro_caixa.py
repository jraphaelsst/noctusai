"""Livro Caixa (E21): cash-basis book over the ledger -- running saldo, transfers out, CSV/PDF, caps, org scope."""
from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from noctusai_lib.domain.finance import livro_caixa, settlements
from noctusai_lib.domain.finance.errors import FinanceError

from .accountant_support import ah, ah_plain  # noqa: F401
from .conftest import mk_account, mk_entry

Q = "from=2026-10-01&to=2026-10-31"


def pay(s, e, acc, amount, on, **kw):
    return settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": amount, "settled_on": on, **kw})


@pytest.fixture
def book(ah):
    s = ah.s
    bank = mk_account(s, "Banco", opening_balance_cents=100_00, opening_date="2026-01-01")
    other = mk_account(s, "Caixa", kind="cash")
    r = mk_entry(s, direction="receivable", description="Mensalidade outubro", counterparty_name="Ana", amount_cents=50_00)
    pay(s, r, bank, 50_00, date(2026, 10, 5), fee_cents=1_00)
    p = mk_entry(s, direction="payable", description="Aluguel", amount_cents=20_00)
    pay(s, p, bank, 20_00, date(2026, 10, 6))
    settlements.create_transfer(s, {"from_account_id": bank["id"], "to_account_id": other["id"], "amount_cents": 30_00, "occurred_on": date(2026, 10, 7)})
    old = mk_entry(s, direction="receivable", description="Setembro", amount_cents=7_00)
    pay(s, old, bank, 7_00, date(2026, 9, 20))
    return ah


def test_running_balance_totals_and_transfers_excluded(book):
    d = book.get(f"/reports/livro-caixa?{Q}").json()["data"]
    assert d["opening_balance_cents"] == 100_00 + 7_00  # opening + September receipt
    hist = [(r["history"], r["in"], r["out"], r["balance_cents"]) for r in d["rows"]]
    assert hist == [
        ("Mensalidade outubro", 50_00, 0, 157_00),
        ("Tarifa: Mensalidade outubro", 0, 1_00, 156_00),
        ("Aluguel", 0, 20_00, 136_00),
    ]  # the R$ 30 transfer between own accounts is neither income nor expense
    assert d["total_in_cents"] == 50_00 and d["total_out_cents"] == 21_00 and d["closing_balance_cents"] == 136_00
    assert d["rows"][0]["counterparty"] == "Ana" and d["rows"][0]["account"] == "Banco"
    assert "LC 123/2006 art. 26" in d["legal_basis"] and d["disclaimer"]


def test_pagination_is_presentation_only(book):
    d = book.get(f"/reports/livro-caixa?{Q}&page=2&page_size=2").json()["data"]
    assert [r["history"] for r in d["rows"]] == ["Aluguel"] and d["row_count"] == 3
    assert d["closing_balance_cents"] == 136_00 and d["rows"][0]["balance_cents"] == 136_00  # saldo spans the whole period


def test_account_opening_inside_the_period_is_a_line(ah):
    mk_account(ah.s, "Novo", opening_balance_cents=40_00, opening_date="2026-10-03")
    d = ah.get(f"/reports/livro-caixa?{Q}").json()["data"]
    assert d["opening_balance_cents"] == 0 and d["rows"][0]["history"] == "Saldo inicial — Novo" and d["closing_balance_cents"] == 40_00


def test_csv(book):
    r = book.get(f"/exports/livro-caixa.csv?{Q}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "no-store" in r.headers["cache-control"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[1] == ["saldo anterior", "107.00"]
    assert rows[3][:1] == ["2026-10-05"] and rows[3][5:] == ["50.00", "", "157.00"]
    assert rows[-3][0] == "total" and rows[-3][5:] == ["50.00", "21.00", "136.00"]


def test_csv_neutralises_formulas(ah):
    bank = mk_account(ah.s, "Banco")
    e = mk_entry(ah.s, direction="receivable", description="=HYPERLINK(\"http://x\")", amount_cents=10_00)
    pay(ah.s, e, bank, 10_00, date(2026, 10, 5))
    text = ah.get(f"/exports/livro-caixa.csv?{Q}").content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text


def test_pdf_is_a_real_pdf(book):
    r = book.get(f"/exports/livro-caixa.pdf?{Q}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")


def test_caps_are_refused_not_truncated(book):
    with pytest.raises(FinanceError) as e:
        livro_caixa.livro_caixa(book.s, date(2026, 10, 1), date(2026, 10, 31), max_rows=2)
    assert e.value.code == "exportacao_grande_demais"


def test_range_is_validated(ah):
    assert ah.get("/reports/livro-caixa?from=2026-10-31&to=2026-10-01").status_code == 422


def test_org_scope(book):
    mk_entry(book.s_b, direction="receivable", amount_cents=999_00)
    other = mk_account(book.s_b, "Banco B")
    pay(book.s_b, mk_entry(book.s_b, direction="receivable", amount_cents=5_00), other, 5_00, date(2026, 10, 9))
    d = book.get(f"/reports/livro-caixa?{Q}").json()["data"]
    assert d["total_in_cents"] == 50_00  # org B's receipt is not in org A's book
    db = book.get(f"/reports/livro-caixa?{Q}", book.admin_b).json()["data"]
    assert db["total_in_cents"] == 5_00 and db["opening_balance_cents"] == 0


def test_gate_matrix(ah, ah_plain):
    for path in (f"/reports/livro-caixa?{Q}", f"/exports/livro-caixa.csv?{Q}", f"/exports/livro-caixa.pdf?{Q}"):
        assert ah.client.get(f"/api/finance{path}").status_code == 401
        assert ah.get(path, ah.staff).status_code == 403
        assert ah.get(path, ah.accountant).status_code == 200
        assert ah_plain.get(path, ah_plain.accountant).status_code == 403
