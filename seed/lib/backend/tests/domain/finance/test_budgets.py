"""Budget vs actual (E21): CRUD (admin), the report on the DRE's own basis, org isolation, strict 401/403."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import budgets, categories, dre
from noctusai_lib.domain.finance.errors import FinanceError

from .accountant_support import ah, ah_plain  # noqa: F401
from .conftest import mk_account, mk_entry


def cat(s, name):
    return next(c for c in categories.list_categories(s) if c["name"] == name)


def put(ah, items, headers=None):
    return ah.client.put("/api/finance/budgets", headers=headers or ah.admin, json={"items": items})


def test_put_is_an_upsert_per_category_and_month(ah):
    mkt = cat(ah.s, "Marketing")
    r = put(ah, [{"category_id": mkt["id"], "month": "2026-10-01", "amount_cents": 50000}])
    assert r.status_code == 200 and r.json()["data"][0]["amount_cents"] == 50000
    r2 = put(ah, [{"category_id": mkt["id"], "month": "2026-10-17", "amount_cents": 70000}])  # any day -> that month's row
    assert r2.status_code == 200
    rows = ah.get("/budgets?from=2026-10-01&to=2026-10-31").json()["data"]
    assert len(rows) == 1 and rows[0]["amount_cents"] == 70000 and rows[0]["month"][:10] == "2026-10-01"
    assert rows[0]["id"] == r.json()["data"][0]["id"]  # updated in place, not duplicated


def test_delete_budget_and_unknown_is_404(ah):
    mkt = cat(ah.s, "Marketing")
    bid = put(ah, [{"category_id": mkt["id"], "month": "2026-10-01", "amount_cents": 1}]).json()["data"][0]["id"]
    assert ah.client.delete(f"/api/finance/budgets/{bid}", headers=ah.admin).status_code == 204
    assert ah.get("/budgets?from=2026-10-01&to=2026-10-31").json()["data"] == []
    assert ah.client.delete(f"/api/finance/budgets/{bid}", headers=ah.admin).status_code == 404


def test_writes_are_strict_401_and_403(ah):
    mkt = cat(ah.s, "Marketing")
    body = {"items": [{"category_id": mkt["id"], "month": "2026-10-01", "amount_cents": 1}]}
    assert ah.client.put("/api/finance/budgets", json=body).status_code == 401
    assert ah.client.put("/api/finance/budgets", headers=ah.staff, json=body).status_code == 403
    assert ah.client.put("/api/finance/budgets", headers=ah.accountant, json=body).status_code == 403  # read grant never writes
    bid = put(ah, body["items"]).json()["data"][0]["id"]
    assert ah.client.delete(f"/api/finance/budgets/{bid}").status_code == 401
    assert ah.client.delete(f"/api/finance/budgets/{bid}", headers=ah.accountant).status_code == 403


def test_inputs_are_validated(ah):
    mkt, transfer = cat(ah.s, "Marketing"), cat(ah.s, "Entre contas")
    assert put(ah, [{"category_id": mkt["id"], "month": "2026-10-01", "amount_cents": -1}]).status_code == 422
    assert put(ah, []).status_code == 422
    assert put(ah, [{"category_id": mkt["id"], "month": "2026-10-01", "amount_cents": 1, "extra": 1}]).status_code == 422  # extra=forbid
    unknown = put(ah, [{"category_id": "11111111-1111-4111-8111-111111111111", "month": "2026-10-01", "amount_cents": 1}])
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "referencia_invalida"
    tr = put(ah, [{"category_id": transfer["id"], "month": "2026-10-01", "amount_cents": 1}])
    assert tr.status_code == 422 and tr.json()["error"]["code"] == "categoria_sem_orcamento"


def test_org_isolation(ah):
    mkt_a = cat(ah.s, "Marketing")
    mkt_b = cat(ah.s_b, "Marketing")
    put(ah, [{"category_id": mkt_a["id"], "month": "2026-10-01", "amount_cents": 111}])
    # org B cannot budget org A's category, cannot see or delete A's budgets
    steal = put(ah, [{"category_id": mkt_a["id"], "month": "2026-10-01", "amount_cents": 1}], headers=ah.admin_b)
    assert steal.status_code == 422 and steal.json()["error"]["code"] == "referencia_invalida"
    assert ah.get("/budgets?from=2026-10-01&to=2026-10-31", ah.admin_b).json()["data"] == []
    bid = ah.get("/budgets?from=2026-10-01&to=2026-10-31").json()["data"][0]["id"]
    assert ah.client.delete(f"/api/finance/budgets/{bid}", headers=ah.admin_b).status_code == 404
    assert put(ah, [{"category_id": mkt_b["id"], "month": "2026-10-01", "amount_cents": 9}], headers=ah.admin_b).status_code == 200
    assert ah.get("/budgets?from=2026-10-01&to=2026-10-31").json()["data"][0]["amount_cents"] == 111


def test_report_actual_is_the_dre_basis_with_variance_and_status(ah):
    s = ah.s
    mkt, sales = cat(s, "Marketing"), cat(s, "Vendas")
    mk_entry(s, direction="payable", description="Anuncio", category_id=mkt["id"], amount_cents=80000, due_date="2026-10-10")
    mk_entry(s, direction="payable", description="Anuncio nov", category_id=mkt["id"], amount_cents=10000, due_date="2026-11-10")
    mk_entry(s, direction="receivable", description="Venda", category_id=sales["id"], amount_cents=300000, due_date="2026-10-12")
    cancelled = mk_entry(s, direction="payable", description="Cancelado", category_id=mkt["id"], amount_cents=99999, due_date="2026-10-15")
    from noctusai_lib.domain.finance import entries
    entries.cancel_entry(s, cancelled["id"])
    put(ah, [
        {"category_id": mkt["id"], "month": "2026-10-01", "amount_cents": 50000},
        {"category_id": mkt["id"], "month": "2026-11-01", "amount_cents": 20000},
        {"category_id": sales["id"], "month": "2026-10-01", "amount_cents": 400000},
    ])
    rep = ah.get("/reports/budget?from=2026-10-01&to=2026-11-30").json()["data"]
    rows = {r["name"]: r for r in rep["rows"]}
    assert rep["months"] == ["2026-10", "2026-11"]
    m = rows["Marketing"]["months"]
    assert m["2026-10"] == {"budget_cents": 50000, "actual_cents": 80000, "variance_cents": 30000, "status": "over"}
    assert m["2026-11"]["status"] == "ok" and m["2026-11"]["actual_cents"] == 10000
    assert rows["Vendas"]["months"]["2026-10"]["status"] == "under"  # income below plan
    assert rows["Marketing"]["total"]["variance_cents"] == (80000 + 10000) - (50000 + 20000)
    # "actual" is exactly what the DRE shows for the category (same collection code), never a second opinion
    d = dre.build_dre(s, date(2026, 10, 1), date(2026, 11, 1))
    selling = next(i for i in d["statement"] if i["key"] == "selling_expenses")
    assert selling["by_month"]["2026-10"] == 80000
    assert rep["expense"]["actual_cents"] == 90000 and rep["income"]["actual_cents"] == 300000
    assert rep["result"]["actual_cents"] == 210000
    assert rep["warnings"] == []


def test_report_without_budgets_warns_and_validates_range(ah):
    s = ah.s
    mkt = cat(s, "Marketing")
    mk_entry(s, direction="payable", category_id=mkt["id"], amount_cents=1000, due_date="2026-10-10")
    rep = ah.get("/reports/budget?from=2026-10-01&to=2026-10-31").json()["data"]
    assert [w["code"] for w in rep["warnings"]] == ["sem_orcamento"]
    assert rep["rows"][0]["months"]["2026-10"]["status"] == "no_budget"
    assert ah.get("/reports/budget?from=2026-10-01&to=2026-01-01").status_code == 422
    assert ah.get("/reports/budget?from=2015-01-01&to=2026-01-01").json()["error"]["code"] == "periodo_grande_demais"


def test_report_and_list_are_org_scoped(ah):
    mk_entry(ah.s_b, direction="payable", category_id=cat(ah.s_b, "Marketing")["id"], amount_cents=5000, due_date="2026-10-10")
    rep = ah.get("/reports/budget?from=2026-10-01&to=2026-10-31").json()["data"]
    assert rep["rows"] == [] and rep["expense"]["actual_cents"] == 0


def test_reads_are_admin_or_accountant_only(ah, ah_plain):
    for path in ("/reports/budget", "/budgets"):
        assert ah.client.get(f"/api/finance{path}").status_code == 401
        assert ah.get(path, ah.staff).status_code == 403
        assert ah.get(path, ah.accountant).status_code == 200
        assert ah.get(path, ah.admin).status_code == 200
        assert ah_plain.get(path, ah_plain.accountant).status_code == 403  # nothing wired -> admins only


def test_service_level_guards(ah):
    with pytest.raises(FinanceError):
        budgets.upsert_budgets(ah.s, [{"category_id": "00000000-0000-4000-8000-000000000000", "month": date(2026, 10, 1), "amount_cents": 1}])
