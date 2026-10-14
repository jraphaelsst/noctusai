"""igig finance -> finance organ importer: mapping, rounding, reconciliation refusal, idempotent re-run, DRE lines.

Fixture rows only -- no live database. The organ side runs on the suite's own mock (schema from `finance_migration`)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from noctusai_lib.domain.finance.importers import igig as imp
from noctusai_lib.domain.finance.types import DreLine
from noctusai_lib.testing.mocks import MockSupabaseClient

from .conftest import ORG_A, ORG_B

CLI = "c1111111-0000-4000-8000-000000000001"


def fatura(i, comp, total, status="aberta", **kw):
    return {"id": f"f{i:07d}-0000-4000-8000-000000000000", "org_id": ORG_A, "cliente_id": CLI, "competencia": comp,
            "valor_total": total, "vencimento": kw.pop("vencimento", None), "status": status, "pago_em": kw.pop("pago_em", None), **kw}


def item(fid, tipo, qtd, unit, n=1):
    return {"id": f"i{n:07d}", "org_id": ORG_A, "fatura_id": fid, "tipo": tipo, "quantidade": qtd, "valor_unit": unit}


CLIENTES = [{"id": CLI, "org_id": ORG_A, "nome": "Cliente Alfa"}]


def rows():
    f1 = fatura(1, "2026-08", "1500.00", "paga", vencimento="2026-08-10", pago_em="2026-08-12T15:00:00+00:00")
    f2 = fatura(2, "2026-08", "300.50", "enviada", vencimento="2026-09-05")
    f3 = fatura(3, "2026-09", "800.00", "cancelada")
    f4 = fatura(4, "2026-09", "0.00", "aberta")
    items = [
        item(f1["id"], "mensalidade", 1, "1600.00", 1), item(f1["id"], "desconto", 1, "100.00", 2),
        item(f2["id"], "excedente", 3, "100.1666666", 3),  # 300.4999998 -> 30050 cents
        item(f3["id"], "avulso", 1, "800.00", 4),
    ]
    return [f1, f2, f3, f4], items


def test_mapping_competence_due_status_category_dre():
    fs, its = rows()
    plan = imp.plan_import(ORG_A, fs, its, CLIENTES)
    assert not plan.issues
    entries = {e.source_ref: e for e in plan.entries}
    paid = entries[f"igig:fatura:{fs[0]['id']}"]
    assert (paid.amount_cents, paid.category_name, paid.dre_line) == (150000, "Mensalidades", DreLine.GROSS_REVENUE.value)
    assert paid.paid and paid.settle_on.isoformat() == "2026-08-12" and paid.competence_month.isoformat() == "2026-08-01"
    assert paid.counterparty_name == "Cliente Alfa" and paid.description == "Fatura 2026-08 - Cliente Alfa"
    sent = entries[f"igig:fatura:{fs[1]['id']}"]
    assert (sent.amount_cents, sent.category_name, sent.paid, sent.due_date.isoformat()) == (30050, "Serviços", False, "2026-09-05")
    cancelled = entries[f"igig:fatura:{fs[2]['id']}"]
    assert cancelled.cancelled and cancelled.due_date.isoformat() == "2026-09-30"  # no vencimento -> month end
    assert [s["reason"] for s in plan.skipped] == ["valor_zero"]


def test_category_to_dre_line_comes_from_the_seed_default_tree():
    assert imp.dre_line_for("Mensalidades") is DreLine.GROSS_REVENUE
    assert imp.dre_line_for("Serviços") is DreLine.GROSS_REVENUE
    assert imp.category_for(["excedente", "mensalidade"]) == "Mensalidades"
    assert imp.category_for(["avulso", "desconto"]) == "Serviços"
    assert imp.category_for([]) == "Serviços"
    assert set(imp.ITEM_TYPE_CATEGORY.values()) <= {"Mensalidades", "Serviços"}


@pytest.mark.parametrize("total, cents", [("0.005", 0), ("0.015", 2), ("10.005", 1000), ("10.015", 1002)])
def test_rounding_edges_half_even(total, cents):
    plan = imp.plan_import(ORG_A, [fatura(1, "2026-08", total)], [], CLIENTES)
    if cents == 0:
        assert plan.skipped and not plan.entries  # rounds to zero -> nothing to book
    else:
        assert plan.entries[0].amount_cents == cents


def test_subcent_total_does_not_reconcile():
    fs = [fatura(1, "2026-08", "10.015")]
    plan = imp.plan_import(ORG_A, fs, [], CLIENTES)
    rec = imp.reconcile(plan, fs)
    assert not rec.ok and Decimal(rec.mismatches[0]["diff_cents"]) == Decimal("-0.5")
    assert rec.mismatches[0]["faturas_not_booked"] == []


def test_negative_total_estorno_is_an_issue_and_refuses():
    fs = [fatura(1, "2026-08", "-50.00")]
    plan = imp.plan_import(ORG_A, fs, [], CLIENTES)
    assert plan.issues[0]["code"] == "valor_negativo"
    rec = imp.reconcile(plan, fs)
    assert not rec.ok and rec.mismatches[0]["faturas_not_booked"] == [fs[0]["id"]]


def test_lines_disagreeing_with_total_refuse():
    f = fatura(1, "2026-08", "100.00")
    plan = imp.plan_import(ORG_A, [f], [item(f["id"], "mensalidade", 1, "90.00")], CLIENTES)
    assert plan.issues[0]["code"] == "linhas_divergentes"


def test_bad_competence_status_and_foreign_org_are_issues():
    fs = [fatura(1, "2026/08", "1.00"), fatura(2, "2026-08", "1.00", "weird"), {**fatura(3, "2026-08", "1.00"), "org_id": ORG_B}]
    codes = {i["code"] for i in imp.plan_import(ORG_A, fs, [], CLIENTES).issues}
    assert codes == {"competencia_invalida", "status_desconhecido", "org_divergente"}


def test_reconciliation_matches_to_the_cent_per_month():
    fs, its = rows()
    plan = imp.plan_import(ORG_A, fs, its, CLIENTES)
    rec = imp.reconcile(plan, fs)
    assert rec.ok
    by_month = {r["competencia"]: r for r in rec.rows}
    assert by_month["2026-08"]["after_cents"] == 180050 and by_month["2026-08"]["before_numeric"] == "1800.50"
    assert by_month["2026-09"]["after_cents"] == 80000 and by_month["2026-09"]["direction"] == "receivable"


def test_apply_refuses_a_plan_with_issues_and_writes_nothing(s):
    plan = imp.plan_import(ORG_A, [fatura(1, "2026-08", "-1.00")], [], CLIENTES)
    with pytest.raises(ValueError):
        imp.apply_plan(s, plan)
    assert s.rows("entries") == []


def test_apply_writes_entries_settlement_cancel_and_totals_match(s):
    fs, its = rows()
    plan = imp.plan_import(ORG_A, fs, its, CLIENTES)
    out = imp.apply_plan(s, plan)
    assert out == {"created": 3, "existing": 0, "settled": 1, "cancelled": 1}
    entries = {r["source_ref"]: r for r in s.rows("entries")}
    paid = entries[f"igig:fatura:{fs[0]['id']}"]
    assert paid["status"] == "paid" and paid["settled_cents"] == 150000 and paid["source"] == "import"
    assert entries[f"igig:fatura:{fs[1]['id']}"]["status"] == "open"
    assert entries[f"igig:fatura:{fs[2]['id']}"]["status"] == "cancelled"
    cats = {r["id"]: r for r in s.rows("categories")}
    assert cats[paid["category_id"]]["name"] == "Mensalidades" and cats[paid["category_id"]]["dre_line"] == "gross_revenue"
    assert [r["settled_on"] for r in s.rows("settlements")] == ["2026-08-12"]
    assert imp.written_totals(s) == {"2026-08": 180050, "2026-09": 80000}


def test_rerun_is_idempotent(s):
    fs, its = rows()
    plan = imp.plan_import(ORG_A, fs, its, CLIENTES)
    imp.apply_plan(s, plan)
    snapshot = (len(s.rows("entries")), len(s.rows("settlements")), len(s.rows("ledger")), len(s.rows("accounts")))
    again = imp.apply_plan(s, plan)
    assert again == {"created": 0, "existing": 3, "settled": 0, "cancelled": 0}
    assert (len(s.rows("entries")), len(s.rows("settlements")), len(s.rows("ledger")), len(s.rows("accounts"))) == snapshot


def test_read_igig_pages_the_source_tables():
    fs, its = rows()
    db = MockSupabaseClient(validate_schema=False, schema="igig")
    db.set_table_data("fatura", fs)
    db.set_table_data("fatura_item", its)
    db.set_table_data("cliente", CLIENTES)
    got_f, got_i, got_c = imp.read_igig(db, ORG_A)
    assert (len(got_f), len(got_i), len(got_c)) == (4, 4, 1)
