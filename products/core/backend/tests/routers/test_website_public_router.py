"""Tests for `app.routers.website_public` — `/api/website/*` (contract §3)."""
from tests.conftest import website_defaults_dict


def _seed_leads_tables(mock_sb):
    mock_sb.set_table_data("website_leads", [])
    mock_sb.set_table_data("website_lead_activities", [])
    mock_sb.set_table_data("website_events", [])


class TestGetSettings:
    def test_returns_public_subset_and_version(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = unauth_client.get("/api/website/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == 0
        assert "trust_items" in body["data"]
        # verified_by must never reach the public client (LGPD-adjacent).
        assert all("verified_by" not in item for item in body["data"]["trust_items"])
        assert "hidden-product" not in {p["slug"] for p in body["data"]["products"]}


class TestGetPlans:
    def test_only_active_plans_ordered_by_price(self, unauth_client):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("plans", [
            {"id": "p2", "slug": "pro", "nome": "Pro", "descricao": "", "price_monthly": 200,
             "price_yearly": 2000, "max_users": 10, "max_products": 5, "features": {}, "is_custom": False, "ativo": True},
            {"id": "p1", "slug": "starter", "nome": "Starter", "descricao": "", "price_monthly": 50,
             "price_yearly": 500, "max_users": 2, "max_products": 1, "features": {}, "is_custom": False, "ativo": True},
            {"id": "p3", "slug": "hidden", "nome": "Hidden", "descricao": "", "price_monthly": 10,
             "price_yearly": 100, "max_users": 1, "max_products": 1, "features": {}, "is_custom": False, "ativo": False},
        ])
        resp = unauth_client.get("/api/website/plans")
        assert resp.status_code == 200
        slugs = [p["slug"] for p in resp.json()["data"]]
        assert "hidden" not in slugs


class TestCreateLead:
    def test_success_returns_id_and_whatsapp_url(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        _seed_leads_tables(mock_sb)
        resp = unauth_client.post("/api/website/leads", json={
            "source": "waitlist", "name": "Ana Silva", "email": "ana@example.com",
            "locale": "pt-BR", "consent_marketing": True, "consent_text_version": "v1",
        })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "id" in data
        assert data["whatsapp_url"].startswith("https://wa.me/5511999999999")

    def test_missing_contact_returns_422(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        _seed_leads_tables(mock_sb)
        resp = unauth_client.post("/api/website/leads", json={
            "source": "contact", "name": "No Contact",
            "locale": "pt-BR", "consent_marketing": False, "consent_text_version": "v1",
        })
        assert resp.status_code == 422

    def test_extra_field_rejected_by_strict_schema(self, unauth_client, website_site):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        _seed_leads_tables(mock_sb)
        resp = unauth_client.post("/api/website/leads", json={
            "source": "waitlist", "name": "Ana", "email": "ana@example.com",
            "locale": "pt-BR", "consent_marketing": True, "consent_text_version": "v1",
            "unexpected_field": "boom",
        })
        assert resp.status_code == 422

    def test_turnstile_failure_returns_403_when_configured(self, unauth_client, website_site, monkeypatch):
        from app.config import settings

        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        _seed_leads_tables(mock_sb)
        settings.website_turnstile_secret = "a-real-secret"
        try:
            resp = unauth_client.post("/api/website/leads", json={
                "source": "waitlist", "name": "Ana", "email": "ana@example.com",
                "locale": "pt-BR", "consent_marketing": True, "consent_text_version": "v1",
                "turnstile_token": "",
            })
        finally:
            settings.website_turnstile_secret = ""
        assert resp.status_code == 403
        assert resp.json()["detail"] == "turnstile_failed"


class TestCreateEvent:
    def test_success_returns_204(self, unauth_client):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_events", [])
        resp = unauth_client.post("/api/website/events", json={"event": "page_view", "path": "/"})
        assert resp.status_code == 204

    def test_bad_event_name_shape_rejected(self, unauth_client):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_events", [])
        resp = unauth_client.post("/api/website/events", json={"event": "Not Valid!"})
        assert resp.status_code == 422

    def test_props_over_2kb_rejected(self, unauth_client):
        mock_sb = unauth_client.mock_supabase
        mock_sb.set_table_data("website_events", [])
        resp = unauth_client.post("/api/website/events", json={
            "event": "cta_click", "props": {"big": "x" * 3000},
        })
        assert resp.status_code == 422
