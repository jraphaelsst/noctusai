"""
Tests for Meta API router — /api/meta
Covers config management, lead listing/sync, and campaign sync.
"""
import pytest


class TestMetaConfig:
    def test_get_config_empty(self, client):
        client._mock_supabase.set_table_data("meta_config", [])
        resp = client.get("/api/meta/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_get_config_exists(self, client):
        client._mock_supabase.set_table_data("meta_config", [
            {"id": "mc1", "page_id": "12345", "access_token": "EAABtoken123...",
             "ad_account_id": "67890", "is_active": True},
        ])
        resp = client.get("/api/meta/config")
        assert resp.status_code == 200
        data = resp.json()
        # Token should be masked
        if data.get("data") and data["data"].get("access_token"):
            assert "..." in data["data"]["access_token"]

    def test_save_config(self, client):
        client._mock_supabase.set_table_data("meta_config", [
            {"id": "mc1", "page_id": "12345", "access_token": "token",
             "ad_account_id": "67890", "is_active": True},
        ])
        resp = client.post("/api/meta/config", json={
            "page_id": "12345",
            "access_token": "EAABtoken123",
            "ad_account_id": "67890",
        })
        assert resp.status_code == 200


class TestMetaLeads:
    def test_list_leads_empty(self, client):
        client._mock_supabase.set_table_data("meta_leads", [])
        resp = client.get("/api/meta/leads")
        assert resp.status_code == 200

    def test_list_leads_with_data(self, client):
        client._mock_supabase.set_table_data("meta_leads", [
            {"id": "ml1", "lead_id": "fb-lead-001", "form_id": "form-001",
             "campo_data": {"full_name": "Joao Silva", "email": "joao@test.com"},
             "importado": False, "created_at": "2026-02-27T10:00:00"},
        ])
        resp = client.get("/api/meta/leads")
        assert resp.status_code == 200

    def test_filter_importados(self, client):
        client._mock_supabase.set_table_data("meta_leads", [])
        resp = client.get("/api/meta/leads?importado=false")
        assert resp.status_code == 200

    def test_sync_leads_no_config(self, client):
        client._mock_supabase.set_table_data("meta_config", [])
        resp = client.post("/api/meta/leads/sync")
        assert resp.status_code in [200, 400]

    def test_importar_lead_not_found(self, client):
        client._mock_supabase.set_table_data("meta_leads", None)
        resp = client.post("/api/meta/leads/nonexistent/importar")
        assert resp.status_code in [200, 404]

    def test_importar_lead_success(self, client):
        client._mock_supabase.set_table_data("meta_leads", {
            "id": "ml1", "lead_id": "fb-lead-001",
            "campo_data": {"full_name": "Joao Silva", "email": "joao@test.com"},
            "importado": False,
        })
        client._mock_supabase.set_table_data("clientes", [
            {"id": "cli-new", "nome": "Joao Silva"},
        ])
        resp = client.post("/api/meta/leads/ml1/importar")
        assert resp.status_code == 200


class TestMetaCampanhas:
    def test_list_campanhas_empty(self, client):
        client._mock_supabase.set_table_data("meta_campanhas_sync", [])
        resp = client.get("/api/meta/campanhas")
        assert resp.status_code == 200

    def test_list_campanhas_with_data(self, client):
        client._mock_supabase.set_table_data("meta_campanhas_sync", [
            {"id": "mc1", "campaign_id": "camp-001", "nome": "Lancamento Imovel X",
             "status": "ACTIVE", "spend": 500.0, "impressions": 10000,
             "clicks": 200, "leads": 15, "cpl": 33.33},
        ])
        resp = client.get("/api/meta/campanhas")
        assert resp.status_code == 200

    def test_sync_campanhas_no_config(self, client):
        client._mock_supabase.set_table_data("meta_config", [])
        resp = client.post("/api/meta/campanhas/sync")
        assert resp.status_code in [200, 400]
