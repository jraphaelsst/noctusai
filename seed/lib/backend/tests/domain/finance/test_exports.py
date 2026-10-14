"""Exports: CSV formula injection, LGPD masking, caps, org scope, OFX 2.x round-trip through our own parser."""
from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from noctusai_lib.domain.finance import exports, settlements
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.domain.finance.exports import csv_safe
from noctusai_lib.domain.finance.ofx import parse_ofx

from .conftest import VALID_CPF, mk_account, mk_entry
from .recon_support import rh  # noqa: F401

P = "/api/finance"


def read_csv(resp) -> list[dict]:
    return list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))


@pytest.mark.parametrize("lead", ["=", "+", "-", "@", "\t", "\r"])
def test_formula_leads_are_neutralised(lead):
    assert csv_safe(f"{lead}HYPERLINK(\"http://x\")").startswith("'" + lead)


def test_safe_text_is_untouched():
    assert csv_safe("Mensalidade = outubro") == "Mensalidade = outubro" and csv_safe(None) == ""


def test_entries_csv_http_injection_and_headers(rh):
    mk_entry(rh.s, description='=HYPERLINK("http://evil","x")', counterparty_name="@cmd", notes="-1+1", amount_cents=12345)
    r = rh.client.get(f"{P}/exports/entries.csv", headers=rh.admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    row = read_csv(r)[0]
    assert row["description"].startswith("'=") and row["counterparty_name"] == "'@cmd" and row["notes"] == "'-1+1"
    assert row["amount"] == "123.45" and row["settled"] == "0.00"


def test_entries_csv_filters_and_org_scope(rh):
    mk_entry(rh.s, description="mine", direction="receivable")
    mk_entry(rh.s, description="pay", direction="payable")
    mk_entry(rh.s_b, description="other org")
    rows = read_csv(rh.client.get(f"{P}/exports/entries.csv?direction=payable", headers=rh.admin))
    assert [r["description"] for r in rows] == ["pay"]
    assert {r["description"] for r in read_csv(rh.client.get(f"{P}/exports/entries.csv", headers=rh.admin))} == {"mine", "pay"}


def test_counterparty_doc_masked_unless_admin(rh):
    mk_entry(rh.s, counterparty_doc=VALID_CPF)
    masked = read_csv_bytes(exports.entries_csv(rh.s, is_admin=False))
    full = read_csv_bytes(exports.entries_csv(rh.s, is_admin=True))
    assert masked[0]["counterparty_doc"] == "***.982.247-**" and VALID_CPF not in str(masked)
    assert full[0]["counterparty_doc"] == VALID_CPF


def read_csv_bytes(b: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))))


def test_row_cap_refuses_instead_of_truncating(rh):
    for _ in range(3):
        mk_entry(rh.s)
    with pytest.raises(FinanceError) as e:
        exports.entries_csv(rh.s, is_admin=True, max_rows=2)
    assert e.value.code == "exportacao_grande_demais" and e.value.status_code == 422
    assert len(read_csv_bytes(exports.entries_csv(rh.s, is_admin=True, max_rows=3))) == 3


def test_csv_pages_past_one_page(rh):
    for i in range(205):
        mk_entry(rh.s, description=f"e{i}")
    assert len(read_csv(rh.client.get(f"{P}/exports/entries.csv", headers=rh.admin))) == 205


def booked_account(rh):
    acc = mk_account(rh.s, "Itaú", bank_code="0341", agency="1234", number="56789-0")
    e = mk_entry(rh.s, description="Venda <b>& \x07co", amount_cents=10000, due_date="2026-10-05")
    settlements.settle_entry(rh.s, e["id"], {"account_id": acc["id"], "amount_cents": 10000, "fee_cents": 199, "settled_on": date(2026, 10, 5)})
    p = mk_entry(rh.s, direction="payable", description="Aluguel", amount_cents=4000, due_date="2026-10-06")
    settlements.settle_entry(rh.s, p["id"], {"account_id": acc["id"], "amount_cents": 4000, "settled_on": date(2026, 10, 6)})
    return acc


def test_ledger_ofx_round_trips_through_our_own_parser(rh):
    acc = booked_account(rh)
    r = rh.client.get(f"{P}/exports/ledger.ofx?account_id={acc['id']}&from=2026-10-01&to=2026-10-31", headers=rh.admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ofx")
    assert r.content.startswith(b"<?xml") and b'OFXHEADER="200"' in r.content and b"<CURDEF>BRL</CURDEF>" in r.content
    parsed = parse_ofx(r.content)
    ledger = {l["id"]: l for l in rh.s.rows("ledger")}
    assert len(parsed.lines) == len(ledger) == 3
    for line in parsed.lines:
        row = ledger[line.fitid]
        sign = 1 if row["direction"] == "in" else -1
        assert line.amount_cents == sign * row["amount_cents"] and line.posted_on.isoformat() == row["occurred_on"]
    assert sum(l.amount_cents for l in parsed.lines) == 10000 - 199 - 4000
    assert (parsed.period_start, parsed.period_end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert b"\x07" not in r.content and b"<b>" not in r.content  # control chars dropped, markup escaped


def test_ledger_ofx_reimports_into_another_account_without_loss(rh):
    acc = booked_account(rh)
    ofx = rh.client.get(f"{P}/exports/ledger.ofx?account_id={acc['id']}&from=2026-10-01&to=2026-10-31", headers=rh.admin).content
    other = mk_account(rh.s, "Espelho")
    d = rh.upload(other["id"], "razao.ofx", ofx).json()["data"]
    assert d["lines"] == 3


def test_ledger_ofx_range_cap_and_scope(rh):
    acc = booked_account(rh)
    with pytest.raises(FinanceError) as e:
        exports.ledger_ofx(rh.s, acc["id"], date_from=date(2026, 10, 1), date_to=date(2026, 10, 31), max_rows=2)
    assert e.value.code == "exportacao_grande_demais"
    assert rh.client.get(f"{P}/exports/ledger.ofx?account_id={acc['id']}", headers=rh.admin_b).status_code == 404
    assert rh.client.get(f"{P}/exports/ledger.ofx", headers=rh.admin).status_code == 422  # account_id is required
