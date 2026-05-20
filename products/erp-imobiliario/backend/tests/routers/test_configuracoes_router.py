"""Tests for the Configurações router — credential testing."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


_RESOLVE_CRED = "app.routers.configuracoes.resolve_credential"


# --------------- POST /api/configuracoes/testar-credencial/{key} ---------------

class TestTestarCredencial:
    def test_chave_invalida_retorna_400(self, client):
        resp = client.post("/api/configuracoes/testar-credencial/chave_inexistente")
        assert resp.status_code == 400

    def test_credencial_nao_configurada_retorna_422(self, client):
        with patch(_RESOLVE_CRED, return_value=None):
            resp = client.post("/api/configuracoes/testar-credencial/openai_api_key")
        assert resp.status_code == 422
        assert "não está configurada" in resp.json()["error"]["message"]

    def test_openai_sucesso(self, client):
        # Router was refactored 2026-05-11 to route via `noctusai_lib.integrations.llm.chat_completion`
        # (LLM-ERP Step A); the previous raw httpx /v1/models probe is gone. Mock the seed
        # entry point — that's the external-LLM-API boundary, allowed by the no-monkey-patching rule
        # (`KB § PATTERNS/testing.md` — external integrations).
        with patch(_RESOLVE_CRED, return_value="sk-test123"), \
             patch("noctusai_lib.integrations.llm.chat_completion", new=AsyncMock(return_value={"choices": [{"message": {"content": "ok"}}]})):
            resp = client.post("/api/configuracoes/testar-credencial/openai_api_key")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is True

    def test_openai_chave_invalida(self, client):
        # Same refactor as test_openai_sucesso. LLMAPIError carrying "401" maps to
        # "API Key inválida ou expirada." per configuracoes.py:83-88.
        from noctusai_lib.integrations.llm.exceptions import LLMAPIError
        with patch(_RESOLVE_CRED, return_value="sk-bad"), \
             patch("noctusai_lib.integrations.llm.chat_completion", new=AsyncMock(side_effect=LLMAPIError("openai", "401 Unauthorized: invalid_api_key", 401))):
            resp = client.post("/api/configuracoes/testar-credencial/openai_api_key")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False
        assert "inválida" in data["message"]

    def test_openai_erro_conexao(self, client):
        # Same refactor as above. A raw Exception (non-LLM-typed) falls through to the
        # bare `except Exception` branch → "Erro de conexão: …" per configuracoes.py:94-103.
        with patch(_RESOLVE_CRED, return_value="sk-test"), \
             patch("noctusai_lib.integrations.llm.chat_completion", new=AsyncMock(side_effect=Exception("Connection refused"))):
            resp = client.post("/api/configuracoes/testar-credencial/openai_api_key")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False
        assert "conexão" in data["message"].lower()

    def test_infosimples_sucesso(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 200, "data": []}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(_RESOLVE_CRED, return_value="tok-valid"), \
             patch("app.routers.configuracoes.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/api/configuracoes/testar-credencial/infosimples_token")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is True

    def test_infosimples_token_invalido_403(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 403, "message": "Token inválido"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(_RESOLVE_CRED, return_value="tok-bad"), \
             patch("app.routers.configuracoes.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/api/configuracoes/testar-credencial/infosimples_token")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False

    def test_infosimples_token_erro_401(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 401, "message": "Não autorizado"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(_RESOLVE_CRED, return_value="tok-bad"), \
             patch("app.routers.configuracoes.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/api/configuracoes/testar-credencial/infosimples_token")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False

    def test_infosimples_erro_conexao(self, client):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(_RESOLVE_CRED, return_value="tok-test"), \
             patch("app.routers.configuracoes.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/api/configuracoes/testar-credencial/infosimples_token")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False
