"""
Router tests for rewards — ledger, rules, redemption request + processing.

Pre-Phase-1 of `adconnect-test-conftest-distributor-binding`: this file
shipped its own `db_and_client` fixture that duplicated the conftest's
patching infrastructure. Phase 1 retires the duplicate; tests now
consume the shared `client` fixture and bind per-test via
`bind_adconnect_user(...)` from the conftest.
"""
from __future__ import annotations

import pytest

from tests.conftest import bind_adconnect_user


def _make_token(payload: dict) -> str:
    """Mint a test JWT (header-shape only — `mock.auth.get_user` ignores
    token content; the binding is the actual control surface)."""
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.config import settings
    body = dict(payload)
    body["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def _admin_token() -> str:
    return _make_token({
        "sub": "user-admin",
        "email": "admin@adconnect.com",
        "role": "admin",
        "orgId": "org-test",
    })


def _distributor_token() -> str:
    return _make_token({
        "sub": "user-distrib",
        "email": "joao@exemplo.com.br",
        "role": "customer",
        "distributorId": "dist-001",
        "orgId": "org-test",
    })


@pytest.fixture
def db_and_client(client):
    """Compat shim — yields (tc, mock_sb) tuple expected by existing tests.

    Tests still use `db.set_table_data(...)` / `db.set_sequential_responses(...)` /
    `tc.get(...)` directly. The new `client` fixture wraps both in an
    AuthClient; we unwrap here for backwards compat.

    Note: the previous standalone fixture used org_id="org-test"; this
    one inherits the conftest default `ORG_ID_BRAND`. Tests that depended
    on the literal "org-test" value re-bind via `bind_adconnect_user(...)`
    explicitly — that's the right shape for AdConnect's auth flow.
    """
    return client.raw(), client.mock_supabase


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_ledger_returns_summary_for_distributor(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    db.set_table_data("recompensas_acumuladas", [
        {"id": "a1", "distributor_id": "dist-001", "tipo": "cashback", "valor": 100.0, "status": "liberado"},
        {"id": "a2", "distributor_id": "dist-001", "tipo": "cashback", "valor": 30.0, "status": "utilizado"},
    ])
    res = tc.get("/rewards/ledger", headers=_auth(_distributor_token()))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 2
    assert body["summary"]["cashbackAvailable"] == 70.0


def test_rules_endpoint_lists_active(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    db.set_table_data("regras_recompensa", [
        {"id": "r1", "org_id": "org-test", "nome": "Cabo 5%", "tipo": "cashback",
         "cashback_pct": 5.0, "ativo": True,
         "aplicavel_categorias": [], "aplicavel_produtos": [], "aplicavel_distribuidores": []},
    ])
    res = tc.get("/rewards/rules", headers=_auth(_distributor_token()))
    assert res.status_code == 200
    body = res.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["nome"] == "Cabo 5%"


def test_redeem_creates_pending_redemption(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    payload = {
        "distributor_id": "dist-001",
        "tipo": "cashback",
        "valor": 50.0,
        "pedido_ref": "ped-1",
    }
    res = tc.post("/rewards/redeem", json=payload, headers=_auth(_distributor_token()))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pendente"
    inserts = db.table("resgates_recompensa").inserted_payloads
    assert len(inserts) == 1
    assert inserts[0]["valor"] == 50.0
    assert inserts[0]["pedido_ref"] == "ped-1"


def test_redeem_rejects_non_positive_amount(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    payload = {
        "distributor_id": "dist-001",
        "tipo": "cashback",
        "valor": 0.0,
    }
    res = tc.post("/rewards/redeem", json=payload, headers=_auth(_distributor_token()))
    assert res.status_code == 400


def test_process_redemption_admin_only(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    res = tc.patch(
        "/rewards/redeem/some-id/process",
        json={"status": "aprovado"},
        headers=_auth(_distributor_token()),
    )
    assert res.status_code == 403


def test_process_redemption_marks_paid(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="admin", distributor_id=None, org_id="org-test")
    db.set_sequential_responses(
        "resgates_recompensa",
        [type("R", (), {"data": [
            {"id": "rd1", "distributor_id": "dist-001", "tipo": "cashback",
             "valor": 50.0, "status": "pago"},
        ]})()],
    )
    res = tc.patch(
        "/rewards/redeem/rd1/process",
        json={"status": "pago"},
        headers=_auth(_admin_token()),
    )
    assert res.status_code == 200, res.text
    updates = db.table("resgates_recompensa").updated_payloads
    assert updates[0]["status"] == "pago"
    assert "paid_at" in updates[0]
