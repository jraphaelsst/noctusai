"""Org scoping, auth boundary (strict 401), the approval rule, validation and the RPC refusal -> HTTP mapping."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.purchasing import PurchasingConfig, orders, settings
from noctusai_lib.domain.purchasing._common import Scope

from .conftest import (
    CFG, ROLES, ITEM, ORDER, ORG_A, ORG_B, PARTY, WH1, build_harness, seed_order, seed_line,
)

LINE = {"item_id": ITEM, "description": "Tinta", "qty": "10.000", "unit_cost_cents": 1000}
BODY = {"party_id": PARTY, "warehouse_id": WH1, "lines": [LINE]}
ID = "55555555-5555-4555-8555-555555555555"

READS = [
    ("GET", "/api/purchasing/settings", None),
    ("GET", "/api/purchasing/orders", None),
    ("GET", f"/api/purchasing/orders/{ORDER}", None),
    ("GET", "/api/purchasing/receipts", None),
    ("GET", f"/api/purchasing/receipts/{ID}", None),
]
SETTINGS_PUT = ("PUT", "/api/purchasing/settings", {"approval_threshold_cents": 100})
ADMIN_WRITES = [
    ("GET", "/api/purchasing/approvers", None),
    ("POST", "/api/purchasing/approvers", {"user_id": ID}),
    ("DELETE", f"/api/purchasing/approvers/{ID}", None),
    ("POST", "/api/purchasing/orders", BODY),
    ("PUT", f"/api/purchasing/orders/{ORDER}", BODY),
    ("POST", f"/api/purchasing/orders/{ORDER}/send", None),
    ("POST", f"/api/purchasing/orders/{ORDER}/cancel", {}),
    ("POST", f"/api/purchasing/orders/{ORDER}/receipts", {"lines": [{"order_line_id": ID, "qty": "1"}]}),
    ("POST", f"/api/purchasing/receipts/{ID}/post", None),
]
APPROVE = ("POST", f"/api/purchasing/orders/{ORDER}/approve", None)


def _send(h, method, path, body, headers):
    return h.client.request(method, path, json=body, headers=headers)


def seed_party(db, *, org=ORG_A, active=True, pid=PARTY):
    db.table("pty_parties").insert({
        "id": pid, "org_id": org, "kind": "PJ", "doc": "11222333000181", "legal_name": "Fornecedor Ltda",
        "trade_name": "Forn", "is_active": active,
    }).execute()


def test_every_route_is_covered(h):
    routes = {(m, r.path) for r in h.app.routes if hasattr(r, "methods") for m in r.methods if r.path.startswith("/api/purchasing")}
    assert len(routes) == len(READS) + len(ADMIN_WRITES) + 2  # + approve + the approver-gated PUT /settings


@pytest.mark.parametrize("method,path,body", [*READS, *ADMIN_WRITES, APPROVE, SETTINGS_PUT])
def test_unauthenticated_is_strictly_401(h, method, path, body):
    assert _send(h, method, path, body, {}).status_code == 401


@pytest.mark.parametrize("method,path,body", ADMIN_WRITES)
def test_staff_cannot_write_403(h, method, path, body):
    assert _send(h, method, path, body, h.as_("user")).status_code == 403


@pytest.mark.parametrize("method,path,body", ADMIN_WRITES)
def test_a_permission_holder_who_is_not_admin_still_cannot_write_other_than_approve(h, method, path, body):
    assert _send(h, method, path, body, h.as_("approver")).status_code == 403


def test_staff_can_read(h):
    seed_order(h.db)
    for method, path, body in READS[:3]:
        assert _send(h, method, path, body, h.as_("user")).status_code == 200, path
    assert h.client.get("/api/purchasing/receipts", headers=h.as_("user")).status_code == 200


def test_unknown_body_field_is_422_not_silently_dropped(h):
    assert h.client.post("/api/purchasing/orders", json={**BODY, "org_id": ORG_B}, headers=h.admin).status_code == 422
    assert h.client.post("/api/purchasing/orders", json={**BODY, "status": "approved"}, headers=h.admin).status_code == 422


@pytest.mark.parametrize(
    "patch",
    [
        {"lines": []},
        {"lines": [{**LINE, "qty": "0"}]},
        {"lines": [{**LINE, "qty": "1.5555"}]},
        {"lines": [{**LINE, "unit_cost_cents": -1}]},
        {"lines": [{**LINE, "description": ""}]},
        {"freight_cents": -1},
        {"installments_count": 0},
        {"installments_count": 121},
        {"party_id": "nope"},
    ],
)
def test_bad_orders_are_rejected_at_the_boundary(h, patch):
    assert h.client.post("/api/purchasing/orders", json={**BODY, **patch}, headers=h.admin).status_code == 422
    assert h.db.rpc_calls == []


# ── save ──────────────────────────────────────────────────────────────────────


def test_create_resolves_the_supplier_snapshot_from_the_party_and_sends_decimals_as_strings(h):
    seed_party(h.db)
    seed_order(h.db)
    h.db.set_rpc_data("pur_save_order", {"status": "ok", "order_id": ORDER})
    r = h.client.post("/api/purchasing/orders", json={**BODY, "freight_cents": 500}, headers=h.admin)
    assert r.status_code == 201 and r.json()["data"]["id"] == ORDER and r.json()["data"]["lines"] == []
    name, params = h.db.rpc_calls[-1]
    row = params["p_row"]
    assert name == "pur_save_order" and params["p_org"] == ORG_A and params["p_order_id"] is None
    assert row["supplier_name"] == "Forn" and row["party_id"] == PARTY and row["freight_cents"] == 500
    assert row["lines"][0]["qty"] == "10.000" and isinstance(row["lines"][0]["unit_cost_cents"], int)


def test_a_supplier_of_another_org_or_archived_is_a_422_before_any_rpc(h):
    seed_party(h.db, org=ORG_B)
    assert h.client.post("/api/purchasing/orders", json=BODY, headers=h.admin).json()["error"]["code"] == "fornecedor_invalido"
    seed_party(h.db, org=ORG_A, active=False, pid="66666666-6666-4666-8666-666666666666")
    r = h.client.post("/api/purchasing/orders", json={**BODY, "party_id": "66666666-6666-4666-8666-666666666666"}, headers=h.admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "fornecedor_invalido"
    assert h.db.rpc_calls == []


def test_a_free_text_supplier_needs_a_name(h):
    r = h.client.post("/api/purchasing/orders", json={"warehouse_id": WH1, "lines": [LINE]}, headers=h.admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "fornecedor_invalido"


def test_without_the_parties_organ_a_party_id_is_refused_and_the_name_is_used(purchasing_schema_cache):
    bare = build_harness(PurchasingConfig(schema=CFG.schema, with_parties=False))
    assert bare.client.post("/api/purchasing/orders", json=BODY, headers=bare.admin).status_code == 422
    seed_order(bare.db)
    bare.db.set_rpc_data("pur_save_order", {"status": "ok", "order_id": ORDER})
    r = bare.client.post("/api/purchasing/orders", json={"supplier_name": " Avulso ", "warehouse_id": WH1, "lines": [LINE]}, headers=bare.admin)
    assert r.status_code == 201 and bare.db.rpc_calls[-1][1]["p_row"]["supplier_name"] == "Avulso"


@pytest.mark.parametrize(
    "code,status",
    [
        ("pedido_nao_editavel", 409), ("transicao_invalida", 409), ("pedido_com_recebimento", 409), ("pedido_nao_aprovado", 409),
        ("recebimento_excede_pedido", 409), ("sem_linhas", 422), ("desconto_excede", 422), ("item_obrigatorio", 422),
        ("deposito_invalido", 422), ("pedido_inexistente", 404),
    ],
)
def test_rpc_refusals_map_to_the_right_http_status(h, code, status):
    seed_party(h.db)
    h.db.set_rpc_data("pur_save_order", {"status": "refused", "code": code})
    r = h.client.put(f"/api/purchasing/orders/{ORDER}", json=BODY, headers=h.admin)
    assert r.status_code == status
    if status != 404:
        assert r.json()["error"]["code"] == code


def test_an_unknown_refusal_code_is_loud_not_swallowed(h):
    seed_party(h.db)
    h.db.set_rpc_data("pur_save_order", {"status": "refused", "code": "made_up"})
    with pytest.raises(RuntimeError, match="unknown refusal code"):
        h.client.put(f"/api/purchasing/orders/{ORDER}", json=BODY, headers=h.admin)


def test_an_unexpected_rpc_payload_is_loud(h):
    seed_party(h.db)
    h.db.set_rpc_data("pur_save_order", {"oops": True})
    with pytest.raises(RuntimeError, match="unexpected payload"):
        h.client.put(f"/api/purchasing/orders/{ORDER}", json=BODY, headers=h.admin)


# ── read / org isolation ──────────────────────────────────────────────────────


def test_orders_of_another_org_are_invisible(h):
    seed_order(h.db, org=ORG_B)
    assert h.client.get(f"/api/purchasing/orders/{ORDER}", headers=h.as_("user")).status_code == 404
    assert h.client.get("/api/purchasing/orders", headers=h.as_("user")).json()["data"] == []
    assert h.client.get(f"/api/purchasing/orders/{ORDER}", headers=h.as_("org-b-admin")).status_code == 200
    assert Scope(h.db, CFG, ORG_A).find("orders", ORDER) is None and Scope(h.db, CFG, ORG_B).find("orders", ORDER)["id"] == ORDER


def test_the_order_detail_carries_lines_in_order_and_filters_validate(h):
    seed_order(h.db)
    seed_line(h.db, "77777777-7777-4777-8777-777777777772", no=2)
    seed_line(h.db, "77777777-7777-4777-8777-777777777771", no=1)
    data = h.client.get(f"/api/purchasing/orders/{ORDER}", headers=h.as_("user")).json()["data"]
    assert [l["line_no"] for l in data["lines"]] == [1, 2] and data["receipts"] == []
    assert h.client.get("/api/purchasing/orders?status=bogus", headers=h.as_("user")).status_code == 422
    assert len(h.client.get("/api/purchasing/orders?status=approved&q=forn", headers=h.as_("user")).json()["data"]) == 1
    assert h.client.get("/api/purchasing/orders?status=draft", headers=h.as_("user")).json()["data"] == []
    assert len(h.client.get("/api/purchasing/orders?q=1", headers=h.as_("user")).json()["data"]) == 1  # by number


# ── settings + the approval rule ──────────────────────────────────────────────


def put_threshold(db, cents, *, org=ORG_A, changed_at=None, previous=None):
    """The state `pur_set_threshold` leaves behind (the RPC itself is proven on a real Postgres)."""
    db.table("pur_settings").insert({
        "org_id": org, "approval_threshold_cents": cents, "previous_threshold_cents": previous, "threshold_changed_at": changed_at,
    }).execute()


def test_settings_default_then_read(h):
    s = Scope(h.db, CFG, ORG_A)
    assert settings.get_settings(s) == {"approval_threshold_cents": None, "persisted": False, "threshold_changed_at": None, "cooldown_until": None}
    put_threshold(h.db, 90_000, changed_at="2026-10-14T12:00:00+00:00")
    got = h.client.get("/api/purchasing/settings", headers=h.as_("user")).json()["data"]
    assert got["approval_threshold_cents"] == 90000 and got["is_approver"] is False and "approve_permission" not in got
    assert got["cooldown_until"] == "2026-10-14T12:10:00+00:00"
    assert h.client.get("/api/purchasing/settings", headers=h.as_("approver")).json()["data"]["is_approver"] is True


def test_changing_the_threshold_goes_through_the_audited_rpc_and_needs_an_approver(h):
    h.db.set_rpc_data("pur_set_threshold", {"status": "ok"})
    r = h.client.put("/api/purchasing/settings", json={"approval_threshold_cents": 500_00}, headers=h.as_("approver"))
    assert r.status_code == 200
    name, params = h.db.rpc_calls[-1]
    assert name == "pur_set_threshold" and params == {"p_org": ORG_A, "p_user": ROLES["approver"]["uid"], "p_cents": 50000}
    assert h.client.put("/api/purchasing/settings", json={"approval_threshold_cents": None}, headers=h.as_("admin-approver")).status_code == 200
    assert h.db.rpc_calls[-1][1]["p_cents"] is None
    assert h.client.put("/api/purchasing/settings", json={"approval_threshold_cents": -1}, headers=h.as_("approver")).status_code == 422


@pytest.mark.parametrize("role", ["user", "admin", "org-b-admin", "cross-org-approver", "cross-org-admin-approver"])
def test_only_an_approver_of_THIS_org_may_change_the_threshold(h, role):
    """An org admin who is not an approver, or an approver of another org only, is refused -- before any RPC."""
    r = h.client.put("/api/purchasing/settings", json={"approval_threshold_cents": 10**9}, headers=h.as_(role))
    assert r.status_code == 403 and r.json()["error"]["code"] == "sem_permissao_limite" and h.db.rpc_calls == []


def test_approver_management_is_admin_only_audited_and_org_scoped(h):
    h.db.set_rpc_data("pur_set_approver", {"status": "ok"})
    r = h.client.post("/api/purchasing/approvers", json={"user_id": ID}, headers=h.admin)
    assert r.status_code == 201
    assert h.db.rpc_calls[-1] == ("pur_set_approver", {"p_org": ORG_A, "p_actor": ROLES["admin"]["uid"], "p_user": ID, "p_grant": True})
    assert h.client.delete(f"/api/purchasing/approvers/{ID}", headers=h.admin).status_code == 200
    assert h.db.rpc_calls[-1][1]["p_grant"] is False and h.db.rpc_calls[-1][1]["p_org"] == ORG_A
    listed = h.client.get("/api/purchasing/approvers", headers=h.admin).json()["data"]
    assert {a["user_id"] for a in listed} == {ROLES["approver"]["uid"], ROLES["admin-approver"]["uid"]}  # org A only; B's grants invisible
    assert h.client.post("/api/purchasing/approvers", json={"user_id": ID, "org_id": ORG_B}, headers=h.admin).status_code == 422
    assert h.client.post("/api/purchasing/approvers", json={"user_id": "nope"}, headers=h.admin).status_code == 422


def _approve(h, role):
    h.db.set_rpc_data("pur_transition", {"status": "ok", "order_id": ORDER})
    return h.client.post(f"/api/purchasing/orders/{ORDER}/approve", headers=h.as_(role))


def test_staff_without_the_permission_cannot_approve(h):
    seed_order(h.db, status="draft", total=100)
    r = _approve(h, "user")
    assert r.status_code == 403 and r.json()["error"]["code"] == "sem_permissao_aprovar" and h.db.rpc_calls == []


@pytest.mark.parametrize("role", ["admin", "approver", "admin-approver"])
def test_no_threshold_means_an_approver_or_admin_approves_any_value(h, role):
    seed_order(h.db, status="draft", total=999_999_999)
    assert _approve(h, role).status_code == 200
    assert h.db.rpc_calls[-1][1]["p_action"] == "approve" and h.db.rpc_calls[-1][1]["p_user"]


@pytest.mark.parametrize(
    "role,total,expected",
    [
        ("admin", 50_000, 200),           # at the threshold: not above
        ("admin", 50_001, 403),           # above: an admin WITHOUT the grant is refused
        ("approver", 50_001, 200),        # above: the grant holder approves, admin or not
        ("admin-approver", 50_001, 200),
        ("user", 100, 403),
    ],
)
def test_above_the_threshold_only_a_permission_holder_approves(h, role, total, expected):
    seed_order(h.db, status="draft", total=total)
    put_threshold(h.db, 50_000)
    r = _approve(h, role)
    assert r.status_code == expected
    if expected == 403:
        assert r.json()["error"]["code"] in {"aprovacao_acima_do_limite", "sem_permissao_aprovar"}


@pytest.mark.parametrize("role", ["cross-org-approver", "cross-org-admin-approver"])
def test_a_grant_in_another_org_never_approves_here(h, role):
    """B3: the approver list is per org -- being an approver in org B grants nothing in org A (the global-permission hole)."""
    seed_order(h.db, status="draft", total=100)
    put_threshold(h.db, 50)
    r = _approve(h, role)
    if role == "cross-org-approver":
        assert r.status_code == 403 and r.json()["error"]["code"] == "sem_permissao_aprovar" and h.db.rpc_calls == []
    else:  # an org-A admin may approve below the limit by role, but ABOVE it needs an org-A approver
        assert r.status_code == 403 and r.json()["error"]["code"] == "aprovacao_acima_do_limite" and h.db.rpc_calls == []


def test_the_rpc_is_told_whether_the_actor_may_exceed_the_limit(h):
    seed_order(h.db, status="draft", total=100)
    _approve(h, "approver")
    assert h.db.rpc_calls[-1][1]["p_actor_can_exceed"] is True
    _approve(h, "admin")
    assert h.db.rpc_calls[-1][1]["p_actor_can_exceed"] is False


@pytest.mark.parametrize("code,status", [("aprovacao_acima_do_limite", 403), ("limite_em_carencia", 409)])
def test_the_rpcs_limit_and_cooldown_refusals_reach_the_caller(h, code, status):
    seed_order(h.db, status="draft", total=100)
    h.db.set_rpc_data("pur_transition", {"status": "refused", "code": code})
    r = h.client.post(f"/api/purchasing/orders/{ORDER}/approve", headers=h.as_("approver"))
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_a_host_can_let_org_admins_approve_above_the_threshold(purchasing_schema_cache):
    h = build_harness(PurchasingConfig(schema=CFG.schema, admin_approves_above_threshold=True))
    seed_order(h.db, status="draft", total=50_001)
    put_threshold(h.db, 50_000)
    h.db.set_rpc_data("pur_transition", {"status": "ok", "order_id": ORDER})
    assert h.client.post(f"/api/purchasing/orders/{ORDER}/approve", headers=h.as_("admin")).status_code == 200
    assert h.db.rpc_calls[-1][1]["p_actor_can_exceed"] is True
    assert h.client.post(f"/api/purchasing/orders/{ORDER}/approve", headers=h.as_("user")).status_code == 403


def test_approving_an_order_of_another_org_is_a_404(h):
    seed_order(h.db, org=ORG_B, status="draft")
    assert _approve(h, "admin").status_code == 404 and h.db.rpc_calls == []


def test_send_and_cancel_go_through_the_transition_rpc_with_the_actor_and_reason(h):
    seed_order(h.db, status="approved")
    h.db.set_rpc_data("pur_transition", {"status": "ok", "order_id": ORDER})
    assert h.client.post(f"/api/purchasing/orders/{ORDER}/send", headers=h.admin).status_code == 200
    assert h.db.rpc_calls[-1][1]["p_action"] == "send"
    r = h.client.post(f"/api/purchasing/orders/{ORDER}/cancel", json={"reason": "duplicado"}, headers=h.admin)
    assert r.status_code == 200 and h.db.rpc_calls[-1][1]["p_reason"] == "duplicado"
    h.db.set_rpc_data("pur_transition", {"status": "refused", "code": "pedido_com_recebimento"})
    assert h.client.post(f"/api/purchasing/orders/{ORDER}/cancel", json={}, headers=h.admin).status_code == 409


def test_check_can_approve_is_pure_over_flags(s):
    order = {"total_cents": 10}
    orders.check_can_approve(s, order, is_admin=True, can_approve=False, threshold=None)
    orders.check_can_approve(s, order, is_admin=False, can_approve=True, threshold=5)
    with pytest.raises(Exception) as exc:
        orders.check_can_approve(s, order, is_admin=True, can_approve=False, threshold=5)
    assert exc.value.status_code == 403 and exc.value.code == "aprovacao_acima_do_limite"
