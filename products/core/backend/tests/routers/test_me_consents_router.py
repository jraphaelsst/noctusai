"""Router-level tests for /api/me/consents (Phase 19 X6)."""
from unittest.mock import patch

import pytest

from noctusai_lib.domain.ai.consent import (
    register_feature,
    reset_catalog_for_test,
)


@pytest.fixture(autouse=True)
def _isolate_catalog():
    reset_catalog_for_test()
    register_feature(
        "erp.lead_score",
        title="Pontuação de leads",
        rationale="Avalia perfis automaticamente para priorização.",
        product="erp",
    )
    register_feature(
        "pf.categorize",
        title="Categorização de transações",
        rationale="Sugere categorias com base em descrições.",
        product="pf",
        default_granted=True,
    )
    yield
    reset_catalog_for_test()


class TestListMyConsents:
    def test_returns_catalog_with_decisions_merged(self, client):
        # No stored decisions → both features show their default state.
        client._mock_supabase.set_table_data("ai_consent", [])
        resp = client.get("/api/me/consents")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert len(body["items"]) == 2
        keys = {row["key"] for row in body["items"]}
        assert keys == {"erp.lead_score", "pf.categorize"}
        # pf.categorize default_granted=True → granted; erp.lead_score → not.
        granted = {row["key"]: row["granted"] for row in body["items"]}
        assert granted == {"erp.lead_score": False, "pf.categorize": True}
        # Two undecided → pending = 2.
        assert body["pending"] == 2

    def test_stored_decision_overrides_default(self, client):
        client._mock_supabase.set_table_data("ai_consent", [
            {
                "feature_key": "pf.categorize", "granted": False,
                "granted_at": None, "revoked_at": "2026-04-26T00:00:00Z",
                "rationale_pt": "...",
            },
        ])
        resp = client.get("/api/me/consents")
        body = resp.json()["data"]
        pf_row = next(r for r in body["items"] if r["key"] == "pf.categorize")
        assert pf_row["granted"] is False
        assert pf_row["decision_recorded"] is True
        # erp.lead_score still pending; pf.categorize now decided.
        assert body["pending"] == 1


class TestUpsertMyConsent:
    def test_grants_a_known_feature(self, client):
        client._mock_supabase.set_table_data("ai_consent", [{
            "id": "row-1", "feature_key": "erp.lead_score", "granted": True,
            "user_id": "test-user-123",
        }])
        resp = client.put(
            "/api/me/consents/erp.lead_score",
            json={"granted": True},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["granted"] is True

    def test_revokes_with_default_granted(self, client):
        client._mock_supabase.set_table_data("ai_consent", [{
            "id": "row-2", "feature_key": "pf.categorize", "granted": False,
        }])
        resp = client.put(
            "/api/me/consents/pf.categorize",
            json={"granted": False},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["granted"] is False

    def test_unknown_feature_returns_404(self, client):
        resp = client.put(
            "/api/me/consents/unknown.feature",
            json={"granted": True},
        )
        assert resp.status_code == 404

    def test_non_toggleable_feature_returns_403(self, client):
        # Register a locked-on infrastructure feature alongside the fixture's
        # toggleable ones. Toggle attempts must fail with 403.
        register_feature(
            "erp.embeddings",
            title="Embeddings",
            rationale="Infraestrutura de busca semântica.",
            product="erp",
            toggleable=False,
        )
        resp = client.put(
            "/api/me/consents/erp.embeddings",
            json={"granted": False},
        )
        assert resp.status_code == 403
        # Framework may wrap HTTPException's detail under .detail OR shape
        # AppException responses with .message — accept either.
        body = resp.json()
        body_text = str(body).lower()
        assert "infraestrutura" in body_text
