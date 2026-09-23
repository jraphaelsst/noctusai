"""Pilot proof: `create_product_app` boots and serves a full
request/response cycle with `audit_trail_enabled` both off (default)
and on — the "SW, core, agents app construction works with flag
on/off" gate from the audit-trail S2 brief. Also the regression proof
for the 2026-09-23 redirect: a class-level patch of
`DatabaseModule.get_core_client` (the exact shape every product's test
fixtures use — see `products/social-wiring/backend/tests/conftest.py`)
must be what `RealAuditSink` actually calls, even though the sink is
built once at `app.main` IMPORT time, before any per-test patch is
active.

Doesn't reach into `RealAuditSink`'s OTHER internals (batching,
overflow, `_to_row` — that's `seed/lib/backend/tests/api/audit
/test_sink.py`'s job) — this file proves `noctusai_seed.app
.create_product_app` + `noctusai_lib.api.app_factory.configure_app`'s
wiring (sink construction, the `audit_sink=` override seam,
`AuditMiddleware` mount, lifespan drain) doesn't break app construction
or the request pipeline for EITHER flag state, which is exactly what
every existing product's pytest suite (SW, core, agents — none of
which set `audit_trail_enabled`) already exercises implicitly for the
off/default state.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from noctusai_lib.api.audit import AuditEntry, FakeAuditSink, RealAuditSink
from noctusai_seed.database import DatabaseModule


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


def test_audit_sink_override_seam_is_used_when_provided() -> None:
    """`create_product_app(audit_sink=...)` — a product's own test
    fixture injects a `FakeAuditSink()` it wants to assert against,
    bypassing the auto-selected sink entirely."""
    from noctusai_seed import create_product_app

    class _S(_BaseSettings):
        audit_trail_enabled = True

    router = APIRouter()

    @router.post("/api/things")
    async def create_thing():
        return {"ok": True}

    injected = FakeAuditSink()
    app = create_product_app(
        name="Test", schema="test", settings=_S(), routers=[router],
        version="9.9.9", standard_routers=["health"], audit_sink=injected,
    )
    with TestClient(app) as client:
        client.post("/api/things")

    assert len(injected.entries) == 1
    assert injected.entries[0].method == "POST"


class TestRealAuditSinkResolvesGetCoreClientLazily:
    """The core regression proof (2026-09-23 redirect): the sink must
    call THROUGH `DatabaseModule.get_core_client` at flush time, not a
    bound-method snapshot taken before a test's patch activates."""

    @staticmethod
    def _entry() -> AuditEntry:
        return AuditEntry(
            product_slug="test",
            method="POST",
            route_template="/api/things",
            path_params={},
            status=200,
            actor_kind="user",
            client_hint="Chrome",
        )

    @pytest.mark.asyncio
    async def test_a_patch_applied_after_sink_construction_is_what_gets_called(self) -> None:
        db = DatabaseModule(
            settings=type("S", (), {
                "supabase_url": "http://example.invalid",
                "supabase_anon_key": "anon",
                "supabase_service_role_key": "service",
            })(),
            schema="test",
        )
        # Built the EXACT SAME shape `create_product_app` wires:
        # `lambda: db.get_core_client()`, not `db.get_core_client`.
        sink = RealAuditSink(lambda: db.get_core_client(), flush_interval_s=60, batch_size=50)

        sentinel_calls: list[str] = []

        class _SentinelAdmin:
            def schema(self, name):
                return self

            def table(self, name):
                return self

            def insert(self, rows):
                sentinel_calls.append("insert")
                return self

            def execute(self):
                return None

        # Patched AFTER `sink` was constructed — mirrors every product's
        # `unittest.mock.patch("noctusai_seed.database.DatabaseModule
        # .get_core_client", ...)` test fixture, which only activates
        # once a TEST is running, long after `app.main` already built
        # the sink at import time.
        with patch.object(DatabaseModule, "get_core_client", return_value=_SentinelAdmin()):
            await sink.record(self._entry())
            await sink.drain()

        assert sentinel_calls == ["insert"], (
            "RealAuditSink did not call through the patched "
            "DatabaseModule.get_core_client — it resolved a stale, "
            "pre-patch bound method instead (the exact bug the lazy "
            "lambda wiring in create_product_app fixes)."
        )

    def test_an_eagerly_bound_method_would_have_missed_the_patch(self) -> None:
        """Contrast case, WITHOUT any real I/O risk: proves the bug class
        is real by showing the OLD (buggy) wiring shape — a bound method
        captured BEFORE the patch, exactly what `create_product_app` used
        to pass — resolves a DIFFERENT function object than the one the
        patch installs. Pure attribute-identity check; never calls the
        method, so there is no chance of an actual network attempt
        against `db`'s (fake) Supabase URL. If this test ever starts
        FAILING, Python's bound-method binding semantics changed
        underneath this whole fix."""
        db = DatabaseModule(
            settings=type("S", (), {
                "supabase_url": "http://example.invalid",
                "supabase_anon_key": "anon",
                "supabase_service_role_key": "service",
            })(),
            schema="test",
        )
        stale_bound_method = db.get_core_client  # captured BEFORE the patch

        with patch.object(DatabaseModule, "get_core_client", return_value="patched") as mocked:
            # The lazy shape (what the fix uses) reaches the patch...
            assert db.get_core_client() == "patched"
            assert mocked.called
            # ...the eagerly-bound method does NOT — it still points at
            # the ORIGINAL unbound function, not the Mock the patch
            # installed onto the class.
            assert stale_bound_method.__func__ is not DatabaseModule.get_core_client


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
