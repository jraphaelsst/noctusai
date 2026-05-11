"""Rate-limit smoke test for daily-life /api/ai/* — added by
`llm-endpoint-rate-limit-rollout-2026-05-11`.

Confirms the `@limiter.limit("30/minute")` decorator on
`GET /api/ai/daily-brief` short-circuits with 429 once the per-minute
window is exhausted. Asserts on `.status_code` per the
status-code-assertion rule.

The limiter is module-level state — `limiter.reset()` clears the
in-memory counters so this test is isolated from any prior call within
the suite.
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _grant_daily_brief_consent(client):
    """Daily Life consents are `default_granted=False` — without explicit
    grants every endpoint returns 412 long before slowapi gets to count.
    Pre-seed daily_brief consent so the limiter is what triggers, not the
    consent gate."""
    client._mock_supabase.set_table_data("ai_consent", [
        {
            "feature_key": "daily_life.daily_brief",
            "granted": True,
            "user_id": "test-user-123",
            "granted_at": "2026-05-11T00:00:00Z",
            "revoked_at": None,
        },
    ])


class TestDailyLifeAIRateLimit:
    def test_daily_brief_rate_limited_at_30_per_minute(self, client):
        """31 successive GETs to /api/ai/daily-brief — last one trips 429."""
        # The limiter is module-level state across the entire test session;
        # reset before driving the 31-call burst so we're isolated.
        from app.rate_limit import limiter
        limiter.reset()

        async def _fake_build(db, *, user_id, user_label, org_id):
            return {
                "chip": "Bom dia",
                "summary": "Tudo certo.",
                "tasks_today": [],
                "events_today": [],
                "habits_pending": [],
                "yesterday_completed": [],
            }

        with patch(
            "app.services.daily_brief_service.build_brief",
            side_effect=_fake_build,
        ):
            statuses = []
            for _ in range(31):
                resp = client.get("/api/ai/daily-brief")
                statuses.append(resp.status_code)

        # First 30 should succeed; 31st should be rate-limited.
        assert statuses[:30] == [200] * 30, (
            f"first 30 expected 200, got distribution {set(statuses[:30])}"
        )
        assert statuses[30] == 429, f"31st call expected 429, got {statuses[30]}"
