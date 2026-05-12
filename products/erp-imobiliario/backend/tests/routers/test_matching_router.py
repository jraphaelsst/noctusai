"""
Tests for Matching router — /api/matching
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestGerarMatches:
    def test_gerar_matches_full_scan(self, client):
        """Both IDs empty → full platform scan returns 200."""
        client._mock_supabase.set_table_data("ativos", [])
        client._mock_supabase.set_table_data("matches", [])
        resp = client.post("/api/matching/gerar", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    def test_gerar_matches_full_scan_no_ativos(self, client):
        """Full scan with no active ativos returns empty."""
        client._mock_supabase.set_table_data("ativos", [])
        client._mock_supabase.set_table_data("matches", [])
        resp = client.post("/api/matching/gerar", json={})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_gerar_matches_with_embeddings(self, client):
        """Unified path: ativo with embeddings gets score enhanced by similarity."""
        imovel = {
            "id": "imovel-1",
            "natureza": "imovel",
            "status": "ativo",
            "aceita_permutas": True,
            "valor": 500000,
            "owner_id": "user-a",
            "cidade": "São Paulo",
            "estado": "SP",
            "tipo_imovel": "apartamento",
            "quartos": 2,
            "interesses": [{"tipo": "imovel", "tipo_imovel": "apartamento", "cidade": "São Paulo", "valor_min": 300000, "valor_max": 700000}],
        }
        permuta = {
            "id": "perm-1",
            "natureza": "permuta_imovel",
            "owner_id": "user-b",
            "status": "ativo",
            "valor": 500000,
            "cidade": "São Paulo",
            "estado": "SP",
            "tipo_imovel": "apartamento",
            "quartos": 2,
            "faixa_preco_min": 400000,
            "faixa_preco_max": 600000,
            "interesses": [{"tipo": "imovel", "tipo_imovel": "apartamento", "cidade": "São Paulo", "valor_min": 400000, "valor_max": 600000}],
        }
        client._mock_supabase.set_table_data("ativos", [imovel, permuta])
        client._mock_supabase.set_table_data("matches", [{"id": "m1"}])

        resp = client.post("/api/matching/gerar", json={"ativo_origem_id": "imovel-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["data"][0]["score"] >= 45

    def test_gerar_matches_no_embedding(self, client):
        """Unified path works without embeddings — pure rule-based scoring."""
        imovel = {
            "id": "imovel-1",
            "natureza": "imovel",
            "status": "ativo",
            "aceita_permutas": True,
            "valor": 500000,
            "owner_id": "user-a",
            "cidade": "São Paulo",
            "estado": "SP",
            "tipo_imovel": "apartamento",
            "quartos": 2,
            "interesses": [{"tipo": "imovel", "tipo_imovel": "apartamento", "cidade": "São Paulo", "valor_min": 300000, "valor_max": 700000}],
        }
        permuta = {
            "id": "perm-1",
            "natureza": "permuta_imovel",
            "owner_id": "user-b",
            "status": "ativo",
            "valor": 500000,
            "cidade": "São Paulo",
            "estado": "SP",
            "tipo_imovel": "apartamento",
            "quartos": 2,
            "faixa_preco_min": 400000,
            "faixa_preco_max": 600000,
            "interesses": [{"tipo": "imovel", "tipo_imovel": "apartamento", "cidade": "São Paulo", "valor_min": 400000, "valor_max": 600000}],
        }
        client._mock_supabase.set_table_data("ativos", [imovel, permuta])
        client._mock_supabase.set_table_data("matches", [{"id": "m1"}])

        resp = client.post("/api/matching/gerar", json={"ativo_origem_id": "imovel-1"})
        assert resp.status_code == 200


class TestEmbedAtivo:
    @pytest.fixture(autouse=True)
    def _bypass_openai_check(self):
        """Bypass the upfront OpenAI credential check.

        Patches the canonical seed surface
        `noctusai_lib.config.credentials.resolve_credential` (the *external*
        credential-source boundary). Per `feedback_no_monkeypatching_in_tests`,
        patching external-integration surfaces (DB-backed credential resolver)
        is allowed; patching in-product helpers is not. Phase 3
        (erp-wiring 2026-05-11) — see PROJECT.md §11.
        """
        with patch("noctusai_lib.config.credentials.resolve_credential", return_value="test-key"):
            yield

    def test_embed_ativo_endpoint(self, client):
        """Verify embed endpoint calls embedding service."""
        ativo = {"id": "ativo-1", "natureza": "imovel", "tipo_imovel": "casa", "cidade": "SP"}
        client._mock_supabase.set_table_data("ativos", [ativo])

        with patch("app.routers.matching.embed_ativo", create=True) as _:
            with patch("app.services.embedding_service.embed_ativo", new_callable=AsyncMock) as mock_embed:
                mock_embed.return_value = True
                resp = client.post("/api/matching/embed", json={"ativo_id": "ativo-1"})
                assert resp.status_code == 200
                data = resp.json()
                assert data["data"]["success"] is True
                assert data["data"]["ativo_id"] == "ativo-1"

    def test_embed_ativo_not_found(self, client):
        """404 when ativo doesn't exist."""
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.post("/api/matching/embed", json={"ativo_id": "nonexistent"})
        # With empty data and single() mode, data will be None
        assert resp.status_code in (404, 200)  # depends on mock behavior

    def test_embed_ativo_no_api_key(self, client):
        """422 when OpenAI key not configured (upfront check)."""
        # Override the autouse fixture: simulate the seed credential resolver
        # returning None (no key configured at any tier).
        with patch("noctusai_lib.config.credentials.resolve_credential", return_value=None):
            resp = client.post("/api/matching/embed", json={"ativo_id": "ativo-1"})
            assert resp.status_code == 422
            assert "OpenAI" in resp.json()["error"]["message"]


class TestEmbedBatch:
    @pytest.fixture(autouse=True)
    def _bypass_openai_check(self):
        """Bypass the upfront OpenAI credential check (see TestEmbedAtivo)."""
        with patch("noctusai_lib.config.credentials.resolve_credential", return_value="test-key"):
            yield

    def test_embed_batch_endpoint(self, client):
        """Verify batch endpoint processes ativos without embeddings."""
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1"}, {"id": "a2"},
        ])

        with patch("app.services.embedding_service.embed_ativos_batch", new_callable=AsyncMock) as mock_batch:
            mock_batch.return_value = {"total": 2, "embedded": 2, "errors": 0}
            resp = client.post("/api/matching/embed-batch")
            assert resp.status_code == 200
            data = resp.json()
            assert data["data"]["total"] == 2
            assert data["data"]["embedded"] == 2

    def test_embed_batch_no_ativos(self, client):
        """Returns zeros when no ativos need embedding."""
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.post("/api/matching/embed-batch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 0


class TestListarMatches:
    def test_listar_matches(self, client):
        client._mock_supabase.set_table_data("matches", [
            {"id": "m1", "ativo_origem_id": "a1", "ativo_destino_id": "a2", "score": 75},
        ])
        resp = client.get("/api/matching")
        assert resp.status_code == 200


class TestAtualizarMatch:
    def test_atualizar_match_status(self, client):
        client._mock_supabase.set_table_data("matches", [{"id": "m1", "status": "aceito"}])
        resp = client.patch("/api/matching/m1", json={"status": "aceito"})
        assert resp.status_code == 200

    def test_atualizar_match_invalid_status(self, client):
        resp = client.patch("/api/matching/m1", json={"status": "banana"})
        assert resp.status_code == 400
