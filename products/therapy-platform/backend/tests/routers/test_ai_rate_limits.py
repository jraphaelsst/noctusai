"""Rate-limit smoke test for therapy-platform AI endpoints — added by
`llm-endpoint-rate-limit-rollout-2026-05-11`.

Confirms the `@limiter.limit("30/minute")` decorator on
`POST /api/matching/embed-paciente` short-circuits with 429 once the
per-minute window is exhausted. Asserts on `.status_code` per the
status-code-assertion rule.

The smoke test drives a 31-call burst against the therapist `client`
fixture — every call returns 403 (therapist trying to embed a patient
profile is not permitted by the router's role check), but slowapi's
decorator runs BEFORE the 403 check, so all 30 still count toward the
window. The 31st must trip 429.

Therapy conftest already auto-resets the limiter between tests via
`_reset_rate_limiter` (autouse) — we still call `limiter.reset()`
explicitly at test start for documentary clarity + isolation from any
prior call within the SAME test.
"""


class TestTherapyAIRateLimit:
    def test_embed_paciente_rate_limited_at_30_per_minute(self, client):
        """31 successive POSTs to /api/matching/embed-paciente — last one trips 429."""
        # The limiter is module-level state; explicit reset (the autouse
        # `_reset_rate_limiter` fixture does this between tests; we do it
        # again here for isolation from any prior call within THIS test).
        from app.rate_limit import limiter
        limiter.reset()

        statuses = []
        for _ in range(31):
            resp = client.post("/api/matching/embed-paciente")
            statuses.append(resp.status_code)

        # First 30 should be 403 (therapist cannot embed patient profile)
        # — the rate-limit decorator runs BEFORE the role check, so all 30
        # still count toward the window.
        assert statuses[:30] == [403] * 30, (
            f"first 30 expected 403, got distribution {set(statuses[:30])}"
        )
        assert statuses[30] == 429, f"31st call expected 429, got {statuses[30]}"
