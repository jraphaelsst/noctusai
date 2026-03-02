"""
Tests for the Site Imoveis (Property Website Builder) router.
Covers config CRUD, preview, and public site endpoints.
"""
import pytest
from tests.conftest import MockSupabaseResponse


class TestObterConfig:
    def test_get_config_exists(self, client):
        client._mock_supabase.set_table_data("site_config", [
            {
                "id": "sc1",
                "org_id": "org1",
                "nome_site": "Imobiliaria ABC",
                "slug": "imob-abc",
                "cor_primaria": "#6366f1",
                "cor_secundaria": "#1a1a2e",
                "is_active": True,
            },
        ])
        resp = client.get("/api/site/config")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome_site"] == "Imobiliaria ABC"

    def test_get_config_empty(self, client):
        client._mock_supabase.set_table_data("site_config", [])
        resp = client.get("/api/site/config")
        assert resp.status_code == 200
        assert resp.json()["data"] is None


class TestCriarConfig:
    def _setup_sequential_responses(self, client, table, responses):
        """Set up sequential execute() responses via the response queue."""
        client._mock_supabase.set_sequential_responses(table, responses)

    def test_create_success(self, client):
        # 1st call: existence check → empty (no config yet)
        # 2nd call: slug uniqueness check (admin) → empty (slug available)
        # 3rd call: insert result
        self._setup_sequential_responses(client, "site_config", [
            MockSupabaseResponse(data=[]),  # existence check
            MockSupabaseResponse(data=[]),  # slug uniqueness check
            MockSupabaseResponse(data={
                "id": "sc-new", "nome_site": "Nova Imobiliaria",
                "slug": "nova-imob", "cor_primaria": "#6366f1",
                "cor_secundaria": "#1a1a2e", "is_active": True,
            }),
        ])
        resp = client.post("/api/site/config", json={
            "nome_site": "Nova Imobiliaria",
            "slug": "nova-imob",
        })
        assert resp.status_code == 200

    def test_create_with_all_fields(self, client):
        # 1st call: existence check → empty
        # 2nd call: slug uniqueness check → empty
        # 3rd call: insert result
        self._setup_sequential_responses(client, "site_config", [
            MockSupabaseResponse(data=[]),  # existence check
            MockSupabaseResponse(data=[]),  # slug uniqueness check
            MockSupabaseResponse(data={
                "id": "sc-full", "nome_site": "Full Config",
                "slug": "full-config", "cor_primaria": "#ff0000",
                "cor_secundaria": "#00ff00", "telefone": "11999999999",
                "whatsapp": "11999999999", "email_contato": "contato@test.com",
                "sobre": "Descricao da imobiliaria", "is_active": True,
            }),
        ])
        resp = client.post("/api/site/config", json={
            "nome_site": "Full Config",
            "slug": "full-config",
            "cor_primaria": "#ff0000",
            "cor_secundaria": "#00ff00",
            "telefone": "11999999999",
            "whatsapp": "11999999999",
            "email_contato": "contato@test.com",
            "sobre": "Descricao da imobiliaria",
        })
        assert resp.status_code == 200

    def test_create_missing_nome(self, client):
        resp = client.post("/api/site/config", json={
            "slug": "test-slug",
        })
        assert resp.status_code == 422

    def test_create_missing_slug(self, client):
        resp = client.post("/api/site/config", json={
            "nome_site": "Test Site",
        })
        assert resp.status_code == 422

    def test_create_invalid_slug_uppercase(self, client):
        resp = client.post("/api/site/config", json={
            "nome_site": "Test Site",
            "slug": "Invalid-Slug",
        })
        assert resp.status_code == 422

    def test_create_invalid_slug_spaces(self, client):
        resp = client.post("/api/site/config", json={
            "nome_site": "Test Site",
            "slug": "has spaces",
        })
        assert resp.status_code == 422

    def test_create_invalid_slug_short(self, client):
        resp = client.post("/api/site/config", json={
            "nome_site": "Test Site",
            "slug": "ab",
        })
        assert resp.status_code == 422

    def test_create_invalid_cor_primaria(self, client):
        resp = client.post("/api/site/config", json={
            "nome_site": "Test Site",
            "slug": "test-site",
            "cor_primaria": "red",
        })
        assert resp.status_code == 422

    def test_create_invalid_cor_secundaria(self, client):
        resp = client.post("/api/site/config", json={
            "nome_site": "Test Site",
            "slug": "test-site",
            "cor_secundaria": "#GGG",
        })
        assert resp.status_code == 422


class TestAtualizarConfig:
    def test_update_nome(self, client):
        client._mock_supabase.set_table_data("site_config", [
            {"id": "sc1"},
        ])
        resp = client.patch("/api/site/config", json={
            "nome_site": "Nome Atualizado",
        })
        assert resp.status_code == 200

    def test_update_slug(self, client):
        client._mock_supabase.set_table_data("site_config", [
            {"id": "sc1"},
        ])
        resp = client.patch("/api/site/config", json={
            "slug": "novo-slug",
        })
        assert resp.status_code == 200

    def test_update_empty_body(self, client):
        resp = client.patch("/api/site/config", json={})
        assert resp.status_code == 400

    def test_update_not_found(self, client):
        client._mock_supabase.set_table_data("site_config", [])
        resp = client.patch("/api/site/config", json={
            "nome_site": "Updated",
        })
        assert resp.status_code == 404

    def test_update_invalid_slug(self, client):
        resp = client.patch("/api/site/config", json={
            "slug": "INVALID",
        })
        assert resp.status_code == 422

    def test_update_invalid_color(self, client):
        resp = client.patch("/api/site/config", json={
            "cor_primaria": "not-a-color",
        })
        assert resp.status_code == 422

    def test_update_toggle_active(self, client):
        client._mock_supabase.set_table_data("site_config", [
            {"id": "sc1"},
        ])
        resp = client.patch("/api/site/config", json={
            "is_active": False,
        })
        assert resp.status_code == 200


class TestPreviewSite:
    def test_preview_success(self, client):
        client._mock_supabase.set_table_data("site_config", [
            {"id": "sc1", "nome_site": "Test Site", "slug": "test", "is_active": True},
        ])
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1", "tipo_imovel": "apartamento", "valor": 500000, "status": "ativo"},
        ])
        resp = client.get("/api/site/preview")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "config" in data
        assert "imoveis" in data

    def test_preview_no_config(self, client):
        client._mock_supabase.set_table_data("site_config", [])
        client._mock_supabase.set_table_data("ativos", [])
        resp = client.get("/api/site/preview")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["config"] is None


class TestSitePublico:
    def test_site_publico_success(self, client):
        client._mock_supabase.set_table_data("site_config", {
            "id": "sc1",
            "org_id": "org1",
            "nome_site": "Imobiliaria ABC",
            "slug": "imob-abc",
            "cor_primaria": "#6366f1",
            "cor_secundaria": "#1a1a2e",
            "is_active": True,
            "created_at": "2026-01-01T00:00:00Z",
        })
        client._mock_supabase.set_table_data("ativos", [
            {"id": "a1", "tipo_imovel": "apartamento", "valor": 500000},
        ])
        resp = client._tc.get("/api/site/public/imob-abc")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "config" in data
        assert "imoveis" in data
        # Sensitive fields should be removed
        assert "id" not in data["config"]
        assert "org_id" not in data["config"]

    def test_site_publico_not_found(self, client):
        client._mock_supabase.set_table_data("site_config", None)
        resp = client._tc.get("/api/site/public/nonexistent-slug")
        assert resp.status_code == 404


class TestSiteImovelDetalhe:
    def test_imovel_detalhe_success(self, client):
        client._mock_supabase.set_table_data("site_config", {
            "id": "sc1",
            "org_id": "org1",
            "whatsapp": "11999999999",
            "telefone": "1133334444",
            "email_contato": "contato@test.com",
        })
        client._mock_supabase.set_table_data("ativos", {
            "id": "a1",
            "tipo_imovel": "apartamento",
            "valor": 500000,
            "cidade": "Sao Paulo",
            "pronto_para_portais": True,
            "status": "ativo",
        })
        resp = client._tc.get("/api/site/public/imob-abc/imovel/a1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "imovel" in data
        assert "contato" in data
        assert data["contato"]["whatsapp"] == "11999999999"

    def test_imovel_detalhe_site_not_found(self, client):
        client._mock_supabase.set_table_data("site_config", None)
        resp = client._tc.get("/api/site/public/bad-slug/imovel/a1")
        assert resp.status_code == 404

    def test_imovel_detalhe_imovel_not_found(self, client):
        client._mock_supabase.set_table_data("site_config", {
            "id": "sc1",
            "org_id": "org1",
            "whatsapp": None,
            "telefone": None,
            "email_contato": None,
        })
        client._mock_supabase.set_table_data("ativos", None)
        resp = client._tc.get("/api/site/public/imob-abc/imovel/nonexistent")
        assert resp.status_code == 404
