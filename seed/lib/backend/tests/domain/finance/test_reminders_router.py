"""Reminders HTTP contract: paths, strict 401, staff read / admin write, envelopes, pt-BR codes, first-enable seeding, preview."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from fastapi import HTTPException

from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.domain.finance.reminders import (
    DEFAULT_RULES,
    FakeReminderChannel,
    ReminderContact,
    ReminderPorts,
    make_finance_reminders_router,
    run_reminders_for_org,
)
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

from .conftest import CFG, ORG_A, Harness, _admin, _auth, _resolve, make_db, mk_entry

P = "/api/finance/reminders"
U0 = "11111111-1111-1111-1111-111111111111"
TODAY = date(2026, 10, 20)


def _contact(_s, entry):
    return ReminderContact(nome="Maria", phone="11999998888", link_pagamento=f"https://pay/{entry['id']}")


@pytest.fixture
def hr(finance_schema_cache):
    db = make_db()
    channel = FakeReminderChannel()
    ports = ReminderPorts(channels={"whatsapp": channel}, resolve_contact=_contact)
    router = make_finance_reminders_router(CFG, _auth, _admin, resolve_context=_resolve, get_db=lambda: db, get_ports=lambda: ports)
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    h = Harness(db, None, app, TestClient(app))  # type: ignore[arg-type]
    h.ports, h.channel = ports, channel  # type: ignore[attr-defined]
    return h


def call(h, method, path, headers=None, **kw):
    return h.client.request(method, path, headers=headers or {}, **kw)


ROUTES = [
    ("GET", f"{P}/settings", False), ("PUT", f"{P}/settings", True), ("GET", f"{P}/rules", False), ("POST", f"{P}/rules", True),
    ("POST", f"{P}/rules/defaults", True), ("PATCH", f"{P}/rules/{U0}", True), ("DELETE", f"{P}/rules/{U0}", True),
    ("PUT", f"{P}/receivables/{U0}/opt-out", True), ("GET", f"{P}/log", False), ("GET", f"{P}/preview", False),
]


@pytest.mark.parametrize("method, path, _w", ROUTES)
def test_unauthenticated_is_strictly_401(hr, method, path, _w):
    assert call(hr, method, path, json={}).status_code == 401


@pytest.mark.parametrize("method, path, _w", [r for r in ROUTES if r[2]])
def test_staff_cannot_write(hr, method, path, _w):
    assert call(hr, method, path, hr.staff("user"), json={}).status_code == 403


@pytest.mark.parametrize("method, path, _w", [r for r in ROUTES if not r[2]])
def test_staff_can_read(hr, method, path, _w):
    assert call(hr, method, path, hr.staff("user")).status_code == 200


def test_off_by_default_and_exposes_the_variable_vocabulary(hr):
    data = call(hr, "GET", f"{P}/settings", hr.staff()).json()["data"]
    assert data["enabled"] is False and data["timezone"] == "America/Sao_Paulo"
    assert "link_pagamento" in data["variables"] and "dias_atraso" in data["variables"]
    assert call(hr, "GET", f"{P}/rules", hr.staff()).json()["data"] == []


def test_first_enable_seeds_the_default_rules_once(hr):
    r = call(hr, "PUT", f"{P}/settings", hr.admin, json={"enabled": True})
    assert r.status_code == 200 and r.json()["data"]["enabled"] is True
    rules = call(hr, "GET", f"{P}/rules", hr.staff()).json()["data"]
    assert sorted(x["offset_days"] for x in rules) == sorted(o for o, _ in DEFAULT_RULES)
    # the org deletes one, switches off and on again: its choice stands (no re-seeding over existing rules)
    gone = next(x for x in rules if x["offset_days"] == 7)
    assert call(hr, "DELETE", f"{P}/rules/{gone['id']}", hr.admin).status_code == 204
    call(hr, "PUT", f"{P}/settings", hr.admin, json={"enabled": False})
    call(hr, "PUT", f"{P}/settings", hr.admin, json={"enabled": True})
    assert len(call(hr, "GET", f"{P}/rules", hr.staff()).json()["data"]) == len(DEFAULT_RULES) - 1
    assert call(hr, "POST", f"{P}/rules/defaults", hr.admin).status_code == 200
    assert len(call(hr, "GET", f"{P}/rules", hr.staff()).json()["data"]) == len(DEFAULT_RULES)


def test_settings_validation(hr):
    assert call(hr, "PUT", f"{P}/settings", hr.admin, json={"typo": 1}).status_code == 422
    r = call(hr, "PUT", f"{P}/settings", hr.admin, json={"timezone": "Mars/Base"})
    assert r.status_code == 422


def test_rule_crud_and_error_codes(hr):
    ok = call(hr, "POST", f"{P}/rules", hr.admin, json={"offset_days": 3, "template": "Oi {nome}, venceu há {dias_atraso} dias"})
    assert ok.status_code == 201
    rule = ok.json()["data"]
    unknown = call(hr, "POST", f"{P}/rules", hr.admin, json={"offset_days": 4, "template": "Oi {nom}"})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "variavel_desconhecida"
    assert "{nom}" in unknown.json()["error"]["message"]
    dup = call(hr, "POST", f"{P}/rules", hr.admin, json={"offset_days": 3, "template": "outra"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "regra_duplicada"
    assert call(hr, "POST", f"{P}/rules", hr.admin, json={"offset_days": 999, "template": "x"}).status_code == 422
    assert call(hr, "POST", f"{P}/rules", hr.admin, json={"offset_days": 5, "template": "x", "oops": 1}).status_code == 422
    upd = call(hr, "PATCH", f"{P}/rules/{rule['id']}", hr.admin, json={"enabled": False, "template": "Olá {nome}"})
    assert upd.status_code == 200 and upd.json()["data"]["enabled"] is False
    bad = call(hr, "PATCH", f"{P}/rules/{rule['id']}", hr.admin, json={"template": "{zzz}"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "variavel_desconhecida"
    assert call(hr, "DELETE", f"{P}/rules/{rule['id']}", hr.admin).status_code == 204
    assert call(hr, "DELETE", f"{P}/rules/{rule['id']}", hr.admin).status_code == 404


def test_rules_are_org_scoped(hr):
    call(hr, "POST", f"{P}/rules", hr.admin, json={"offset_days": 1, "template": "a"})
    assert call(hr, "GET", f"{P}/rules", hr.staff("org-b")).json()["data"] == []


def test_opt_out_marks_the_receivable_and_removes_it_from_the_preview(hr):
    s = Scope(hr.db, CFG, ORG_A)
    entry = mk_entry(s, due_date="2026-10-20")
    call(hr, "PUT", f"{P}/settings", hr.admin, json={"enabled": True})
    pv = call(hr, "GET", f"{P}/preview?on=2026-10-20", hr.staff()).json()["data"]
    assert [p["entry_id"] for p in pv["planned"]] == [entry["id"]] and pv["planned"][0]["description"] == "Mensalidade"
    r = call(hr, "PUT", f"{P}/receivables/{entry['id']}/opt-out", hr.admin, json={"opt_out": True})
    assert r.json()["data"] == {"entry_id": entry["id"], "reminders_opt_out": True}
    pv = call(hr, "GET", f"{P}/preview?on=2026-10-20", hr.staff()).json()["data"]
    assert pv["planned"] == [] and pv["skipped"][0]["reason"] == "receivable_opt_out"
    assert call(hr, "PUT", f"{P}/receivables/{U0}/opt-out", hr.admin, json={"opt_out": True}).status_code == 404
    assert call(hr, "PUT", f"{P}/receivables/{entry['id']}/opt-out", hr.admin, json={}).status_code == 422


def test_preview_is_empty_while_off_and_writes_nothing(hr):
    mk_entry(Scope(hr.db, CFG, ORG_A), due_date="2026-10-20")
    pv = call(hr, "GET", f"{P}/preview?on=2026-10-20", hr.staff()).json()["data"]
    assert pv["enabled"] is False and pv["planned"] == []
    call(hr, "PUT", f"{P}/settings", hr.admin, json={"enabled": True})
    assert call(hr, "GET", f"{P}/preview?on=2026-10-20", hr.staff()).json()["data"]["planned"]
    assert hr.channel.sent == [] and call(hr, "GET", f"{P}/log", hr.staff()).json()["pagination"]["total"] == 0


def test_log_is_paginated_filterable_and_org_scoped(hr):
    s = Scope(hr.db, CFG, ORG_A)
    for _ in range(3):
        mk_entry(s, due_date="2026-10-20")
    call(hr, "PUT", f"{P}/settings", hr.admin, json={"enabled": True})
    assert run_reminders_for_org(s, hr.ports, on=TODAY)["sent"] == 3
    page = call(hr, "GET", f"{P}/log?page=1&page_size=2", hr.staff()).json()
    assert page["pagination"]["total"] == 3 and len(page["data"]) == 2 and page["data"][0]["status"] == "sent"
    assert call(hr, "GET", f"{P}/log?status=failed", hr.staff()).json()["pagination"]["total"] == 0
    assert call(hr, "GET", f"{P}/log?status=bogus", hr.staff()).status_code == 422
    assert call(hr, "GET", f"{P}/log", hr.staff("org-b")).json()["pagination"]["total"] == 0
