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
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(_RESOLVE_CRED, return_value="sk-test123"), \
             patch("app.routers.configuracoes.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/api/configuracoes/testar-credencial/openai_api_key")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is True

    def test_openai_chave_invalida(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(_RESOLVE_CRED, return_value="sk-bad"), \
             patch("app.routers.configuracoes.httpx.AsyncClient", return_value=mock_client):
            resp = client.post("/api/configuracoes/testar-credencial/openai_api_key")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is False
        assert "inválida" in data["message"]

    def test_openai_erro_conexao(self, client):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(_RESOLVE_CRED, return_value="sk-test"), \
             patch("app.routers.configuracoes.httpx.AsyncClient", return_value=mock_client):
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
