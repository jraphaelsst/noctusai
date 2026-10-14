"""The structured DRE (CONTRACT §10 / §10.5): line math per regime, routing of fees / refunds / chargebacks /
interest, the unclassified block, guidance, the managerial reconciliation, default-category seeding."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import categories, dre, dre_settings, entries, reports, settlements
from noctusai_lib.domain.finance.errors import FinanceError

from .conftest import USER_ID, mk_account, mk_entry

MAR_APR = (date(2026, 3, 1), date(2026, 4, 30))


def cat(s, name):
    return next(c for c in categories.list_categories(s) if c["name"] == name)


def pay(s, e, acc, amount, on, **kw):
    return settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": amount, "settled_on": on, **kw})


def regime(s, name, **extra):
    return dre_settings.update_settings(s, {"tax_regime": name, **extra}, user_id=USER_ID)


def statement(s, *, view="statement", rng=MAR_APR):
    return reports.dre(s, rng[0], rng[1], view=view)


def line(out, key):
    return next(i for i in out["statement"] if i["key"] == key)


def seed_month(s):
    """One March: sale 100000 (paid, fee 3000), interest 2000, a refund of 10000 in APRIL, cost 20000, marketing 5000,
    rent 8000, DAS 6000. Net before tax-regime effects = 100000 + 2000 - 10000 - 20000 - 5000 - 3000 - 8000 - 6000 = 50000."""
    acc = mk_account(s)
    sale = mk_entry(s, amount_cents=100000, due_date="2026-03-10", category_id=cat(s, "Vendas")["id"], source="external", source_ref="o1")
    mk_entry(s, amount_cents=2000, due_date="2026-03-10", category_id=cat(s, "Juros de parcelamento")["id"], source="external", source_ref="o1:interest")
    mk_entry(s, direction="payable", amount_cents=20000, due_date="2026-03-12", category_id=cat(s, "Mercadorias / insumos para revenda")["id"])
    mk_entry(s, direction="payable", amount_cents=5000, due_date="2026-03-12", category_id=cat(s, "Marketing")["id"])
    mk_entry(s, direction="payable", amount_cents=8000, due_date="2026-03-12", category_id=cat(s, "Aluguel e condomínio")["id"])
    mk_entry(s, direction="payable", amount_cents=6000, due_date="2026-03-20", category_id=cat(s, "Impostos sobre vendas")["id"])
    pay(s, sale, acc, 100000, "2026-03-10", fee_cents=3000, external_ref="pay1")
    pay(s, sale, acc, 10000, "2026-04-05", kind="refund", external_ref="ref1")
    return acc, sale


# ── default categories ──


def test_defaults_carry_the_d56_table(s):
    by = {c["name"]: c for c in categories.list_categories(s)}
    expect = {
        "Vendas": ("gross_revenue", "variable"), "Juros de parcelamento": ("gross_revenue", "variable"),
        "Outras receitas": ("other_operating", None), "Rendimentos e juros recebidos": ("financial_revenue", None),
        "Impostos sobre vendas": ("deductions", "variable"), "Mercadorias / insumos para revenda": ("cost_of_sales", "variable"),
        "Pessoal": ("administrative_expenses", "fixed"), "DAS-MEI": ("administrative_expenses", "fixed"),
        "Marketing": ("selling_expenses", "variable"), "Tarifa de chargeback": ("selling_expenses", "variable"),
        "Tarifas bancárias": ("financial_expenses", None), "Antecipação de recebíveis": ("financial_expenses", None),
        "IRPJ / CSLL": ("income_taxes", None), "Outras despesas": ("other_operating", None), "Entre contas": (None, None),
    }
    for name, (ln, beh) in expect.items():
        assert (by[name]["dre_line"], by[name]["behavior"]) == (ln, beh), name
    assert by["Impostos sobre vendas"]["is_das"] and by["DAS-MEI"]["is_das"] and not by["Vendas"]["is_das"]


def test_seeding_is_idempotent(s):
    first = categories.list_categories(s)
    assert categories.seed_default_categories(s) == []
    assert len(categories.list_categories(s)) == len(first)


def test_a_legacy_org_gets_lines_and_the_new_defaults_without_clobbering_edits(s):
    """An org seeded by the pre-DRE generator: default rows without lines + one the owner edited."""
    root = categories._insert_category(s, name="Despesas operacionais", direction="expense", parent_id=None, is_default=True)
    inc = categories._insert_category(s, name="Receitas operacionais", direction="income", parent_id=None, is_default=True)
    vendas = categories._insert_category(s, name="Vendas", direction="income", parent_id=inc["id"], is_default=True)
    mkt = categories._insert_category(s, name="Marketing", direction="expense", parent_id=root["id"], is_default=True)
    legacy = categories._insert_category(s, name="Fornecedores", direction="expense", parent_id=root["id"], is_default=True)
    custom = categories._insert_category(s, name="Brindes", direction="expense", parent_id=root["id"], is_default=False)
    categories.update_category(s, mkt["id"], {"dre_line": "administrative_expenses", "behavior": "fixed"})  # the owner's edit

    created = categories.seed_default_categories(s)  # what the first touch does for an org with no DRE lines
    after = {c["name"]: c for c in s.rows("categories")}
    assert after["Vendas"]["dre_line"] == "gross_revenue" and after["Vendas"]["id"] == vendas["id"]  # filled where NULL
    assert after["Marketing"]["dre_line"] == "administrative_expenses" and after["Marketing"]["behavior"] == "fixed"  # kept
    assert after["Fornecedores"]["dre_line"] is None and after["Fornecedores"]["id"] == legacy["id"]  # ambiguous: owner decides
    assert after["Brindes"]["dre_line"] is None  # never a default row: untouched
    assert "Mercadorias / insumos para revenda" in after and "Juros de parcelamento" in after  # the new defaults are added
    assert {c["name"] for c in created} >= {"Juros de parcelamento", "Taxas de cartão/gateway"}
    assert custom["id"] == after["Brindes"]["id"]
    assert categories.seed_default_categories(s) == []  # converged


def test_a_deleted_default_is_not_resurrected_once_the_tree_is_mapped(s):
    categories.list_categories(s)
    pessoal = cat(s, "Pessoal")
    categories.delete_category(s, pessoal["id"])
    assert "Pessoal" not in {c["name"] for c in categories.list_categories(s)}


# ── line math per regime ──


def test_simples_whole_das_goes_to_deductions(s):
    seed_month(s)
    regime(s, "simples")
    out = statement(s)
    assert line(out, "gross_revenue")["cents"] == 102000  # sale + interest, fee NOT netted
    assert line(out, "deductions")["cents"] == 16000  # refund 10000 + DAS 6000
    assert line(out, "net_revenue")["cents"] == 86000
    assert line(out, "cost_of_sales")["cents"] == 20000 and line(out, "gross_result")["cents"] == 66000
    assert line(out, "selling_expenses")["cents"] == 8000  # marketing 5000 + gateway fee 3000
    assert line(out, "administrative_expenses")["cents"] == 8000
    assert line(out, "result_before_financial")["cents"] == 50000 == out["net_result_cents"]
    assert line(out, "income_taxes")["cents"] == 0


def test_monthly_columns_follow_competence_for_entries_and_the_settlement_month_for_refunds(s):
    seed_month(s)
    regime(s, "simples")
    out = statement(s)
    assert out["months"] == ["2026-03", "2026-04"]
    assert line(out, "deductions")["by_month"] == {"2026-03": 6000, "2026-04": 10000}  # the refund lands in April
    assert line(out, "gross_revenue")["by_month"] == {"2026-03": 102000, "2026-04": 0}
    assert line(out, "net_result")["by_month"] == {"2026-03": 102000 - 6000 - 20000 - 8000 - 5000 - 3000, "2026-04": -10000}


def test_simples_split_moves_the_irpj_csll_share_to_income_taxes(s):
    seed_month(s)
    regime(s, "simples", das_split_irpj_csll=True, das_irpj_csll_share_bps=3000)
    out = statement(s)
    assert line(out, "deductions")["cents"] == 10000 + 4200
    assert line(out, "income_taxes")["cents"] == 1800
    assert [d["name"] for d in line(out, "income_taxes")["detail"]] == ["Impostos sobre vendas (parcela IRPJ/CSLL do DAS)"]
    assert out["net_result_cents"] == 50000  # the split moves money between lines, never the result


def test_mei_das_is_an_administrative_expense_and_the_statement_is_titled_managerial(s):
    seed_month(s)
    regime(s, "mei")
    out = statement(s)
    assert out["title"] == "DRE gerencial (MEI não é obrigado a ter DRE)"
    assert line(out, "deductions")["cents"] == 10000  # only the refund
    assert line(out, "administrative_expenses")["cents"] == 8000 + 6000
    assert out["net_result_cents"] == 50000


def test_presumido_revenue_taxes_are_deductions_and_irpj_csll_is_income_taxes(s):
    seed_month(s)
    regime(s, "presumido")
    mk_entry(s, direction="payable", amount_cents=1500, due_date="2026-03-25", category_id=cat(s, "IRPJ / CSLL")["id"])
    out = statement(s)
    assert line(out, "deductions")["cents"] == 16000
    assert line(out, "income_taxes")["cents"] == 1500
    assert out["net_result_cents"] == 48500
    assert out["title"] == "Demonstração do Resultado do Exercício (DRE)"


def test_subtotals_are_computed_not_stored(s):
    seed_month(s)
    out = statement(s)
    keys = [i["key"] for i in out["statement"]]
    assert keys == ["gross_revenue", "deductions", "net_revenue", "cost_of_sales", "gross_result", "selling_expenses",
                    "administrative_expenses", "other_operating", "result_before_financial", "financial_revenue",
                    "financial_expenses", "result_before_income_taxes", "income_taxes", "net_result"]
    assert all("net_revenue" not in str(r) for r in s.rows("entries"))
    assert line(out, "other_operating")["empty"] and not line(out, "gross_revenue")["empty"]  # zero lines stay, flagged


def test_financial_and_other_lines_sign(s):
    mk_entry(s, amount_cents=900, due_date="2026-03-02", category_id=cat(s, "Rendimentos e juros recebidos")["id"])
    mk_entry(s, direction="payable", amount_cents=400, due_date="2026-03-02", category_id=cat(s, "Tarifas bancárias")["id"])
    mk_entry(s, amount_cents=300, due_date="2026-03-02", category_id=cat(s, "Outras receitas")["id"])
    mk_entry(s, direction="payable", amount_cents=100, due_date="2026-03-02", category_id=cat(s, "Outras despesas")["id"])
    out = statement(s)
    assert line(out, "other_operating")["cents"] == 200  # + income - expense
    assert line(out, "result_before_financial")["cents"] == 200
    assert line(out, "result_before_income_taxes")["cents"] == 200 + 900 - 400
    assert out["net_result_cents"] == 700


# ── routing ──


def test_installment_interest_follows_the_store_setting_but_stays_a_detail_row(s):
    seed_month(s)
    out = statement(s)
    assert "Juros de parcelamento" in [d["name"] for d in line(out, "gross_revenue")["detail"]]
    dre_settings.update_settings(s, {"installment_interest_line": "financial_revenue"}, user_id=USER_ID)
    moved = statement(s)
    assert line(moved, "gross_revenue")["cents"] == 100000 and line(moved, "financial_revenue")["cents"] == 2000
    assert moved["net_result_cents"] == out["net_result_cents"]


def test_gateway_fee_routing_is_a_setting(s):
    seed_month(s)
    dre_settings.update_settings(s, {"gateway_fee_line": "financial_expenses"}, user_id=USER_ID)
    out = statement(s)
    assert line(out, "financial_expenses")["cents"] == 3000 and line(out, "selling_expenses")["cents"] == 5000
    assert [d["name"] for d in line(out, "financial_expenses")["detail"]] == ["Taxas do gateway/cartão (MDR)"]


def test_a_reversed_settlement_leaves_the_dre(s):
    acc, sale = seed_month(s)
    st = s.rows("settlements", eq={"external_ref": "ref1"})[0]
    settlements.reverse_settlement(s, st["id"], "estorno indevido")
    out = statement(s)
    assert line(out, "deductions")["cents"] == 6000  # the refund is gone


def test_chargebacks_route_by_setting_and_fees_on_gateway_sync_rows_count_once(s):
    acc, sale = seed_month(s)
    pay(s, sale, acc, 5000, "2026-04-20", kind="refund", external_ref="chargeback:ch1")
    out = statement(s)
    assert line(out, "deductions")["cents"] == 6000 + 10000 + 5000
    assert "Chargebacks (valor devolvido ao comprador)" in [d["name"] for d in line(out, "deductions")["detail"]]
    assert any(a["code"] == "chargeback_base_simples" for a in out["accountant_alerts"])
    dre_settings.update_settings(s, {"chargeback_line": "other_operating"}, user_id=USER_ID)
    moved = statement(s)
    assert line(moved, "deductions")["cents"] == 16000 and line(moved, "other_operating")["cents"] == -5000
    assert moved["net_result_cents"] == out["net_result_cents"]
    # A fee booked by the gateway sync (adjustment OUT, "Tarifa do gateway:") is a gateway fee too.
    s.tbl("ledger").insert({
        "org_id": s.org_id, "account_id": acc["id"], "occurred_on": "2026-03-15", "direction": "out", "amount_cents": 700,
        "origin": "adjustment", "description": "Tarifa do gateway: pay9",
    }).execute()
    again = statement(s)
    assert line(again, "selling_expenses")["cents"] == 5000 + 3000 + 700
    s.tbl("ledger").insert({
        "org_id": s.org_id, "account_id": acc["id"], "occurred_on": "2026-03-15", "direction": "out", "amount_cents": 123,
        "origin": "adjustment", "description": "Ajuste manual",
    }).execute()
    assert line(statement(s), "selling_expenses")["cents"] == 8700  # only the gateway-fee description counts


def test_transfers_never_enter_the_dre(s):
    # The API refuses a transfer-direction category on an entry; the DRE still excludes one reaching it by other means.
    e = mk_entry(s, amount_cents=5000, due_date="2026-03-02")
    s.tbl("entries").update({"category_id": cat(s, "Entre contas")["id"]}).eq("id", e["id"]).execute()
    out = statement(s)
    assert out["net_result_cents"] == 0 and out["unclassified"]["detail"] == []


def test_cancelled_entries_and_foreign_orgs_stay_out(s, s_b):
    e = mk_entry(s, direction="payable", amount_cents=99999, due_date="2026-03-02", category_id=cat(s, "Pessoal")["id"])
    entries.cancel_entry(s, e["id"])
    mk_entry(s_b, amount_cents=777, due_date="2026-03-02")
    out = statement(s)
    assert out["net_result_cents"] == 0 and out["unclassified"]["net_cents"] == 0


# ── unclassified + guidance ──


def test_unclassified_is_its_own_block_with_a_warning_and_outside_net_result(s):
    custom = categories.create_category(s, {"name": "Brindes", "direction": "expense"})
    mk_entry(s, direction="payable", amount_cents=500, due_date="2026-03-02", category_id=custom["id"])
    mk_entry(s, direction="payable", amount_cents=70, due_date="2026-03-02")  # no category at all
    mk_entry(s, amount_cents=900, due_date="2026-03-02")  # revenue without a category
    out = statement(s)
    assert out["net_result_cents"] == 0
    assert out["unclassified"]["net_cents"] == -500 - 70 + 900 and out["unclassified"]["included_in_net_result"] is False
    names = {d["name"] for d in out["unclassified"]["detail"]}
    assert {"Brindes", "Sem categoria"} <= names
    codes = {w["code"] for w in out["warnings"]}
    assert {"categoria_sem_linha_dre", "receita_sem_categoria"} <= codes
    brindes = next(w for w in out["warnings"] if w["code"] == "categoria_sem_linha_dre")
    assert "Brindes" in brindes["details"]["categories"]
    categories.update_category(s, custom["id"], {"dre_line": "selling_expenses"})  # classify -> it joins the result
    assert statement(s)["net_result_cents"] == -500


def test_a_child_inherits_its_parents_line(s):
    parent = cat(s, "Marketing")
    child = categories.create_category(s, {"name": "Anúncios", "direction": "expense", "parent_id": parent["id"]})
    mk_entry(s, direction="payable", amount_cents=300, due_date="2026-03-02", category_id=child["id"])
    out = statement(s)
    assert line(out, "selling_expenses")["cents"] == 300 and out["unclassified"]["detail"] == []


def test_warnings_regime_provisional_and_cmv(s):
    seed_month(s)
    out = statement(s)
    codes = {w["code"]: w for w in out["warnings"]}
    assert "regime_nao_informado" in codes and codes["regime_nao_informado"]["severity"] == "warning"
    assert set(codes["escolha_provisoria"]["details"]["choices"]) == set(dre_settings.CHOICES)
    assert "cmv_por_compras" in codes
    regime(s, "simples", confirmations={name: {"confirmed": True} for name in dre_settings.CHOICES})
    later = {w["code"] for w in statement(s)["warnings"]}
    assert "regime_nao_informado" not in later and "escolha_provisoria" not in later
    for w in out["warnings"]:
        assert {"code", "severity", "message", "action"} <= set(w)


def test_micro_entity_limit_uses_the_trailing_twelve_months_not_just_the_window(s):
    mk_entry(s, amount_cents=480_000_001, due_date="2025-12-10", category_id=cat(s, "Vendas")["id"])
    out = reports.dre(s, date(2026, 3, 1), date(2026, 3, 31))  # the window itself has no revenue
    assert out["trailing_12m_gross_revenue_cents"] == 480_000_001 and out["standard"] == "nbc_tg_1001"
    assert "limite_microentidade_excedido" in {w["code"] for w in out["warnings"]}
    assert "padrao_nbc_tg_1001" in {a["code"] for a in out["accountant_alerts"]}
    assert line(out, "gross_revenue")["cents"] == 0  # the extra window is for the switch only, never displayed
    below = reports.dre(s, date(2027, 1, 1), date(2027, 1, 31))  # 13 months later: out of the trailing window
    assert "limite_microentidade_excedido" not in {w["code"] for w in below["warnings"]}


def test_help_is_shipped_per_line_with_a_source(s):
    out = statement(s)
    for key in ("gross_revenue", "deductions", "cost_of_sales", "selling_expenses", "administrative_expenses",
                "other_operating", "financial_revenue", "financial_expenses", "income_taxes", "unclassified",
                "net_revenue", "gross_result", "net_result"):
        h = out["help"][key]
        assert h["label"] and h["what"] and h["source"], key
    assert "[norma]" in out["help"]["gross_revenue"]["source"]


def test_range_and_view_validation(s):
    with pytest.raises(FinanceError):
        reports.dre(s, date(2026, 3, 1), date(2026, 2, 1))
    with pytest.raises(FinanceError) as err:
        reports.dre(s, date(2020, 1, 1), date(2026, 1, 1))
    assert err.value.code == "periodo_grande_demais"
    with pytest.raises(FinanceError) as err:
        reports.dre(s, *MAR_APR, view="pie")
    assert err.value.code == "visao_invalida"


def test_dre_is_accrual_not_cash(s):
    e = mk_entry(s, amount_cents=1000, due_date="2026-02-05", category_id=cat(s, "Vendas")["id"])
    assert line(reports.dre(s, date(2026, 2, 1), date(2026, 2, 1)), "gross_revenue")["cents"] == 1000
    pay(s, e, mk_account(s), 1000, "2026-05-01")
    assert line(reports.dre(s, date(2026, 2, 1), date(2026, 2, 1)), "gross_revenue")["cents"] == 1000


# ── managerial view ──


@pytest.mark.parametrize("name,extra", [("simples", {}), ("mei", {}), ("simples", {"das_split_irpj_csll": True, "das_irpj_csll_share_bps": 2500})])
def test_managerial_view_reconciles_to_net_result(s, name, extra):
    acc, sale = seed_month(s)
    pay(s, sale, acc, 4000, "2026-04-02", kind="refund", external_ref="chargeback:c")
    mk_entry(s, amount_cents=250, due_date="2026-03-03", category_id=cat(s, "Rendimentos e juros recebidos")["id"])
    mk_entry(s, direction="payable", amount_cents=90, due_date="2026-03-03", category_id=cat(s, "Tarifas bancárias")["id"])
    regime(s, name, **extra)
    stmt, man = statement(s), statement(s, view="managerial")
    m = man["managerial"]
    assert "statement" not in man and man["view"] == "managerial"
    assert m["net_result"]["cents"] == stmt["net_result_cents"] == man["net_result_cents"]
    assert m["net_result"]["by_month"] == line(stmt, "net_result")["by_month"]
    assert m["contribution_margin"]["cents"] == m["revenue"]["cents"] - m["variable_costs"]["cents"]
    assert m["net_result"]["cents"] == m["contribution_margin"]["cents"] - m["fixed_costs"]["cents"] + m["other_income"]["cents"]
    assert m["revenue"]["cents"] == line(stmt, "gross_revenue")["cents"]
    assert m["contribution_margin"]["percent_of_revenue_bps"] == m["contribution_margin"]["cents"] * 10_000 // m["revenue"]["cents"]


def test_managerial_variable_vs_fixed_follows_category_behavior(s):
    mk_entry(s, amount_cents=10000, due_date="2026-03-02", category_id=cat(s, "Vendas")["id"])
    mk_entry(s, direction="payable", amount_cents=1000, due_date="2026-03-02", category_id=cat(s, "Marketing")["id"])  # variable
    mk_entry(s, direction="payable", amount_cents=2000, due_date="2026-03-02", category_id=cat(s, "Pessoal")["id"])  # fixed
    m = statement(s, view="managerial")["managerial"]
    assert [d["name"] for d in m["variable_costs"]["detail"]] == ["Marketing"] and m["variable_costs"]["cents"] == 1000
    assert [d["name"] for d in m["fixed_costs"]["detail"]] == ["Pessoal"] and m["fixed_costs"]["cents"] == 2000
    categories.update_category(s, cat(s, "Marketing")["id"], {"behavior": "fixed"})  # the owner says marketing is fixed
    m = statement(s, view="managerial")["managerial"]
    assert m["variable_costs"]["cents"] == 0 and m["fixed_costs"]["cents"] == 3000


# ── the fee seam ──


def test_classify_fee_is_the_single_seam_and_defaults_to_gateway():
    assert dre.classify_fee({"fee_cents": 1}) == "gateway"
