"""The accountant READ role (E16): reports + exports pass, every write is refused, documents stay masked, default stays admin-only."""
from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from noctusai_lib.domain.finance import settlements

from .accountant_support import ah, ah_plain  # noqa: F401
from .conftest import VALID_CPF, mk_account, mk_entry

READS = [
    "/reports/dre", "/reports/simples-base", "/reports/budget", "/reports/livro-caixa", "/reports/mei-monthly", "/budgets",
    "/accountant-checklist", "/exports/dre.csv", "/exports/entries.csv", "/exports/livro-caixa.csv", "/exports/livro-caixa.pdf",
    "/exports/mei-monthly.csv", "/exports/mei-monthly.pdf",
]


@pytest.mark.parametrize("path", READS)
def test_accountant_reads_what_an_admin_reads(ah, path):
    assert ah.client.get(f"/api/finance{path}").status_code == 401
    assert ah.get(path, ah.staff).status_code == 403
    assert ah.get(path, ah.accountant).status_code == 200, path
    assert ah.get(path, ah.admin).status_code == 200


def test_ofx_export_is_readable_by_the_accountant_too(ah):
    acc = mk_account(ah.s)
    path = f"/exports/ledger.ofx?account_id={acc['id']}"
    assert ah.client.get(f"/api/finance{path}").status_code == 401
    assert ah.get(path, ah.staff).status_code == 403
    assert ah.get(path, ah.accountant).status_code == 200


@pytest.mark.parametrize("path", READS + ["/exports/ledger.ofx?account_id=11111111-1111-4111-8111-111111111111"])
def test_default_without_the_grant_wired_stays_admin_only(ah_plain, path):
    assert ah_plain.get(path, ah_plain.accountant).status_code == 403
    assert ah_plain.get(path, ah_plain.staff).status_code == 403


WRITES = [
    ("post", "/entries", {"direction": "payable", "description": "x", "due_date": "2026-10-20", "amount_cents": 1}),
    ("post", "/accounts", {"name": "x", "kind": "cash"}),
    ("post", "/categories", {"name": "x", "direction": "expense"}),
    ("post", "/cost-centers", {"code": "x", "name": "x"}),
    ("post", "/transfers", {"from_account_id": "11111111-1111-4111-8111-111111111111", "to_account_id": "22222222-2222-4222-8222-222222222222", "amount_cents": 1}),
    ("put", "/dre-settings", {"tax_regime": "mei"}),
    ("put", "/budgets", {"items": [{"category_id": "11111111-1111-4111-8111-111111111111", "month": "2026-10-01", "amount_cents": 1}]}),
    ("post", "/recurrences", {}),
    ("post", "/statements", None),
    ("post", "/accounts/11111111-1111-4111-8111-111111111111/gateway-sync", {}),
    ("post", "/statement-lines/11111111-1111-4111-8111-111111111111/ignore", None),
]


@pytest.mark.parametrize("method,path,body", WRITES)
def test_the_read_grant_never_writes(ah, method, path, body):
    kw = {} if body is None else {"json": body}
    assert ah.client.request(method, f"/api/finance{path}", headers=ah.accountant, **kw).status_code == 403
    assert ah.client.request(method, f"/api/finance{path}", **kw).status_code == 401
    assert ah.client.request(method, f"/api/finance{path}", headers=ah.staff, **kw).status_code == 403


def test_settling_and_attachments_are_closed_to_the_accountant(ah):
    e = mk_entry(ah.s, direction="payable", amount_cents=10_00)
    acc = mk_account(ah.s)
    body = {"account_id": acc["id"], "amount_cents": 10_00}
    assert ah.client.post(f"/api/finance/entries/{e['id']}/settlements", headers=ah.accountant, json=body).status_code == 403
    assert ah.client.patch(f"/api/finance/entries/{e['id']}", headers=ah.accountant, json={"notes": "x"}).status_code == 403
    assert ah.client.post(f"/api/finance/entries/{e['id']}/cancel", headers=ah.accountant).status_code == 403
    assert ah.client.post(f"/api/finance/entries/{e['id']}/attachments", headers=ah.accountant, files={"file": ("a.pdf", b"%PDF", "application/pdf")}).status_code == 403
    assert ah.client.get(f"/api/finance/entries/{e['id']}", headers=ah.accountant).status_code == 200  # staff reads stay open


def test_documents_stay_masked_for_the_accountant(ah):
    mk_entry(ah.s, counterparty_doc=VALID_CPF, description="Venda")
    admin_rows = list(csv.DictReader(io.StringIO(ah.get("/exports/entries.csv").content.decode("utf-8-sig"))))
    acc_rows = list(csv.DictReader(io.StringIO(ah.get("/exports/entries.csv", ah.accountant).content.decode("utf-8-sig"))))
    assert admin_rows[0]["counterparty_doc"] == VALID_CPF  # the org admin decides who sees the number
    assert acc_rows[0]["counterparty_doc"] == "***.982.247-**" and VALID_CPF not in str(acc_rows)


def test_the_grant_does_not_cross_orgs(ah):
    mk_entry(ah.s_b, description="Other org entry", amount_cents=1)
    rows = list(csv.DictReader(io.StringIO(ah.get("/exports/entries.csv", ah.accountant).content.decode("utf-8-sig"))))
    assert rows == []  # the accountant's session is org A's; org B's data is not there
    assert ah.get("/exports/entries.csv", ah.as_("org-b-admin")).status_code == 200


def test_checklist_reports_dominio_readiness_and_links(ah):
    acc = mk_account(ah.s, "Banco")
    from noctusai_lib.domain.finance import categories
    categories.list_categories(ah.s)
    d = ah.get("/accountant-checklist", ah.accountant).json()["data"]
    r = d["dominio_readiness"]
    assert r["ready"] is False and r["accounts_without_code"] == 1 and r["categories_without_code"] > 10
    names = {e["name"] for e in d["exports"]}
    assert {"livro_caixa_csv", "livro_caixa_pdf", "dominio_txt"} <= names
    ah.client.patch(f"/api/finance/accounts/{acc['id']}", headers=ah.admin, json={"accounting_code": "1.1"})
    assert ah.get("/accountant-checklist").json()["data"]["dominio_readiness"]["accounts_without_code"] == 0
