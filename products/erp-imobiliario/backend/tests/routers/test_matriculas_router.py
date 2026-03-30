"""Tests for the Matrículas router — file upload, list, get, delete."""
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import AuthClient

SAMPLE_EXTRACAO = {
    "id": "ext-001",
    "org_id": "test-org-123",
    "user_id": "test-user-123",
    "nome_arquivo": "matricula.pdf",
    "tamanho_bytes": 1024,
    "num_paginas": 3,
    "texto_extraido": "Texto extraído da matrícula",
    "status": "concluida",
    "erro_mensagem": None,
    "created_at": "2026-03-13T12:00:00Z",
}


# ---------------------------------------------------------------------------
# POST /api/matriculas/extrair
# ---------------------------------------------------------------------------

class TestExtrairMatricula:
    def test_upload_pdf_sucesso(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        with patch("app.routers.matriculas.check_required_credentials", return_value=[]):
            resp = client.post(
                "/api/matriculas/extrair",
                files={"file": ("matricula.pdf", b"%PDF-1.0 fake", "application/pdf")},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["nome_arquivo"] == "matricula.pdf"

    def test_rejeita_arquivo_nao_pdf(self, client: AuthClient):
        with patch("app.routers.matriculas.check_required_credentials", return_value=[]):
            resp = client.post(
                "/api/matriculas/extrair",
                files={"file": ("doc.txt", b"plain text", "text/plain")},
            )
        assert resp.status_code == 400
        assert "PDF" in resp.json()["error"]["message"]

    def test_rejeita_arquivo_vazio(self, client: AuthClient):
        with patch("app.routers.matriculas.check_required_credentials", return_value=[]):
            resp = client.post(
                "/api/matriculas/extrair",
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )
        assert resp.status_code == 400
        assert "vazio" in resp.json()["error"]["message"].lower()

    def test_rejeita_sem_credenciais(self, client: AuthClient):
        with patch(
            "app.routers.matriculas.check_required_credentials",
            return_value=["OpenAI API Key não configurada."],
        ):
            resp = client.post(
                "/api/matriculas/extrair",
                files={"file": ("matricula.pdf", b"%PDF-1.0 fake", "application/pdf")},
            )
        assert resp.status_code == 422
        assert "OpenAI" in resp.json()["error"]["message"]

    def test_insert_falha_retorna_500(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [])
        with patch("app.routers.matriculas.check_required_credentials", return_value=[]):
            resp = client.post(
                "/api/matriculas/extrair",
                files={"file": ("matricula.pdf", b"%PDF-1.0 fake", "application/pdf")},
            )
        assert resp.status_code == 500

    def test_log_action_chamado(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        mock_log = MagicMock()
        with patch("app.routers.matriculas.check_required_credentials", return_value=[]), \
             patch("app.routers.matriculas.log_action", mock_log):
            client.post(
                "/api/matriculas/extrair",
                files={"file": ("test.pdf", b"%PDF-1.0 fake", "application/pdf")},
            )
        mock_log.assert_called_once()
        assert "test.pdf" in mock_log.call_args[0][4]


# ---------------------------------------------------------------------------
# GET /api/matriculas/extracoes
# ---------------------------------------------------------------------------

class TestListarExtracoes:
    def test_lista_vazia(self, client: AuthClient):
        resp = client.get("/api/matriculas/extracoes")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_lista_com_dados(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [
            SAMPLE_EXTRACAO,
            {**SAMPLE_EXTRACAO, "id": "ext-002", "nome_arquivo": "mat2.pdf"},
        ])
        resp = client.get("/api/matriculas/extracoes")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_busca_por_nome(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.get("/api/matriculas/extracoes?busca=lote5")
        assert resp.status_code == 200

    def test_paginacao_params(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.get("/api/matriculas/extracoes?page=1&page_size=10")
        assert resp.status_code == 200
        assert "pagination" in resp.json()


# ---------------------------------------------------------------------------
# GET /api/matriculas/extracoes/{id}
# ---------------------------------------------------------------------------

class TestObterExtracao:
    def test_extracao_encontrada(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", SAMPLE_EXTRACAO)
        resp = client.get("/api/matriculas/extracoes/ext-001")
        assert resp.status_code == 200
        assert resp.json()["data"]["texto_extraido"] == "Texto extraído da matrícula"

    def test_extracao_nao_encontrada(self, client: AuthClient):
        resp = client.get("/api/matriculas/extracoes/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/matriculas/extracoes/{id}
# ---------------------------------------------------------------------------

class TestExcluirExtracao:
    def test_exclui_com_sucesso(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.delete("/api/matriculas/extracoes/ext-001")
        assert resp.status_code == 200
        assert "sucesso" in resp.json()["message"].lower()

    def test_exclui_nao_encontrada(self, client: AuthClient):
        resp = client.delete("/api/matriculas/extracoes/nonexistent")
        assert resp.status_code == 404

    def test_exclui_log_action(self, client: AuthClient):
        client._mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        mock_log = MagicMock()
        with patch("app.routers.matriculas.log_action", mock_log):
            client.delete("/api/matriculas/extracoes/ext-001")
        mock_log.assert_called_once()
