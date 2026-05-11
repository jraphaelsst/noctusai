"""
Rate-limit smoke tests for media-scheduling OAuth — added by
`auth-rate-limit-rollout-2026-05-11`.

Coverage:
  - GET  /oauth/google/init      @ 10/min
  - POST /oauth/google/init      @ 10/min
  - GET  /oauth/google/callback  @ 10/min

The audit-status route (`GET /api/oauth/google/status`) is gated by
the admin role dep — out of scope per the brief.

The `reset_rate_limiter` autouse fixture (re-imported from
`noctusai_lib.testing.fixtures` in `conftest.py`) clears the
in-memory slowapi counters before/after every test.
"""


class TestOAuthInitRateLimits:
    def test_init_get_rate_limited(self, client):
        # Endpoint 503s when env not configured; we don't care — limiter
        # fires before route logic. Just need to hit 11×.
        responses = [client.get("/oauth/google/init", follow_redirects=False) for _ in range(11)]
        assert responses[-1].status_code == 429

    def test_init_post_rate_limited(self, client):
        responses = [client.post("/oauth/google/init") for _ in range(11)]
        assert responses[-1].status_code == 429


class TestOAuthCallbackRateLimit:
    def test_callback_rate_limited(self, client):
        responses = [client.get("/oauth/google/callback") for _ in range(11)]
        assert responses[-1].status_code == 429
