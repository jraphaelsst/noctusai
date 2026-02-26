"""
Tests for Metas router — /api/metas
"""
import pytest


class TestListarMetas:
    def test_list_metas(self, client):
        client._mock_supabase.set_table_data("metas", [
            {"id": "m1", "categoria": "captacao", "meta_pretendida": 10},
        ])
        resp = client.get("/api/metas")
        assert resp.status_code == 200

    def test_list_by_corretor(self, client):
        resp = client.get("/api/metas?corretor_id=user-123")
        assert resp.status_code == 200


class TestCriarMeta:
    def test_create_meta(self, client):
        client._mock_supabase.set_table_data("metas", {"id": "m-new", "categoria": "contatos"})
        resp = client.post("/api/metas", json={
            "categoria": "contatos",
            "tipo": "diaria",
            "meta_pretendida": 10,
            "data_prazo": "2026-02-23",
        })
        assert resp.status_code == 200

    def test_create_meta_missing_fields(self, client):
        resp = client.post("/api/metas", json={"categoria": "captacao"})
        assert resp.status_code == 422


class TestAtualizarMeta:
    def test_update_meta(self, client):
        client._mock_supabase.set_table_data("metas", {"id": "m1", "meta_realizada": 5})
        resp = client.patch("/api/metas/m1", json={"meta_realizada": 5})
        assert resp.status_code == 200


class TestExcluirMeta:
    def test_delete_meta(self, client):
        resp = client.delete("/api/metas/m1")
        assert resp.status_code == 200
