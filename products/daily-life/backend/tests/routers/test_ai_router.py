"""Router-level tests for the Daily Life AI endpoints (Phase 11 D6).

Daily Life's AI features are HIGH-RISK personal narrative / clinical-adjacent
data — registered with `default_granted=False` per §7.2 rubric. Existing
happy-path tests in this file pre-seed `ai_consent` with `granted=True` rows
via the autouse fixture below; the `TestConsentGuards` class at the end
covers the revoked + default-revoked paths.
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _grant_all_daily_life_consents(client):
    """Pre-seed `ai_consent` with grants for all 3 Daily Life features so
    happy-path tests can run. Daily Life features are `default_granted=False`
    (opt-in only) so without explicit grants every endpoint would return 412."""
    client._mock_supabase.set_table_data("ai_consent", [
        {
            "feature_key": "daily_life.daily_brief",
            "granted": True, "user_id": "test-user-123",
            "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None,
        },
        {
            "feature_key": "daily_life.weekly_review",
            "granted": True, "user_id": "test-user-123",
            "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None,
        },
        {
            "feature_key": "daily_life.note_extract",
            "granted": True, "user_id": "test-user-123",
            "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None,
        },
    ])


class TestWeeklyReview:
    def test_get_returns_digest_and_summary(self, client):
        from noctusai_lib.integrations.email.digest import Digest

        async def _fake_build(db, *, user_id, user_label, org_id, period_days):
            return (
                Digest(
                    subject=f"[NoctusAI] Sua semana — {user_label}",
                    text="Resumo simples.",
                    html="<p>Resumo simples.</p>",
                ),
                {
                    "tasks_completed": 3,
                    "tasks_pending": 2,
                    "tasks_cancelled": 1,
                    "habit_streaks": [("Correr", 3)],
                    "notas_count": 4,
                    "focus_minutes": 120,
                    "narrative": "Panorama.",
                    "period_label": "Últimos 7 dias",
                },
            )

        with patch(
            "app.services.weekly_review_service.build_review",
            side_effect=_fake_build,
        ):
            resp = client.get("/api/ai/weekly-review")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "Resumo simples" in data["text"]
        assert data["summary"]["tasks_completed"] == 3


class TestDailyBrief:
    def test_returns_chip_summary_and_counters(self, client):
        with patch(
            "app.services.daily_brief_service.build_brief",
            new_callable=AsyncMock,
            return_value={
                "chip": "3 tarefas · 1 hábito",
                "summary": "Hoje você tem 3 tarefas pendentes.",
                "tasks_today": 3,
                "events_today": 0,
                "habits_pending": 1,
                "yesterday_completed": 5,
                "prompt_version": "daily-life-daily-brief@v1",
            },
        ):
            resp = client.get("/api/ai/daily-brief")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["chip"] == "3 tarefas · 1 hábito"
        assert "3 tarefas" in data["summary"]
        assert data["tasks_today"] == 3
        assert data["yesterday_completed"] == 5


# ---------------------------------------------------------------------------
# Consent guards — consent-guard-rollout Phase 4 (2026-04-27)
#
# Daily Life features are HIGH-RISK (personal narrative / clinical-adjacent)
# and `default_granted=False` — opt-in only. The autouse fixture above
# pre-grants for happy-path tests; here we override to test the revoked /
# default-revoked paths.
# ---------------------------------------------------------------------------


class TestConsentGuards:
    def test_daily_brief_returns_412_when_revoked(self, client):
        # Override the autouse fixture's grant with a revoked decision.
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "daily_life.daily_brief",
            "granted": False, "user_id": "test-user-123",
            "granted_at": None, "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.daily_brief_service.build_brief", new_callable=AsyncMock
        ) as mock_svc:
            resp = client.get("/api/ai/daily-brief")
        assert resp.status_code == 412
        body_text = str(resp.json()).lower()
        assert "consentimento" in body_text or "consent" in body_text
        mock_svc.assert_not_called()

    def test_weekly_review_returns_412_when_revoked(self, client):
        client._mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "daily_life.weekly_review",
            "granted": False, "user_id": "test-user-123",
            "granted_at": None, "revoked_at": "2026-04-27T00:00:00Z",
        }])
        with patch(
            "app.services.weekly_review_service.build_review", new_callable=AsyncMock
        ) as mock_svc:
            resp = client.get("/api/ai/weekly-review")
        assert resp.status_code == 412
        mock_svc.assert_not_called()

    def test_daily_brief_returns_412_when_no_decision_and_default_false(self, client):
        # No stored decision + default_granted=False → guard fails-closed (412).
        # This is the OPT-IN-only path for high-risk features.
        client._mock_supabase.set_table_data("ai_consent", [])  # empty
        with patch(
            "app.services.daily_brief_service.build_brief", new_callable=AsyncMock
        ) as mock_svc:
            resp = client.get("/api/ai/daily-brief")
        assert resp.status_code == 412
        mock_svc.assert_not_called()
