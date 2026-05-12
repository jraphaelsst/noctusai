"""
Tests for the Gamificacao (Gamification) router — /api/gamificacao
Covers leaderboard, points history, achievements, point registration, and rules.
"""
import pytest
from unittest.mock import patch


class TestLeaderboard:
    def test_leaderboard_geral(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [
            {"user_id": "u1", "pontos": 100, "created_at": "2026-02-01T00:00:00"},
            {"user_id": "u1", "pontos": 50, "created_at": "2026-02-10T00:00:00"},
            {"user_id": "u2", "pontos": 80, "created_at": "2026-02-05T00:00:00"},
        ])
        client._mock_supabase.set_table_data("profiles", [
            {"id": "u1", "nome": "Ana", "avatar_url": None},
            {"id": "u2", "nome": "Carlos", "avatar_url": None},
        ])
        resp = client.get("/api/gamificacao/leaderboard")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_leaderboard_semana(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        client._mock_supabase.set_table_data("profiles", [])
        resp = client.get("/api/gamificacao/leaderboard?periodo=semana")
        assert resp.status_code == 200

    def test_leaderboard_mes(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        client._mock_supabase.set_table_data("profiles", [])
        resp = client.get("/api/gamificacao/leaderboard?periodo=mes")
        assert resp.status_code == 200

    def test_leaderboard_empty(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        client._mock_supabase.set_table_data("profiles", [])
        resp = client.get("/api/gamificacao/leaderboard")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_leaderboard_invalid_periodo(self, client):
        resp = client.get("/api/gamificacao/leaderboard?periodo=invalido")
        assert resp.status_code == 422


class TestMeusPontos:
    def test_pontos_success(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [
            {"id": "p1", "user_id": "test-user-123", "acao": "novo_cliente", "pontos": 10},
            {"id": "p2", "user_id": "test-user-123", "acao": "visita_realizada", "pontos": 15},
        ])
        resp = client.get("/api/gamificacao/pontos")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_pontos_empty(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        resp = client.get("/api/gamificacao/pontos")
        assert resp.status_code == 200

    def test_pontos_pagination(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        resp = client.get("/api/gamificacao/pontos?page=1&page_size=10")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 10


class TestMinhasConquistas:
    def test_conquistas_success(self, client):
        client._mock_supabase.set_table_data("conquistas", [
            {"tipo": "primeiro_passo", "desbloqueada_em": "2026-01-15T10:00:00"},
        ])
        resp = client.get("/api/gamificacao/conquistas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        # Should include all badge definitions with locked/unlocked state
        assert len(data) > 0

    def test_conquistas_all_locked(self, client):
        client._mock_supabase.set_table_data("conquistas", [])
        resp = client.get("/api/gamificacao/conquistas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        for badge in data:
            assert badge["desbloqueada"] is False

    def test_conquistas_unlocked_has_date(self, client):
        client._mock_supabase.set_table_data("conquistas", [
            {"tipo": "primeiro_passo", "desbloqueada_em": "2026-01-15T10:00:00"},
        ])
        resp = client.get("/api/gamificacao/conquistas")
        assert resp.status_code == 200
        data = resp.json()["data"]
        primeiro = next((b for b in data if b["tipo"] == "primeiro_passo"), None)
        assert primeiro is not None
        assert primeiro["desbloqueada"] is True
        assert "desbloqueada_em" in primeiro


class TestRegistrarPontos:
    def test_registrar_success(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        client._mock_supabase.set_table_data("conquistas", [])
        resp = client.post("/api/gamificacao/registrar", json={
            "acao": "novo_cliente",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pontos"] == 10
        assert data["acao"] == "novo_cliente"

    def test_registrar_with_referencia(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        client._mock_supabase.set_table_data("conquistas", [])
        resp = client.post("/api/gamificacao/registrar", json={
            "acao": "visita_realizada",
            "referencia_id": "visit-123",
            "referencia_tipo": "visita",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["pontos"] == 15

    def test_registrar_venda_fechada(self, client):
        client._mock_supabase.set_table_data("pontuacoes", [])
        client._mock_supabase.set_table_data("conquistas", [])
        resp = client.post("/api/gamificacao/registrar", json={
            "acao": "venda_fechada",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["pontos"] == 100

    def test_registrar_acao_desconhecida(self, client):
        resp = client.post("/api/gamificacao/registrar", json={
            "acao": "acao_inexistente",
        })
        assert resp.status_code == 400

    def test_registrar_missing_acao(self, client):
        resp = client.post("/api/gamificacao/registrar", json={})
        assert resp.status_code == 422


class TestRegras:
    def test_regras_success(self, client):
        resp = client.get("/api/gamificacao/regras")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "pontos_por_acao" in data
        assert "conquistas_disponiveis" in data
        assert "novo_cliente" in data["pontos_por_acao"]
        assert len(data["conquistas_disponiveis"]) > 0

    def test_regras_conquistas_structure(self, client):
        resp = client.get("/api/gamificacao/regras")
        assert resp.status_code == 200
        data = resp.json()["data"]
        for conquista in data["conquistas_disponiveis"]:
            assert "tipo" in conquista
            assert "nome" in conquista
            assert "descricao" in conquista
            assert "icone" in conquista


class TestNoAuth:
    def test_no_token_leaderboard(self, client):
        from fastapi.testclient import TestClient
        from app.main import app
        tc = TestClient(app)
        resp = tc.get("/api/gamificacao/leaderboard")
        assert resp.status_code == 401
