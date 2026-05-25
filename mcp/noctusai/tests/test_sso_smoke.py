"""Tests for noctus.dev.sso_smoke — the SSO login chain, zero network.

The HTTP layer + creds are injected, so the full pass / mid-chain-fail /
not-configured paths run deterministically without touching Supabase or core.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import sso_smoke as S  # noqa: E402

_CREDS = {
    "supabase_url": "https://proj.supabase.co",
    "service_key": "service-key",
    "anon_key": "anon-key",
    "email": "test@example.com",
}


def _happy_http():
    """A fake HTTP layer that returns the success response for each step."""
    calls: list[tuple[str, str]] = []

    def http(method, url, body, headers):
        calls.append((method, url))
        if url.endswith("/admin/generate_link"):
            return 200, {"email_otp": "otp-123"}
        if url.endswith("/auth/v1/verify"):
            return 200, {"access_token": "core-token"}
        if url.endswith("/api/sso/token"):
            return 200, {"sso_token": "sso-token", "product_slug": "erp-imobiliario"}
        if url.endswith("/api/sso/session"):
            return 200, {"access_token": "prod-token", "email": "test@example.com"}
        if url.endswith("/api/auth/me"):
            return 200, {"email": "test@example.com"}
        raise AssertionError(f"unexpected url {url}")

    return http, calls


def test_full_chain_passes():
    http, calls = _happy_http()
    r = S.sso_smoke(creds=_CREDS, http=http)
    assert r["status"] == "pass"
    assert r["ok"] is True
    assert r["exit_code"] == 0
    assert [s["step"] for s in r["steps"]] == S._STEPS
    assert all(s["ok"] for s in r["steps"])
    # all five steps were actually exercised
    assert len(calls) == 5


def test_not_configured_without_creds():
    """Empty creds → honest not_configured, NEVER a faked pass, no network."""
    def explode(*_a, **_k):
        raise AssertionError("must not hit the network when not configured")

    r = S.sso_smoke(creds={}, http=explode)
    assert r["status"] == "not_configured"
    assert r["ok"] is False
    assert "SUPABASE_URL" in r["missing"]
    assert "email/NOCTUS_SSO_SMOKE_EMAIL" in r["missing"]


def test_license_denied_stops_at_sso_token():
    """A 403 at /api/sso/token (expired/absent license) → fail, chain stops."""
    def http(method, url, body, headers):
        if url.endswith("/admin/generate_link"):
            return 200, {"email_otp": "o"}
        if url.endswith("/auth/v1/verify"):
            return 200, {"access_token": "core-token"}
        if url.endswith("/api/sso/token"):
            return 403, {}
        raise AssertionError("must stop before /api/sso/session")

    r = S.sso_smoke(creds=_CREDS, http=http)
    assert r["status"] == "fail"
    assert r["ok"] is False
    assert r["steps"][-1]["step"] == "core_sso_token"
    assert r["steps"][-1]["ok"] is False


def test_session_exchange_failure_is_caught():
    """A 200-but-no-token at /api/sso/session (the SSOCallback call) → fail."""
    def http(method, url, body, headers):
        if url.endswith("/admin/generate_link"):
            return 200, {"email_otp": "o"}
        if url.endswith("/auth/v1/verify"):
            return 200, {"access_token": "core-token"}
        if url.endswith("/api/sso/token"):
            return 200, {"sso_token": "sso-token"}
        if url.endswith("/api/sso/session"):
            return 200, {}  # no access_token
        raise AssertionError("must stop at /api/sso/session")

    r = S.sso_smoke(creds=_CREDS, http=http)
    assert r["status"] == "fail"
    assert r["steps"][-1]["step"] == "core_sso_session"


def test_identity_mismatch_fails():
    """auth/me returning a different email → fail (identity must match)."""
    http, _ = _happy_http()

    def wrong_me(method, url, body, headers):
        if url.endswith("/api/auth/me"):
            return 200, {"email": "someone-else@example.com"}
        return http(method, url, body, headers)

    r = S.sso_smoke(creds=_CREDS, http=wrong_me)
    assert r["status"] == "fail"
    assert r["steps"][-1]["step"] == "core_auth_me"
    assert r["steps"][-1]["ok"] is False
