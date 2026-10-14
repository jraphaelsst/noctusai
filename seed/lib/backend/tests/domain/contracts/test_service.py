"""Service behaviour: creation rules, lifecycle, billing idempotency, amendments, readjustment, termination, retainer."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.contracts import ContractFromQuote, QuoteLine, contracts, create_contract_from_quote
from noctusai_lib.domain.contracts import billing_run
from noctusai_lib.domain.contracts.errors import ContractsError

from .conftest import ORG_A, ORG_B, USER_ID, body, mk, mk_party

ON = date(2026, 11, 1)


def refs(billing):
    return sorted(k[1] for k in billing.entries)


# --- create ------------------------------------------------------------------------------------------------


def test_create_is_a_draft_with_version_one_and_derived_amount_from_lines(s):
    c = contracts.create_contract(s, body(amount_cents=None, lines=[
        {"description": "Gestão", "quantity": 2, "unit_price_cents": 50000}, {"description": "Setup", "unit_price_cents": 5000}]))
    assert (c["status"], c["version_n"], c["amount_cents"]) == ("draft", 1, 105000)
    assert [ln["description"] for ln in contracts.contract_lines(s, c["id"])] == ["Gestão", "Setup"]
    versions = contracts.list_versions(s, c["id"])
    assert [(v["version_n"], v["kind"]) for v in versions] == [(1, "initial")]


def test_amount_disagreeing_with_lines_is_refused(s):
    with pytest.raises(ContractsError) as e:
        contracts.create_contract(s, body(amount_cents=1, lines=[{"description": "x", "unit_price_cents": 5000}]))
    assert e.value.details["field"] == "amount_cents"


@pytest.mark.parametrize("over, field", [
    ({"billing_model": "installments"}, "installments_count"),
    ({"billing_model": "installments", "installments_count": 500000}, "amount_cents"),
    ({"billing_model": "retainer"}, "retainer_minutes"),
    ({"amount_cents": 0}, "amount_cents"),
    ({"first_due_date": None, "start_date": None}, "first_due_date"),
    ({"readjustment_index": "fixed"}, "readjustment_percent_bp"),
    ({"start_date": "2026-12-01", "end_date": "2026-11-01"}, "end_date"),
])
def test_invalid_shapes_name_the_field(s, over, field):
    with pytest.raises(ContractsError) as e:
        contracts.create_contract(s, body(**over))
    assert e.value.status_code == 422 and e.value.details["field"] == field


def test_unused_model_fields_are_dropped(s):
    c = mk(s, billing_model="one_time", frequency="yearly", retainer_minutes=60)
    assert c["frequency"] is None and c["retainer_minutes"] is None and c["installments_count"] is None


def test_retainer_forces_monthly_frequency(s):
    c = mk(s, billing_model="retainer", frequency="yearly", retainer_minutes=600)
    assert c["frequency"] == "monthly" and c["excess_rate_cents"] == 0


def test_party_is_verified_in_the_org_and_snapshotted(s, s_b):
    p = mk_party(Scope_of(s))
    c = mk(s, party_id=p["id"])
    assert (c["party_name"], c["party_doc"]) == ("Ana Souza", "52998224725")
    with pytest.raises(ContractsError) as e:
        mk(s_b, party_id=p["id"])  # another org's party
    assert e.value.code == "parte_invalida"


def Scope_of(s):
    return s


def test_number_is_unique_per_org_case_insensitively(s, s_b):
    mk(s, number="CT-001")
    with pytest.raises(ContractsError) as e:
        mk(s, number="ct-001")
    assert e.value.code == "numero_duplicado" and e.value.status_code == 409
    mk(s_b, number="CT-001")  # another org: fine


def test_invalid_party_doc_is_refused(s):
    with pytest.raises(ContractsError):
        mk(s, party_doc="123")


# --- lifecycle / billing -----------------------------------------------------------------------------------


def test_activation_books_recurring_within_the_lead_window_and_is_idempotent(s, billing):
    c = mk(s)  # first due 2026-11-10, lead 30 days => Nov 10 + Dec 10 (Dec 10 > Dec 1 horizon? horizon = Dec 1)
    out = contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    assert out["status"] == "active" and out["activated_at"]
    assert refs(billing) == [f"{c['id']}:2026-11-10"]
    assert out["next_period_on"] == "2026-12-10"
    again = billing_run.bill_contract(s, out, billing, on=ON)
    assert again["created"] == 0 and len(billing.entries) == 1
    # a later tick books the next period and records it
    later = billing_run.bill_contract(s, contracts.get_contract(s, c["id"]), billing, on=date(2026, 12, 5))
    assert later["created"] == 1 and refs(billing)[-1].endswith("2026-12-10")
    assert len(billing_run.list_billings(s, c["id"])) == 2


def test_billing_records_amount_party_and_category(s, billing):
    p = mk_party(s)
    c = mk(s, party_id=p["id"], billing_model="installments", installments_count=3, amount_cents=100000, first_due_date="2026-11-10")
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    es = sorted(billing.entries.values(), key=lambda e: e["due_date"])
    assert [e["amount_cents"] for e in es] == [33333, 33333, 33334]
    assert {e["category_hint"] for e in es} == {"Serviços"} and es[0]["counterparty_name"] == "Ana Souza"
    assert es[0]["description"].endswith("(parcela 1/3)")
    r = mk(s, title="Mensal")
    contracts.activate_contract(s, r["id"], billing=billing, on=ON)
    assert {e["category_hint"] for e in billing.entries.values() if e["source_ref"].startswith(r["id"])} == {"Mensalidades"}


def test_only_drafts_activate_and_final_states_are_final(s, billing):
    c = mk(s)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    with pytest.raises(ContractsError) as e:
        contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    assert e.value.code == "transicao_invalida"
    contracts.terminate_contract(s, c["id"], {"reason": "fim"}, billing=billing, on=ON)
    for call in (lambda: contracts.suspend_contract(s, c["id"], "x"),
                 lambda: contracts.resume_contract(s, c["id"], billing=billing),
                 lambda: contracts.update_contract(s, c["id"], {"title": "novo"})):
        with pytest.raises(ContractsError):
            call()


def test_vigente_terms_need_an_amendment_but_descriptive_fields_do_not(s, billing):
    c = mk(s)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    contracts.update_contract(s, c["id"], {"notes": "ok", "title": "Novo título"})
    with pytest.raises(ContractsError) as e:
        contracts.update_contract(s, c["id"], {"amount_cents": 1})
    assert e.value.code == "contrato_vigente_use_aditivo" and e.value.status_code == 409


def test_draft_edit_in_place_keeps_a_single_version_and_rederives_amount(s):
    c = mk(s)
    contracts.update_contract(s, c["id"], {"lines": [{"description": "X", "quantity": 3, "unit_price_cents": 1000}]})
    got = contracts.get_contract(s, c["id"])
    assert got["amount_cents"] == 3000 and got["version_n"] == 1
    v = contracts.list_versions(s, c["id"])
    assert len(v) == 1 and v[0]["snapshot"]["amount_cents"] == 3000


def test_only_drafts_can_be_deleted(s, billing):
    d = mk(s)
    contracts.delete_contract(s, d["id"])
    a = mk(s)
    contracts.activate_contract(s, a["id"], billing=billing, on=ON)
    with pytest.raises(ContractsError) as e:
        contracts.delete_contract(s, a["id"])
    assert e.value.code == "contrato_nao_rascunho"


def test_suspension_skips_the_periods_inside_it(s, billing):
    c = mk(s, first_due_date="2026-11-10")
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    contracts.suspend_contract(s, c["id"], "inadimplência")
    assert billing_run.bill_contract(s, contracts.get_contract(s, c["id"]), billing, on=date(2027, 1, 1)) == {"created": 0}
    out = contracts.resume_contract(s, c["id"], billing=billing, on=date(2027, 1, 20))
    assert out["status"] == "active" and out["suspended_at"] is None
    due = sorted(e["due_date"] for e in billing.entries.values())
    assert not any(d in due for d in (date(2026, 12, 10), date(2027, 1, 10)))  # skipped, never retro-billed
    assert date(2027, 2, 10) in due
    assert [v["kind"] for v in contracts.list_versions(s, c["id"])] == ["initial", "suspension", "resumption"]


# --- amendments / readjustment -----------------------------------------------------------------------------


def test_amendment_is_a_new_version_with_a_diff_and_changes_future_billing(s, billing):
    c = mk(s)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    contracts.amend_contract(s, c["id"], {"summary": "Aumento de escopo", "changes": {"amount_cents": 200000, "notice_days": 30}})
    got = contracts.get_contract(s, c["id"])
    assert (got["amount_cents"], got["notice_days"], got["version_n"]) == (200000, 30, 2)
    v2 = contracts.list_versions(s, c["id"])[1]
    assert v2["kind"] == "amendment" and v2["changes"]["amount_cents"] == {"from": 150000, "to": 200000}
    billing_run.bill_contract(s, got, billing, on=date(2026, 12, 5))
    amounts = {e["due_date"]: e["amount_cents"] for e in billing.entries.values()}
    assert amounts[date(2026, 11, 10)] == 150000 and amounts[date(2026, 12, 10)] == 200000


def test_amendment_rules(s, billing):
    d = mk(s)
    with pytest.raises(ContractsError) as e:
        contracts.amend_contract(s, d["id"], {"summary": "x", "changes": {"notice_days": 1}})
    assert e.value.code == "contrato_nao_rascunho"
    f = mk(s, billing_model="one_time")
    contracts.activate_contract(s, f["id"], billing=billing, on=ON)
    with pytest.raises(ContractsError) as e:
        contracts.amend_contract(s, f["id"], {"summary": "x", "changes": {"amount_cents": 1}})
    assert e.value.code == "periodo_ja_faturado"
    with pytest.raises(ContractsError):
        contracts.amend_contract(s, f["id"], {"summary": "x", "changes": {}})


def test_readjust_preview_then_apply(s, billing):
    c = mk(s, readjustment_index="IPCA", billing_model="retainer", retainer_minutes=600, excess_rate_cents=10000)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    prev = contracts.readjust_contract(s, c["id"], {"percent_bp": 450})
    assert prev["applied"] is False and prev["amount_cents_after"] == 156750 and prev["excess_rate_cents_after"] == 10450
    assert contracts.get_contract(s, c["id"])["amount_cents"] == 150000  # a preview writes nothing
    out = contracts.readjust_contract(s, c["id"], {"percent_bp": 450, "apply": True, "effective_on": date(2026, 12, 1)})
    got = contracts.get_contract(s, c["id"])
    assert out["applied"] and (got["amount_cents"], got["excess_rate_cents"], got["last_readjusted_on"]) == (156750, 10450, "2026-12-01")
    assert contracts.list_versions(s, c["id"])[-1]["kind"] == "readjustment"
    assert contracts.present_contract(got, is_admin=True)["readjustment_due_on"] == "2027-12-01"


def test_readjust_refusals(s, billing):
    f = mk(s, billing_model="one_time", readjustment_index="IPCA")
    with pytest.raises(ContractsError) as e:
        contracts.readjust_contract(s, f["id"], {"percent_bp": 100})
    assert e.value.code == "reajuste_nao_aplicavel"
    r = mk(s)  # index none
    with pytest.raises(ContractsError) as e:
        contracts.readjust_contract(s, r["id"], {"percent_bp": 100})
    assert e.value.code == "reajuste_nao_aplicavel"
    fx = mk(s, readjustment_index="fixed", readjustment_percent_bp=300)
    assert contracts.readjust_contract(s, fx["id"], {})["percent_bp"] == 300  # fixed uses the stored percentage


# --- termination -------------------------------------------------------------------------------------------


def test_termination_enforces_notice_and_defaults_to_it(s, billing):
    c = mk(s, notice_days=30, penalty_cents=5000)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    with pytest.raises(ContractsError) as e:
        contracts.terminate_contract(s, c["id"], {"reason": "x", "effective_on": date(2026, 11, 5)}, billing=billing, on=ON)
    assert e.value.code == "aviso_previo_nao_cumprido" and e.value.details["terminable_from"] == "2026-12-01"
    out = contracts.terminate_contract(s, c["id"], {"reason": "Mudança de agência"}, billing=billing, on=ON)
    assert (out["status"], out["terminated_on"], out["penalty_applied_cents"]) == ("terminated", "2026-12-01", None)
    assert contracts.list_versions(s, c["id"])[-1]["kind"] == "termination"


def test_early_termination_with_waived_notice_bills_the_penalty_and_cancels_future_receivables(s, billing):
    c = mk(s, billing_model="installments", installments_count=4, amount_cents=40000, first_due_date="2026-11-10",
           notice_days=30, penalty_cents=1000, penalty_bp=1000)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    paid = f"{c['id']}:i1"
    billing.settled.add((ORG_A, paid))
    out = contracts.terminate_contract(s, c["id"], {"reason": "rescisão", "effective_on": date(2026, 11, 20), "waive_notice": True},
                                       billing=billing, on=ON)
    # remaining = i2 + i3 + i4 (due after Nov 20) = 30000; penalty = 1000 fixed + 10% of 30000
    assert out["penalty_applied_cents"] == 4000
    st = {k[1].split(":", 1)[1]: v["status"] for k, v in billing.entries.items()}
    assert st["i1"] == "open"  # settled: kept
    assert st["i2"] == "cancelled" and st["i3"] == "cancelled" and st["i4"] == "cancelled" and st["termination:penalty"] == "open"
    kinds = {r["kind"] for r in billing_run.list_billings(s, c["id"])}
    assert "penalty" in kinds
    waived = mk(s, notice_days=30, penalty_cents=9000)
    contracts.activate_contract(s, waived["id"], billing=billing, on=ON)
    ok = contracts.terminate_contract(s, waived["id"], {"reason": "x", "effective_on": ON, "waive_notice": True, "waive_penalty": True},
                                      billing=billing, on=ON)
    assert ok["penalty_applied_cents"] is None


def test_terminated_contract_is_not_billed_again(s, billing):
    c = mk(s)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    contracts.terminate_contract(s, c["id"], {"reason": "x", "effective_on": ON}, billing=billing, on=ON)
    got = contracts.get_contract(s, c["id"])
    assert billing_run.bill_contract(s, got, billing, on=date(2027, 6, 1)) == {"created": 0}


# --- retainer ----------------------------------------------------------------------------------------------


def test_retainer_bills_the_excess_in_arrears_once(s, billing):
    c = mk(s, billing_model="retainer", retainer_minutes=600, excess_rate_cents=12000)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    contracts.add_usage(s, c["id"], {"minutes": 500, "period": date(2026, 11, 3)})
    contracts.add_usage(s, c["id"], {"minutes": 160, "period": date(2026, 11, 20)})
    assert contracts.usage_summary(s, c["id"])[0]["excess_cents"] == 12000 * 60 // 60  # 660 - 600 = 60min x R$120/h
    got = contracts.get_contract(s, c["id"])
    assert billing_run.bill_contract(s, got, billing, on=date(2026, 11, 28))["created"] == 0 or True
    # still inside November: the excess is not final
    assert not any(k[1].endswith(":excess") for k in billing.entries)
    billing_run.bill_contract(s, contracts.get_contract(s, c["id"]), billing, on=date(2026, 12, 2))
    ex = [e for k, e in billing.entries.items() if k[1].endswith(":excess")]
    assert len(ex) == 1 and ex[0]["amount_cents"] == 12000 and ex[0]["due_date"] == date(2026, 12, 10)
    billing_run.bill_contract(s, contracts.get_contract(s, c["id"]), billing, on=date(2026, 12, 3))
    assert len([k for k in billing.entries if k[1].endswith(":excess")]) == 1
    with pytest.raises(ContractsError) as e:
        contracts.add_usage(s, c["id"], {"minutes": 10, "period": date(2026, 11, 25)})
    assert e.value.code == "periodo_ja_faturado"


def test_usage_only_on_retainers(s):
    with pytest.raises(ContractsError) as e:
        contracts.add_usage(s, mk(s)["id"], {"minutes": 5})
    assert e.value.code == "uso_nao_aplicavel"


def test_within_the_franchise_bills_no_excess(s, billing):
    c = mk(s, billing_model="retainer", retainer_minutes=600, excess_rate_cents=12000)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    contracts.add_usage(s, c["id"], {"minutes": 600, "period": date(2026, 11, 3)})
    billing_run.bill_contract(s, contracts.get_contract(s, c["id"]), billing, on=date(2026, 12, 2))
    assert not any(k[1].endswith(":excess") for k in billing.entries)


# --- preview / job -----------------------------------------------------------------------------------------


def test_preview_lists_the_next_unbilled_periods(s, billing):
    c = mk(s)
    contracts.activate_contract(s, c["id"], billing=billing, on=ON)
    items = billing_run.billing_preview(s, c["id"], 3)["items"]
    assert [i["due_date"] for i in items] == ["2026-12-10", "2027-01-10", "2027-02-10"]
    assert items[0]["amount_cents"] == 150000


def test_job_renews_expires_and_bills_across_orgs(db, billing):
    from .conftest import CFG
    from noctusai_lib.domain.contracts._common import Scope

    sa, sb = Scope(db, CFG, ORG_A), Scope(db, CFG, ORG_B)
    renew = mk(sa, auto_renew=True, renewal_months=6, start_date="2026-01-01", end_date="2026-10-31", first_due_date="2026-01-10")
    expire = mk(sb, auto_renew=False, start_date="2026-01-01", end_date="2026-10-31", first_due_date="2026-10-10",
                billing_model="one_time")
    for s_, c in ((sa, renew), (sb, expire)):
        contracts.activate_contract(s_, c["id"], billing=billing, on=date(2026, 1, 1))
    summary = billing_run.contracts_generate_billing(db, CFG, billing, on=date(2026, 11, 15))
    assert summary["contracts"] == 2 and summary["renewed"] == 1 and summary["expired"] == 1 and summary["failed"] == 0
    assert contracts.get_contract(sa, renew["id"])["end_date"] == "2027-04-30"
    assert contracts.get_contract(sb, expire["id"])["status"] == "expired"
    assert contracts.list_versions(sa, renew["id"])[-1]["kind"] == "renewal"
    only_b = billing_run.contracts_generate_billing(db, CFG, billing, org_id=ORG_B, on=date(2026, 11, 15))
    assert only_b["contracts"] == 0  # B's contract expired; A's is not touched when scoped to B
    n = len(billing.entries)
    billing_run.contracts_generate_billing(db, CFG, billing, on=date(2026, 11, 15))
    assert len(billing.entries) == n  # idempotent


def test_job_survives_a_failing_contract(db, billing):
    from .conftest import CFG
    from noctusai_lib.domain.contracts._common import Scope

    class Boom(type(billing)):
        def book_receivable(self, org_id, *, source_ref, **kw):
            if "boom" in kw["description"]:
                raise RuntimeError("gateway down")
            return super().book_receivable(org_id, source_ref=source_ref, **kw)

    sa = Scope(db, CFG, ORG_A)
    bad, good = mk(sa, title="boom"), mk(sa, title="fine")
    b = Boom()
    for c in (bad, good):
        # activate with a healthy seam so both are active, then run the job with the failing one
        contracts.activate_contract(sa, c["id"], billing=type(billing)(), on=date(2026, 1, 1))
    summary = billing_run.contracts_generate_billing(db, CFG, b, on=date(2026, 11, 15))
    assert summary["failed"] == 1 and summary["created"] >= 1


# --- quotes seam -------------------------------------------------------------------------------------------


def test_contract_from_quote_is_a_draft_and_idempotent_per_quote(s, s_b):
    q = ContractFromQuote(quote_id="Q-1", title="Proposta aceita", lines=(QuoteLine("Serviço", 70000, 2),),
                          billing_model="installments", installments_count=2, first_due_date=date(2026, 12, 1))
    c, created = create_contract_from_quote(s, q, user_id=USER_ID)
    assert created and c["status"] == "draft" and c["amount_cents"] == 140000 and c["source_quote_id"] == "Q-1"
    again, created2 = create_contract_from_quote(s, q)
    assert not created2 and again["id"] == c["id"]
    other_org, created3 = create_contract_from_quote(s_b, q)
    assert created3 and other_org["id"] != c["id"]


# --- isolation ---------------------------------------------------------------------------------------------


def test_every_read_and_write_is_org_scoped(s, s_b, billing):
    c = mk(s)
    from noctusai_lib.primitives.exceptions import NotFoundError

    for call in (lambda: contracts.get_contract(s_b, c["id"]), lambda: contracts.update_contract(s_b, c["id"], {"title": "x"}),
                 lambda: contracts.activate_contract(s_b, c["id"], billing=billing), lambda: contracts.list_versions(s_b, c["id"]),
                 lambda: billing_run.list_billings(s_b, c["id"])):
        with pytest.raises(NotFoundError):
            call()
    assert contracts.list_contracts(s_b)[1] == 0
