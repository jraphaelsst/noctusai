"""Accounts, balances, categories (tree + defaults), cost centers."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.finance import accounts, categories
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.primitives.exceptions import NotFoundError

from .conftest import mk_account, mk_entry


def code(exc: pytest.ExceptionInfo) -> str:
    return exc.value.code


# ── accounts ──


def test_create_and_list_accounts(s):
    a = mk_account(s, "Itaú", opening_balance_cents=10000, opening_date="2026-01-01")
    assert a["active"] is True and a["opening_balance_cents"] == 10000
    assert [r["name"] for r in accounts.list_accounts(s)] == ["Itaú"]


def test_gateway_account_requires_gateway_and_is_unique_per_org(s, s_b):
    with pytest.raises(FinanceError) as e:
        accounts.create_account(s, {"name": "G", "kind": "gateway"})
    assert e.value.status_code == 422
    mk_account(s, "Asaas", "gateway", gateway="Asaas")
    with pytest.raises(FinanceError) as e:
        mk_account(s, "Asaas 2", "gateway", gateway="asaas")
    assert (e.value.status_code, code(e)) == (409, "conta_gateway_duplicada")
    mk_account(s_b, "Asaas", "gateway", gateway="asaas")  # other org: unaffected


def test_get_or_create_gateway_account_is_idempotent(s):
    first = accounts.get_or_create_gateway_account(s, "asaas")
    again = accounts.get_or_create_gateway_account(s, "asaas")
    assert first["id"] == again["id"] and len(accounts.list_accounts(s)) == 1


def test_non_gateway_account_drops_a_stray_gateway(s):
    assert mk_account(s, "Cofre", "cash", gateway="x")["gateway"] is None


def test_opening_balance_frozen_once_the_ledger_has_rows(s):
    a, b = mk_account(s, "A", opening_balance_cents=100), mk_account(s, "B")
    from noctusai_lib.domain.finance import settlements

    settlements.create_transfer(s, {"from_account_id": a["id"], "to_account_id": b["id"], "amount_cents": 10})
    with pytest.raises(FinanceError) as e:
        accounts.update_account(s, a["id"], {"opening_balance_cents": 999})
    assert (e.value.status_code, code(e)) == (409, "conta_com_movimento")
    assert accounts.update_account(s, a["id"], {"name": "A2"})["name"] == "A2"


def test_balance_is_opening_plus_ledger_up_to_the_day(s):
    from noctusai_lib.domain.finance import settlements

    a, b = mk_account(s, "A", opening_balance_cents=1000, opening_date="2026-01-01"), mk_account(s, "B")
    settlements.create_transfer(s, {"from_account_id": a["id"], "to_account_id": b["id"], "amount_cents": 300, "occurred_on": "2026-03-10"})
    bal = lambda acc, on: accounts.account_balance(s, acc["id"], date.fromisoformat(on))["balance_cents"]  # noqa: E731
    assert bal(a, "2026-03-09") == 1000
    assert bal(a, "2026-03-10") == 700
    assert bal(b, "2026-03-10") == 300
    assert bal(a, "2025-12-31") == 0  # before the opening date the opening balance does not count


def test_account_of_another_org_is_a_404(s, s_b):
    other = mk_account(s_b, "B")
    with pytest.raises(NotFoundError):
        accounts.get_account(s, other["id"])
    with pytest.raises(NotFoundError):
        accounts.update_account(s, other["id"], {"name": "x"})
    with pytest.raises(NotFoundError):
        accounts.account_balance(s, other["id"])


def test_inactive_account_cannot_take_money(s):
    a = mk_account(s)
    accounts.update_account(s, a["id"], {"active": False})
    with pytest.raises(FinanceError) as e:
        accounts.require_usable_account(s, a["id"])
    assert code(e) == "conta_inativa"


# ── categories ──


def test_defaults_are_seeded_on_first_use_and_only_once(s):
    first = categories.list_categories(s)
    assert any(c["name"] == "Vendas" and c["is_default"] for c in first)
    n = len(first)
    assert len(categories.list_categories(s)) == n
    assert categories.seed_default_categories(s) == []  # idempotent: nothing missing
    roots = [c for c in first if c["parent_id"] is None]
    assert {r["direction"] for r in roots} == {"income", "expense", "transfer"}


def test_defaults_are_per_org(s, s_b):
    categories.list_categories(s)
    assert categories.list_categories(s_b)  # seeds B too
    assert {c["org_id"] for c in categories.list_categories(s_b)} == {s_b.org_id}


def test_category_tree_rules(s):
    root = categories.create_category(s, {"name": "Operação", "direction": "expense"})
    child = categories.create_category(s, {"name": "Cloud", "direction": "expense", "parent_id": root["id"]})
    with pytest.raises(FinanceError) as e:  # child must share the parent's direction
        categories.create_category(s, {"name": "Bad", "direction": "income", "parent_id": root["id"]})
    assert code(e) == "categoria_direcao_invalida"
    with pytest.raises(FinanceError) as e:  # duplicate sibling, case-insensitive
        categories.create_category(s, {"name": "CLOUD", "direction": "expense", "parent_id": root["id"]})
    assert (e.value.status_code, code(e)) == (409, "categoria_duplicada")
    # the same name under a different parent is fine
    categories.create_category(s, {"name": "Cloud", "direction": "expense"})
    assert set(categories.descendant_ids(s, root["id"])) == {root["id"], child["id"]}


def test_category_cannot_move_under_itself(s):
    a = categories.create_category(s, {"name": "A", "direction": "expense"})
    b = categories.create_category(s, {"name": "B", "direction": "expense", "parent_id": a["id"]})
    with pytest.raises(FinanceError) as e:
        categories.update_category(s, a["id"], {"parent_id": b["id"]})
    assert code(e) == "categoria_ciclo"


def test_category_in_use_cannot_be_deleted(s):
    cat = categories.create_category(s, {"name": "Aluguel X", "direction": "expense"})
    sub = categories.create_category(s, {"name": "Sub", "direction": "expense", "parent_id": cat["id"]})
    with pytest.raises(FinanceError) as e:  # has a child
        categories.delete_category(s, cat["id"])
    assert (e.value.status_code, code(e)) == (409, "categoria_em_uso")
    mk_entry(s, direction="payable", category_id=sub["id"])
    with pytest.raises(FinanceError) as e:  # has an entry
        categories.delete_category(s, sub["id"])
    assert code(e) == "categoria_em_uso"
    free = categories.create_category(s, {"name": "Livre", "direction": "income"})
    categories.delete_category(s, free["id"])
    with pytest.raises(NotFoundError):
        categories.get_category(s, free["id"])


def test_category_referenced_by_a_recurrence_template_is_in_use(s):
    from noctusai_lib.domain.finance import recurrences

    cat = categories.create_category(s, {"name": "Assinatura", "direction": "expense"})
    recurrences.create_recurrence(s, {
        "template": {"direction": "payable", "description": "SaaS", "amount_cents": 5000, "category_id": cat["id"]},
        "frequency": "monthly", "next_date": "2026-11-05",
    })
    with pytest.raises(FinanceError) as e:
        categories.delete_category(s, cat["id"])
    assert code(e) == "categoria_em_uso"


def test_category_of_another_org_is_invisible(s, s_b):
    other = categories.create_category(s_b, {"name": "Só da B", "direction": "income"})
    with pytest.raises(NotFoundError):
        categories.get_category(s, other["id"])
    with pytest.raises(NotFoundError):
        categories.delete_category(s, other["id"])


def test_category_hint_resolves_by_name_and_direction(s):
    sales = categories.find_category_by_hint(s, "vendas", categories.CategoryDirection.INCOME)
    assert sales is not None
    assert categories.find_category_by_hint(s, "vendas", categories.CategoryDirection.EXPENSE) is None
    assert categories.find_category_by_hint(s, None, categories.CategoryDirection.INCOME) is None


# ── cost centers ──


def test_cost_centers_code_unique_per_org(s, s_b):
    cc = categories.create_cost_center(s, {"code": "ADM", "name": "Administrativo"})
    with pytest.raises(FinanceError) as e:
        categories.create_cost_center(s, {"code": "adm", "name": "Outro"})
    assert (e.value.status_code, code(e)) == (409, "centro_custo_duplicado")
    categories.create_cost_center(s_b, {"code": "ADM", "name": "Admin B"})
    assert categories.update_cost_center(s, cc["id"], {"active": False})["active"] is False
    with pytest.raises(FinanceError):
        mk_entry(s, cost_center_id=cc["id"])  # inactive cost center refused for new entries
