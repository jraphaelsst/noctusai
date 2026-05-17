"""Tests for the Google OAuth scope resolver + tokeninfo probe + gap diagnosis.

Mirrors the Meta scope tests shape so the patterns track 1:1. No live
Google calls — httpx is mocked for tokeninfo.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx

from app.services.google_scopes import (
    GOOGLE_KITCHEN_SINK_SCOPES,
    diagnose_consent_screen_gaps,
    discover_granted_scopes,
    format_scopes_for_authorize,
    resolve_google_scopes,
)


class TestResolveGoogleScopes:
    def test_auto_returns_kitchen_sink(self):
        assert resolve_google_scopes(configured="auto") == list(
            GOOGLE_KITCHEN_SINK_SCOPES
        )

    def test_uppercase_auto_also_works(self):
        assert resolve_google_scopes(configured="AUTO") == list(
            GOOGLE_KITCHEN_SINK_SCOPES
        )

    def test_empty_string_is_same_as_auto(self):
        assert resolve_google_scopes(configured="") == list(
            GOOGLE_KITCHEN_SINK_SCOPES
        )
        assert resolve_google_scopes(configured="   ") == list(
            GOOGLE_KITCHEN_SINK_SCOPES
        )

    def test_explicit_space_separated_list_is_honored(self):
        configured = (
            "https://www.googleapis.com/auth/calendar "
            "https://www.googleapis.com/auth/drive.readonly"
        )
        result = resolve_google_scopes(configured=configured)
        assert result == [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

    def test_explicit_comma_separated_list_is_honored(self):
        configured = (
            "https://www.googleapis.com/auth/calendar,"
            "https://www.googleapis.com/auth/drive.readonly"
        )
        result = resolve_google_scopes(configured=configured)
        assert result == [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

    def test_dedupes_preserving_first_occurrence(self):
        configured = "a b a c b"
        assert resolve_google_scopes(configured=configured) == ["a", "b", "c"]


class TestFormatScopesForAuthorize:
    def test_joins_with_spaces(self):
        scopes = [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        assert format_scopes_for_authorize(scopes) == (
            "https://www.googleapis.com/auth/calendar "
            "https://www.googleapis.com/auth/drive.readonly"
        )

    def test_empty_list_becomes_empty_string(self):
        assert format_scopes_for_authorize([]) == ""


class TestDiscoverGrantedScopes:
    def test_returns_granted_scopes_from_tokeninfo(self):
        body = {
            "scope": (
                "https://www.googleapis.com/auth/calendar "
                "https://www.googleapis.com/auth/drive.readonly "
                "openid"
            ),
            "expires_in": 3599,
            "email": "test@example.com",
        }

        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=200, json=body, request=request)

        with patch("httpx.get", side_effect=fake_get):
            granted = discover_granted_scopes(access_token="ya29.fake")

        assert granted == [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
            "openid",
        ]

    def test_returns_empty_on_non_200(self):
        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(status_code=401, text="bad token", request=request)

        with patch("httpx.get", side_effect=fake_get):
            granted = discover_granted_scopes(access_token="bad")
        assert granted == []

    def test_returns_empty_on_network_exception(self):
        def fake_get(url, params=None, timeout=None):
            raise httpx.ConnectError("network down")

        with patch("httpx.get", side_effect=fake_get):
            granted = discover_granted_scopes(access_token="x")
        assert granted == []

    def test_missing_scope_field_returns_empty(self):
        def fake_get(url, params=None, timeout=None):
            request = httpx.Request("GET", url)
            return httpx.Response(
                status_code=200,
                json={"email": "x@y.com"},  # no scope key
                request=request,
            )

        with patch("httpx.get", side_effect=fake_get):
            granted = discover_granted_scopes(access_token="x")
        assert granted == []


class TestDiagnoseConsentScreenGaps:
    def test_perfect_overlap_gives_100_coverage(self):
        diff = diagnose_consent_screen_gaps(
            requested=["a", "b", "c"],
            granted=["a", "b", "c"],
        )
        assert diff["missing"] == []
        assert diff["extra"] == []
        assert diff["coverage_pct"] == 100.0

    def test_partial_grant_reports_missing(self):
        diff = diagnose_consent_screen_gaps(
            requested=["a", "b", "c", "d"],
            granted=["a", "b"],
        )
        assert diff["missing"] == ["c", "d"]
        assert diff["extra"] == []
        assert diff["coverage_pct"] == 50.0

    def test_extra_grant_reports_extra(self):
        # include_granted_scopes=true can pull in scopes from a previous
        # consent — useful to surface.
        diff = diagnose_consent_screen_gaps(
            requested=["a", "b"],
            granted=["a", "b", "x", "y"],
        )
        assert diff["missing"] == []
        assert diff["extra"] == ["x", "y"]
        assert diff["coverage_pct"] == 100.0

    def test_empty_requested_returns_zero_coverage(self):
        diff = diagnose_consent_screen_gaps(requested=[], granted=["a"])
        assert diff["coverage_pct"] == 0.0
        assert diff["missing"] == []
        assert diff["extra"] == ["a"]
