"""Domínio export (E16/E21): official-sample shape, accounting codes, 422 listing what is missing, org scope, gates."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import categories, settlements

from .accountant_support import ah, ah_plain  # noqa: F401
from .conftest import VALID_CNPJ, mk_account, mk_entry

Q = f"from=2026-10-01&to=2026-10-31&cnpj={VALID_CNPJ}"


def cat(s, name):
    return next(c for c in categories.list_categories(s) if c["name"] == name)


def pay(s, e, acc, amount, on, **kw):
    return settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": amount, "settled_on": on, **kw})


def code(ah, cat_row, value, headers=None):
    r = ah.client.patch(f"/api/finance/categories/{cat_row['id']}", headers=headers or ah.admin, json={"accounting_code": value})
    assert r.status_code == 200, r.text


def acct_code(ah, acc, value):
    r = ah.client.patch(f"/api/finance/accounts/{acc['id']}", headers=ah.admin, json={"accounting_code": value})
    assert r.status_code == 200, r.text


def lines(resp) -> list[str]:
    assert resp.status_code == 200, resp.text
    return resp.content.decode("ascii").split("\r\n")[:-1]


@pytest.fixture
def mapped(ah):
    s = ah.s
    bank = mk_account(s, "Banco")
    sales, rent, fees = cat(s, "Vendas"), cat(s, "Aluguel e condomínio"), cat(s, "Taxas de cartão/gateway")
    for c, v in ((sales, "3.1.01"), (rent, "4.1.02"), (fees, "4.2.09")):
        code(ah, c, v)
    acct_code(ah, bank, "1.1.01")
    return ah, s, bank, sales, rent


def test_official_shape_receivable_payable_and_fee(mapped):
    ah, s, bank, sales, rent = mapped
    r = mk_entry(s, direction="receivable", description="Mensalidade ação outubro", category_id=sales["id"], amount_cents=557124)
    pay(s, r, bank, 557124, date(2026, 10, 10), fee_cents=199)
    p = mk_entry(s, direction="payable", description="Aluguel", category_id=rent["id"], amount_cents=120000)
    pay(s, p, bank, 120000, date(2026, 10, 5))
    out = lines(ah.get(f"/exports/dominio.txt?{Q}"))
    assert out[0] == f"|0000|{VALID_CNPJ}|"
    body = out[1:]
    assert body == [
        "|6000|X||||", "|6100|05/10/2026|4.1.02|1.1.01|1200,00||Aluguel||||",
        "|6000|X||||", "|6100|10/10/2026|1.1.01|3.1.01|5571,24||Mensalidade acao outubro||||",
        "|6000|X||||", "|6100|10/10/2026|4.2.09|1.1.01|1,99||Tarifa: Mensalidade acao outubro||||",
    ]
    # 6100 has exactly the 10 fields of the layout (id + 9) between its pipes, like the official sample
    assert all(len(row[1:-1].split("|")) == 10 for row in body if row.startswith("|6100"))
    r = ah.get(f"/exports/dominio.txt?{Q}")
    assert r.headers["content-type"].startswith("text/plain") and "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"


def test_history_code_is_optional_and_numeric(mapped):
    ah, s, bank, sales, _ = mapped
    pay(s, mk_entry(s, direction="receivable", category_id=sales["id"], amount_cents=1000), bank, 1000, date(2026, 10, 10))
    assert lines(ah.get(f"/exports/dominio.txt?{Q}&history_code=7"))[2].endswith("|10,00|7|Mensalidade||||")
    assert ah.get(f"/exports/dominio.txt?{Q}&history_code=0").status_code == 422


def test_refund_and_reversal_and_refund_of_payable(mapped):
    ah, s, bank, sales, rent = mapped
    e = mk_entry(s, direction="receivable", category_id=sales["id"], amount_cents=10_00)
    st = pay(s, e, bank, 10_00, date(2026, 10, 3))
    settlements.settle_entry(s, e["id"], {"account_id": bank["id"], "kind": "refund", "amount_cents": 4_00, "settled_on": date(2026, 10, 8)})
    p = mk_entry(s, direction="payable", category_id=rent["id"], amount_cents=9_00)
    st2 = pay(s, p, bank, 9_00, date(2026, 10, 9))
    settlements.reverse_settlement(s, st2["settlement"]["id"] if "settlement" in st2 else st2["id"], "erro", user_id=None)
    out = lines(ah.get(f"/exports/dominio.txt?{Q}"))
    posted = [x for x in out if x.startswith("|6100")]
    assert posted == ["|6100|03/10/2026|1.1.01|3.1.01|10,00||Mensalidade||||", "|6100|08/10/2026|3.1.01|1.1.01|4,00||Mensalidade||||"]


def test_transfer_between_accounts(mapped):
    ah, s, bank, sales, _ = mapped
    cash = mk_account(s, "Caixa", kind="cash")
    acct_code(ah, cash, "1.1.02")
    pay(s, mk_entry(s, direction="receivable", category_id=sales["id"], amount_cents=1000), bank, 1000, date(2026, 10, 2))
    settlements.create_transfer(s, {"from_account_id": bank["id"], "to_account_id": cash["id"], "amount_cents": 25_00, "occurred_on": date(2026, 10, 4), "description": "Sangria"})
    posted = [x for x in lines(ah.get(f"/exports/dominio.txt?{Q}")) if x.startswith("|6100")]
    assert "|6100|04/10/2026|1.1.02|1.1.01|25,00||Sangria||||" in posted


def test_missing_codes_are_refused_with_the_exact_list(ah):
    s = ah.s
    bank = mk_account(s, "Banco Sem Codigo")
    sales = cat(s, "Vendas")
    pay(s, mk_entry(s, direction="receivable", category_id=sales["id"], amount_cents=1000), bank, 1000, date(2026, 10, 10), fee_cents=10)
    r = ah.get(f"/exports/dominio.txt?{Q}")
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "dominio_codigos_ausentes"
    assert err["details"]["accounts"] == [{"id": bank["id"], "name": "Banco Sem Codigo"}]
    assert {c["name"] for c in err["details"]["categories"]} == {"Vendas", "Taxas de cartão/gateway"}
    assert "Preencha os códigos" in err["message"]
    # fixing exactly what was listed unblocks the export -- nothing else is asked for
    code(ah, sales, "3.1.01")
    code(ah, cat(s, "Taxas de cartão/gateway"), "4.2.09")
    acct_code(ah, bank, "1.1.01")
    assert ah.get(f"/exports/dominio.txt?{Q}").status_code == 200


def test_entry_without_category_is_listed_not_guessed(ah):
    s = ah.s
    bank = mk_account(s, "Banco")
    acct_code(ah, bank, "1.1.01")
    pay(s, mk_entry(s, direction="receivable", amount_cents=1000), bank, 1000, date(2026, 10, 10))
    err = ah.get(f"/exports/dominio.txt?{Q}").json()["error"]
    assert err["code"] == "dominio_codigos_ausentes" and err["details"]["issues"] == [{"code": "lancamento_sem_categoria", "count": 1}]


def test_empty_period_and_inscription_validation(mapped):
    ah, *_ = mapped
    empty = ah.get(f"/exports/dominio.txt?{Q}")
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "dominio_sem_movimento"
    bad = ah.get("/exports/dominio.txt?from=2026-10-01&to=2026-10-31&cnpj=11111111111111")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "inscricao_invalida"
    assert ah.get("/exports/dominio.txt?from=2026-10-01&to=2026-10-31").status_code == 422  # cnpj is required
    assert ah.get(f"/exports/dominio.txt?from=2026-10-31&to=2026-10-01&cnpj={VALID_CNPJ}").status_code == 422


def test_text_is_ascii_and_cannot_break_the_layout(mapped):
    ah, s, bank, sales, _ = mapped
    pay(s, mk_entry(s, direction="receivable", description="A|B\r\nC\tção — “x”", category_id=sales["id"], amount_cents=1000), bank, 1000, date(2026, 10, 10))
    posted = [x for x in lines(ah.get(f"/exports/dominio.txt?{Q}")) if x.startswith("|6100")]
    assert len(posted) == 1 and posted[0].count("|") == 11
    assert posted[0].split("|")[7] == "A B C cao x"


def test_org_scope(mapped):
    ah, s, bank, sales, _ = mapped
    other = mk_account(ah.s_b, "Banco B")
    pay(ah.s_b, mk_entry(ah.s_b, direction="receivable", category_id=cat(ah.s_b, "Vendas")["id"], amount_cents=500_00), other, 500_00, date(2026, 10, 10))
    r = ah.get(f"/exports/dominio.txt?{Q}")
    assert r.status_code == 422 and r.json()["error"]["code"] == "dominio_sem_movimento"  # org A has nothing; B's receipt is invisible
    r = ah.get(f"/exports/dominio.txt?{Q}", ah.admin_b)
    assert r.status_code == 422 and r.json()["error"]["details"]["accounts"][0]["name"] == "Banco B"


def test_accounting_code_api(ah):
    sales = cat(ah.s, "Vendas")
    assert sales.get("accounting_code") is None
    code(ah, sales, "  3.1.01  ")
    assert cat(ah.s, "Vendas")["accounting_code"] == "3.1.01"
    code(ah, sales, "")  # blank clears
    assert cat(ah.s, "Vendas").get("accounting_code") is None
    r = ah.client.post("/api/finance/categories", headers=ah.admin, json={"name": "Nova", "direction": "expense", "accounting_code": "9.9"})
    assert r.json()["data"]["accounting_code"] == "9.9"
    assert ah.client.patch(f"/api/finance/categories/{sales['id']}", headers=ah.admin, json={"accounting_code": "x" * 41}).status_code == 422
    assert ah.client.patch(f"/api/finance/categories/{sales['id']}", headers=ah.accountant, json={"accounting_code": "1"}).status_code == 403
    assert ah.client.patch(f"/api/finance/categories/{sales['id']}", json={"accounting_code": "1"}).status_code == 401


def test_gate_matrix(mapped, ah_plain):
    ah, s, bank, sales, _ = mapped
    pay(s, mk_entry(s, direction="receivable", category_id=sales["id"], amount_cents=1000), bank, 1000, date(2026, 10, 10))
    path = f"/exports/dominio.txt?{Q}"
    assert ah.client.get(f"/api/finance{path}").status_code == 401
    assert ah.get(path, ah.staff).status_code == 403
    assert ah.get(path, ah.accountant).status_code == 200
    assert ah_plain.get(path, ah_plain.accountant).status_code == 403
