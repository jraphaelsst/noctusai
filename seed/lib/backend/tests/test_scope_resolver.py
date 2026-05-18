"""Tests for `noctusai_lib.security.oauth.scopes` — the unified
cross-provider `ScopeResolver` Protocol + Fake + Real + factory.

External boundary only is mocked: Google's `oauth2/v3/tokeninfo` via an
`httpx.MockTransport`, Meta's Graph via `patch.object(httpx, "get", ...)`
(external-service carve-out per the no-monkeypatching rule — httpx is a
network boundary; no noctusai_lib code is patched). Network-free.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from noctusai_lib.integrations.google_scopes import GOOGLE_KITCHEN_SINK_SCOPES
from noctusai_lib.integrations.meta._meta_api import META_KITCHEN_SINK_SCOPES
from noctusai_lib.security.oauth import (
    FakeScopeResolver,
    GoogleScopeResolver,
    MetaScopeResolver,
    ScopeResolver,
    make_scope_resolver,
)


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    @property
    def text(self):
        return str(self._payload)


class TestScopeResolverProtocol:
    def test_real_impls_satisfy_protocol(self) -> None:
        # runtime_checkable Protocol — structural conformance.
        assert isinstance(GoogleScopeResolver(), ScopeResolver)
        assert isinstance(MetaScopeResolver(), ScopeResolver)
        assert isinstance(FakeScopeResolver(), ScopeResolver)

    def test_provider_identifiers(self) -> None:
        assert GoogleScopeResolver().provider == "google"
        assert MetaScopeResolver().provider == "meta"
        assert FakeScopeResolver(provider="x").provider == "x"


class TestFactorySelection:
    def test_google_selection(self) -> None:
        r = make_scope_resolver("google")
        assert isinstance(r, GoogleScopeResolver)
        assert r.provider == "google"

    def test_meta_selection(self) -> None:
        r = make_scope_resolver("meta", app_id="a", app_secret="s")
        assert isinstance(r, MetaScopeResolver)
        assert r.provider == "meta"

    def test_use_fake_short_circuits_any_name(self) -> None:
        r = make_scope_resolver("anything", use_fake=True)
        assert isinstance(r, FakeScopeResolver)
        assert r.provider == "anything"

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown scope-resolver"):
            make_scope_resolver("tiktok")


class TestGoogleResolver:
    def test_resolve_auto_returns_kitchen_sink(self) -> None:
        assert (
            GoogleScopeResolver().resolve("auto") == GOOGLE_KITCHEN_SINK_SCOPES
        )

    def test_resolve_explicit_dedupes(self) -> None:
        assert GoogleScopeResolver().resolve("a,b a,b") == ["a", "b"]

    def test_list_app_scopes_is_none_for_google(self) -> None:
        # Google exposes NO app-scope endpoint — the provider-shaped
        # divergence the Protocol encodes.
        assert GoogleScopeResolver().list_app_scopes() is None

    def test_discover_granted_probes_tokeninfo(self) -> None:
        # The resolver delegates to discover_granted_scopes, which
        # builds its own httpx.Client when none is injected. Patch the
        # httpx.Client constructor (network boundary) with a mock
        # transport — no noctusai_lib code is patched.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"scope": "openid email profile"})

        mock_client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch.object(httpx, "Client", return_value=mock_client):
            granted = GoogleScopeResolver().discover_granted("tok")
        assert granted == ["openid", "email", "profile"]

    def test_diagnose_coverage(self) -> None:
        d = GoogleScopeResolver().diagnose(["a", "b"], ["a"])
        assert d["coverage_pct"] == 50.0
        assert d["missing"] == ["b"]


class TestMetaResolver:
    def test_resolve_explicit_verbatim(self) -> None:
        assert MetaScopeResolver().resolve("public_profile,email") == [
            "public_profile",
            "email",
        ]

    def test_resolve_auto_no_creds_falls_back_to_kitchen_sink(self) -> None:
        assert MetaScopeResolver().resolve("auto") == list(
            META_KITCHEN_SINK_SCOPES
        )

    def test_list_app_scopes_none_without_creds(self) -> None:
        assert MetaScopeResolver().list_app_scopes() is None

    def test_list_app_scopes_queries_graph_with_creds(self) -> None:
        body = {"data": [{"permission": "pages_show_list", "status": "live"}]}
        with patch.object(
            httpx, "get", return_value=_FakeResponse(body, 200)
        ):
            scopes = MetaScopeResolver(
                app_id="123", app_secret="sek"
            ).list_app_scopes()
        assert scopes == ["pages_show_list"]

    def test_discover_granted_returns_empty_from_resolver_seat(self) -> None:
        # Meta's granted probe lives in the introspection router, not
        # the resolver — [] = "unknown from here", never raises.
        assert MetaScopeResolver().discover_granted("tok") == []

    def test_diagnose_reuses_provider_agnostic_math(self) -> None:
        d = MetaScopeResolver().diagnose(["x"], ["x"])
        assert d["coverage_pct"] == 100.0


class TestFakeResolver:
    def test_resolve_auto_returns_seeded_kitchen_sink(self) -> None:
        f = FakeScopeResolver(kitchen_sink=["k1", "k2"])
        assert f.resolve("auto") == ["k1", "k2"]
        assert f.resolve("") == ["k1", "k2"]

    def test_resolve_explicit_dedupes(self) -> None:
        assert FakeScopeResolver().resolve("a, b, a") == ["a", "b"]

    def test_list_app_scopes_defaults_none_google_shape(self) -> None:
        assert FakeScopeResolver().list_app_scopes() is None

    def test_list_app_scopes_returns_seeded(self) -> None:
        assert FakeScopeResolver(app_scopes=["s1"]).list_app_scopes() == ["s1"]

    def test_discover_granted_returns_seeded(self) -> None:
        assert FakeScopeResolver(granted=["g"]).discover_granted("t") == ["g"]

    def test_diagnose_uses_real_coverage_math(self) -> None:
        # The Fake exercises the SAME report shape the Real does.
        d = FakeScopeResolver().diagnose(["a", "b"], ["a", "b"])
        assert d["coverage_pct"] == 100.0
        assert d["missing"] == []
