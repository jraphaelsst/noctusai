"""Router contract: paths, statuses, envelopes, pt-BR error codes, authz (staff read / admin write), masking."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from .conftest import VALID_CNPJ, VALID_CPF

U0 = "11111111-1111-1111-1111-111111111111"
PDF = b"%PDF-1.7\n" + b"0" * 64
P = "/api/finance"

#: (method, path, is_write) -- the whole surface of slice C.
ROUTES = [
    ("GET", f"{P}/accounts", False), ("POST", f"{P}/accounts", True), ("PATCH", f"{P}/accounts/{U0}", True),
    ("GET", f"{P}/accounts/{U0}/balance", False),
    ("GET", f"{P}/categories", False), ("POST", f"{P}/categories", True),
    ("PATCH", f"{P}/categories/{U0}", True), ("DELETE", f"{P}/categories/{U0}", True),
    ("GET", f"{P}/cost-centers", False), ("POST", f"{P}/cost-centers", True), ("PATCH", f"{P}/cost-centers/{U0}", True),
    ("GET", f"{P}/entries", False), ("POST", f"{P}/entries", True), ("GET", f"{P}/entries/{U0}", False),
    ("PATCH", f"{P}/entries/{U0}", True), ("POST", f"{P}/entries/{U0}/cancel", True),
    ("POST", f"{P}/entries/{U0}/settlements", True), ("POST", f"{P}/settlements/{U0}/reverse", True),
    ("GET", f"{P}/recurrences", False), ("POST", f"{P}/recurrences", True), ("PATCH", f"{P}/recurrences/{U0}", True),
    ("POST", f"{P}/transfers", True),
    ("GET", f"{P}/reports/cashflow", False), ("GET", f"{P}/reports/dre", True), ("GET", f"{P}/reports/aging", False),
    ("GET", f"{P}/reports/simples-base", True), ("GET", f"{P}/dre-settings", False), ("PUT", f"{P}/dre-settings", True),
    ("GET", f"{P}/accountant-checklist", True), ("GET", f"{P}/exports/dre.csv", True),
    ("GET", f"{P}/entries/{U0}/attachments", False), ("POST", f"{P}/entries/{U0}/attachments", True),
    ("DELETE", f"{P}/attachments/{U0}", True),
    ("DELETE", f"{P}/entries/{U0}", True), ("DELETE", f"{P}/accounts/{U0}", True),
]


def call(h, method, path, headers=None, **kw):
    return h.client.request(method, path, headers=headers or {}, **kw)


@pytest.mark.parametrize("method, path, _write", ROUTES)
def test_unauthenticated_is_strictly_401(h, method, path, _write):
    assert call(h, method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if r[2]])
def test_staff_cannot_write(h, method, path, write):
    body = {"files": {"file": ("a.pdf", PDF, "application/pdf")}} if path.endswith("/attachments") else {"json": {}}
    assert call(h, method, path, h.staff("user"), **body).status_code == 403


@pytest.mark.parametrize("method, path, write", [r for r in ROUTES if not r[2]])
def test_staff_can_read(h, method, path, write):
    status = call(h, method, path, h.staff("user")).status_code
    assert status != 403 and status != 401  # 200, or 404 for the placeholder id -- never an authz refusal


def test_extra_fields_are_rejected_not_silently_dropped(h):
    r = call(h, "POST", f"{P}/accounts", h.admin, json={"name": "A", "kind": "cash", "typo_field": 1})
    assert r.status_code == 422


def mk_account(h, **over):
    r = call(h, "POST", f"{P}/accounts", h.admin, json={"name": "Banco", "kind": "checking", **over})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def mk_entry(h, **over):
    r = call(h, "POST", f"{P}/entries", h.admin, json={
        "direction": "receivable", "description": "Mensalidade",
        "due_date": (date.today() + timedelta(days=30)).isoformat(), "amount_cents": 10000, **over})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_create_entry_always_answers_a_list_and_installments_make_the_group(h):
    single = mk_entry(h)
    assert isinstance(single, list) and len(single) == 1
    group = mk_entry(h, installments=3, amount_cents=10000)
    assert [e["amount_cents"] for e in group] == [3333, 3333, 3334]


def test_entry_lifecycle_through_http(h):
    acc = mk_account(h)
    e = mk_entry(h)[0]
    r = call(h, "POST", f"{P}/entries/{e['id']}/settlements", h.admin,
             json={"account_id": acc["id"], "amount_cents": 4000, "fee_cents": 100, "external_ref": "pay_1"})
    assert r.status_code == 201
    body = r.json()["data"]
    assert body["entry"]["status"] == "partial" and body["replayed"] is False
    again = call(h, "POST", f"{P}/entries/{e['id']}/settlements", h.admin,
                 json={"account_id": acc["id"], "amount_cents": 4000, "fee_cents": 100, "external_ref": "pay_1"})
    assert again.status_code == 200 and again.json()["data"]["replayed"] is True  # idempotent replay is not a 201
    bal = call(h, "GET", f"{P}/accounts/{acc['id']}/balance", h.staff()).json()["data"]
    assert bal["balance_cents"] == 3900
    rev = call(h, "POST", f"{P}/settlements/{body['settlement']['id']}/reverse", h.admin, json={"reason": "duplicado"})
    assert rev.status_code == 200 and rev.json()["data"]["entry"]["status"] == "open"
    cancel = call(h, "POST", f"{P}/entries/{e['id']}/cancel", h.admin)
    assert cancel.json()["data"]["status"] == "cancelled"
    detail = call(h, "GET", f"{P}/entries/{e['id']}", h.staff()).json()["data"]
    assert len(detail["settlements"]) == 1 and detail["settlements"][0]["reversed_at"]


def test_pt_br_error_codes_and_statuses(h):
    acc = mk_account(h)
    e = mk_entry(h)[0]
    sett = call(h, "POST", f"{P}/entries/{e['id']}/settlements", h.admin, json={"account_id": acc["id"], "amount_cents": 100}).json()["data"]
    r = call(h, "POST", f"{P}/entries/{e['id']}/cancel", h.admin)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "lancamento_com_baixa")
    r = call(h, "POST", f"{P}/entries/{e['id']}/settlements", h.admin, json={"account_id": acc["id"], "amount_cents": 10**6})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "baixa_excede_saldo")
    call(h, "POST", f"{P}/settlements/{sett['settlement']['id']}/reverse", h.admin, json={"reason": "motivo"})
    r = call(h, "POST", f"{P}/settlements/{sett['settlement']['id']}/reverse", h.admin, json={"reason": "motivo"})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "baixa_ja_estornada")
    cat = call(h, "POST", f"{P}/categories", h.admin, json={"name": "Usada", "direction": "income"}).json()["data"]
    mk_entry(h, category_id=cat["id"])
    r = call(h, "DELETE", f"{P}/categories/{cat['id']}", h.admin)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "categoria_em_uso")
    r = call(h, "GET", f"{P}/entries/{U0}", h.staff())
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_lists_use_the_seed_envelopes(h):
    mk_account(h)
    r = call(h, "GET", f"{P}/accounts", h.staff()).json()
    assert set(r) == {"data"} and isinstance(r["data"], list)
    mk_entry(h)
    r = call(h, "GET", f"{P}/entries?page=1&page_size=10", h.staff()).json()
    assert set(r) == {"data", "pagination"} and r["pagination"]["total"] == 1
    assert call(h, "GET", f"{P}/entries?page_size=101", h.staff()).status_code == 422


def test_entries_filters_via_query_string(h):
    mk_entry(h, direction="payable", description="Conta de luz", due_date="2026-10-20")  # data inside the queried window
    mk_entry(h, description="Venda", due_date="2026-10-20")
    r = call(h, "GET", f"{P}/entries?direction=payable&from=2026-10-01&to=2026-10-31", h.staff()).json()
    assert [e["description"] for e in r["data"]] == ["Conta de luz"]
    assert call(h, "GET", f"{P}/entries?status=overdue", h.staff()).status_code == 422
    assert call(h, "GET", f"{P}/entries?overdue=true", h.staff()).status_code == 200


# ── LGPD masking ──


def test_counterparty_doc_is_masked_for_staff_everywhere_and_whole_for_admin(h):
    created = mk_entry(h, counterparty_name="Ana", counterparty_doc="529.982.247-25")[0]
    assert created["counterparty_doc"] == VALID_CPF  # the admin who wrote it sees it whole
    staff_list = call(h, "GET", f"{P}/entries", h.staff()).json()["data"][0]
    admin_list = call(h, "GET", f"{P}/entries", h.admin).json()["data"][0]
    assert staff_list["counterparty_doc"] == "***.982.247-**" and admin_list["counterparty_doc"] == VALID_CPF
    staff_detail = call(h, "GET", f"{P}/entries/{created['id']}", h.staff()).json()["data"]
    assert staff_detail["counterparty_doc"] == "***.982.247-**"
    assert VALID_CPF not in call(h, "GET", f"{P}/entries/{created['id']}", h.staff()).text
    mk_entry(h, counterparty_name="Bia", counterparty_doc=VALID_CNPJ, due_date="2026-01-01")
    aging = call(h, "GET", f"{P}/reports/aging", h.staff()).json()["data"]
    assert VALID_CNPJ not in str(aging) and "**.***.333/0001-**" in str(aging)
    assert VALID_CNPJ in str(call(h, "GET", f"{P}/reports/aging", h.admin).json())


# ── tenant isolation over HTTP ──


def test_org_b_cannot_see_or_touch_org_a(h):
    acc = mk_account(h)
    e = mk_entry(h)[0]
    b_admin, b_staff = h.staff("org-b-admin"), h.staff("org-b")
    assert call(h, "GET", f"{P}/entries", b_staff).json()["pagination"]["total"] == 0
    assert call(h, "GET", f"{P}/accounts", b_staff).json()["data"] == []
    for method, path, kw in (
        ("GET", f"{P}/entries/{e['id']}", {}),
        ("PATCH", f"{P}/entries/{e['id']}", {"json": {"notes": "x"}}),
        ("POST", f"{P}/entries/{e['id']}/cancel", {}),
        ("POST", f"{P}/entries/{e['id']}/settlements", {"json": {"account_id": acc["id"], "amount_cents": 1}}),
        ("PATCH", f"{P}/accounts/{acc['id']}", {"json": {"name": "hack"}}),
        ("GET", f"{P}/accounts/{acc['id']}/balance", {}),
    ):
        headers = b_admin if method != "GET" else b_staff
        assert call(h, method, path, headers, **kw).status_code in (404, 422), (method, path)
    mine = call(h, "GET", f"{P}/entries/{e['id']}", h.staff()).json()["data"]
    assert mine["status"] == "open" and mine["notes"] is None


def test_reports_defaults_and_validation(h):
    assert call(h, "GET", f"{P}/reports/cashflow", h.staff()).status_code == 200
    assert call(h, "GET", f"{P}/reports/dre", h.admin).status_code == 200
    assert call(h, "GET", f"{P}/reports/cashflow?from=2026-03-01&to=2026-01-01", h.staff()).status_code == 422
    assert call(h, "GET", f"{P}/reports/dre?from=2026-01-01&to=2026-02-01", h.admin).json()["data"]["months"] == ["2026-01", "2026-02"]
    assert call(h, "GET", f"{P}/reports/dre?view=managerial", h.admin).json()["data"]["view"] == "managerial"
    assert call(h, "GET", f"{P}/reports/dre?view=pie", h.admin).status_code == 422


def test_transfer_and_recurrence_routes(h):
    a, b = mk_account(h, name="A"), mk_account(h, name="B")
    r = call(h, "POST", f"{P}/transfers", h.admin, json={"from_account_id": a["id"], "to_account_id": b["id"], "amount_cents": 700})
    assert r.status_code == 201 and r.json()["data"]["transfer_group"]
    r = call(h, "POST", f"{P}/transfers", h.admin, json={"from_account_id": a["id"], "to_account_id": a["id"], "amount_cents": 1})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "transferencia_mesma_conta")
    rec = call(h, "POST", f"{P}/recurrences", h.admin, json={
        "template": {"direction": "payable", "description": "Aluguel", "amount_cents": 1000},
        "frequency": "monthly", "next_date": "2026-11-05"})
    assert rec.status_code == 201
    upd = call(h, "PATCH", f"{P}/recurrences/{rec.json()['data']['id']}", h.admin, json={"active": False})
    assert upd.json()["data"]["active"] is False
    assert len(call(h, "GET", f"{P}/recurrences", h.staff()).json()["data"]) == 1


def test_categories_and_cost_centers_routes(h):
    cats = call(h, "GET", f"{P}/categories", h.staff()).json()["data"]
    assert any(c["is_default"] for c in cats)  # defaults seeded on first read
    cc = call(h, "POST", f"{P}/cost-centers", h.admin, json={"code": "ADM", "name": "Admin"})
    assert cc.status_code == 201
    dup = call(h, "POST", f"{P}/cost-centers", h.admin, json={"code": "ADM", "name": "Outro"})
    assert (dup.status_code, dup.json()["error"]["code"]) == (409, "centro_custo_duplicado")
    new = call(h, "POST", f"{P}/categories", h.admin, json={"name": "Nova", "direction": "expense"}).json()["data"]
    assert call(h, "PATCH", f"{P}/categories/{new['id']}", h.admin, json={"name": "Renomeada"}).json()["data"]["name"] == "Renomeada"
    assert call(h, "DELETE", f"{P}/categories/{new['id']}", h.admin).status_code == 204


def test_attachment_routes(h):
    e = mk_entry(h)[0]
    ok = call(h, "POST", f"{P}/entries/{e['id']}/attachments", h.admin, files={"file": ("nota.pdf", PDF, "application/pdf")})
    assert ok.status_code == 201
    data = ok.json()["data"]
    assert data["filename"] == "nota.pdf" and data["url"] and "storage_path" not in data
    bad = call(h, "POST", f"{P}/entries/{e['id']}/attachments", h.admin, files={"file": ("x.pdf", b"not pdf", "application/pdf")})
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "anexo_invalido")
    listed = call(h, "GET", f"{P}/entries/{e['id']}/attachments", h.staff()).json()["data"]
    assert [a["id"] for a in listed] == [data["id"]]
    assert call(h, "DELETE", f"{P}/attachments/{data['id']}", h.staff()).status_code == 403
    assert call(h, "DELETE", f"{P}/attachments/{data['id']}", h.admin).status_code == 204
