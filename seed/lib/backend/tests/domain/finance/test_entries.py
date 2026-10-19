"""Entries: creation, installments, references, LGPD masking, listing filters, cancel."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from noctusai_lib.domain.finance import categories, entries, settlements
from noctusai_lib.domain.finance._common import add_months
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import ORG_B, VALID_CNPJ, VALID_CPF, mk_account, mk_entry


def test_single_entry_defaults(s):
    e = mk_entry(s, due_date="2026-10-20")
    assert (e["status"], e["settled_cents"], e["source"]) == ("open", 0, "manual")
    assert e["competence_month"] == "2026-10-01"  # defaults to the due month, day 1
    assert e["org_id"] == s.org_id


@pytest.mark.parametrize("total, n, parts", [
    (10000, 3, [3333, 3333, 3334]),
    (10000, 4, [2500] * 4),
    (100, 7, [14] * 6 + [16]),
    (5, 5, [1] * 5),
])
def test_installment_split_last_absorbs_remainder(total, n, parts):
    assert entries.split_installments(total, n) == parts
    assert sum(parts) == total


def test_installment_group_dates_numbering_and_sources(s):
    rows = entries.create_entry(s, {
        "direction": "payable", "description": "Notebook", "due_date": "2026-01-31",
        "amount_cents": 10000, "installments": 3,
    })
    assert [r["amount_cents"] for r in rows] == [3333, 3333, 3334]
    assert [r["due_date"] for r in rows] == ["2026-01-31", "2026-02-28", "2026-03-31"]  # anchored, clamped
    assert [r["competence_month"] for r in rows] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert [(r["installment_n"], r["installment_total"]) for r in rows] == [(1, 3), (2, 3), (3, 3)]
    assert len({r["installment_group_id"] for r in rows}) == 1
    assert {r["source"] for r in rows} == {"installment"} and len({r["source_ref"] for r in rows}) == 3
    assert rows[0]["description"] == "Notebook (1/3)"


def test_installment_rules(s):
    base = {"direction": "payable", "description": "x", "due_date": "2026-01-10"}
    with pytest.raises(FinanceError):
        entries.create_entry(s, {**base, "amount_cents": 2, "installments": 3})  # less than a cent each
    with pytest.raises(FinanceError):
        entries.create_entry(s, {**base, "amount_cents": 900, "installments": 3, "source_ref": "x"})
    with pytest.raises(FinanceError):
        entries.create_entry(s, {**base, "amount_cents": 900, "installments": 121})


def test_amount_must_be_positive(s):
    with pytest.raises(FinanceError):
        mk_entry(s, amount_cents=0)


def test_source_ref_is_unique_per_org_and_source(s, s_b):
    mk_entry(s, source="external", source_ref="inv-1")
    with pytest.raises(FinanceError) as e:
        mk_entry(s, source="external", source_ref="inv-1")
    assert (e.value.status_code, e.value.code) == (409, "lancamento_duplicado")
    mk_entry(s, source="manual", source_ref="inv-1")  # another source: fine
    mk_entry(s_b, source="external", source_ref="inv-1")  # another org: fine


def test_references_must_belong_to_the_callers_org(s, s_b):
    other_acc = mk_account(s_b)
    other_cat = categories.create_category(s_b, {"name": "Da B", "direction": "income"})
    other_cc = categories.create_cost_center(s_b, {"code": "B1", "name": "B"})
    for field, value in (("expected_account_id", other_acc["id"]), ("category_id", other_cat["id"]), ("cost_center_id", other_cc["id"])):
        with pytest.raises(FinanceError) as e:
            mk_entry(s, **{field: value})
        assert e.value.status_code == 422 and e.value.details["field"] == field
    assert s.rows("entries") == []  # nothing leaked through


def test_category_direction_must_fit_the_entry(s):
    cats = {c["name"]: c for c in categories.list_categories(s)}
    mk_entry(s, direction="receivable", category_id=cats["Vendas"]["id"])
    with pytest.raises(FinanceError) as e:
        mk_entry(s, direction="payable", category_id=cats["Vendas"]["id"])
    assert e.value.code == "categoria_direcao_invalida"


def test_counterparty_doc_is_validated_and_normalised(s):
    e = mk_entry(s, counterparty_doc="529.982.247-25")
    assert e["counterparty_doc"] == VALID_CPF
    assert mk_entry(s, counterparty_doc="11.222.333/0001-81")["counterparty_doc"] == VALID_CNPJ
    assert mk_entry(s, counterparty_doc="  ")["counterparty_doc"] is None
    with pytest.raises(FinanceError) as e2:
        mk_entry(s, counterparty_doc="123.456.789-00")
    assert e2.value.code == "documento_invalido"


@pytest.mark.parametrize("doc, masked", [
    (VALID_CPF, "***.982.247-**"),
    ("12345678901", "***.456.789-**"),
    (VALID_CNPJ, "**.***.333/0001-**"),
    (None, None),
    ("", ""),
])
def test_mask_doc(doc, masked):
    assert entries.mask_doc(doc) == masked


def test_present_entry_masks_for_staff_only(s):
    e = mk_entry(s, counterparty_doc=VALID_CPF)
    assert entries.present_entry(e, is_admin=True)["counterparty_doc"] == VALID_CPF
    assert entries.present_entry(e, is_admin=False)["counterparty_doc"] == "***.982.247-**"
    assert e["counterparty_doc"] == VALID_CPF  # presentation never mutates the row


def test_overdue_is_computed_on_read_and_never_stored(s):
    today = date(2026, 10, 13)
    late = mk_entry(s, due_date="2026-10-01")
    ontime = mk_entry(s, due_date="2026-10-13")
    assert entries.present_entry(late, is_admin=True, on=today)["overdue"] is True
    assert entries.present_entry(ontime, is_admin=True, on=today)["overdue"] is False
    assert late["status"] == "open" and s.find("entries", late["id"])["status"] == "open"
    acc = mk_account(s)
    settlements.settle_entry(s, late["id"], {"account_id": acc["id"], "amount_cents": 10000})
    paid = s.find("entries", late["id"])
    assert entries.present_entry(paid, is_admin=True, on=today)["overdue"] is False  # paid is never overdue
    cancelled = entries.cancel_entry(s, ontime["id"])
    assert entries.present_entry(cancelled, is_admin=True, on=date(2027, 1, 1))["overdue"] is False


def test_list_filters(s):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    a = mk_entry(s, direction="receivable", description="Alpha", due_date=yesterday)
    b = mk_entry(s, direction="payable", description="Beta", due_date=tomorrow)
    cat = categories.create_category(s, {"name": "Raiz", "direction": "income"})
    sub = categories.create_category(s, {"name": "Folha", "direction": "income", "parent_id": cat["id"]})
    c = mk_entry(s, direction="receivable", description="Gamma", due_date=tomorrow, category_id=sub["id"])
    cc = categories.create_cost_center(s, {"code": "X", "name": "X"})
    # explicit, far-future due date: the conftest default is a fixed calendar day that becomes
    # "tomorrow" (and later "overdue") as the clock moves, which flaked the date filters below
    d = mk_entry(s, description="Delta", cost_center_id=cc["id"], due_date=(date.today() + timedelta(days=30)).isoformat())

    def ids(**kw):
        rows, total, _, _ = entries.list_entries(s, **kw)
        assert total == len(rows)
        return {r["id"] for r in rows}

    assert ids(direction="payable") == {b["id"]}
    assert ids(overdue=True) == {a["id"]}
    assert ids(date_from=date.fromisoformat(tomorrow), date_to=date.fromisoformat(tomorrow)) == {b["id"], c["id"]}
    assert ids(category_id=cat["id"]) == {c["id"]}  # a parent filter includes the subtree
    assert ids(cost_center_id=cc["id"]) == {d["id"]}
    assert ids(status="paid") == set()
    with pytest.raises(FinanceError):
        entries.list_entries(s, status="overdue")  # overdue is never a stored status
    with pytest.raises(FinanceError):
        entries.list_entries(s, direction="sideways")


def test_search_term_can_never_inject_postgrest_syntax(s):
    from noctusai_lib.domain.finance._common import like_term

    cleaned = like_term('ac"me, (x).y%_*\\').strip("%")
    assert not any(ch in cleaned for ch in ',()".%_*\\')
    mk_entry(s, description="Aluguel")
    # NOTE: the mock evaluates PostgREST `or()` as match-all, so this proves the query is accepted
    # and bounded, not that it filters; the filter text itself is pinned by `like_term` above.
    rows, total, _, _ = entries.list_entries(s, q='ac"me, (x).y')
    assert total == len(rows)


def test_list_is_paginated_with_exact_total(s):
    for i in range(5):
        mk_entry(s, description=f"E{i}")
    rows, total, page, size = entries.list_entries(s, page=2, page_size=2)
    assert (len(rows), total, page, size) == (2, 5, 2, 2)


def test_list_is_org_scoped(s, s_b):
    mk_entry(s_b, description="de outra org")
    assert entries.list_entries(s)[1] == 0


def test_update_entry_rules(s):
    e = mk_entry(s, amount_cents=10000)
    acc = mk_account(s)
    settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 4000})
    with pytest.raises(FinanceError) as err:  # below what was already paid
        entries.update_entry(s, e["id"], {"amount_cents": 3000})
    assert err.value.code == "valor_abaixo_baixado"
    out = entries.update_entry(s, e["id"], {"amount_cents": 4000})
    assert out["status"] == "paid"  # status re-derived
    with pytest.raises(FinanceError):
        entries.update_entry(s, e["id"], {"description": None})
    assert entries.update_entry(s, e["id"], {"notes": "ok"})["notes"] == "ok"


def test_update_competence_normalises_to_day_one(s):
    e = mk_entry(s)
    assert entries.update_entry(s, e["id"], {"competence_month": date(2026, 5, 17)})["competence_month"] == "2026-05-01"


def test_cancelled_entry_is_frozen(s):
    e = mk_entry(s)
    entries.cancel_entry(s, e["id"])
    with pytest.raises(FinanceError) as err:
        entries.update_entry(s, e["id"], {"notes": "x"})
    assert (err.value.status_code, err.value.code) == (409, "lancamento_cancelado")
    assert entries.cancel_entry(s, e["id"])["status"] == "cancelled"  # idempotent


def test_cancel_with_unreversed_settlements_is_409(s):
    e, acc = mk_entry(s), mk_account(s)
    sett = settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 1000})["settlement"]
    with pytest.raises(FinanceError) as err:
        entries.cancel_entry(s, e["id"])
    assert (err.value.status_code, err.value.code) == (409, "lancamento_com_baixa")
    settlements.reverse_settlement(s, sett["id"], "erro de digitação")
    assert entries.cancel_entry(s, e["id"])["status"] == "cancelled"  # reversed settlements no longer block


def test_entry_of_another_org_is_a_404(s, s_b):
    other = mk_entry(s_b)
    for fn in (entries.get_entry, entries.cancel_entry, entries.get_entry_detail):
        with pytest.raises(NotFoundError):
            fn(s, other["id"])
    with pytest.raises(NotFoundError):
        entries.update_entry(s, other["id"], {"notes": "x"})
    assert s_b.find("entries", other["id"])["status"] == "open" and ORG_B == s_b.org_id


def test_detail_includes_settlements_history_and_hides_storage_paths(s):
    e, acc = mk_entry(s), mk_account(s)
    sett = settlements.settle_entry(s, e["id"], {"account_id": acc["id"], "amount_cents": 1000})["settlement"]
    settlements.reverse_settlement(s, sett["id"], "estorno")
    detail = entries.get_entry_detail(s, e["id"])
    assert [x["id"] for x in detail["settlements"]] == [sett["id"]] and detail["settlements"][0]["reversed_at"]
    assert detail["attachments"] == []


def test_add_months_keeps_the_anchor():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 31), 2) == date(2026, 3, 31)
    assert add_months(date(2026, 2, 28), 1, anchor_day=31) == date(2026, 3, 31)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
