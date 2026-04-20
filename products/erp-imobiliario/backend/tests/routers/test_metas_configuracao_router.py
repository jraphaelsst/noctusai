"""
Tests for /api/metas/configuracao — per-org scoring configuration.
"""
from __future__ import annotations

import pytest


class TestObterConfig:
    def test_get_saved_config(self, client):
        client._mock_supabase.set_table_data("metas_configuracao", [
            {
                "org_id": "test-org-123",
                "vgv_por_ponto": 15000,
                "peso_pontos": 1.0,
                "peso_vgv": 1.5,
                "metrica_ranking_padrao": "vgv",
            }
        ])
        resp = client.get("/api/metas/configuracao")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert float(data["vgv_por_ponto"]) == 15000
        assert data["metrica_ranking_padrao"] == "vgv"

    def test_get_returns_virtual_defaults_when_unsaved(self, client):
        client._mock_supabase.set_table_data("metas_configuracao", [])
        resp = client.get("/api/metas/configuracao")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert float(data["vgv_por_ponto"]) == 10000   # default
        assert data["metrica_ranking_padrao"] == "unificado"


class TestUpsertConfig:
    def test_update_vgv_por_ponto(self, client):
        client._mock_supabase.set_table_data("metas_configuracao", {
            "org_id": "test-org-123",
            "vgv_por_ponto": 20000,
            "peso_pontos": 1.0,
            "peso_vgv": 1.0,
            "metrica_ranking_padrao": "unificado",
        })
        resp = client.put("/api/metas/configuracao", json={"vgv_por_ponto": 20000})
        assert resp.status_code == 200

    def test_reject_nonpositive_vgv_por_ponto(self, client):
        resp = client.put("/api/metas/configuracao", json={"vgv_por_ponto": 0})
        assert resp.status_code == 422

    def test_reject_negative_peso(self, client):
        resp = client.put("/api/metas/configuracao", json={"peso_pontos": -0.5})
        assert resp.status_code == 422

    def test_reject_invalid_ranking_metric(self, client):
        resp = client.put("/api/metas/configuracao", json={"metrica_ranking_padrao": "random"})
        assert resp.status_code == 422
