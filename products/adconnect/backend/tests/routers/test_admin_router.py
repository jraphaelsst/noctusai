"""
Router tests for the brand-admin V1 surface (Phase 6).

Auth gating uses the seed's `make_require_role`, which resolves the role
via `_resolve_role(user) → user.user_metadata["role"]`. To gate as admin
in tests, we mint a `MockUser(role="admin")` and patch the mock's
`auth.get_user` to return it. Tests use a local fixture (rather than the
shared `client` fixture) so the role can vary per test.

The MockSupabaseClient's `.eq(...)` / `.in_(...)` are validator-only no-ops
— we seed only the rows each query expects to return. Service-level filters
are exercised in `tests/services/test_admin_service.py`.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)


ORG_ID = "org-admin-test-123"
DIST_A = "11111111-1111-1111-1111-111111111111"
DIST_B = "22222222-2222-2222-2222-222222222222"


def _make_token(payload: dict[str, Any]) -> str:
    """Mint a header-shape JWT (token content is ignored — `auth.get_user`
    is patched to return a fixed MockUser regardless)."""
    import jwt
    from datetime import datetime, timedelta, timezone

    from app.config import settings

    body = dict(payload)
    body["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def _bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token({'sub': f'user-{role}', 'role': role, 'orgId': ORG_ID})}"}


def _make_client(role: str) -> tuple[TestClient, MockSupabaseClient]:
    """Build a TestClient + MockSupabaseClient pair where the auth resolution
    yields a user with the given product-native role."""
    mock_sb = MockSupabaseClient(validate_schema=False, schema="adconnect")
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(role=role, org_id=ORG_ID))
    )
    return mock_sb


@pytest.fixture
def admin_client():
    mock_sb = _make_client("admin")
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


@pytest.fixture
def customer_client():
    mock_sb = _make_client("customer")
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


# ---------------------------------------------------------------------------
# Auth boundary
# ---------------------------------------------------------------------------


class TestAdminAuthBoundary:
    def test_dashboard_unauthenticated_rejected(self, admin_client) -> None:
        tc, _ = admin_client
        r = tc.get("/admin/dashboard")
        assert r.status_code == 401

    def test_dashboard_distributor_user_forbidden(self, customer_client) -> None:
        tc, _ = customer_client
        r = tc.get("/admin/dashboard", headers=_bearer("customer"))
        assert r.status_code == 403

    def test_distributor_list_distributor_user_forbidden(self, customer_client) -> None:
        tc, _ = customer_client
        r = tc.get("/admin/distributors", headers=_bearer("customer"))
        assert r.status_code == 403

    def test_create_distributor_distributor_user_forbidden(self, customer_client) -> None:
        tc, _ = customer_client
        r = tc.post(
            "/admin/distributors",
            json={"cnpj": "00.000.000/0001-00", "nome": "X"},
            headers=_bearer("customer"),
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/dashboard
# ---------------------------------------------------------------------------


class TestDashboard:
    def test_dashboard_returns_aggregates(self, admin_client) -> None:
        tc, db = admin_client
        # MockSupabaseClient applies .eq() predicates at SELECT — seeded rows
        # MUST carry org_id matching the admin's MockUser(org_id=ORG_ID) so
        # the service's `.eq("org_id", org_id)` filter returns both rows.
        # Pre-predicate-fix the rows leaked through unfiltered.
        db.set_table_data("distributors", [
            {"id": DIST_A, "org_id": ORG_ID, "status": "ativo"},
            {"id": DIST_B, "org_id": ORG_ID, "status": "pendente"},
        ])
        db.set_table_data("relatorios_sellout", [
            {"id": "s1", "org_id": ORG_ID, "status": "pendente"},
            {"id": "s2", "org_id": ORG_ID, "status": "aprovado"},
        ])
        r = tc.get("/admin/dashboard", headers=_bearer("admin"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["distributors"]["total"] == 2
        assert body["distributors"]["by_status"]["ativo"] == 1
        assert body["distributors"]["by_status"]["pendente"] == 1
        assert body["sellout"]["total"] == 2


# ---------------------------------------------------------------------------
# GET /admin/distributors
# ---------------------------------------------------------------------------


class TestDistributorList:
    def test_list_with_metrics(self, admin_client) -> None:
        tc, db = admin_client
        db.set_table_data("distributors", [
            {"id": DIST_A, "org_id": ORG_ID, "cnpj": "11.111.111/0001-11",
             "nome": "Distribuidor A", "status": "ativo", "tier": "STARTER"},
        ])
        db.set_table_data("pedidos", [
            {"id": "p1", "distributor_id": DIST_A, "placed_at": "2026-04-01"},
        ])
        db.set_table_data("recompensas_acumuladas", [
            {"distributor_id": DIST_A, "valor": 75.0, "status": "acumulado"},
        ])
        db.set_table_data("faturas", [
            {"distributor_id": DIST_A, "status": "emitida"},
        ])
        r = tc.get("/admin/distributors", headers=_bearer("admin"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["data"]) == 1
        a = body["data"][0]
        assert a["id"] == DIST_A
        assert a["metrics"]["total_pedidos"] == 1
        assert a["metrics"]["recompensa_balance"] == 75.0
        assert a["metrics"]["invoices_pending"] == 1


# ---------------------------------------------------------------------------
# POST /admin/distributors  +  PATCH /admin/distributors/{id}
# ---------------------------------------------------------------------------


class TestDistributorCreatePatch:
    def test_create_distributor_inserts_row(self, admin_client) -> None:
        tc, db = admin_client
        payload = {
            "cnpj": "33.333.333/0001-33",
            "nome": "Novo Distribuidor",
            "endereco_uf": "SP",
            "tier": "STARTER",
        }
        r = tc.post(
            "/admin/distributors", json=payload, headers=_bearer("admin")
        )
        assert r.status_code == 201, r.text
        # The mock response yields the inserted row + auto id; check insert payload.
        inserts = db.table("distributors").inserted_payloads
        assert len(inserts) == 1
        assert inserts[0]["cnpj"] == "33.333.333/0001-33"
        assert inserts[0]["org_id"] == ORG_ID

    def test_patch_distributor_updates_fields(self, admin_client) -> None:
        tc, db = admin_client
        # Pre-seed sequential response so update().eq().execute() returns a row.
        db.set_sequential_responses(
            "distributors",
            [type("R", (), {
                "data": [{
                    "id": DIST_A, "org_id": ORG_ID,
                    "cnpj": "11.111.111/0001-11", "nome": "Distribuidor A",
                    "status": "suspenso", "tier": "STARTER",
                }]
            })()],
        )
        r = tc.patch(
            f"/admin/distributors/{DIST_A}",
            json={"status": "suspenso"},
            headers=_bearer("admin"),
        )
        assert r.status_code == 200, r.text
        updates = db.table("distributors").updated_payloads
        assert updates[-1]["status"] == "suspenso"
        assert "updated_at" in updates[-1]

    def test_patch_empty_body_rejected(self, admin_client) -> None:
        tc, _ = admin_client
        r = tc.patch(
            f"/admin/distributors/{DIST_A}", json={}, headers=_bearer("admin")
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /admin/sellout/queue
# ---------------------------------------------------------------------------


class TestSelloutQueue:
    def test_queue_returns_only_pending(self, admin_client) -> None:
        tc, db = admin_client
        # MockSupabaseClient applies .eq() predicates at SELECT — seeded rows
        # MUST carry org_id matching the admin's MockUser(org_id=ORG_ID) so
        # the service's `.eq("org_id", org_id)` filter returns them.
        db.set_table_data("relatorios_sellout", [
            {"id": "s1", "org_id": ORG_ID, "status": "pendente"},
            {"id": "s2", "org_id": ORG_ID, "status": "em_analise"},
            {"id": "s3", "org_id": ORG_ID, "status": "aprovado"},
        ])
        r = tc.get("/admin/sellout/queue", headers=_bearer("admin"))
        assert r.status_code == 200, r.text
        statuses = {row["status"] for row in r.json()["data"]}
        assert statuses == {"pendente", "em_analise"}


# ---------------------------------------------------------------------------
# Reward rules CRUD
# ---------------------------------------------------------------------------


class TestRewardRulesCrud:
    def test_list_rules_includes_inactive_for_admin(self, admin_client) -> None:
        tc, db = admin_client
        db.set_table_data("regras_recompensa", [
            {"id": "r1", "org_id": ORG_ID, "ativa": True, "nome": "Active"},
            {"id": "r2", "org_id": ORG_ID, "ativa": False, "nome": "Inactive"},
        ])
        r = tc.get("/admin/reward-rules", headers=_bearer("admin"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["data"]) == 2

    def test_create_rule(self, admin_client) -> None:
        tc, db = admin_client
        payload = {
            "nome": "Cashback 5%",
            "tipo": "cashback_percentual",
            "valor": 5.0,
        }
        r = tc.post(
            "/admin/reward-rules", json=payload, headers=_bearer("admin")
        )
        assert r.status_code == 201, r.text
        inserts = db.table("regras_recompensa").inserted_payloads
        assert len(inserts) == 1
        assert inserts[0]["nome"] == "Cashback 5%"
        assert inserts[0]["org_id"] == ORG_ID

    def test_update_rule(self, admin_client) -> None:
        tc, db = admin_client
        db.set_sequential_responses(
            "regras_recompensa",
            [type("R", (), {
                "data": [{
                    "id": "r1", "org_id": ORG_ID, "ativa": True,
                    "nome": "Updated", "tipo": "cashback_percentual",
                    "valor": 7.5,
                }]
            })()],
        )
        payload = {
            "nome": "Updated",
            "tipo": "cashback_percentual",
            "valor": 7.5,
        }
        r = tc.patch(
            "/admin/reward-rules/r1", json=payload, headers=_bearer("admin")
        )
        assert r.status_code == 200, r.text
        updates = db.table("regras_recompensa").updated_payloads
        assert updates[-1]["nome"] == "Updated"

    def test_delete_rule_soft_deletes(self, admin_client) -> None:
        tc, db = admin_client
        db.set_sequential_responses(
            "regras_recompensa",
            [type("R", (), {
                "data": [{"id": "r1", "ativa": False}]
            })()],
        )
        r = tc.delete(
            "/admin/reward-rules/r1", headers=_bearer("admin")
        )
        assert r.status_code == 204, r.text
        updates = db.table("regras_recompensa").updated_payloads
        assert updates[-1]["ativa"] is False


# ---------------------------------------------------------------------------
# GET /admin/invoices
# ---------------------------------------------------------------------------


class TestAdminInvoices:
    def test_invoices_lists_for_org(self, admin_client) -> None:
        tc, db = admin_client
        db.set_table_data("distributors", [
            {"id": DIST_A, "org_id": ORG_ID},
        ])
        db.set_table_data("faturas", [
            {"id": "f1", "distributor_id": DIST_A, "status": "emitida"},
            {"id": "f2", "distributor_id": DIST_A, "status": "paga"},
        ])
        r = tc.get("/admin/invoices", headers=_bearer("admin"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["data"]) == 2

    def test_invoices_filters_by_status(self, admin_client) -> None:
        tc, db = admin_client
        db.set_table_data("distributors", [
            {"id": DIST_A, "org_id": ORG_ID},
        ])
        db.set_table_data("faturas", [
            {"id": "f1", "distributor_id": DIST_A, "status": "emitida"},
            {"id": "f2", "distributor_id": DIST_A, "status": "paga"},
        ])
        r = tc.get("/admin/invoices?status=emitida", headers=_bearer("admin"))
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["status"] == "emitida"
