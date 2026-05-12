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


_JWT_SECRET = "test-only-decorative-secret"


def _make_token(payload: dict) -> str:
    """Mint a test JWT (header-shape only — `mock.auth.get_user` ignores
    token content; the binding is the actual control surface)."""
    import jwt
    from datetime import datetime, timedelta, timezone
    body = dict(payload)
    body["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(body, _JWT_SECRET, algorithm="HS256")


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
    """Ledger rows must use the CHECK-valid status vocabulary:
    ('acumulado', 'resgatado', 'expirado'). Pre-fix this test seeded
    'liberado'/'utilizado' which the prod CHECK rejects.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    db.set_table_data("recompensas_acumuladas", [
        {"id": "a1", "distributor_id": "dist-001", "tipo": "cashback", "valor": 100.0, "status": "acumulado"},
        {"id": "a2", "distributor_id": "dist-001", "tipo": "cashback", "valor": 30.0, "status": "resgatado"},
    ])
    res = tc.get("/rewards/ledger", headers=_auth(_distributor_token()))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 2
    # cashbackAvailable now = sum(tipo=cashback, status=acumulado) = 100.0.
    # cashbackUsed = sum(tipo=cashback, status=resgatado) = 30.0.
    assert body["summary"]["cashbackAvailable"] == 100.0
    assert body["summary"]["cashbackUsed"] == 30.0


def test_rules_endpoint_lists_active(db_and_client) -> None:
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    db.set_table_data("regras_recompensa", [
        {"id": "r1", "org_id": "org-test", "nome": "Cabo 5%", "tipo": "cashback",
         "valor": 5.0, "ativa": True,
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


def test_redeem_rejects_unknown_field_with_422(db_and_client) -> None:
    """StrictHttpModel migration guard — payloads with unknown keys 422.

    Pre-migration (`pydantic.BaseModel`, `extra="ignore"`) silently dropped
    `bogus_field`. Post-migration (`StrictHttpModel`, `extra="forbid"`) the
    schema rejects with 422 and names the offending `loc`. Defends against
    the silent-drop misroute class (`KB § PATTERNS/pydantic-strict-http.md`).
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    payload = {
        "distributor_id": "dist-001",
        "tipo": "cashback",
        "valor": 50.0,
        "bogus_field": "should-422",
    }
    res = tc.post("/rewards/redeem", json=payload, headers=_auth(_distributor_token()))
    assert res.status_code == 422, res.text
    body = res.json()
    # FastAPI surfaces the offending key name in the `loc` tuple.
    assert any("bogus_field" in str(err.get("loc", "")) for err in body.get("detail", []))


# ---------------------------------------------------------------------------
# Response-model audit regressions — R1 + R3 + R4
# (projects/adco-response-model-rewards-fix/PROJECT.md)
# ---------------------------------------------------------------------------


def test_rules_serializes_real_db_column_names(db_and_client) -> None:
    """R1 — `GET /rewards/rules` returns rows with the REAL DB columns
    (`valor`, `ativa`) intact. Pre-fix, `RewardRulesListOut` held a broken
    `RewardRuleOut` whose Literal `tipo` excluded the DB's CHECK values and
    whose `cashback_pct` / `ativo` field names didn't match the table;
    those rows silently dropped `valor` / `ativa` / `created_at` /
    `updated_at` from the response. Post-fix `RewardRulesListOut` carries
    `list[dict[str, Any]]` so the row passes through verbatim.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    db.set_table_data("regras_recompensa", [
        {
            "id": "r1",
            "org_id": "org-test",
            "nome": "Cabo 5%",
            "tipo": "cashback_percentual",  # real DB CHECK value
            "valor": 5.0,                     # real DB column (was cashback_pct)
            "ativa": True,                    # real DB column (was ativo)
            "aplicavel_categorias": [],
            "aplicavel_produtos": [],
            "aplicavel_distribuidores": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        },
    ])
    res = tc.get("/rewards/rules", headers=_auth(_distributor_token()))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 1
    row = body["data"][0]
    # The four columns that pre-fix were dropped MUST now serialize.
    assert row["valor"] == 5.0
    assert row["ativa"] is True
    assert row["tipo"] == "cashback_percentual"
    assert row["created_at"] == "2026-01-01T00:00:00Z"
    assert row["updated_at"] == "2026-01-02T00:00:00Z"


def test_redemption_response_includes_pre_and_post_migration_columns(db_and_client) -> None:
    """R3 — `RedemptionOut` covers BOTH the original-migration columns
    (`valor_total`, `metodo`, `observacoes`, `created_at`, `processed_at`)
    AND the schema-driven additions landed by migration 003 (`org_id`,
    `tipo`, `valor`, `pedido_ref`, `review_notes`, `reviewed_by`,
    `reviewed_at`, `paid_at`, `requested_at`). The response must not
    silently drop either side.
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="admin", distributor_id=None, org_id="org-test")
    # Seed a row that carries every documented column.
    full_row = {
        "id": "rd-full",
        "org_id": "org-test",
        "distributor_id": "dist-001",
        "tipo": "cashback",
        "valor": 25.0,
        "pedido_ref": "ped-1",
        "status": "pago",
        "review_notes": "ok",
        "reviewed_by": "user-admin",
        "reviewed_at": "2026-01-02T00:00:00Z",
        "paid_at": "2026-01-03T00:00:00Z",
        "requested_at": "2026-01-01T00:00:00Z",
        "requested_by": "user-distrib",
        # original-migration columns
        "valor_total": 25.0,
        "metodo": "reembolso_pix",
        "observacoes": "obs",
        "created_at": "2026-01-01T00:00:00Z",
        "processed_at": "2026-01-03T00:00:00Z",
    }
    # Sequential responses drive the update path: process_redemption issues
    # a single UPDATE and returns the full row back.
    db.set_sequential_responses(
        "resgates_recompensa",
        [type("R", (), {"data": [full_row]})()],
    )
    res = tc.patch(
        "/rewards/redeem/rd-full/process",
        json={"status": "pago"},
        headers=_auth(_admin_token()),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # Every documented field must come through — both halves of the audit fix.
    for key in (
        # post-003 schema fields
        "org_id", "tipo", "valor", "pedido_ref", "review_notes",
        "reviewed_by", "reviewed_at", "paid_at", "requested_at",
        # original-migration fields
        "valor_total", "metodo", "observacoes", "created_at", "processed_at",
    ):
        assert key in body, f"RedemptionOut dropped {key!r}"


def test_ledger_carries_source_relatorio_sellout_id(db_and_client) -> None:
    """R4 — `RewardLedgerEntry.source_relatorio_sellout_id` matches the
    DB column name. Pre-fix the schema field was `source_relatorio_id`,
    so sellout-sourced accruals silently dropped their source-link on
    the response (frontend couldn't link back to the sellout report).
    """
    tc, db = db_and_client
    bind_adconnect_user(db, role="customer", distributor_id="dist-001", org_id="org-test")
    db.set_table_data("recompensas_acumuladas", [
        {
            "id": "led-1",
            "distributor_id": "dist-001",
            "tipo": "cashback",
            "valor": 50.0,
            # CHECK-valid lifecycle (was 'liberado' which the prod
            # CHECK rejects — `recompensas_acumuladas.status` is
            # 'acumulado'/'resgatado'/'expirado').
            "status": "acumulado",
            "source_pedido_id": None,
            "source_relatorio_sellout_id": "rel-001",
        },
    ])
    res = tc.get("/rewards/ledger", headers=_auth(_distributor_token()))
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 1
    row = body["data"][0]
    # The renamed field name must serialize at the new (correct) key.
    assert row["source_relatorio_sellout_id"] == "rel-001"
