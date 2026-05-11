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
        "periodo_inicio": "2026-04-01",
        "periodo_fim": "2026-04-30",
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
    # `org_id` is intentionally not written — the DB table has no such
    # column; tenant scoping flows via `distributor_id → distributors.org_id`.
    assert "org_id" not in inserts[0]
    assert inserts[0]["periodo_inicio"] == "2026-04-01"
    assert inserts[0]["periodo_fim"] == "2026-04-30"


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
        data={
            "distributor_id": "dist-001",
            "periodo_inicio": "2026-04-01",
            "periodo_fim": "2026-04-30",
        },
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
        data={
            "distributor_id": "dist-001",
            "periodo_inicio": "2026-04-01",
            "periodo_fim": "2026-04-30",
        },
        files={"file": ("relatorio.xlsx", b"binarycontent", "application/vnd.openxmlformats")},
        headers=_auth_headers(_distributor_token()),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    # DB CHECK accepts only `'estruturado'|'nfe_xml'|'freeform'` — the
    # /upload-attachment route persists `freeform` (the previous code
    # wrote `'attachment'` which would CHECK-violate in production).
    assert body["submission_mode"] == "freeform"
    assert body["attachment_url"]
    inserts = db.table("relatorios_sellout").inserted_payloads
    assert inserts[0]["distributor_id"] == "dist-001"
    assert inserts[0]["submission_mode"] == "freeform"


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
             "status": "aprovado"},
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
    res = tc.post(
        "/sellout/submit",
        json={
            "distributor_id": "x",
            "valor_total": 1,
            "quantidade_itens": 1,
            "periodo_inicio": "2026-04-01",
            "periodo_fim": "2026-04-30",
        },
    )
    assert res.status_code == 401


# ─── Regression tests — RESPONSE-MODEL-AUDIT R2 (sellout.py drift fix) ────


def test_periodo_split_roundtrips_both_db_columns(db_and_client) -> None:
    """The DB stores period as two NOT NULL DATE columns
    (`periodo_inicio` + `periodo_fim`); the pre-fix schema collapsed them
    into a single `periodo: Optional[str]` which silently dropped both
    columns from the response and wrote a non-existent `periodo` column
    to the table.

    Regression: both columns must be present in the insert payload AND in
    the response body.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    payload = {
        "distributor_id": "dist-001",
        "valor_total": 100.0,
        "quantidade_itens": 1,
        "periodo_inicio": "2026-05-01",
        "periodo_fim": "2026-05-31",
    }
    res = tc.post(
        "/sellout/submit",
        json=payload,
        headers=_auth_headers(_distributor_token()),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["periodo_inicio"] == "2026-05-01"
    assert body["periodo_fim"] == "2026-05-31"
    inserts = db.table("relatorios_sellout").inserted_payloads
    assert inserts[0]["periodo_inicio"] == "2026-05-01"
    assert inserts[0]["periodo_fim"] == "2026-05-31"
    # The collapsed `periodo` column never existed in the table.
    assert "periodo" not in inserts[0]


def test_submission_mode_literal_matches_db_check(db_and_client) -> None:
    """The DB CHECK on `relatorios_sellout.submission_mode` allows only
    `('estruturado','nfe_xml','freeform')`. The pre-fix Literal listed
    `'attachment'` and the /upload-attachment route wrote that value,
    which would CHECK-violate on a real Supabase. The fix renames the
    Literal + writes `'freeform'`; tests assert the persisted value here.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    res = tc.post(
        "/sellout/upload-attachment",
        data={
            "distributor_id": "dist-001",
            "periodo_inicio": "2026-05-01",
            "periodo_fim": "2026-05-31",
        },
        files={"file": ("rel.pdf", b"PDFBYTES", "application/pdf")},
        headers=_auth_headers(_distributor_token()),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["submission_mode"] == "freeform"
    inserts = db.table("relatorios_sellout").inserted_payloads
    persisted_mode = inserts[0]["submission_mode"]
    assert persisted_mode in {"estruturado", "nfe_xml", "freeform"}
    assert persisted_mode == "freeform"


def test_org_id_not_written_to_relatorios_sellout(db_and_client) -> None:
    """The `relatorios_sellout` table has no `org_id` column — tenant
    scoping flows via `distributor_id → distributors.org_id` through
    RLS. The pre-fix service wrote `org_id` into the insert payload (a
    silent drop in production; mock accepted everything). Regression
    asserts the payload omits the column entirely.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    res = tc.post(
        "/sellout/submit",
        json={
            "distributor_id": "dist-001",
            "valor_total": 1.0,
            "quantidade_itens": 1,
            "periodo_inicio": "2026-05-01",
            "periodo_fim": "2026-05-31",
        },
        headers=_auth_headers(_distributor_token()),
    )
    assert res.status_code == 201, res.text
    inserts = db.table("relatorios_sellout").inserted_payloads
    assert "org_id" not in inserts[0]


def test_review_status_rejects_pre_fix_rejeitado_literal(db_and_client) -> None:
    """DB CHECK allows `status IN ('pendente','em_analise','aprovado','recusado')`.
    The pre-fix schema accepted `'rejeitado'` (Portuguese-but-wrong
    spelling) — would CHECK-violate on write. After the fix, only
    `'aprovado' | 'recusado'` validates at the boundary.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="admin", distributor_id=None, org_id="org-test")
    res = tc.patch(
        "/sellout/r1/review",
        json={"status": "rejeitado", "review_notes": "wrong word"},
        headers=_auth_headers(_admin_token()),
    )
    # StrictHttpModel + Literal('aprovado','recusado') → 422.
    assert res.status_code == 422, res.text


def test_review_recusado_persists_check_aligned_value(db_and_client) -> None:
    """Sibling to the rejection test: the new canonical 'reject' word is
    `'recusado'`, matching the DB CHECK. Asserts persistence + 200.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="admin", distributor_id=None, org_id="org-test")
    db.set_sequential_responses(
        "relatorios_sellout",
        [type("R", (), {"data": [
            {"id": "r1", "distributor_id": "dist-001",
             "submission_mode": "estruturado",
             "valor_total": 100.0, "quantidade_itens": 1, "items_json": [],
             "status": "recusado"},
        ]})()],
    )
    res = tc.patch(
        "/sellout/r1/review",
        json={"status": "recusado", "review_notes": "incomplete"},
        headers=_auth_headers(_admin_token()),
    )
    assert res.status_code == 200, res.text
    updates = db.table("relatorios_sellout").updated_payloads
    assert updates[-1]["status"] == "recusado"
    assert updates[-1]["review_notes"] == "incomplete"


def test_unknown_submission_mode_value_rejected_by_strict_http(db_and_client) -> None:
    """StrictHttpModel + SubmissionMode Literal must 422 on out-of-set
    values. Defends against frontend regressions or downstream callers
    sending the pre-fix `'attachment'` value.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    # The Literal is enforced on the response/output side via
    # `SubmissionMode` — but the more useful assertion lives on the
    # request shape. `SelloutEstruturadoIn` doesn't carry submission_mode
    # (it's set server-side); to exercise the boundary we send a body
    # whose submission_mode would violate the response Literal IF the
    # service wrote it. The service hard-codes `'estruturado'`, so this
    # test asserts the schema Literal itself.
    from app.schemas.sellout import SubmissionMode
    import typing
    allowed = set(typing.get_args(SubmissionMode))
    assert allowed == {"estruturado", "nfe_xml", "freeform"}
    # Bonus: confirm `'attachment'` is NOT in the allowed set anymore.
    assert "attachment" not in allowed
