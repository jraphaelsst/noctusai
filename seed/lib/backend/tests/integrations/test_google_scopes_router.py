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


def _client(
    *, configured: str, token: str | None, with_resolver: bool = True
) -> TestClient:
    async def resolver(tenant_id: str | None) -> str | None:
        return token

    app = FastAPI()
    app.include_router(
        google_scopes_router(
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
