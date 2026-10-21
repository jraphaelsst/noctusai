"""Hard delete ("lançado por engano"): entries and accounts. Anything with a trail is cancel / deactivate only."""
from __future__ import annotations

from datetime import date, timedelta

from noctusai_lib.domain.finance import entries

from noctusai_lib.domain.finance import recurrences
from noctusai_lib.domain.finance._common import Scope

from .conftest import CFG, ORG_A, mk_account as svc_account
from .test_router import PDF, P, call, mk_account, mk_entry

U_MISSING = "99999999-9999-9999-9999-999999999999"


def _code(r):
    return r.status_code, r.json()["error"]["code"]


def _settle(h, e, acc, amount=100):
    r = call(h, "POST", f"{P}/entries/{e['id']}/settlements", h.admin, json={"account_id": acc["id"], "amount_cents": amount})
    assert r.status_code == 201, r.text
    return r.json()["data"]["settlement"]


# ── entries ──


def test_delete_mistaken_entry_ok_and_detail_says_deletable(h):
    e = mk_entry(h)[0]
    assert call(h, "GET", f"{P}/entries/{e['id']}", h.staff()).json()["data"]["deletable"] is True
    assert call(h, "DELETE", f"{P}/entries/{e['id']}", h.admin).status_code == 204
    assert call(h, "GET", f"{P}/entries/{e['id']}", h.staff()).status_code == 404


def test_delete_removes_the_entrys_own_attachments_and_objects(h):
    e = mk_entry(h)[0]
    att = call(h, "POST", f"{P}/entries/{e['id']}/attachments", h.admin, files={"file": ("n.pdf", PDF, "application/pdf")}).json()["data"]
    assert call(h, "DELETE", f"{P}/entries/{e['id']}", h.admin).status_code == 204
    assert h.db.table("fin_attachments").select("id").eq("id", att["id"]).execute().data == []
    assert call(h, "DELETE", f"{P}/attachments/{att['id']}", h.admin).status_code == 404


def test_delete_installment_removes_only_that_row(h):
    group = mk_entry(h, installments=3, amount_cents=9000)
    assert call(h, "DELETE", f"{P}/entries/{group[1]['id']}", h.admin).status_code == 204
    left = call(h, "GET", f"{P}/entries", h.staff()).json()["data"]
    assert {r["id"] for r in left} == {group[0]["id"], group[2]["id"]}


def test_delete_refused_with_live_settlement(h):
    e, acc = mk_entry(h)[0], mk_account(h)
    _settle(h, e, acc)
    assert _code(call(h, "DELETE", f"{P}/entries/{e['id']}", h.admin)) == (409, "lancamento_com_historico")
    assert call(h, "GET", f"{P}/entries/{e['id']}", h.staff()).json()["data"]["deletable"] is False


def test_delete_refused_with_only_a_reversed_settlement(h):
    e, acc = mk_entry(h)[0], mk_account(h)
    st = _settle(h, e, acc)
    assert call(h, "POST", f"{P}/settlements/{st['id']}/reverse", h.admin, json={"reason": "engano"}).status_code == 200
    assert call(h, "GET", f"{P}/entries/{e['id']}", h.staff()).json()["data"]["settled_cents"] == 0
    assert _code(call(h, "DELETE", f"{P}/entries/{e['id']}", h.admin)) == (409, "lancamento_com_historico")
    assert call(h, "POST", f"{P}/entries/{e['id']}/cancel", h.admin).json()["data"]["status"] == "cancelled"


def test_delete_refused_when_system_sourced(h):
    s = Scope(h.db, CFG, ORG_A)
    row = entries.create_entry(s, {
        "direction": "receivable", "description": "Contrato", "due_date": (date.today() + timedelta(days=5)).isoformat(),
        "amount_cents": 500, "source": "contracts", "source_ref": "ctr-1:1",
    })[0]
    assert _code(call(h, "DELETE", f"{P}/entries/{row['id']}", h.admin)) == (409, "lancamento_de_sistema")
    assert call(h, "GET", f"{P}/entries/{row['id']}", h.staff()).json()["data"]["deletable"] is False


def test_delete_entry_foreign_org_404_missing_404_staff_403_anon_401(h):
    e = mk_entry(h)[0]
    assert call(h, "DELETE", f"{P}/entries/{e['id']}", h.staff("org-b-admin")).status_code == 404
    assert call(h, "DELETE", f"{P}/entries/{U_MISSING}", h.admin).status_code == 404
    assert call(h, "DELETE", f"{P}/entries/{e['id']}", h.staff("user")).status_code == 403
    assert call(h, "DELETE", f"{P}/entries/{e['id']}").status_code == 401
    assert call(h, "GET", f"{P}/entries/{e['id']}", h.staff()).status_code == 200  # still there


# ── accounts ──


def test_delete_unused_account_ok(h):
    acc = mk_account(h)
    assert call(h, "DELETE", f"{P}/accounts/{acc['id']}", h.admin).status_code == 204
    assert [a["id"] for a in call(h, "GET", f"{P}/accounts", h.staff()).json()["data"]] == []


def test_delete_account_refused_when_settled_against(h):
    acc, e = mk_account(h), mk_entry(h)[0]
    _settle(h, e, acc)
    r = call(h, "DELETE", f"{P}/accounts/{acc['id']}", h.admin)
    assert _code(r) == (409, "conta_em_uso")
    assert r.json()["error"]["message"] == "A conta tem movimentações; desative-a."


def test_delete_account_refused_when_expected_by_an_entry(h):
    acc = mk_account(h)
    mk_entry(h, expected_account_id=acc["id"])
    assert _code(call(h, "DELETE", f"{P}/accounts/{acc['id']}", h.admin)) == (409, "conta_em_uso")


def test_delete_account_refused_after_a_transfer(h):
    a, b = mk_account(h, name="A"), mk_account(h, name="B")
    assert call(h, "POST", f"{P}/transfers", h.admin, json={"from_account_id": a["id"], "to_account_id": b["id"], "amount_cents": 50}).status_code == 201
    assert _code(call(h, "DELETE", f"{P}/accounts/{a['id']}", h.admin)) == (409, "conta_em_uso")
    assert _code(call(h, "DELETE", f"{P}/accounts/{b['id']}", h.admin)) == (409, "conta_em_uso")


def test_delete_account_refused_when_a_recurrence_template_names_it(h):
    s = Scope(h.db, CFG, ORG_A)
    acc = svc_account(s)
    recurrences.create_recurrence(s, {
        "template": {"direction": "payable", "description": "Aluguel", "amount_cents": 1000, "expected_account_id": acc["id"]},
        "frequency": "monthly", "next_date": date.today().isoformat(),
    })
    assert _code(call(h, "DELETE", f"{P}/accounts/{acc['id']}", h.admin)) == (409, "conta_em_uso")


def test_delete_account_foreign_org_404_staff_403(h):
    acc = mk_account(h)
    assert call(h, "DELETE", f"{P}/accounts/{acc['id']}", h.staff("org-b-admin")).status_code == 404
    assert call(h, "DELETE", f"{P}/accounts/{acc['id']}", h.staff("user")).status_code == 403
    assert call(h, "DELETE", f"{P}/accounts/{U_MISSING}", h.admin).status_code == 404
