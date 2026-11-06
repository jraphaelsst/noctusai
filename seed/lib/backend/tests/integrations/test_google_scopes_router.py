"""`/api/google/scopes` 4-layer introspection router tests.

FastAPI TestClient against the factory-built router with injected
config + token resolver seams. The granted-layer (tokeninfo probe)
math is covered exhaustively in `test_google_scopes.py`
(`diagnose_consent_screen_gaps` / `discover_granted_scopes`); here we
assert the router *wiring*: configured/kitchen-sink layers always
present, granted layer null without a resolvable token. Status code
asserted alongside body (status-code-assertion rule). Network-free.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.integrations.google_scopes import GOOGLE_KITCHEN_SINK_SCOPES
from noctusai_lib.integrations.google_scopes_router import google_scopes_router


def _platform_admin_ok() -> None:
    """Stand-in for `require_platform_admin` that lets the caller through."""
    return None


def _client(
    *, configured: str, token: str | None, with_resolver: bool = True
) -> TestClient:
    async def resolver(tenant_id: str | None) -> str | None:
        return token

    app = FastAPI()
    app.include_router(
        google_scopes_router(
            platform_admin_dep=_platform_admin_ok,
            configured_scopes=lambda: configured,
            access_token_resolver=resolver if with_resolver else None,
        )
    )
    return TestClient(app)


class TestGoogleScopesEndpoint:
    def test_layers_present_no_resolver(self) -> None:
        client = _client(configured="auto", token=None, with_resolver=False)
        resp = client.get("/api/google/scopes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] == GOOGLE_KITCHEN_SINK_SCOPES
        assert body["kitchen_sink"] == GOOGLE_KITCHEN_SINK_SCOPES
        assert body["granted_to_user"] is None
        assert body["declined_by_user"] is None
        assert body["coverage_pct"] is None

    def test_resolver_present_but_no_token(self) -> None:
        client = _client(configured="auto", token=None)
        resp = client.get("/api/google/scopes?tenant_id=t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["granted_to_user"] is None
        assert "Consent not yet probed" in body["note"]

    def test_explicit_configured_scopes_echoed(self) -> None:
        client = _client(
            configured="openid email", token=None, with_resolver=False
        )
        resp = client.get("/api/google/scopes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] == ["openid", "email"]
        # Kitchen-sink layer is independent of the configured value.
        assert body["kitchen_sink"] == GOOGLE_KITCHEN_SINK_SCOPES


class TestGoogleScopesAccess:
    """OWASP API1/API5: the route probes any tenant's stored token, so it is platform-only."""

    def test_refuses_anonymous_and_non_admin_and_is_not_in_schema(self) -> None:
        from fastapi import HTTPException

        def deny_401() -> None:
            raise HTTPException(status_code=401, detail="unauthenticated")

        def deny_403() -> None:
            raise HTTPException(status_code=403, detail="platform_admin_required")

        for gate, expected in ((deny_401, 401), (deny_403, 403)):
            app = FastAPI()
            app.include_router(
                google_scopes_router(platform_admin_dep=gate, configured_scopes=lambda: "auto")
            )
            client = TestClient(app)
            assert client.get("/api/google/scopes?tenant_id=t1").status_code == expected
            assert "/api/google/scopes" not in client.get("/openapi.json").json()["paths"]
