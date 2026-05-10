"""
Router tests for sellout — three submission modes + listing + review.

Phase 1 of `adconnect-test-conftest-distributor-binding` retired this
file's standalone `db_and_client` fixture; tests now consume the shared
`client` fixture and bind per-test via `bind_adconnect_user(...)`.
"""
from __future__ import annotations

import pytest

from tests.conftest import bind_adconnect_user


def _make_token(payload: dict) -> str:
    """Mint a test JWT. Production auth runs through the seed's
    `make_get_current_user` factory (Supabase-backed); the `client`
    fixture's mock IGNORES token content — the binding via
    `bind_adconnect_user(...)` is the actual control surface."""
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

    Tests still call `db.set_table_data(...)` / `db.set_sequential_responses(...)`
    and `tc.post(...)` directly. This shim unwraps the `AuthClient`'s
    underlying TestClient + mock supabase so the existing test bodies stay
    intact. Per-test `bind_adconnect_user(db, role=..., distributor_id=...,
    org_id="org-test")` controls the resolved user.
    """
    return client.raw(), client.mock_supabase


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_submit_estruturado_inserts_row(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    payload = {
        "distributor_id": "dist-001",
        "valor_total": 1500.0,
        "quantidade_itens": 12,
        "periodo": "2026-04",
        "observacoes": "abril",
    }
    res = tc.post("/sellout/submit", json=payload, headers=_auth_headers(_distributor_token()))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["submission_mode"] == "estruturado"
    assert body["status"] == "pendente"
    inserts = db.table("relatorios_sellout").inserted_payloads
    assert len(inserts) == 1
    assert inserts[0]["distributor_id"] == "dist-001"
    assert inserts[0]["valor_total"] == 1500.0
    assert inserts[0]["org_id"] == "org-test"


def test_upload_nfe_parses_and_inserts(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">'
        '<NFe><infNFe Id="NFe35200612345678000190550010000123451123456789">'
        '<dest><CNPJ>11222333000181</CNPJ></dest>'
        '<det><prod><cProd>X</cProd><xProd>Item</xProd>'
        '<qCom>2.0</qCom><vUnCom>50.0</vUnCom><vProd>100.0</vProd></prod></det>'
        '<total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>'
        '</infNFe></NFe></nfeProc>'
    ).encode("utf-8")

    res = tc.post(
        "/sellout/upload-nfe",
        data={"distributor_id": "dist-001", "periodo": "2026-04"},
        files={"file": ("sellout.xml", xml, "application/xml")},
        headers=_auth_headers(_distributor_token()),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["submission_mode"] == "nfe_xml"
    assert body["cnpj_cliente_final"] == "11222333000181"
    assert body["valor_total"] == 100.0
    assert body["nfe_chave"] == "35200612345678000190550010000123451123456789"
    inserts = db.table("relatorios_sellout").inserted_payloads
    assert inserts[0]["nfe_xml_url"]


def test_upload_attachment_stores_url(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    res = tc.post(
        "/sellout/upload-attachment",
        data={"distributor_id": "dist-001"},
        files={"file": ("relatorio.xlsx", b"binarycontent", "application/vnd.openxmlformats")},
        headers=_auth_headers(_distributor_token()),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["submission_mode"] == "attachment"
    assert body["attachment_url"]
    inserts = db.table("relatorios_sellout").inserted_payloads
    assert inserts[0]["distributor_id"] == "dist-001"


def test_list_reports_distributor_scoped(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    db.set_table_data("relatorios_sellout", [
        {"id": "r1", "distributor_id": "dist-001", "submission_mode": "estruturado", "status": "pendente"},
    ])
    res = tc.get("/sellout/list", headers=_auth_headers(_distributor_token()))
    assert res.status_code == 200
    assert res.json()["data"][0]["id"] == "r1"


def test_review_writes_status(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="admin", distributor_id=None, org_id="org-test")
    db.set_sequential_responses(
        "relatorios_sellout",
        [type("R", (), {"data": [
            {"id": "r1", "distributor_id": "dist-001", "submission_mode": "estruturado",
             "valor_total": 100.0, "quantidade_itens": 1, "items_json": [],
             "status": "aprovado", "org_id": "org-test"},
        ]})()],
    )
    res = tc.patch(
        "/sellout/r1/review",
        json={"status": "aprovado", "review_notes": "ok"},
        headers=_auth_headers(_admin_token()),
    )
    assert res.status_code == 200, res.text
    updates = db.table("relatorios_sellout").updated_payloads
    assert len(updates) == 1
    assert updates[0]["status"] == "aprovado"
    assert updates[0]["review_notes"] == "ok"


def test_review_rejects_for_non_admin(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    res = tc.patch(
        "/sellout/r1/review",
        json={"status": "aprovado"},
        headers=_auth_headers(_distributor_token()),
    )
    assert res.status_code == 403


def test_submit_requires_auth(db_and_client) -> None:
    tc, _ = db_and_client
    res = tc.post("/sellout/submit", json={"distributor_id": "x", "valor_total": 1, "quantidade_itens": 1})
    assert res.status_code == 401
