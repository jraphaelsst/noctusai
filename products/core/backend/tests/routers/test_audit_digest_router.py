"""Router-level tests for the audit-log digest endpoints (Phase 9)."""
from unittest.mock import AsyncMock, patch


class TestSendDigestEndpoint:
    def test_admin_can_trigger_send(self, admin_client):
        with patch(
            "app.services.audit_digest_service.send_weekly_audit_digest",
            new_callable=AsyncMock,
            return_value={
                "sent": 2,
                "results": [
                    {"recipient": "a@x", "sent": True, "dry_run": False, "external_id": "1", "error": None},
                    {"recipient": "b@x", "sent": True, "dry_run": False, "external_id": "2", "error": None},
                ],
                "summary": {"total_events": 25, "period_days": 7, "actions_top": [], "high_priority_count": 0, "narrative_chars": 100},
                "subject": "[NoctusAI] Digest semanal — Acme",
            },
        ):
            resp = admin_client.post("/api/admin/audit-digest/org-1")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["sent"] == 2
        assert len(body["results"]) == 2

    def test_non_admin_rejected(self, client):
        resp = client.post("/api/admin/audit-digest/org-1")
        assert resp.status_code == 403

    def test_org_not_found_returns_404(self, admin_client):
        with patch(
            "app.services.audit_digest_service.send_weekly_audit_digest",
            new_callable=AsyncMock,
            return_value={"sent": 0, "results": [], "summary": None, "error": "org_not_found"},
        ):
            resp = admin_client.post("/api/admin/audit-digest/missing-org")
        assert resp.status_code == 404


class TestPreviewDigestEndpoint:
    def test_preview_returns_subject_html_text(self, admin_client):
        from noctusai_lib.integrations.email.digest import Digest

        async def _fake_build(db, *, org_id, period_days):
            return (
                Digest(
                    subject=f"[NoctusAI] Digest — Org-{org_id}",
                    text="Resumo simples.",
                    html="<p>Resumo simples.</p>",
                ),
                [{"id": "a1", "email": "a@x", "role": "admin"}],
                {"total_events": 5, "period_days": 7, "actions_top": [], "high_priority_count": 0, "narrative_chars": 12},
            )

        with patch(
            "app.services.audit_digest_service.build_digest",
            side_effect=_fake_build,
        ):
            resp = admin_client.get("/api/admin/audit-digest/org-1/preview")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "Org-org-1" in data["subject"]
        assert data["recipients"] == ["a@x"]
        assert "Resumo simples" in data["text"]
        assert data["summary"]["total_events"] == 5

    def test_preview_org_not_found_returns_404(self, admin_client):
        with patch(
            "app.services.audit_digest_service.build_digest",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = admin_client.get("/api/admin/audit-digest/missing/preview")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Consent guards — consent-guard-rollout Phase 6 (2026-04-27)
#
# `core.audit_digest` is registered with `default_granted=True` (admin-tier,
# low-risk: only aggregates + privileged-action highlights enter the prompt).
# Existing happy-path tests above pass via the default-grant path. These
# tests verify the guard fires when an admin has explicitly revoked consent.
# ---------------------------------------------------------------------------


class TestConsentGuards:
    def test_send_returns_412_when_admin_revoked_consent(self, admin_client):
        # Seed a revoked decision for the admin user — guard must block before
        # the digest service is reached.
        admin_client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "core.audit_digest",
            "granted": False, "user_id": "admin-user-456",
            "granted_at": None, "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.audit_digest_service.send_weekly_audit_digest",
            new_callable=AsyncMock,
        ) as mock_svc:
            resp = admin_client.post("/api/admin/audit-digest/org-1")
        assert resp.status_code == 412
        body_text = str(resp.json()).lower()
        assert "consentimento" in body_text or "consent" in body_text
        mock_svc.assert_not_called()

    def test_preview_returns_412_when_admin_revoked_consent(self, admin_client):
        admin_client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "core.audit_digest",
            "granted": False, "user_id": "admin-user-456",
            "granted_at": None, "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.audit_digest_service.build_digest",
            new_callable=AsyncMock,
        ) as mock_svc:
            resp = admin_client.get("/api/admin/audit-digest/org-1/preview")
        assert resp.status_code == 412
        mock_svc.assert_not_called()
