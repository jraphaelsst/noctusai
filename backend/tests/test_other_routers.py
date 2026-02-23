"""
Tests for Profiles, Metas, Atividades, Funil, and Action Log routers.
"""
import pytest
from unittest.mock import MagicMock


# ========== PROFILES ==========
class TestProfiles:
    def test_list_profiles(self, client):
        client._mock_supabase.set_table_data("profiles", [
            {"id": "p1", "nome": "Admin", "email": "admin@test.com"},
        ])
        resp = client.get("/api/profiles")
        assert resp.status_code == 200

    def test_create_profile_success(self, client):
        # Mock admin.createUser
        client._mock_supabase.auth.admin = type("Admin", (), {
            "create_user": lambda self, data: type("Res", (), {"user": type("U", (), {"id": "new-user"})()})()
        })()
        resp = client.post("/api/profiles", json={
            "nome": "novo corretor",
            "email": "novo@test.com",
            "telefone": "11999999999",
            "password": "senha123456",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "Novo Corretor"  # capitalized

    def test_create_profile_missing_password(self, client):
        resp = client.post("/api/profiles", json={
            "nome": "Test", "email": "test@test.com",
        })
        assert resp.status_code == 422

    def test_create_profile_missing_email(self, client):
        resp = client.post("/api/profiles", json={
            "nome": "Test", "password": "123456",
        })
        assert resp.status_code == 422

    def test_update_profile(self, client):
        client._mock_supabase.set_table_data("profiles", {"id": "p1", "nome": "Updated"})
        resp = client.patch("/api/profiles/p1", json={"nome": "Updated Name"})
        assert resp.status_code == 200

    def test_update_empty(self, client):
        resp = client.patch("/api/profiles/p1", json={})
        assert resp.status_code == 400

    def test_delete_profile_secure(self, client):
        client._mock_supabase.set_table_data("profiles", {"nome": "ToDelete"})
        client._mock_supabase.auth.admin = MagicMock()
        client._mock_supabase.auth.admin.delete_user = MagicMock(return_value=None)
        resp = client.delete("/api/profiles/p1")
        assert resp.status_code == 200


# ========== METAS ==========
class TestMetas:
    def test_list_metas(self, client):
        client._mock_supabase.set_table_data("metas", [
            {"id": "m1", "categoria": "ligacao", "quantidade_alvo": 10},
        ])
        resp = client.get("/api/metas")
        assert resp.status_code == 200

    def test_list_by_corretor(self, client):
        resp = client.get("/api/metas?corretor_id=user-123")
        assert resp.status_code == 200

    def test_create_meta(self, client):
        client._mock_supabase.set_table_data("metas", {"id": "m-new", "categoria": "ligacao"})
        resp = client.post("/api/metas", json={
            "categoria": "ligacao",
            "tipo_meta": "diaria",
            "quantidade_alvo": 10,
            "data_referencia": "2026-02-23",
        })
        assert resp.status_code == 200

    def test_create_meta_missing_fields(self, client):
        resp = client.post("/api/metas", json={"categoria": "ligacao"})
        assert resp.status_code == 422

    def test_update_meta(self, client):
        client._mock_supabase.set_table_data("metas", {"id": "m1", "quantidade_realizada": 5})
        resp = client.patch("/api/metas/m1", json={"quantidade_realizada": 5})
        assert resp.status_code == 200

    def test_delete_meta(self, client):
        resp = client.delete("/api/metas/m1")
        assert resp.status_code == 200


# ========== ATIVIDADES ==========
class TestAtividades:
    def test_list_atividades(self, client):
        client._mock_supabase.set_table_data("atividades", [
            {"id": "a1", "tipo": "ligacao", "descricao": "Ligou para cliente"},
        ])
        resp = client.get("/api/atividades?cliente_id=c1")
        assert resp.status_code == 200

    def test_list_without_cliente_id(self, client):
        resp = client.get("/api/atividades")
        assert resp.status_code == 200

    def test_create_atividade(self, client):
        client._mock_supabase.set_table_data("atividades", {"id": "a-new", "tipo": "visita"})
        resp = client.post("/api/atividades", json={
            "cliente_id": "c1",
            "tipo": "visita",
            "descricao": "Visita ao imóvel",
        })
        assert resp.status_code == 200

    def test_create_atividade_missing_descricao(self, client):
        resp = client.post("/api/atividades", json={"cliente_id": "c1", "tipo": "ligacao"})
        assert resp.status_code == 422

    def test_create_atividade_with_date(self, client):
        client._mock_supabase.set_table_data("atividades", {"id": "a-date", "tipo": "ligacao"})
        resp = client.post("/api/atividades", json={
            "cliente_id": "c1", "tipo": "ligacao",
            "descricao": "Follow-up", "data_execucao": "2026-02-23T10:00:00",
        })
        assert resp.status_code == 200


# ========== FUNIL ==========
class TestFunil:
    def test_get_funil(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "João", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 100000, "email": None, "telefone": None},
            {"id": "c2", "nome": "Maria", "etapa_atual": "proposta",
             "kanban_pos": 0, "valor_estimado": 200000, "email": None, "telefone": None},
        ])
        resp = client.get("/api/funil")
        assert resp.status_code == 200
        colunas = resp.json()["data"]
        assert len(colunas) == 5  # 5 etapas
        etapas = [c["etapa"] for c in colunas]
        assert "qualificacao" in etapas
        assert "proposta" in etapas

    def test_funil_grouping_correct(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "A", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 50000, "email": None, "telefone": None},
            {"id": "c2", "nome": "B", "etapa_atual": "qualificacao",
             "kanban_pos": 1, "valor_estimado": 100000, "email": None, "telefone": None},
        ])
        resp = client.get("/api/funil")
        colunas = resp.json()["data"]
        qualificacao = next(c for c in colunas if c["etapa"] == "qualificacao")
        assert qualificacao["total"] == 2
        assert qualificacao["valorTotal"] == 150000

    def test_funil_search_filters(self, client):
        client._mock_supabase.set_table_data("clientes", [
            {"id": "c1", "nome": "João Silva", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 0, "email": None, "telefone": None},
            {"id": "c2", "nome": "Maria Santos", "etapa_atual": "qualificacao",
             "kanban_pos": 0, "valor_estimado": 0, "email": None, "telefone": None},
        ])
        resp = client.get("/api/funil?busca=joão")
        colunas = resp.json()["data"]
        total_cards = sum(c["total"] for c in colunas)
        assert total_cards == 1

    def test_funil_empty(self, client):
        client._mock_supabase.set_table_data("clientes", [])
        resp = client.get("/api/funil")
        colunas = resp.json()["data"]
        assert all(c["total"] == 0 for c in colunas)


# ========== ACTION LOG ==========
class TestActionLog:
    def test_list_logs(self, client):
        client._mock_supabase.set_table_data("user_actions_log", [
            {"id": "l1", "usuario_id": "u1", "tipo_acao": "criar",
             "tipo_entidade": "cliente", "descricao": "Criou cliente"},
        ])
        client._mock_supabase.set_table_data("profiles", [
            {"id": "u1", "nome": "Admin", "email": "admin@test.com"},
        ])
        resp = client.get("/api/logs")
        assert resp.status_code == 200

    def test_list_logs_filtered_by_user(self, client):
        resp = client.get("/api/logs?usuario_id=u1")
        assert resp.status_code == 200

    def test_list_logs_filtered_by_date(self, client):
        resp = client.get("/api/logs?data_inicio=2026-01-01T00:00:00Z&data_fim=2026-12-31T23:59:59Z")
        assert resp.status_code == 200


# ========== MATCHING ROUTER ==========
class TestMatchingRouter:
    def test_gerar_matches_missing_ids(self, client):
        resp = client.post("/api/matching/gerar", json={"score_minimo": 20})
        assert resp.status_code == 422

    def test_listar_matches(self, client):
        client._mock_supabase.set_table_data("matches", [
            {"id": "m1", "ativo_origem_id": "a1", "ativo_destino_id": "a2", "score": 75},
        ])
        resp = client.get("/api/matching")
        assert resp.status_code == 200

    def test_atualizar_match_status(self, client):
        client._mock_supabase.set_table_data("matches", [{"id": "m1", "status": "aceito"}])
        resp = client.patch("/api/matching/m1", json={"status": "aceito"})
        assert resp.status_code == 200

    def test_atualizar_match_invalid_status(self, client):
        resp = client.patch("/api/matching/m1", json={"status": "banana"})
        assert resp.status_code == 400


# ========== CONDOMINIOS ==========
class TestCondominiosRouter:
    def test_list_condominios(self, client):
        client._mock_supabase.set_table_data("condominios", [
            {"id": "cond1", "nome": "Edifício Aurora"},
        ])
        resp = client.get("/api/condominios")
        assert resp.status_code == 200
