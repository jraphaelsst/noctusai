"""Rate-limit smoke test for email_marketing /api/email-marketing/ai/* — added by
`llm-endpoint-rate-limit-rollout-2026-05-11`.

Confirms the `@limiter.limit("30/minute")` decorator on
`POST /api/ai/subjects` short-circuits with 429 once the per-minute
window is exhausted. Asserts on `.status_code` per the
status-code-assertion rule.

The limiter is module-level state — `limiter.reset()` clears the
in-memory counters so this test is isolated from any prior call within
the suite (see `noctusai_lib.testing.framework_test_suites` notes on
shared limiter pollution).
"""
from unittest.mock import AsyncMock, patch


class TestEmailMarketingAIRateLimit:
    def test_subjects_rate_limited_at_30_per_minute(self, client):
        """31 successive POSTs to /api/ai/subjects — last one trips 429.

        Mirrors `dev-team/backend/tests/test_api_smoke.py::test_run_team_over_limit_returns_429`.
        """
        # The limiter is module-level state across the entire test session;
        # reset before driving the 31-call burst so we're isolated.
        from app.rate_limit import limiter
        limiter.reset()

        with patch(
            "app.modules.email_marketing.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = (
                '[{"text": "subj-1", "tone": "neutral"}]'
            )
            # Fixed one-minute windows: a burst that straddles a minute
            # boundary splits its count, so stop at the FIRST 429 (at most
            # 61 calls ⇒ a full window is always exhausted) instead of
            # assuming the 31st call lands in the same window as the 1st.
            statuses = []
            for _ in range(61):
                resp = client.post(
                    "/api/email-marketing/ai/subjects", json={"campaign_summary": "test"}
                )
                statuses.append(resp.status_code)
                if resp.status_code == 429:
                    break

        assert statuses[-1] == 429, f"no 429 within 61 calls: {set(statuses)}"
        allowed = statuses[:-1]
        assert set(allowed) == {200}, f"non-200 before the limit: {set(allowed)}"
        assert len(allowed) >= 30, f"limit tripped after only {len(allowed)} calls (expected 30/minute)"
