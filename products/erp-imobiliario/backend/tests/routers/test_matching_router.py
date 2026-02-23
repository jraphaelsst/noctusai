"""
Tests for Matching router — /api/matching
"""
import pytest


class TestGerarMatches:
    def test_gerar_matches_missing_ids(self, client):
        resp = client.post("/api/matching/gerar", json={"score_minimo": 20})
        assert resp.status_code == 422


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
