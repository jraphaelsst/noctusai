"""Pilot proof: `create_product_app` boots and serves a full
request/response cycle with `audit_trail_enabled` both off (default)
and on — the "SW, core, agents app construction works with flag
on/off" gate from the audit-trail S2 brief.

Doesn't reach into `RealAuditSink`'s internals (that's
`seed/lib/backend/tests/api/audit/test_sink.py`'s job) — this file
only proves `noctusai_seed.app.create_product_app` +
`noctusai_lib.api.app_factory.configure_app`'s NEW wiring (sink
construction, `AuditMiddleware` mount, lifespan drain) doesn't break
app construction or the request pipeline for EITHER flag state, which
is exactly what every existing product's pytest suite (SW, core,
agents — none of which set `audit_trail_enabled`) already exercises
implicitly for the off/default state.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient


class _BaseSettings:
    cors_origins = "http://localhost:3000"
    cors_origins_list = ["http://localhost:3000"]
    debug = True
    is_production = False
    sentry_dsn = None
    product_slug = "test"
    supabase_url = "http://localhost:54321"
    supabase_anon_key = "anon"
    supabase_service_role_key = "service"
    consent_gating = False
    llm_usage_tracking = False
    redis_url = None


def _app(*, audit_trail_enabled: bool):
    from noctusai_seed import create_product_app

    class _S(_BaseSettings):
        pass

    _S.audit_trail_enabled = audit_trail_enabled

    router = APIRouter()

    @router.post("/api/things")
    async def create_thing():
        return {"ok": True}

    return create_product_app(
        name="Test",
        schema="test",
        settings=_S(),
        routers=[router],
        version="9.9.9",
        standard_routers=["health"],
    )


def test_app_boots_and_serves_with_audit_trail_disabled() -> None:
    app = _app(audit_trail_enabled=False)
    with TestClient(app) as client:
        resp = client.post("/api/things")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


def test_app_boots_and_serves_with_audit_trail_enabled() -> None:
    app = _app(audit_trail_enabled=True)
    with TestClient(app) as client:
        resp = client.post("/api/things")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
    # `with TestClient(...)` triggers lifespan shutdown on exit —
    # `audit_sink.drain()` must not raise even though the RealAuditSink
    # never actually flushed against a live DB in this test.


def test_app_boots_when_settings_has_no_audit_trail_attribute_at_all() -> None:
    """`getattr(settings, "audit_trail_enabled", False)` — a product's
    `Settings` that predates this field (hasn't pulled the new
    `ProductSettings` default yet) must still boot inert, not crash."""
    from noctusai_seed import create_product_app

    class _S(_BaseSettings):
        pass

    app = create_product_app(
        name="Test", schema="test", settings=_S(), routers=None,
        version="9.9.9", standard_routers=["health"],
    )
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
