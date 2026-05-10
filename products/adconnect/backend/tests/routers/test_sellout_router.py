"""
Router tests for sellout — three submission modes + listing + review.

The custom-JWT auth dep decodes a real JWT, so we mint tokens with the
product's own `create_token` helper (no monkey-patching of our auth code).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import (
    AuthClient,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)


def _make_token(payload: dict) -> str:
    """Mint a test JWT. Production auth runs through the seed's
    `make_get_current_user` factory (Supabase-backed); this helper just
    produces a header-shape-valid token. `MockSupabaseClient.auth.get_user`
    is patched in `db_and_client` fixture to ignore the token content."""
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


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_submit_estruturado_inserts_row(db_and_client) -> None:
    tc, db = db_and_client
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
    db.set_table_data("relatorios_sellout", [
        {"id": "r1", "distributor_id": "dist-001", "submission_mode": "estruturado", "status": "pendente"},
    ])
    res = tc.get("/sellout/list", headers=_auth_headers(_distributor_token()))
    assert res.status_code == 200
    assert res.json()["data"][0]["id"] == "r1"


def test_review_writes_status(db_and_client) -> None:
    tc, db = db_and_client
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
    tc, _ = db_and_client
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
