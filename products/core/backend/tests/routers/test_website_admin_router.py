"""Tests for `app.routers.website_admin` — `/api/admin/website/*` (contract §3)."""
from tests.conftest import website_defaults_dict


class TestGetSettings:
    def test_unauth_401(self, unauth_client):
        resp = unauth_client.get("/api/admin/website/settings")
        assert resp.status_code == 401

    def test_non_editor_user_403(self, client):
        resp = client.get(
            "/api/admin/website/settings", headers={"Authorization": "Bearer test-token"}
        )
        assert resp.status_code == 403

    def test_marketing_user_can_read(self, marketing_client, website_site):
        mock_sb = marketing_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = marketing_client.get(
            "/api/admin/website/settings", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["version"] == 0

    def test_admin_can_read(self, admin_client, website_site):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = admin_client.get(
            "/api/admin/website/settings", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 200


class TestPutSettings:
    def test_version_conflict_409(self, admin_client, website_site):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_settings", [{"version": 5, "data": website_defaults_dict()}])
        resp = admin_client.put(
            "/api/admin/website/settings",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"settings": website_defaults_dict(), "expected_version": 1},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "version_conflict"

    def test_social_proof_shape_422(self, admin_client, website_site):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        bad = website_defaults_dict()
        bad["sections"]["social_proof"] = True
        bad["social_proof_items"] = []
        resp = admin_client.put(
            "/api/admin/website/settings",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"settings": bad, "expected_version": 0},
        )
        assert resp.status_code == 422

    def test_marketing_cannot_change_site_enabled(self, marketing_client, website_site):
        mock_sb = marketing_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        changed = website_defaults_dict()
        changed["site_enabled"] = False
        resp = marketing_client.put(
            "/api/admin/website/settings",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"settings": changed, "expected_version": 0},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "admin_only_field"

    def test_marketing_can_change_other_fields(self, marketing_client, website_site):
        mock_sb = marketing_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        changed = website_defaults_dict()
        changed["faq"] = [{"q": {"pt": "Novo?", "en": "New?"}, "a": {"pt": "Sim", "en": "Yes"}}]
        resp = marketing_client.put(
            "/api/admin/website/settings",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"settings": changed, "expected_version": 0},
        )
        assert resp.status_code == 200

    def test_admin_success_bumps_version(self, admin_client, website_site):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = admin_client.put(
            "/api/admin/website/settings",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"settings": website_defaults_dict(), "expected_version": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["version"] == 1


class TestRollback:
    def test_marketing_403(self, marketing_client, website_site):
        resp = marketing_client.post(
            "/api/admin/website/settings/rollback",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"version": 1},
        )
        assert resp.status_code == 403

    def test_missing_version_404(self, admin_client, website_site):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_settings", [])
        resp = admin_client.post(
            "/api/admin/website/settings/rollback",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"version": 99},
        )
        assert resp.status_code == 404


class TestLeads:
    def test_list_leads(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_leads", [
            {"id": "l1", "stage": "novo", "source": "waitlist", "created_at": "2026-01-01"},
        ])
        resp = admin_client.get(
            "/api/admin/website/leads", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_get_lead_404(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_leads", [])
        resp = admin_client.get(
            "/api/admin/website/leads/missing", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 404

    def test_get_lead_includes_activities(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_leads", [{"id": "l1", "stage": "novo"}])
        mock_sb.set_table_data("website_lead_activities", [{"id": "a1", "lead_id": "l1", "kind": "created"}])
        resp = admin_client.get(
            "/api/admin/website/leads/l1", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["activities"][0]["id"] == "a1"

    def test_patch_lead_stage_change(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_leads", [{"id": "l1", "stage": "novo"}])
        mock_sb.set_table_data("website_lead_activities", [])
        resp = admin_client.patch(
            "/api/admin/website/leads/l1",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"stage": "contatado"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["stage"] == "contatado"

    def test_patch_lead_empty_body_422(self, admin_client):
        resp = admin_client.patch(
            "/api/admin/website/leads/l1",
            headers={"Authorization": "Bearer test-token-valid"},
            json={},
        )
        assert resp.status_code == 422

    def test_add_activity(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_leads", [{"id": "l1"}])
        mock_sb.set_table_data("website_lead_activities", [])
        resp = admin_client.post(
            "/api/admin/website/leads/l1/activities",
            headers={"Authorization": "Bearer test-token-valid"},
            json={"kind": "note", "body": "Ligar amanhã"},
        )
        assert resp.status_code == 201

    def test_export_csv_marketing_403(self, marketing_client):
        resp = marketing_client.get(
            "/api/admin/website/leads/export.csv", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 403

    def test_export_csv_admin_ok(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_leads", [
            {"id": "l1", "created_at": "2026-01-01", "source": "waitlist", "name": "Ana",
             "email": "a@x.com", "phone_e164": None, "company": None, "profile": None,
             "product_interest": [], "locale": "pt-BR", "stage": "novo", "owner_user_id": None,
             "score": None, "next_action": None, "next_action_at": None, "lost_reason": None},
        ])
        resp = admin_client.get(
            "/api/admin/website/leads/export.csv", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "Ana" in resp.text

    def test_stats(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("website_leads", [])
        mock_sb.set_table_data("website_events", [])
        resp = admin_client.get(
            "/api/admin/website/stats", headers={"Authorization": "Bearer test-token-valid"}
        )
        assert resp.status_code == 200
        assert "new_today" in resp.json()["data"]
