"""Tests for the Certidões Negativas router."""
import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import MockSupabaseResponse

_CRED_PATCH_TARGET = "app.routers.certidoes.check_required_credentials"


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
    "total_certidoes": 10,
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
        assert len(data) == 10
        assert data[0]["tipo"] == "cnd_federal"
        assert data[0]["nome"] == "CND Federal (Receita)"

    def test_cada_tipo_tem_campos_obrigatorios(self, client):
        resp = client.get("/api/certidoes/tipos")
        for item in resp.json()["data"]:
            assert "tipo" in item
            assert "nome" in item
            assert "ordem" in item

    def test_ordem_sequencial(self, client):
        resp = client.get("/api/certidoes/tipos")
        ordens = [t["ordem"] for t in resp.json()["data"]]
        assert ordens == list(range(1, 11))


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

    def test_busca_e_status_combinados(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.get("/api/certidoes/consultas?busca=João&status=pendente")
        assert resp.status_code == 200

    def test_paginacao_params(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.get("/api/certidoes/consultas?page=2&page_size=10")
        assert resp.status_code == 200
        pagination = resp.json()["pagination"]
        assert pagination["page"] == 2
        assert pagination["page_size"] == 10

    def test_paginacao_retorna_total(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.get("/api/certidoes/consultas")
        assert "pagination" in resp.json()
        assert "total" in resp.json()["pagination"]

    def test_page_invalida(self, client):
        resp = client.get("/api/certidoes/consultas?page=0")
        assert resp.status_code == 422

    def test_page_size_invalida(self, client):
        resp = client.get("/api/certidoes/consultas?page_size=0")
        assert resp.status_code == 422

    def test_page_size_excede_maximo(self, client):
        resp = client.get("/api/certidoes/consultas?page_size=999")
        assert resp.status_code == 422


# --------------- POST /api/certidoes/consultas ---------------

class TestCriarConsulta:
    """Tests that bypass credential check (validation tests + happy path)."""

    @pytest.fixture(autouse=True)
    def _bypass_credentials(self):
        with patch(_CRED_PATCH_TARGET, return_value=[]):
            yield

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

    def test_cria_consulta_com_todos_campos_opcionais(self, client):
        consulta_full = {
            **SAMPLE_CONSULTA,
            "genero": "M",
            "rg": "123456789",
            "nome_mae": "Maria da Silva",
            "nome_pai": "José da Silva",
        }
        client._mock_supabase.set_table_data("certidao_consultas", [consulta_full])
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "João da Silva",
            "data_nascimento": "1990-01-15",
            "genero": "M",
            "rg": "123456789",
            "nome_mae": "Maria da Silva",
            "nome_pai": "José da Silva",
        })
        assert resp.status_code == 200

    def test_resposta_inclui_resultados(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "João da Silva",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "resultados" in data

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

    def test_nome_curto_demais(self, client):
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "A",
        })
        assert resp.status_code == 422

    def test_tipo_documento_invalido(self, client):
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "rg",
            "documento": "12345678901",
            "nome": "Teste da Silva",
        })
        assert resp.status_code == 422

    def test_genero_invalido(self, client):
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "Teste da Silva",
            "genero": "X",
        })
        assert resp.status_code == 422

    def test_campos_obrigatorios_ausentes(self, client):
        resp = client.post("/api/certidoes/consultas", json={})
        assert resp.status_code == 422

    def test_documento_longo_demais(self, client):
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "1" * 19,
            "nome": "Teste da Silva",
        })
        assert resp.status_code == 422

    def test_insert_falha_retorna_500(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [])
        resp = client.post("/api/certidoes/consultas", json={
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "Teste da Silva",
        })
        assert resp.status_code == 500

    def test_log_action_chamado(self, client):
        mock_log = MagicMock()
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        with patch("app.routers.certidoes.log_action", mock_log):
            client.post("/api/certidoes/consultas", json={
                "tipo_documento": "cpf",
                "documento": "12345678901",
                "nome": "João da Silva",
            })
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][1] == "criar"
        assert call_args[0][2] == "certidao_consulta"


# --------------- POST /api/certidoes/consultas (credential validation) ----

class TestCriarConsultaCredenciais:
    def test_rejeita_sem_infosimples_token(self, client):
        with patch(
            _CRED_PATCH_TARGET,
            return_value=["Token InfoSimples não configurado — necessário para emissão de certidões."],
        ):
            resp = client.post("/api/certidoes/consultas", json={
                "tipo_documento": "cpf",
                "documento": "12345678901",
                "nome": "Teste da Silva",
            })
        assert resp.status_code == 422
        error_msg = resp.json()["error"]["message"]
        assert "InfoSimples" in error_msg
        assert "Configurações" in error_msg

    def test_aceita_com_credenciais_configuradas(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        with patch(_CRED_PATCH_TARGET, return_value=[]):
            resp = client.post("/api/certidoes/consultas", json={
                "tipo_documento": "cpf",
                "documento": "12345678901",
                "nome": "João da Silva",
            })
        assert resp.status_code == 200


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

    def test_consulta_retorna_resultados_lista(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", SAMPLE_CONSULTA)
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        resp = client.get("/api/certidoes/consultas/consulta-001")
        data = resp.json()["data"]
        assert isinstance(data["resultados"], list)

    def test_consulta_sem_resultados(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", SAMPLE_CONSULTA)
        client._mock_supabase.set_table_data("certidao_resultados", [])
        resp = client.get("/api/certidoes/consultas/consulta-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["resultados"] == []


# --------------- POST /api/certidoes/consultas/{id}/reprocessar ---------------

class TestReprocessarConsulta:
    def test_reprocessa_com_sucesso(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", SAMPLE_CONSULTA)
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        with patch("app.routers.certidoes.schedule_tjsp_for_org"):
            resp = client.post("/api/certidoes/consultas/consulta-001/reprocessar")
        assert resp.status_code == 200

    def test_reprocessa_nao_encontrada(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [])
        resp = client.post("/api/certidoes/consultas/inexistente/reprocessar")
        assert resp.status_code in (404, 500)

    def test_reprocessa_retorna_mensagem(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", SAMPLE_CONSULTA)
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        with patch("app.routers.certidoes.schedule_tjsp_for_org"):
            resp = client.post("/api/certidoes/consultas/consulta-001/reprocessar")
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body

    def test_reprocessa_log_action(self, client):
        mock_log = MagicMock()
        client._mock_supabase.set_table_data("certidao_consultas", SAMPLE_CONSULTA)
        client._mock_supabase.set_table_data("certidao_resultados", [SAMPLE_RESULTADO])
        with patch("app.routers.certidoes.log_action", mock_log), \
             patch("app.routers.certidoes.schedule_tjsp_for_org"):
            client.post("/api/certidoes/consultas/consulta-001/reprocessar")
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][1] == "editar"
        assert call_args[0][2] == "certidao_consulta"


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

    def test_exclui_retorna_mensagem(self, client):
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        resp = client.delete("/api/certidoes/consultas/consulta-001")
        body = resp.json()
        assert "message" in body

    def test_exclui_log_action(self, client):
        mock_log = MagicMock()
        client._mock_supabase.set_table_data("certidao_consultas", [SAMPLE_CONSULTA])
        with patch("app.routers.certidoes.log_action", mock_log):
            client.delete("/api/certidoes/consultas/consulta-001")
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][1] == "excluir"
        assert call_args[0][2] == "certidao_consulta"
