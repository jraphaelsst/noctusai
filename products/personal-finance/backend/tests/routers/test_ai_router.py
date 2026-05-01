"""Tests for the Personal Finance AI router (Phase 7 P1 indicators).

PF features registered with consent-gating per `consent-guard-rollout` Phase 5
(2026-04-27): `pf.transaction_categorize` and `pf.recurring_flag` default-grant
True (medium-risk org-internal data). `pf.monthly_narrative` default-grants
False (HIGH-RISK personal financial narrative — opt-in only). The autouse
fixture below pre-seeds grants for all 3 features so happy-path tests run;
`TestConsentGuards` at the end overrides to test revoked + opt-in-only paths.
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _bypass_openai_check():
    with patch("app.services.ai_service.check_openai_configured", return_value=True):
        yield


@pytest.fixture(autouse=True)
def _grant_all_pf_consents(client):
    """Pre-seed `ai_consent` with grants for all 3 PF features so happy-path
    tests can run. `pf.monthly_narrative` is `default_granted=False`
    (opt-in only) — without this, `TestMonthlyNarrative` tests would 412."""
    client._mock_supabase.set_table_data("ai_consent", [
        {
            "feature_key": "pf.transaction_categorize",
            "granted": True, "user_id": "test-user-123",
            "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None,
        },
        {
            "feature_key": "pf.recurring_flag",
            "granted": True, "user_id": "test-user-123",
            "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None,
        },
        {
            "feature_key": "pf.monthly_narrative",
            "granted": True, "user_id": "test-user-123",
            "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None,
        },
    ])


@pytest.fixture
def _stub_persist():
    with patch(
        "app.routers.ai.persist_output",
        side_effect=lambda db, schema, output: {
            **output.to_insert_payload(),
            "id": "ai-out-1",
        },
    ) as p:
        yield p


SAMPLE_TX = {
    "id": "11111111-1111-1111-1111-111111111111",
    "org_id": "test-org-123",
    "conta_id": "c1",
    "categoria_id": None,
    "data": "2026-04-20",
    "valor": 39.90,
    "tipo": "despesa",
    "descricao": "Netflix",
    "comerciante": "NETFLIX BRASIL",
}


class TestCategorizeTransaction:
    def test_persists_classification_and_returns_match_id(self, client, _stub_persist):
        client._mock_supabase.set_table_data("transacoes", SAMPLE_TX)
        client._mock_supabase.set_table_data("categorias", [
            {"id": "cat-1", "nome": "Streaming", "tipo": "despesa"},
        ])
        with patch(
            "app.services.ai_service.categorize_transaction",
            new_callable=AsyncMock,
            return_value={
                "kind": "classification",
                "label": "Streaming",
                "chip": "STREAMING",
                "explanation": "assinatura mensal",
                "confidence": 0.94,
                "score": None,
                "model_version": "gpt-4o-mini",
                "prompt_version": "pf-categorize@v1",
                "matched_categoria_id": "cat-1",
            },
        ):
            resp = client.post(
                "/api/ai/transacoes/11111111-1111-1111-1111-111111111111/categorize"
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["label"] == "Streaming"
        assert data["matched_categoria_id"] == "cat-1"
        assert data["ref_type"] == "transacao"
        _stub_persist.assert_called_once()

    def test_transacao_not_found_returns_404(self, client):
        client._mock_supabase.set_table_data("transacoes", [])
        resp = client.post(
            "/api/ai/transacoes/22222222-2222-2222-2222-222222222222/categorize"
        )
        assert resp.status_code == 404


class TestMonthlyNarrative:
    def test_get_returns_digest_and_summary(self, client):
        from noctusai_lib.integrations.email.digest import Digest

        async def _fake_build(db, *, org_id, period_days):
            return (
                Digest(
                    subject="[NoctusAI] Resumo financeiro mensal — Família",
                    text="Resumo simples.",
                    html="<p>Resumo simples.</p>",
                ),
                {
                    "period_days": 30,
                    "period_label": "Últimos 30 dias",
                    "receita_total": 5000.0,
                    "despesa_total": 2300.0,
                    "fluxo_liquido": 2700.0,
                    "taxa_poupanca": 54.0,
                    "top_categorias": [{"nome": "Aluguel", "total": 1500.0}],
                    "transacoes_count": 3,
                    "narrative": "Panorama.",
                },
            )

        with patch(
            "app.services.monthly_narrative_service.build_narrative",
            side_effect=_fake_build,
        ):
            resp = client.get("/api/ai/monthly-narrative")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "Família" in data["subject"]
        assert data["summary"]["fluxo_liquido"] == 2700.0

    def test_send_endpoint_returns_outcome(self, client):
        with patch(
            "app.services.monthly_narrative_service.send_monthly_narrative",
            new_callable=AsyncMock,
            return_value={
                "sent": True, "dry_run": False, "external_id": "id-1",
                "error": None, "subject": "x", "summary": {"receita_total": 1.0},
            },
        ):
            resp = client.post(
                "/api/ai/monthly-narrative/send",
                json={"recipient": "u@x.com", "period_days": 30},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["sent"] is True


class TestRecurringFlag:
    def test_persists_flag(self, client, _stub_persist):
        client._mock_supabase.set_table_data("transacoes", SAMPLE_TX)
        with patch(
            "app.services.ai_service.flag_recurring_expense",
            new_callable=AsyncMock,
            return_value={
                "kind": "flag",
                "label": "recorrente",
                "score": 0.92,
                "chip": "RECORRENTE",
                "explanation": "três meses consecutivos",
                "confidence": 0.92,
                "model_version": "gpt-4o-mini",
                "prompt_version": "pf-recurring@v1",
            },
        ):
            resp = client.post(
                "/api/ai/transacoes/11111111-1111-1111-1111-111111111111/recurring-flag"
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["label"] == "recorrente"
        assert data["chip"] == "RECORRENTE"


# ---------------------------------------------------------------------------
# Consent guards — consent-guard-rollout Phase 5 (2026-04-27)
# ---------------------------------------------------------------------------


class TestConsentGuards:
    def test_categorize_returns_412_when_revoked(self, client):
        # Override the autouse seed with a revoked decision.
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "pf.transaction_categorize",
            "granted": False, "user_id": "test-user-123",
            "granted_at": None, "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.ai_service.categorize_transaction", new_callable=AsyncMock
        ) as mock_svc:
            resp = client.post(
                "/api/ai/transacoes/11111111-1111-1111-1111-111111111111/categorize"
            )
        assert resp.status_code == 412
        body_text = str(resp.json()).lower()
        assert "consentimento" in body_text or "consent" in body_text
        mock_svc.assert_not_called()

    def test_monthly_narrative_returns_412_when_no_decision_and_default_false(self, client):
        # `pf.monthly_narrative` is `default_granted=False` — no stored
        # decision → fail-closed (412). Override autouse with empty seed.
        client._mock_supabase.set_table_data("ai_consent", [])
        with patch(
            "app.services.monthly_narrative_service.build_narrative",
            new_callable=AsyncMock,
        ) as mock_svc:
            resp = client.get("/api/ai/monthly-narrative")
        assert resp.status_code == 412
        mock_svc.assert_not_called()

    def test_recurring_flag_returns_412_when_revoked(self, client):
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "pf.recurring_flag",
            "granted": False, "user_id": "test-user-123",
            "granted_at": None, "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.ai_service.flag_recurring_expense", new_callable=AsyncMock
        ) as mock_svc:
            resp = client.post(
                "/api/ai/transacoes/11111111-1111-1111-1111-111111111111/recurring-flag"
            )
        assert resp.status_code == 412
        mock_svc.assert_not_called()
