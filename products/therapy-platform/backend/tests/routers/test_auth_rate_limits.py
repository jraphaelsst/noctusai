"""
Rate-limit smoke test for therapy-platform auth /me — added by
`auth-rate-limit-rollout-2026-05-11`.

Existing decorators (already shipped before this rollout) cover register
(10/min × 3), login (30/min), google (30/min), forgot-password (5/min).
Only `/me` was uncovered. The brief asks for defense-in-depth even on
otherwise-orphaned routes (THE-P9 noted 7 are orphans wire-wise).

The `reset_rate_limiter` autouse fixture (re-imported from
`noctusai_lib.testing.fixtures` in `conftest.py`) clears the
in-memory slowapi counters before/after every test.
"""


class TestAuthMeRateLimit:
    def test_get_me_rate_limited(self, client):
        responses = [client.get("/api/auth/me") for _ in range(31)]
        assert responses[-1].status_code == 429
