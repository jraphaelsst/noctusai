"""Public (unauthenticated) endpoints are rate limited per client IP.

Token-gated / org-id-addressed endpoints have no auth to throttle abuse
(lead-spam into any org, token guessing), so slowapi limits apply.
Bodies must still bind as bodies (422 on bad payload, not a Query fallback).
"""
from uuid import uuid4

TOKEN = str(uuid4())
ORG = "00000000-0000-0000-0000-000000000001"


def _hammer(send, limit_plus):
    codes = [send().status_code for _ in range(limit_plus)]
    return codes


class TestPublicRateLimits:
    def test_capture_is_rate_limited(self, client):
        codes = _hammer(
            lambda: client.raw().post(f"/api/capture/{ORG}", json={"name": "x"}), 25
        )
        assert 429 in codes
        assert codes[0] != 429

    def test_capture_body_still_validated_as_body(self, client):
        resp = client.raw().post(f"/api/capture/{ORG}", json={"email": "not-an-email"})
        assert resp.status_code == 422

    def test_public_report_is_rate_limited(self, client):
        codes = _hammer(lambda: client.raw().get(f"/api/reports/public/{TOKEN}"), 35)
        assert 429 in codes
        assert codes[0] != 429

    def test_approval_get_is_rate_limited(self, client):
        codes = _hammer(lambda: client.raw().get(f"/api/content/approve/{TOKEN}"), 35)
        assert 429 in codes
        assert codes[0] != 429

    def test_approval_post_is_rate_limited_and_body_validated(self, client):
        bad = client.raw().post(f"/api/content/approve/{TOKEN}", json={"decision": "nope"})
        assert bad.status_code == 422
        codes = _hammer(
            lambda: client.raw().post(f"/api/content/approve/{TOKEN}", json={"decision": "approved"}),
            15,
        )
        assert 429 in codes
