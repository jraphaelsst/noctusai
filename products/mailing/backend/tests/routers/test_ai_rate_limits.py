"""Rate-limit smoke test for mailing /api/ai/* — added by
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


class TestMailingAIRateLimit:
    def test_subjects_rate_limited_at_30_per_minute(self, client):
        """31 successive POSTs to /api/ai/subjects — last one trips 429.

        Mirrors `dev-team/backend/tests/test_api_smoke.py::test_run_team_over_limit_returns_429`.
        """
        # The limiter is module-level state across the entire test session;
        # reset before driving the 31-call burst so we're isolated.
        from app.rate_limit import limiter
        limiter.reset()

        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = (
                '[{"text": "subj-1", "tone": "neutral"}]'
            )
            statuses = []
            for _ in range(31):
                resp = client.post(
                    "/api/ai/subjects", json={"campaign_summary": "test"}
                )
                statuses.append(resp.status_code)

        # First 30 should succeed; 31st should be rate-limited.
        assert statuses[:30] == [200] * 30, (
            f"first 30 expected 200, got distribution {set(statuses[:30])}"
        )
        assert statuses[30] == 429, f"31st call expected 429, got {statuses[30]}"
