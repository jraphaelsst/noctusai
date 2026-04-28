"""Router-level integration tests for /api/ai/* (mailing).

Tier 1.5 G1 hardening, 2026-04-24. Each test exercises the full FastAPI
request → router → service path; service-level FakeProvider tests live
separately in tests/services/test_ai_service.py.
"""
from unittest.mock import patch, AsyncMock


class TestSubjectsEndpoint:
    def test_returns_variants(self, client):
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = (
                '[{"text": "50% off só hoje", "tone": "urgência"},'
                ' {"text": "Você sabia?", "tone": "curiosidade"}]'
            )
            resp = client.post(
                "/api/ai/subjects", json={"campaign_summary": "Black Friday"}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "variants" in body["data"]
        assert len(body["data"]["variants"]) == 2

    def test_no_auth_rejects(self, client):
        resp = client.raw().post("/api/ai/subjects", json={"campaign_summary": "x"})
        assert resp.status_code == 401


class TestTemplateDraftEndpoint:
    def test_returns_html(self, client):
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = "<h1>Welcome</h1>"
            resp = client.post(
                "/api/ai/template-draft", json={"prompt": "welcome email"}
            )
        assert resp.status_code == 200
        assert "<h1>Welcome</h1>" in resp.json()["data"]["html"]


class TestReengagementEndpoint:
    def test_returns_three_variants(self, client):
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = (
                '['
                ' {"tone": "leve", "subject": "Tá sumido!", "body_html": "<p>oi</p>"},'
                ' {"tone": "direto", "subject": "Vamos conversar", "body_html": "<p>x</p>"},'
                ' {"tone": "valor", "subject": "Um presente", "body_html": "<p>y</p>"}'
                ']'
            )
            resp = client.post(
                "/api/ai/reengagement", json={"context": "inativos 90d+"}
            )
        assert resp.status_code == 200
        variants = resp.json()["data"]["variants"]
        assert len(variants) == 3


class TestDeliverabilityEndpoint:
    def test_returns_findings(self, client):
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = (
                '{"findings": [{"code": "risky_phrasing", "severity": "warning",'
                ' "message": "CLIQUE AQUI"}]}'
            )
            resp = client.post(
                "/api/ai/deliverability",
                json={"html": "<p>CLIQUE AQUI</p>", "subject": "Oi"},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["findings"][0]["code"] == "risky_phrasing"


class TestTranslateEndpoint:
    def test_translates_to_english(self, client):
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = "<p>Hello {{name}}</p>"
            resp = client.post(
                "/api/ai/translate",
                json={"html": "<p>Olá {{name}}</p>", "target_lang": "en"},
            )
        assert resp.status_code == 200
        assert "Hello" in resp.json()["data"]["html"]
        assert "{{name}}" in resp.json()["data"]["html"]

    def test_unsupported_lang_returns_original(self, client):
        # Service short-circuits before calling chat_completion for unsupported langs.
        resp = client.post(
            "/api/ai/translate",
            json={"html": "<p>Olá</p>", "target_lang": "jp"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["html"] == "<p>Olá</p>"


# ---------------------------------------------------------------------------
# M3 — Contact segmentation (ai-expansion Phase 8)
# ---------------------------------------------------------------------------


class TestSegmentContactsEndpoint:

    def test_segments_active_contacts_and_persists(self, client):
        client._mock_supabase.set_table_data("contacts", [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "email": "a@x.com",
                "nome": "Ana",
                "empresa": "ACME",
                "tags": ["vip"],
                "custom_fields": {},
                "status": "active",
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "email": "b@x.com",
                "nome": "Bruno",
                "empresa": "Beta",
                "tags": ["churn"],
                "custom_fields": {},
                "status": "active",
            },
        ])

        with patch(
            "app.services.segmentation_service.segment_contacts",
            new_callable=AsyncMock,
            return_value=[
                {
                    "_contact_id": "11111111-1111-1111-1111-111111111111",
                    "kind": "classification",
                    "label": "Clientes ativos",
                    "chip": "ATIVOS",
                    "explanation": None,
                    "confidence": None,
                    "score": None,
                    "model_version": "gpt-4o-mini",
                    "prompt_version": "mailing-segment@v1",
                    "metadata": {"cluster": 0},
                },
                {
                    "_contact_id": "22222222-2222-2222-2222-222222222222",
                    "kind": "classification",
                    "label": "Em risco de churn",
                    "chip": "CHURN RISCO",
                    "explanation": None,
                    "confidence": None,
                    "score": None,
                    "model_version": "gpt-4o-mini",
                    "prompt_version": "mailing-segment@v1",
                    "metadata": {"cluster": 1},
                },
            ],
        ), patch(
            "app.routers.ai.persist_output",
            side_effect=lambda db, schema, output: {
                **output.to_insert_payload(),
                "id": f"ai-{output.ref_id[:4]}",
            },
        ) as persist_mock:
            resp = client.post("/api/ai/segment-contacts", json={})

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["segmented"] == 2
        assert len(body["persisted"]) == 2
        labels = sorted(p["label"] for p in body["persisted"])
        assert labels == ["Clientes ativos", "Em risco de churn"]
        assert persist_mock.call_count == 2

    def test_no_active_contacts_returns_zero(self, client):
        client._mock_supabase.set_table_data("contacts", [])
        resp = client.post("/api/ai/segment-contacts", json={})
        assert resp.status_code == 200
        assert resp.json()["data"]["segmented"] == 0

    def test_list_id_with_no_members_returns_404(self, client):
        client._mock_supabase.set_table_data("contact_list_members", [])
        resp = client.post(
            "/api/ai/segment-contacts",
            json={"list_id": "33333333-3333-3333-3333-333333333333"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# M4 — Campaign debrief (Phase 12)
# ---------------------------------------------------------------------------


class TestCampaignDebriefEndpoints:
    def test_preview_returns_subject_html_summary(self, client):
        from noctusai_lib.email.digest import Digest

        async def _fake_build(db, *, campaign_id, org_id):
            return (
                Digest(
                    subject=f"[NoctusAI] Debrief — Campanha {campaign_id}",
                    text="Resumo simples.",
                    html="<p>Resumo simples.</p>",
                ),
                {
                    "campaign_id": campaign_id,
                    "campaign_name": "BFCM",
                    "metrics": {"sent": 100, "open_rate": 30.0},
                    "top_links": [],
                    "narrative": "Panorama.",
                },
            )

        with patch(
            "app.services.campaign_debrief_service.build_debrief",
            side_effect=_fake_build,
        ):
            resp = client.get("/api/ai/campaigns/c1/debrief")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert "Debrief" in body["subject"]
        assert body["summary"]["campaign_name"] == "BFCM"

    def test_preview_404_when_campaign_missing(self, client):
        with patch(
            "app.services.campaign_debrief_service.build_debrief",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/api/ai/campaigns/missing/debrief")
        assert resp.status_code == 404

    def test_send_endpoint_returns_outcome(self, client):
        with patch(
            "app.services.campaign_debrief_service.send_campaign_debrief",
            new_callable=AsyncMock,
            return_value={
                "sent": True, "dry_run": False, "external_id": "id-1",
                "error": None, "subject": "x", "summary": {"metrics": {"sent": 1}},
            },
        ):
            resp = client.post(
                "/api/ai/campaigns/c1/debrief/send",
                json={"recipient": "u@x"},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["sent"] is True

    def test_send_404_when_campaign_missing(self, client):
        with patch(
            "app.services.campaign_debrief_service.send_campaign_debrief",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(
                "/api/ai/campaigns/missing/debrief/send",
                json={"recipient": "u@x"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Consent guards — consent-guard-rollout Phase 2 (2026-04-27)
#
# Each endpoint mounts `Depends(consent_required("<feature_key>"))`. Tests
# below confirm: (a) a stored revoked decision blocks the call with HTTP 412
# AIConsentRequired, (b) the default-granted=True catalog default is what
# lets the existing happy-path tests above pass without a stored decision.
# ---------------------------------------------------------------------------


class TestConsentGuards:
    def test_subjects_returns_412_when_user_revoked_consent(self, client):
        # Seed a revoke decision for mailing.subject_gen — the consent_required
        # dep should raise AIConsentRequired (412) BEFORE the body executes.
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "mailing.subject_gen",
            "granted": False,
            "user_id": "test-user-123",
            "granted_at": None,
            "revoked_at": "2026-04-27T00:00:00Z",
        }])
        # If the guard fires correctly, chat_completion is never called.
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            resp = client.post(
                "/api/ai/subjects", json={"campaign_summary": "Black Friday"}
            )
        assert resp.status_code == 412
        # Body should reference AI consent — framework formats AIConsentRequired
        body_text = str(resp.json()).lower()
        assert "consentimento" in body_text or "consent" in body_text
        # And the LLM should never have been invoked.
        mock_chat.assert_not_called()

    def test_segment_contacts_returns_412_when_user_revoked_consent(self, client):
        # Different endpoint shape (uses get_user_client + complex body) — same
        # guard. Verifies the dep mounts correctly across endpoint patterns.
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "mailing.segment_contacts",
            "granted": False,
            "user_id": "test-user-123",
            "granted_at": None,
            "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.segmentation_service.segment_contacts",
            new_callable=AsyncMock,
        ) as mock_seg:
            resp = client.post(
                "/api/ai/segment-contacts", json={"list_id": "list-1"}
            )
        assert resp.status_code == 412
        mock_seg.assert_not_called()

    def test_default_granted_path_lets_request_through(self, client):
        # No stored decision for mailing.template_draft + catalog default is
        # True → guard passes silently → endpoint runs normally.
        client._mock_supabase.set_table_data("ai_consent", [])  # no decisions
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = "<h1>Welcome</h1>"
            resp = client.post(
                "/api/ai/template-draft", json={"prompt": "welcome email"}
            )
        assert resp.status_code == 200
        # LLM was actually called (not blocked by guard).
        mock_chat.assert_called_once()
