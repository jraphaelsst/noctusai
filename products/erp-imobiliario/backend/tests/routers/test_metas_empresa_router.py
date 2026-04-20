"""
Tests for the Metas Empresa router — /api/metas/empresa

Covers CRUD + cascade summary. Real RLS is exercised by realdb tests.
"""
from __future__ import annotations

import pytest


class TestListarMetasEmpresa:
    def test_list_returns_200(self, client):
        client._mock_supabase.set_table_data("metas_empresa", [
            {"id": "me1", "periodo_id": "p1", "categoria": "vgv", "valor_meta": 30000000},
        ])
        resp = client.get("/api/metas/empresa")
        assert resp.status_code == 200

    def test_list_filter_by_periodo(self, client):
        client._mock_supabase.set_table_data("metas_empresa", [])
        resp = client.get("/api/metas/empresa?periodo_id=p1")
        assert resp.status_code == 200


class TestUpsertMetaEmpresa:
    def test_create_new(self, client):
        client._mock_supabase.set_table_data("metas_empresa", {
            "id": "me-new",
            "periodo_id": "p1",
            "categoria": "vgv",
            "valor_meta": 30000000,
        })
        resp = client.post("/api/metas/empresa", json={
            "periodo_id": "p1",
            "valor_meta": 30000000,
        })
        assert resp.status_code == 201
        assert float(resp.json()["data"]["valor_meta"]) == 30000000

    def test_negative_valor_rejected(self, client):
        resp = client.post("/api/metas/empresa", json={
            "periodo_id": "p1",
            "valor_meta": -1,
        })
        assert resp.status_code == 422

    def test_missing_periodo_rejected(self, client):
        resp = client.post("/api/metas/empresa", json={"valor_meta": 100})
        assert resp.status_code == 422


class TestResumoCascata:
    def test_resumo_shape(self, client):
        # Empresa has a 30M target; equipes allocated 22M total (10M + 8M + 4M)
        client._mock_supabase.set_table_data("metas_empresa", [
            {"id": "me1", "periodo_id": "p1", "categoria": "vgv", "valor_meta": 30000000}
        ])
        client._mock_supabase.set_table_data("metas_equipe", [
            {"id": "teq1", "periodo_id": "p1", "equipe_id": "e1", "categoria": "vgv", "valor_meta": 10000000},
            {"id": "teq2", "periodo_id": "p1", "equipe_id": "e2", "categoria": "vgv", "valor_meta": 8000000},
            {"id": "teq3", "periodo_id": "p1", "equipe_id": "e3", "categoria": "vgv", "valor_meta": 4000000},
        ])
        resp = client.get("/api/metas/empresa/resumo?periodo_id=p1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["meta_empresa"] == 30000000
        assert data["alocado_em_equipes"] == 22000000
        assert data["saldo_a_alocar"] == 8000000
        assert data["estouro"] == 0
        assert data["equipes_count"] == 3

    def test_resumo_overshoot_shows_estouro(self, client):
        client._mock_supabase.set_table_data("metas_empresa", [
            {"id": "me1", "periodo_id": "p1", "categoria": "vgv", "valor_meta": 10000000}
        ])
        client._mock_supabase.set_table_data("metas_equipe", [
            {"id": "teq1", "periodo_id": "p1", "equipe_id": "e1", "categoria": "vgv", "valor_meta": 6000000},
            {"id": "teq2", "periodo_id": "p1", "equipe_id": "e2", "categoria": "vgv", "valor_meta": 7000000},
        ])
        resp = client.get("/api/metas/empresa/resumo?periodo_id=p1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["alocado_em_equipes"] == 13000000
        assert data["saldo_a_alocar"] == 0
        assert data["estouro"] == 3000000

    def test_resumo_requires_periodo_id(self, client):
        resp = client.get("/api/metas/empresa/resumo")
        assert resp.status_code == 422


class TestObterMetaEmpresa:
    def test_get_missing_returns_404(self, client):
        client._mock_supabase.set_table_data("metas_empresa", [])
        resp = client.get("/api/metas/empresa/ghost")
        assert resp.status_code == 404


class TestAtualizarMetaEmpresa:
    def test_update_valor(self, client):
        client._mock_supabase.set_table_data("metas_empresa", {
            "id": "me1", "valor_meta": 35000000,
        })
        resp = client.patch("/api/metas/empresa/me1", json={"valor_meta": 35000000})
        assert resp.status_code == 200

    def test_negative_rejected(self, client):
        resp = client.patch("/api/metas/empresa/me1", json={"valor_meta": -5})
        assert resp.status_code == 422


class TestDeletarMetaEmpresa:
    def test_delete_existing(self, client):
        client._mock_supabase.set_table_data("metas_empresa", [
            {"id": "me1"}
        ])
        resp = client.delete("/api/metas/empresa/me1")
        assert resp.status_code == 200
