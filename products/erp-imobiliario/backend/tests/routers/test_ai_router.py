"""
Tests for the AI Features router.
Covers property description generation, lead scoring, and price suggestion endpoints.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def _bypass_openai_check():
    """Bypass upfront OpenAI credential check for all AI router tests."""
    with patch("app.routers.ai.check_openai_configured", return_value=True):
        yield


class TestGenerateDescription:
    def test_generate_with_imovel_id(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "cidade": "Sao Paulo",
            "bairro": "Jardins",
            "area_privativa": 120,
            "quartos": 3,
            "suites": 1,
            "vagas": 2,
            "valor": 800000,
        })
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            return_value={
                "titulo_sugerido": "Lindo apartamento no Jardins",
                "descricao": "Excelente apartamento com 3 quartos...",
            },
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_id": "a1",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert "titulo_sugerido" in data
            assert "descricao" in data

    def test_generate_with_imovel_data(self, client):
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            return_value={
                "titulo_sugerido": "Casa ampla em Alphaville",
                "descricao": "Casa espacosa com 4 quartos...",
            },
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_data": {
                    "tipo_imovel": "casa",
                    "cidade": "Barueri",
                    "bairro": "Alphaville",
                    "quartos": 4,
                    "valor": 1500000,
                },
            })
            assert resp.status_code == 200

    def test_generate_no_data(self, client):
        resp = client.post("/api/ai/generate-description", json={})
        assert resp.status_code == 400

    def test_generate_imovel_not_found(self, client):
        client._mock_supabase.set_table_data("ativos", None)
        resp = client.post("/api/ai/generate-description", json={
            "imovel_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_generate_ai_service_error(self, client):
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            side_effect=Exception("OpenAI API error"),
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_data": {
                    "tipo_imovel": "casa",
                    "quartos": 3,
                },
            })
            assert resp.status_code == 500

    def test_generate_ai_value_error(self, client):
        with patch(
            "app.services.ai_service.generate_description",
            new_callable=AsyncMock,
            side_effect=ValueError("Chave da API OpenAI nao configurada"),
        ):
            resp = client.post("/api/ai/generate-description", json={
                "imovel_data": {
                    "tipo_imovel": "terreno",
                },
            })
            assert resp.status_code == 400


class TestLeadScore:
    def test_score_with_cliente_id(self, client):
        client._mock_supabase.set_table_data("clientes", {
            "id": "c1",
            "nome": "Joao Silva",
            "email": "joao@test.com",
            "telefone": "11999999999",
            "origem": "indicacao",
            "interesse": "Apartamento 3 quartos",
            "valor_estimado": 500000,
            "etapa_atual": "visitas",
            "probabilidade": 70,
        })
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            return_value={
                "score": 78,
                "justificativa": "Lead com dados completos e alta probabilidade.",
                "recomendacao": "Agendar visita ao imovel.",
            },
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_id": "c1",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["score"] == 78
            assert "justificativa" in data

    def test_score_with_cliente_data(self, client):
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            return_value={
                "score": 55,
                "justificativa": "Dados parciais.",
                "recomendacao": "Completar cadastro.",
            },
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_data": {
                    "nome": "Maria",
                    "email": "maria@test.com",
                    "interesse": "Casa",
                },
            })
            assert resp.status_code == 200

    def test_score_no_data(self, client):
        resp = client.post("/api/ai/lead-score", json={})
        assert resp.status_code == 400

    def test_score_cliente_not_found(self, client):
        client._mock_supabase.set_table_data("clientes", None)
        resp = client.post("/api/ai/lead-score", json={
            "cliente_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_score_ai_error(self, client):
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            side_effect=Exception("AI service down"),
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_data": {
                    "nome": "Test",
                },
            })
            assert resp.status_code == 500

    def test_score_ai_value_error(self, client):
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            side_effect=ValueError("API key not configured"),
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_data": {"nome": "Test"},
            })
            assert resp.status_code == 400


    def test_score_persists_to_clientes_table(self, client):
        """When cliente_id is provided, the score should be persisted to the clientes table."""
        client._mock_supabase.set_table_data("clientes", {
            "id": "c1",
            "nome": "Joao Silva",
            "email": "joao@test.com",
            "etapa_atual": "visitas",
            "probabilidade": 70,
            "valor_estimado": 500000,
        })
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            return_value={
                "score": 85,
                "justificativa": "Lead muito qualificado.",
                "recomendacao": "Fechar negocio.",
            },
        ):
            # Spy on the update method while preserving real return type
            clientes_builder = client._mock_supabase.table("clientes")
            original_update = clientes_builder.update
            update_spy = MagicMock(side_effect=original_update)
            clientes_builder.update = update_spy

            resp = client.post("/api/ai/lead-score", json={
                "cliente_id": "c1",
            })
            assert resp.status_code == 200

            # Verify update was called with the score data
            update_spy.assert_called_once()
            update_data = update_spy.call_args[0][0]
            assert update_data["lead_score"] == 85
            assert update_data["lead_score_justificativa"] == "Lead muito qualificado."
            assert "lead_score_updated_at" in update_data

    def test_score_does_not_persist_without_cliente_id(self, client):
        """When only cliente_data is provided (no ID), the score should NOT be persisted."""
        with patch(
            "app.services.ai_service.score_lead",
            new_callable=AsyncMock,
            return_value={
                "score": 50,
                "justificativa": "Dados parciais.",
                "recomendacao": "Completar cadastro.",
            },
        ):
            resp = client.post("/api/ai/lead-score", json={
                "cliente_data": {
                    "nome": "Maria",
                    "email": "maria@test.com",
                },
            })
            assert resp.status_code == 200
            # No clientes table interaction expected (no update call)
            assert "clientes" not in client._mock_supabase._tables


class TestSuggestPrice:
    def test_suggest_with_imovel_id(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "cidade": "Sao Paulo",
            "bairro": "Jardins",
            "area_privativa": 120,
            "quartos": 3,
            "vagas": 2,
            "natureza": "imovel",
            "status": "ativo",
        })
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            return_value={
                "preco_sugerido": 850000,
                "faixa_min": 750000,
                "faixa_max": 950000,
                "analise": "Baseado em comparaveis da regiao.",
            },
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_id": "a1",
            })
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["preco_sugerido"] == 850000
            assert data["faixa_min"] == 750000
            assert data["faixa_max"] == 950000
            assert "analise" in data
            assert "total_comparaveis" in data

    def test_suggest_with_imovel_data(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            return_value={
                "preco_sugerido": 600000,
                "faixa_min": 500000,
                "faixa_max": 700000,
                "analise": "Estimativa sem comparaveis.",
            },
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_data": {
                    "tipo_imovel": "casa",
                    "cidade": "Campinas",
                    "bairro": "Cambui",
                    "area_privativa": 200,
                    "quartos": 4,
                },
            })
            assert resp.status_code == 200

    def test_suggest_no_data(self, client):
        resp = client.post("/api/ai/suggest-price", json={})
        assert resp.status_code == 400

    def test_suggest_imovel_not_found(self, client):
        client._mock_supabase.set_table_data("ativos", None)
        resp = client.post("/api/ai/suggest-price", json={
            "imovel_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_suggest_ai_error(self, client):
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            side_effect=Exception("OpenAI timeout"),
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_data": {
                    "tipo_imovel": "apartamento",
                    "quartos": 2,
                },
            })
            assert resp.status_code == 500

    def test_suggest_ai_value_error(self, client):
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            side_effect=ValueError("No API key"),
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_data": {"tipo_imovel": "casa"},
            })
            assert resp.status_code == 400

    def test_suggest_with_comparables(self, client):
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "cidade": "Sao Paulo",
            "bairro": "Vila Mariana",
            "area_privativa": 80,
            "quartos": 2,
            "vagas": 1,
            "natureza": "imovel",
            "status": "ativo",
        })
        with patch(
            "app.services.ai_service.suggest_price",
            new_callable=AsyncMock,
            return_value={
                "preco_sugerido": 500000,
                "faixa_min": 450000,
                "faixa_max": 550000,
                "analise": "Baseado em 5 comparaveis.",
            },
        ):
            resp = client.post("/api/ai/suggest-price", json={
                "imovel_id": "a1",
            })
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tier 1.5 G1 — E4 follow-up draft endpoint (ai-expansion Phase 15)
# ---------------------------------------------------------------------------

class TestFollowUpDraft:
    def test_happy_path_returns_draft(self, client):
        client._mock_supabase.set_table_data("clientes", {
            "id": "lead-1",
            "nome": "João Silva",
            "etapa_atual": "negociação",
            "lead_score_justificativa": "ativo",
            "observacoes": "Negociava preço.",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-03-01T00:00:00Z",
        })
        with patch(
            "app.services.ai_service.draft_follow_up",
            new_callable=AsyncMock,
            return_value={
                "channel": "whatsapp",
                "subject": None,
                "body": "Olá João, tudo bem?",
            },
        ):
            resp = client.post(
                "/api/ai/leads/lead-1/follow-up-draft",
                json={"cliente_id": "lead-1"},
            )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["channel"] == "whatsapp"
        assert "João" in body["body"]
        assert "days_since_activity" in body

    def test_lead_not_found_returns_404(self, client):
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.post(
            "/api/ai/leads/missing/follow-up-draft",
            json={"cliente_id": "missing"},
        )
        assert resp.status_code == 404

    def test_llm_failure_returns_500(self, client):
        client._mock_supabase.set_table_data("clientes", {
            "id": "lead-1",
            "nome": "Ana",
            "etapa_atual": "qualificação",
            "updated_at": "2026-04-01T00:00:00Z",
        })
        with patch(
            "app.services.ai_service.draft_follow_up",
            new_callable=AsyncMock,
            side_effect=RuntimeError("upstream timeout"),
        ):
            resp = client.post(
                "/api/ai/leads/lead-1/follow-up-draft",
                json={"cliente_id": "lead-1"},
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Phase 6 P1 indicator endpoints (E2/E6/E7/E8/E10)
# ---------------------------------------------------------------------------


@pytest.fixture
def _stub_persist():
    """Stub persist_output so the integration test doesn't depend on the
    erp.ai_outputs table being seeded into the mock."""
    with patch(
        "app.routers.ai.persist_output",
        side_effect=lambda db, schema, output: {
            **output.to_insert_payload(),
            "id": "ai-out-1",
        },
    ) as p:
        yield p


class TestWhatsAppIntent:
    def test_persists_classification(self, client, _stub_persist):
        with patch(
            "app.services.ai_service.classify_whatsapp_intent",
            new_callable=AsyncMock,
            return_value={
                "kind": "classification",
                "label": "interessado",
                "chip": "INTERESSADO",
                "explanation": "preocupado com prazo",
                "confidence": 0.9,
                "score": None,
                "model_version": "gpt-4o-mini",
                "prompt_version": "erp-whatsapp-intent@v1",
            },
        ):
            resp = client.post(
                "/api/ai/whatsapp-intent",
                json={
                    "cliente_id": "11111111-1111-1111-1111-111111111111",
                    "message_text": "Quero saber se o apto está disponível",
                    "cliente_nome": "João",
                },
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["label"] == "interessado"
        assert data["ref_id"] == "11111111-1111-1111-1111-111111111111"
        _stub_persist.assert_called_once()


class TestCertidoesScore:
    def test_happy_path(self, client, _stub_persist):
        # Post keeper-trio-erp Phase 1: the router queries the canonical
        # certidões schema (erp.certidao_consultas joined with
        # erp.certidao_resultados via consulta_id, name-matched by
        # cliente.nome). The legacy phantom `certidoes_negativas` table
        # is gone; the stubs below mirror the real shape.
        client._mock_supabase.set_table_data("clientes", {
            "id": "11111111-1111-1111-1111-111111111111",
            "nome": "Pedro",
        })
        client._mock_supabase.set_table_data("certidao_consultas", [
            {
                "id": "cc111111-1111-1111-1111-111111111111",
                "nome": "Pedro",
                "tipo_documento": "cpf",
                "documento": "12345678900",
                "created_at": "2026-04-01T10:00:00Z",
            },
        ])
        client._mock_supabase.set_table_data("certidao_resultados", [
            {
                "tipo": "fed",
                "nome_display": "Federal",
                "status": "sucesso",
                "analise_ia": "ok",
                "api_requested_at": "2026-04-01T10:00:00Z",
                "consulta_id": "cc111111-1111-1111-1111-111111111111",
            },
        ])
        with patch(
            "app.services.ai_service.score_certidoes",
            new_callable=AsyncMock,
            return_value={
                "kind": "score",
                "label": "saúde 80/100",
                "score": 80.0,
                "chip": "80/100",
                "explanation": "ok",
                "confidence": None,
                "model_version": "gpt-4o-mini",
                "prompt_version": "erp-certidoes-score@v1",
            },
        ):
            resp = client.post(
                "/api/ai/clientes/11111111-1111-1111-1111-111111111111/certidoes-score",
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["score"] == 80.0

    def test_cliente_not_found_returns_404(self, client):
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.post("/api/ai/clientes/22222222-2222-2222-2222-222222222222/certidoes-score")
        assert resp.status_code == 404

    def test_no_consultas_returns_empty_score(self, client, _stub_persist):
        """Cliente exists but no certidões — score_certidoes receives []."""
        client._mock_supabase.set_table_data("clientes", {
            "id": "33333333-3333-3333-3333-333333333333",
            "nome": "Maria",
        })
        client._mock_supabase.set_table_data("certidao_consultas", [])
        with patch(
            "app.services.ai_service.score_certidoes",
            new_callable=AsyncMock,
            return_value={
                "kind": "score",
                "label": "sem certidões",
                "score": 0.0,
                "chip": "0/100",
                "explanation": "Nenhuma certidão registrada para o cliente.",
                "confidence": 1.0,
                "model_version": "gpt-4o-mini",
                "prompt_version": "erp-certidoes-score@v1",
            },
        ) as stub:
            resp = client.post(
                "/api/ai/clientes/33333333-3333-3333-3333-333333333333/certidoes-score",
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["score"] == 0.0
        # Verify the certidões list passed to the service was empty.
        assert stub.call_args.kwargs["certidoes"] == []


class TestMetasCoachTip:
    def test_persists_narrative(self, client, _stub_persist):
        with patch(
            "app.services.ai_service.generate_metas_coach_tip",
            new_callable=AsyncMock,
            return_value={
                "kind": "narrative",
                "label": "Foque em retomar leads parados",
                "explanation": "Foque em retomar leads parados",
                "chip": "REATIVAR",
                "score": 35.0,
                "confidence": None,
                "model_version": "gpt-4o-mini",
                "prompt_version": "erp-metas-coach@v1",
            },
        ):
            resp = client.post(
                "/api/ai/metas/coach-tip",
                json={
                    "user_id": "33333333-3333-3333-3333-333333333333",
                    "user_nome": "Ana",
                    "progresso_percent": 35.0,
                    "dias_restantes": 12,
                    "eventos_recentes": ["visita"],
                },
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["chip"] == "REATIVAR"
        assert data["ref_type"] == "user_metas"


class TestPhotoCompliance:
    def test_persists_flag(self, client, _stub_persist):
        client._mock_supabase.set_table_data("ativos", {
            "id": "44444444-4444-4444-4444-444444444444",
            "descricao": "Apto 3 quartos",
            "fotos": [{"filename": "a.jpg", "alt_text": ""}],
        })
        with patch(
            "app.services.ai_service.assess_photo_compliance",
            new_callable=AsyncMock,
            return_value={
                "kind": "flag",
                "label": "revisar",
                "score": 60.0,
                "chip": "REVISAR",
                "explanation": "alt-text vazio",
                "confidence": None,
                "model_version": "gpt-4o-mini",
                "prompt_version": "erp-photo-compliance@v1",
            },
        ):
            resp = client.post(
                "/api/ai/imoveis/44444444-4444-4444-4444-444444444444/photo-compliance",
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["chip"] == "REVISAR"

    def test_imovel_not_found_returns_404(self, client):
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.post("/api/ai/imoveis/55555555-5555-5555-5555-555555555555/photo-compliance")
        assert resp.status_code == 404


class TestSearchRelevance:
    def test_persists_score(self, client, _stub_persist):
        client._mock_supabase.set_table_data("ativos", {
            "id": "66666666-6666-6666-6666-666666666666",
            "tipo_imovel": "Apto",
            "bairro": "Centro",
            "cidade": "SP",
            "area_privativa": 80,
            "area_total": 90,
            "quartos": 2,
            "valor": 500000,
            "descricao": "Apto reformado",
        })
        with patch(
            "app.services.ai_service.score_search_relevance",
            new_callable=AsyncMock,
            return_value={
                "kind": "score",
                "label": "relevância 75%",
                "score": 0.75,
                "chip": "75%",
                "explanation": "match em bairro",
                "confidence": 0.75,
                "model_version": "gpt-4o-mini",
                "prompt_version": "erp-search-relevance@v1",
            },
        ):
            resp = client.post(
                "/api/ai/search-relevance",
                json={
                    "imovel_id": "66666666-6666-6666-6666-666666666666",
                    "query": "apto 2 quartos centro",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["score"] == 0.75


# ---------------------------------------------------------------------------
# Consent guards — consent-guard-rollout Phase 3 (2026-04-27)
#
# Each ERP AI endpoint mounts `Depends(consent_required("erp.<feature>"))`.
# Tests below confirm: (a) revoked decisions block with HTTP 412 + the
# underlying service is never called, (b) `erp.embeddings` is registered
# as `toggleable=False` (locked-on infra), (c) default-granted=True passes
# the guard transparently.
# ---------------------------------------------------------------------------


class TestConsentGuards:
    def test_lead_score_returns_412_when_user_revoked_consent(self, client):
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "erp.lead_score",
            "granted": False,
            "user_id": "test-user-123",
            "granted_at": None,
            "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.ai_service.score_lead", new_callable=AsyncMock
        ) as mock_svc:
            resp = client.post(
                "/api/ai/lead-score",
                json={"cliente_id": "cli-1"},
            )
        assert resp.status_code == 412
        body_text = str(resp.json()).lower()
        assert "consentimento" in body_text or "consent" in body_text
        mock_svc.assert_not_called()

    def test_follow_up_draft_returns_412_when_user_revoked_consent(self, client):
        # Different endpoint shape (path param + body) — same guard mechanism.
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "erp.lead_follow_up_draft",
            "granted": False,
            "user_id": "test-user-123",
            "granted_at": None,
            "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.ai_service.draft_follow_up", new_callable=AsyncMock
        ) as mock_svc:
            resp = client.post(
                "/api/ai/leads/lead-1/follow-up-draft",
                json={"cliente_id": "lead-1"},
            )
        assert resp.status_code == 412
        mock_svc.assert_not_called()

    def test_embeddings_feature_is_locked_on_via_toggleable_false(self, client):
        # `erp.embeddings` is `toggleable=False` per §7.6 — visible in the
        # catalog for billing transparency but cannot be disabled. The
        # toggle-attempt 403 path is exercised in core's me_consents tests;
        # here we just confirm the ERP catalog has the entry with the right
        # locked-on shape.
        from noctusai_lib.domain.ai.consent import get_feature
        feature = get_feature("erp.embeddings")
        assert feature is not None
        assert feature.toggleable is False
        assert feature.default_granted is True
        assert feature.product == "erp"

    def test_default_granted_path_lets_request_through(self, client):
        # No stored decision + default_granted=True → guard passes silently.
        client._mock_supabase.set_table_data("ai_consent", [])
        with patch(
            "app.services.ai_service.classify_whatsapp_intent", new_callable=AsyncMock
        ) as mock_svc:
            mock_svc.return_value = {
                "kind": "classification",
                "label": "interesse_compra",
                "score": 0.85,
                "chip": "compra",
                "explanation": "menciona valor + financiamento",
                "confidence": 0.85,
                "model_version": "gpt-4o-mini",
                "prompt_version": "erp-whatsapp-intent@v1",
            }
            resp = client.post(
                "/api/ai/whatsapp-intent",
                json={
                    "cliente_id": "11111111-1111-1111-1111-111111111111",
                    "message_text": "Tenho interesse em financiar este apartamento",
                },
            )
        assert resp.status_code == 200
        mock_svc.assert_called_once()
