"""Google OAuth scope resolution + introspection tests.

Pure-logic functions tested directly; `discover_granted_scopes` tested
with a mocked httpx transport (external-service carve-out per the
no-monkeypatching rule — httpx is an external network boundary).
Network-free.
"""

from __future__ import annotations

import httpx
import pytest

from noctusai_lib.integrations.google_scopes import (
    GOOGLE_KITCHEN_SINK_BASE,
    GOOGLE_KITCHEN_SINK_SCOPES,
    diagnose_consent_screen_gaps,
    discover_granted_scopes,
    format_scopes_for_authorize,
    resolve_google_scopes,
)


class TestResolveGoogleScopes:
    def test_auto_returns_kitchen_sink(self) -> None:
        assert resolve_google_scopes("auto") == GOOGLE_KITCHEN_SINK_SCOPES

    def test_auto_case_insensitive(self) -> None:
        assert resolve_google_scopes("AUTO") == GOOGLE_KITCHEN_SINK_SCOPES

    def test_empty_returns_kitchen_sink(self) -> None:
        assert resolve_google_scopes("") == GOOGLE_KITCHEN_SINK_SCOPES
        assert resolve_google_scopes(None) == GOOGLE_KITCHEN_SINK_SCOPES
        assert resolve_google_scopes("   ") == GOOGLE_KITCHEN_SINK_SCOPES

    def test_explicit_comma_separated(self) -> None:
        assert resolve_google_scopes("openid,email,profile") == [
            "openid",
            "email",
            "profile",
        ]

    def test_explicit_space_separated(self) -> None:
        assert resolve_google_scopes("openid email profile") == [
            "openid",
            "email",
            "profile",
        ]

    def test_explicit_mixed_separators_and_dedupe(self) -> None:
        assert resolve_google_scopes("openid, email openid,  profile") == [
            "openid",
            "email",
            "profile",
        ]

    def test_per_product_kitchen_sink_override(self) -> None:
        custom = GOOGLE_KITCHEN_SINK_BASE + [
            "https://www.googleapis.com/auth/gmail.readonly"
        ]
        assert resolve_google_scopes("auto", kitchen_sink=custom) == custom


class TestFormatScopesForAuthorize:
    def test_space_joined_not_comma(self) -> None:
        assert format_scopes_for_authorize(["a", "b", "c"]) == "a b c"

    def test_empty(self) -> None:
        assert format_scopes_for_authorize([]) == ""


class TestDiscoverGrantedScopes:
    def test_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"scope": "openid email profile"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        assert discover_granted_scopes("tok", http_client=client) == [
            "openid",
            "email",
            "profile",
        ]

    def test_401_returns_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "invalid_token"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        assert discover_granted_scopes("tok", http_client=client) == []

    def test_missing_scope_field_returns_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"email": "x@y.z"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        assert discover_granted_scopes("tok", http_client=client) == []

    def test_network_error_returns_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        assert discover_granted_scopes("tok", http_client=client) == []


class TestDiagnoseConsentScreenGaps:
    def test_perfect_coverage(self) -> None:
        out = diagnose_consent_screen_gaps(["a", "b"], ["a", "b"])
        assert out["coverage_pct"] == 100.0
        assert out["missing"] == []
        assert out["extra"] == []

    def test_partial_coverage(self) -> None:
        out = diagnose_consent_screen_gaps(["a", "b", "c", "d"], ["a", "b"])
        assert out["coverage_pct"] == 50.0
        assert out["missing"] == ["c", "d"]

    def test_extra_granted(self) -> None:
        out = diagnose_consent_screen_gaps(["a"], ["a", "b"])
        assert out["coverage_pct"] == 100.0
        assert out["extra"] == ["b"]

    def test_empty_requested_is_full_coverage(self) -> None:
        out = diagnose_consent_screen_gaps([], ["a"])
        assert out["coverage_pct"] == 100.0
        assert out["missing"] == []
