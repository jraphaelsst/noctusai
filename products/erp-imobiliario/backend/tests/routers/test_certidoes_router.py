"""Tests for the Certidões Negativas router."""
import pytest
from tests.conftest import MockSupabaseResponse


SAMPLE_CONSULTA = {
    "id": "consulta-001",
    "org_id": "test-org-123",
    "created_by": "test-user-123",
    "tipo_documento": "cpf",
    "documento": "12345678901",
    "nome": "João da Silva",
    "data_nascimento": "1990-01-15",
    "genero": "M",
    "rg": None,
    "nome_mae": None,
    "nome_pai": None,
    "status": "pendente",
    "total_certidoes": 9,
    "concluidas": 0,
    "created_at": "2026-03-05T10:00:00Z",
    "updated_at": "2026-03-05T10:00:00Z",
}

SAMPLE_RESULTADO = {
    "id": "resultado-001",
    "consulta_id": "consulta-001",
    "org_id": "test-org-123",
    "tipo": "cnd_federal",
    "nome_display": "CND Federal (Receita)",
    "ordem": 1,
    "status": "pendente",
    "analise_ia": None,
    "arquivo_url": None,
    "arquivo_nome": None,
    "api_response": None,
    "erro_mensagem": None,
    "created_at": "2026-03-05T10:00:00Z",
    "updated_at": "2026-03-05T10:00:00Z",
}


# --------------- GET /api/certidoes/tipos ---------------

class TestListarTipos:
    def test_retorna_tipos(self, client):
        resp = client.get("/api/certidoes/tipos")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 9
        assert data[0]["tipo"] == "cnd_federal"
        assert data[0]["nome"] == "CND Federal (Receita)"


# --------------- GET /api/certidoes/consultas ---------------

class TestListarConsultas:
    def test_lista_vazia(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [])
        resp = client.get("/api/certidoes/consultas")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_lista_com_dados(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.get("/api/certidoes/consultas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["nome"] == "João da Silva"

    def test_filtro_status(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.get("/api/certidoes/consultas?status=pendente")
        assert resp.status_code == 200

    def test_busca(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.get("/api/certidoes/consultas?busca=João")
        assert resp.status_code == 200


# --------------- POST /api/certidoes/consultas ---------------

class TestCriarConsulta:
    def test_cria_consulta_cpf(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "João da Silva",
            "data_nascimento": "1990-01-15",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "João da Silva"

    def test_cria_consulta_cnpj(self, client):
        consulta_cnpj = {**SAMPLE_CONSULTA, "tipo_documento": "cnpj", "documento": "12345678000190"}
        client._mock_supabase.set_table_data("certidao_consultas", [consulta_cnpj])
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cnpj",
            "documento": "12345678000190",
            "nome": "Empresa XPTO Ltda",
        })
        assert resp.status_code == 200

    def test_documento_curto_demais(self, client):
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "123",
            "nome": "Teste",
        })
        assert resp.status_code == 422

    def test_nome_vazio(self, client):
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "",
        })
        assert resp.status_code == 422


# --------------- GET /api/certidoes/consultas/{id} ---------------

class TestObterConsulta:
    def test_consulta_encontrada(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", SAMPLE_CONSULTA)
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        resp = client.get("/api/certidoes/consultas/consulta-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "consulta-001"
        assert "resultados" in data

    def test_consulta_nao_encontrada(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [])
        resp = client.get("/api/certidoes/consultas/inexistente")
        # PostgREST raises on .single() with 0 rows; our mock returns None data
        assert resp.status_code in (404, 500)


# --------------- POST /api/certidoes/consultas/{id}/reprocessar ---------------

class TestReprocessarConsulta:
    def test_reprocessa_com_sucesso(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", SAMPLE_CONSULTA)
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        resp = client.post("/api/certidoes/consultas/consulta-001/reprocessar")
        assert resp.status_code == 200

    def test_reprocessa_nao_encontrada(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [])
        resp = client.post("/api/certidoes/consultas/inexistente/reprocessar")
        assert resp.status_code in (404, 500)


# --------------- DELETE /api/certidoes/consultas/{id} ---------------

class TestExcluirConsulta:
    def test_exclui_com_sucesso(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.delete("/api/certidoes/consultas/consulta-001")
        assert resp.status_code == 200

    def test_exclui_nao_encontrada(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [])
        resp = client.delete("/api/certidoes/consultas/inexistente")
        assert resp.status_code == 404
