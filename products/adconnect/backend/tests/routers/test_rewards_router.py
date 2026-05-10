"""
Router tests for rewards — ledger, rules, redemption request + processing.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)


def _make_token(payload: dict) -> str:
    """Mint a test JWT (header-shape only — MockSupabaseClient.auth.get_user
    is patched in db_and_client to ignore token content)."""
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
def db_and_client():
    mock_sb = MockSupabaseClient(validate_schema=False, schema="adconnect")
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="org-test")
    ))
    with patch("app.database._db.get_client", return_value=mock_sb), \
         patch("app.database._db.get_core_client", return_value=mock_sb), \
         patch("app.database._db.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc, mock_sb


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_ledger_returns_summary_for_distributor(db_and_client) -> None:
    tc, db = db_and_client
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
    tc, _ = db_and_client
    payload = {
        "distributor_id": "dist-001",
        "tipo": "cashback",
        "valor": 0.0,
    }
    res = tc.post("/rewards/redeem", json=payload, headers=_auth(_distributor_token()))
    assert res.status_code == 400


def test_process_redemption_admin_only(db_and_client) -> None:
    tc, _ = db_and_client
    res = tc.patch(
        "/rewards/redeem/some-id/process",
        json={"status": "aprovado"},
        headers=_auth(_distributor_token()),
    )
    assert res.status_code == 403


def test_process_redemption_marks_paid(db_and_client) -> None:
    tc, db = db_and_client
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
