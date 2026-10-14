"""DRE settings API, the Simples tax base (2026/2027 boundary), the accountant checklist, the DRE CSV."""
from __future__ import annotations

import csv
import io
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.finance import categories, dre_settings, exports, make_finance_router, settlements, simples_base
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

from noctusai_lib.domain.finance._common import Scope
from .conftest import CFG, ORG_A, ORG_B, USER_ID, _admin, _auth, _resolve, make_db, mk_account, mk_entry
from .recon_support import rh  # noqa: F401

P = "/api/finance"


def call(h, method, path, headers=None, **kw):
    return h.client.request(method, path, headers=headers or {}, **kw)


def cat(s, name):
    return next(c for c in categories.list_categories(s) if c["name"] == name)


def pay(s, e, acc, amount, on, **kw):
    return settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": amount, "settled_on": on, **kw})


# ── settings API ──


def test_get_defaults_before_any_save(h):
    r = call(h, "GET", f"{P}/dre-settings", h.staff())
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["persisted"] is False and data["tax_regime"] == "unknown" and data["das_split_irpj_csll"] is False
    assert {k: v["value"] for k, v in data["choices"].items()} == {
        "gateway_fee_line": "selling_expenses", "anticipation_fee_line": "financial_expenses", "chargeback_line": "deductions",
        "chargeback_fee_line": "selling_expenses", "installment_interest_line": "gross_revenue",
    }
    assert all(c["provisional"] and c["confirmed_by"] is None for c in data["choices"].values())


def test_put_is_admin_only_with_strict_status_codes(h):
    body = {"tax_regime": "simples"}
    assert call(h, "PUT", f"{P}/dre-settings", json=body).status_code == 401
    assert call(h, "PUT", f"{P}/dre-settings", h.staff("user"), json=body).status_code == 403
    assert call(h, "GET", f"{P}/dre-settings").status_code == 401
    ok = call(h, "PUT", f"{P}/dre-settings", h.admin, json=body)
    assert ok.status_code == 200 and ok.json()["data"]["tax_regime"] == "simples" and ok.json()["data"]["persisted"] is True


def test_confirming_clears_provisional_and_changing_the_value_reopens_it(h):
    r = call(h, "PUT", f"{P}/dre-settings", h.admin, json={"confirmations": {"gateway_fee_line": {"confirmed": True, "note": "ok, contador Ana"}}})
    c = r.json()["data"]["choices"]["gateway_fee_line"]
    assert c["provisional"] is False and c["confirmed_by"] == USER_ID and c["confirmed_at"] and c["note"] == "ok, contador Ana"
    assert r.json()["data"]["choices"]["chargeback_line"]["provisional"] is True  # untouched
    # Changing the VALUE without a fresh sign-off puts the choice back to provisional.
    r = call(h, "PUT", f"{P}/dre-settings", h.admin, json={"gateway_fee_line": "financial_expenses"})
    c = r.json()["data"]["choices"]["gateway_fee_line"]
    assert c["value"] == "financial_expenses" and c["provisional"] is True and c["confirmed_by"] is None
    # ...unless the same request confirms it.
    r = call(h, "PUT", f"{P}/dre-settings", h.admin, json={
        "gateway_fee_line": "selling_expenses", "confirmations": {"gateway_fee_line": {"confirmed": True}}})
    assert r.json()["data"]["choices"]["gateway_fee_line"]["provisional"] is False
    r = call(h, "PUT", f"{P}/dre-settings", h.admin, json={"confirmations": {"gateway_fee_line": {"confirmed": False}}})
    assert r.json()["data"]["choices"]["gateway_fee_line"]["provisional"] is True


@pytest.mark.parametrize("body,code", [
    ({"gateway_fee_line": "unclassified"}, "invalid"),  # the enum accepts it, the service refuses it
    ({"tax_regime": "lucro_real"}, None),
    ({"gateway_fee_line": "marketing"}, None),
    ({"confirmations": {"nope": {"confirmed": True}}}, "escolha_desconhecida"),
    ({"das_split_irpj_csll": True}, "reparticao_das_obrigatoria"),
    ({"das_irpj_csll_share_bps": 10001}, None),
    ({"surprise": 1}, None),
])
def test_put_validation_is_422(h, body, code):
    r = call(h, "PUT", f"{P}/dre-settings", h.admin, json=body)
    assert r.status_code == 422, r.text
    if code and code != "invalid":
        assert r.json()["error"]["code"] == code
    if code == "invalid":
        assert r.json()["error"]["code"] == "linha_dre_invalida"


def test_split_needs_a_share_and_both_can_arrive_together(h):
    ok = call(h, "PUT", f"{P}/dre-settings", h.admin, json={"tax_regime": "simples", "das_split_irpj_csll": True, "das_irpj_csll_share_bps": 3350})
    assert ok.status_code == 200 and ok.json()["data"]["das_irpj_csll_share_bps"] == 3350
    off = call(h, "PUT", f"{P}/dre-settings", h.admin, json={"das_split_irpj_csll": False, "das_irpj_csll_share_bps": 0})
    assert off.status_code == 200 and off.json()["data"]["das_split_irpj_csll"] is False


def test_settings_are_per_org(h):
    call(h, "PUT", f"{P}/dre-settings", h.admin, json={"tax_regime": "mei"})
    b = call(h, "GET", f"{P}/dre-settings", h.staff("org-b"))
    assert b.json()["data"]["tax_regime"] == "unknown" and b.json()["data"]["persisted"] is False
    call(h, "PUT", f"{P}/dre-settings", h.staff("org-b-admin"), json={"tax_regime": "presumido"})
    assert call(h, "GET", f"{P}/dre-settings", h.staff()).json()["data"]["tax_regime"] == "mei"
    assert len(h.db.table("fin_dre_settings").select("*").execute().data) == 2


def test_the_host_can_prefill_the_regime_until_the_org_saves_its_own():
    db = make_db()
    router = make_finance_router(
        CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db, get_storage=lambda: FakeStorageBackend(),
        default_tax_regime=lambda ctx: "simples",
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    client = TestClient(app)
    staff = {"Authorization": "Bearer user"}
    got = client.get(f"{P}/dre-settings", headers=staff).json()["data"]
    assert got["tax_regime"] == "simples" and got["tax_regime_prefilled"] is True and got["persisted"] is False
    assert "regime_nao_informado" not in {w["code"] for w in client.get(f"{P}/reports/dre", headers={"Authorization": "Bearer admin"}).json()["data"]["warnings"]}
    client.put(f"{P}/dre-settings", headers={"Authorization": "Bearer admin"}, json={"tax_regime": "mei"})
    assert client.get(f"{P}/dre-settings", headers=staff).json()["data"]["tax_regime"] == "mei"


# ── Simples tax base ──


def seed_boundary(s):
    acc = mk_account(s)
    # Nov/2026 (cash basis): R$100 received with a R$5 fee that must NOT be netted; competence is irrelevant.
    nov = mk_entry(s, amount_cents=10000, due_date="2026-11-10", category_id=cat(s, "Vendas")["id"], source="external", source_ref="n1")
    pay(s, nov, acc, 10000, "2026-11-12", fee_cents=500, external_ref="p-nov")
    # Dec/2026 sale, received only in Jan/2027: not Dec cash, and not a 2027 invoice either.
    dec = mk_entry(s, amount_cents=30000, due_date="2026-12-10", category_id=cat(s, "Vendas")["id"], source="external", source_ref="d1")
    pay(s, dec, acc, 30000, "2027-01-10", external_ref="p-dec")
    # Dec/2026 sale received in Dec: cash.
    dec2 = mk_entry(s, amount_cents=5000, due_date="2026-12-15", category_id=cat(s, "Vendas")["id"], source="external", source_ref="d2")
    pay(s, dec2, acc, 5000, "2026-12-20", external_ref="p-dec2")
    # Jan/2027 (invoice basis): sale + the buyer's interest, nothing received yet; Feb refund of part of the sale.
    jan = mk_entry(s, amount_cents=20000, due_date="2027-01-20", category_id=cat(s, "Vendas")["id"], source="external", source_ref="j1")
    mk_entry(s, amount_cents=5000, due_date="2027-01-20", category_id=cat(s, "Juros de parcelamento")["id"], source="external", source_ref="j1:interest")
    pay(s, jan, acc, 20000, "2027-02-02", external_ref="p-jan")
    pay(s, jan, acc, 2000, "2027-02-10", kind="refund", external_ref="r-jan")
    pay(s, jan, acc, 700, "2027-02-11", kind="refund", external_ref="chargeback:j")
    # Not Simples gross revenue: financial income and a payable.
    mk_entry(s, amount_cents=999, due_date="2027-01-05", category_id=cat(s, "Rendimentos e juros recebidos")["id"])
    mk_entry(s, direction="payable", amount_cents=888, due_date="2027-01-05", category_id=cat(s, "Marketing")["id"])


def test_simples_base_switches_basis_at_2027_and_splits_a_period_crossing_it(s):
    seed_boundary(s)
    out = simples_base.simples_base(s, date(2026, 11, 1), date(2027, 2, 28))
    rows = {r["month"]: r for r in out["months"]}
    assert [r["basis"] for r in out["months"]] == ["cash", "cash", "invoice", "invoice"] and out["crosses_basis_boundary"] is True
    assert rows["2026-11"]["base_cents"] == 10000 and rows["2026-11"]["sales_cents"] == 10000  # the fee is not netted
    assert rows["2026-12"]["base_cents"] == 5000  # only what was RECEIVED in December
    assert (rows["2027-01"]["sales_cents"], rows["2027-01"]["interest_cents"], rows["2027-01"]["base_cents"]) == (20000, 5000, 25000)
    assert rows["2027-02"]["refunds_cents"] == 2000 and rows["2027-02"]["base_cents"] == -2000
    assert rows["2027-02"]["chargebacks_cents"] == 700  # reported, never netted
    assert out["totals"]["cash_basis"]["base_cents"] == 15000 and out["totals"]["invoice_basis"]["base_cents"] == 23000
    assert out["totals"]["base_cents"] == 38000
    codes = {w["code"] for w in out["warnings"]}
    assert {"chargeback_fora_da_base", "transicao_caixa_faturamento", "base_faturamento_aproximada", "regime_nao_informado"} <= codes
    transition = next(w for w in out["warnings"] if w["code"] == "transicao_caixa_faturamento")
    assert transition["details"]["cents"] == 30000  # the December sale received in January


def test_simples_base_pure_periods_and_boundary_edges(s):
    seed_boundary(s)
    cash = simples_base.simples_base(s, date(2026, 12, 1), date(2026, 12, 31))
    assert cash["crosses_basis_boundary"] is False and cash["months"][0]["basis"] == "cash"
    invoice = simples_base.simples_base(s, date(2027, 1, 1), date(2027, 1, 31))
    assert invoice["months"][0]["basis"] == "invoice" and invoice["totals"]["base_cents"] == 25000
    assert simples_base.basis_of("2026-12") == "cash" and simples_base.basis_of("2027-01") == "invoice"


def test_simples_base_interest_always_counts_even_when_the_dre_line_is_financial(s):
    seed_boundary(s)
    dre_settings.update_settings(s, {"installment_interest_line": "financial_revenue"}, user_id=USER_ID)
    out = simples_base.simples_base(s, date(2027, 1, 1), date(2027, 1, 31))
    assert out["months"][0]["interest_cents"] == 5000  # the tax answer does not follow the accounting choice


def test_simples_base_org_scope_validation_and_http(h, s_b):
    mk_entry(s_b, amount_cents=777, due_date="2027-01-05", category_id=cat(s_b, "Vendas")["id"])
    r = call(h, "GET", f"{P}/reports/simples-base?from=2027-01-01&to=2027-01-31", h.admin)
    assert r.status_code == 200 and r.json()["data"]["totals"]["base_cents"] == 0
    assert call(h, "GET", f"{P}/reports/simples-base?from=2027-03-01&to=2027-01-01", h.admin).status_code == 422
    assert call(h, "GET", f"{P}/reports/simples-base?from=2010-01-01&to=2027-01-01", h.admin).json()["error"]["code"] == "periodo_grande_demais"
    assert call(h, "GET", f"{P}/reports/simples-base").status_code == 401


def test_simples_base_presumido_is_flagged(s):
    dre_settings.update_settings(s, {"tax_regime": "presumido"}, user_id=USER_ID)
    out = simples_base.simples_base(s, date(2027, 1, 1), date(2027, 1, 31))
    assert "relatorio_somente_simples" in {w["code"] for w in out["warnings"]} and out["tax_regime"] == "presumido"


# ── accountant checklist ──


def test_checklist_lists_provisional_choices_questions_and_export_links(h):
    r = call(h, "GET", f"{P}/accountant-checklist", h.admin)
    assert r.status_code == 200
    data = r.json()["data"]
    assert [c["choice"] for c in data["provisional_choices"]] == list(dre_settings.CHOICES) and data["confirmed_choices"] == []
    assert data["tax_regime_informed"] is False
    first = data["provisional_choices"][0]
    assert first["question"] and first["why_open"] and first["sources"] and first["current_value"] in first["options"]
    assert {q["id"] for q in data["open_questions"]} >= {"Q4", "Q5", "Q6", "Q7", "Q8", "Q9"}
    assert all(q["sources"] for q in data["open_questions"])
    assert {e["name"]: e["path"] for e in data["exports"]} == {
        "dre_csv": f"{P}/exports/dre.csv", "entries_csv": f"{P}/exports/entries.csv", "ledger_ofx": f"{P}/exports/ledger.ofx"}
    assert "não assina" in data["disclaimer"]
    assert call(h, "GET", f"{P}/accountant-checklist").status_code == 401


def test_checklist_moves_a_confirmed_choice_out_of_the_provisional_list(h):
    call(h, "PUT", f"{P}/dre-settings", h.admin, json={"tax_regime": "simples", "confirmations": {"chargeback_line": {"confirmed": True}}})
    data = call(h, "GET", f"{P}/accountant-checklist", h.admin).json()["data"]
    assert "chargeback_line" not in [c["choice"] for c in data["provisional_choices"]]
    assert [c["choice"] for c in data["confirmed_choices"]] == ["chargeback_line"] and data["tax_regime_informed"] is True
    other = call(h, "GET", f"{P}/accountant-checklist", h.staff("org-b-admin")).json()["data"]
    assert other["confirmed_choices"] == []  # org isolation


# ── DRE CSV ──


def read_rows(body: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))


def test_dre_csv_has_the_statement_unclassified_block_and_warnings(s):
    mk_entry(s, amount_cents=10000, due_date="2026-03-02", category_id=cat(s, "Vendas")["id"])
    bad = categories.create_category(s, {"name": '=HYPERLINK("http://x")', "direction": "expense"})
    mk_entry(s, direction="payable", amount_cents=700, due_date="2026-03-02", category_id=bad["id"])
    rows = read_rows(exports.dre_csv(s, date(2026, 3, 1), date(2026, 3, 31)))
    assert rows[0][0].startswith("Demonstração")
    header = next(r for r in rows if r[:1] == ["tipo"])
    assert header == ["tipo", "linha", "nome", "2026-03", "total"]
    by_key = {(r[0], r[1]): r for r in rows if r and r[0] in ("linha", "subtotal")}
    assert by_key[("linha", "gross_revenue")][3:] == ["100.00", "100.00"]
    assert by_key[("subtotal", "net_result")][4] == "100.00"
    block = next(r for r in rows if r and r[0] == "sem_classificacao")
    assert block[4] == "-7.00"
    detail = [r for r in rows if r and r[0] == "detalhe" and r[1] == "unclassified"]
    assert detail and detail[0][2].startswith("'=")  # formula injection neutralised
    assert any(r and r[0] == "aviso" and r[1] == "categoria_sem_linha_dre" for r in rows)


def test_dre_csv_managerial_and_mei_title(s):
    dre_settings.update_settings(s, {"tax_regime": "mei"}, user_id=USER_ID)
    mk_entry(s, amount_cents=10000, due_date="2026-03-02", category_id=cat(s, "Vendas")["id"])
    mk_entry(s, direction="payable", amount_cents=4000, due_date="2026-03-02", category_id=cat(s, "Marketing")["id"])
    rows = read_rows(exports.dre_csv(s, date(2026, 3, 1), date(2026, 3, 31), view="managerial"))
    assert rows[0] == ["DRE gerencial (MEI não é obrigado a ter DRE)"]
    margin = next(r for r in rows if len(r) > 1 and r[1] == "contribution_margin")
    assert margin[4] == "60.00"


def test_dre_csv_route_is_admin_only_and_org_scoped(rh):
    c = rh.client
    assert c.get(f"{P}/exports/dre.csv").status_code == 401
    assert c.get(f"{P}/exports/dre.csv", headers=rh.staff()).status_code == 403
    mk_entry(rh.s_b, amount_cents=555, due_date="2026-03-02", category_id=cat(rh.s_b, "Vendas")["id"])
    r = c.get(f"{P}/exports/dre.csv?from=2026-03-01&to=2026-03-31", headers=rh.admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="dre.csv"' in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    rows = read_rows(r.content)
    assert next(r_ for r_ in rows if r_[:2] == ["linha", "gross_revenue"])[-1] == "0.00"
    assert c.get(f"{P}/exports/dre.csv?view=pie", headers=rh.admin).status_code == 422
    with pytest.raises(FinanceError):
        exports.dre_csv(rh.s, date(2026, 3, 1), date(2026, 1, 1))


def test_financial_statements_are_admin_only_strict(h):
    for path in (f"{P}/reports/dre", f"{P}/reports/simples-base", f"{P}/accountant-checklist"):
        assert call(h, "GET", path).status_code == 401, path
        assert call(h, "GET", path, h.staff("user")).status_code == 403, path
        assert call(h, "GET", path, h.admin).status_code == 200, path
    # cashflow + aging stay staff-readable
    for path in (f"{P}/reports/cashflow", f"{P}/reports/aging"):
        assert call(h, "GET", path, h.staff("user")).status_code == 200, path


class _RacingDb:
    """DB proxy: the loser's first dre_settings INSERT is preceded by the winner's committed write."""

    def __init__(self, db, winner):
        self._db, self._winner, self._fired = db, winner, False

    def table(self, name):
        tbl = self._db.table(name)
        if not name.endswith("dre_settings") or self._fired:
            return tbl
        outer = self

        class _T:
            def __getattr__(self, attr):
                return getattr(tbl, attr)

            def insert(self, row):
                outer._fired = True
                outer._winner()  # winner commits first
                raise RuntimeError("duplicate key value violates unique constraint (23505)")

        return _T()


def test_first_put_race_loser_reapplies_against_winner_row(db):
    winner = Scope(db, CFG, ORG_A)
    loser = Scope(_RacingDb(db, lambda: dre_settings.update_settings(
        winner, {"confirmations": {"chargeback_line": {"confirmed": True}}}, user_id="winner")), CFG, ORG_A)
    out = dre_settings.update_settings(
        loser, {"tax_regime": "simples", "confirmations": {"gateway_fee_line": {"confirmed": True}}}, user_id="loser")
    ch = out["choices"]
    assert ch["chargeback_line"]["confirmed_by"] == "winner" and ch["chargeback_line"]["provisional"] is False
    assert ch["gateway_fee_line"]["confirmed_by"] == "loser" and out["tax_regime"] == "simples"
