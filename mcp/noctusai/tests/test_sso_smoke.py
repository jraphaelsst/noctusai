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


# ── sso_cors_smoke — the leg the chain test structurally cannot cover ─────
#
# `sso_smoke` above is server-to-server: it sends no `Origin` header, so CORS is
# never evaluated and it returns 'pass' while a browser is blocked. That is not
# a bug in it — it is why this second probe exists. On 2026-08-19 p-studio and
# igig were both live, healthy, correctly built, answering 200 on every
# endpoint, and completely unloggable: core's OPTIONS preflight came back 400
# with no allow-origin, so the token exchange never left the browser.

ORIGINS = {"p-studio": "https://p-studio.noctusai.com", "igig": "https://igig.noctusai.com"}


def _preflight(table):
    """Fake preflight: {origin: (status, headers)}."""
    def probe(url, origin):
        return table.get(origin, (0, {"_error": "unreachable"}))
    return probe


def test_allowed_origin_passes():
    r = S.sso_cors_smoke(
        origins=ORIGINS,
        preflight=_preflight({
            o: (200, {"access-control-allow-origin": o}) for o in ORIGINS.values()
        }),
    )
    assert r["status"] == "pass"
    assert r["exit_code"] == 0
    assert r["blocked"] == []


def test_the_actual_incident_a_400_with_no_allow_origin_header():
    """🔴 THE incident, verbatim: core answered 400 and named no origin."""
    r = S.sso_cors_smoke(
        origins=ORIGINS,
        preflight=_preflight({
            "https://p-studio.noctusai.com": (400, {}),
            "https://igig.noctusai.com": (200, {"access-control-allow-origin": "https://igig.noctusai.com"}),
        }),
    )
    assert r["status"] == "fail"
    assert r["blocked"] == ["p-studio"]
    bad = next(x for x in r["results"] if x["product"] == "p-studio")
    # The finding must name the cause and the remedy — "CORS failed" sends the
    # reader back to the browser console they already could not read.
    assert "start.sh" in bad["detail"]
    assert "PRODUCT_URL_P_STUDIO" in bad["detail"]


def test_a_200_without_the_header_is_still_a_block():
    """The trap: browsers require the HEADER, not the status. A probe that
    asserted only `status == 200` would have called the broken state healthy."""
    r = S.sso_cors_smoke(
        origins={"p-studio": ORIGINS["p-studio"]},
        preflight=_preflight({ORIGINS["p-studio"]: (200, {})}),
    )
    assert r["status"] == "fail"


def test_a_wildcard_allow_origin_counts_as_allowed():
    r = S.sso_cors_smoke(
        origins={"p-studio": ORIGINS["p-studio"]},
        preflight=_preflight({ORIGINS["p-studio"]: (204, {"access-control-allow-origin": "*"})}),
    )
    assert r["status"] == "pass"


def test_a_trailing_slash_is_not_a_mismatch():
    r = S.sso_cors_smoke(
        origins={"p-studio": ORIGINS["p-studio"] + "/"},
        preflight=_preflight({ORIGINS["p-studio"]: (200, {"access-control-allow-origin": ORIGINS["p-studio"]})}),
    )
    assert r["status"] == "pass"


def test_an_unreachable_core_is_a_block_not_a_pass():
    r = S.sso_cors_smoke(origins=ORIGINS, preflight=_preflight({}))
    assert r["status"] == "fail"
    assert sorted(r["blocked"]) == ["igig", "p-studio"]


def test_no_resolvable_origins_is_not_configured_never_a_faked_pass():
    r = S.sso_cors_smoke(origins={})
    assert r["status"] == "not_configured"
    assert r["exit_code"] == 1
