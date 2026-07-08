"""Tests for the seed-baked `/_health` + `/_ready` endpoints
(`noctusai_seed.health`).

Two layers:
  1. Direct unit tests against `mount_health_endpoints(app, config)` on a
     bare `FastAPI()` — fast, no seed-wiring overhead, one assertion per
     concern. Covers default-empty / hooks-ok / hooks-not-ok / multi-hook
     /  raising-hook / idempotency.
  2. Smoke through `create_product_app(...)` so we know the factory
     plumbing actually mounts the routes. One end-to-end fastpath using
     the smallest plausible settings shape.

Network-free: hooks are inline async lambdas. No DB, no Redis, no Supabase.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_seed.health import (
    HealthCheckHook,
    HealthEndpointConfig,
    mount_health_endpoints,
)


# ---------------------------------------------------------------------------
# Direct unit tests against `mount_health_endpoints`
# ---------------------------------------------------------------------------


def _bare_app(config: HealthEndpointConfig) -> TestClient:
    """Mount endpoints on a fresh FastAPI() and return a TestClient."""
    app = FastAPI()
    mount_health_endpoints(app, config)
    return TestClient(app)


def _ok_hook_named(name: str):
    """Build a hook whose `__name__` is `name` so it surfaces in `checks`."""

    async def _hook() -> tuple[bool, str | None]:
        return (True, None)

    _hook.__name__ = name
    return _hook


def _failing_hook(name: str, msg: str):
    async def _hook() -> tuple[bool, str | None]:
        return (False, msg)

    _hook.__name__ = name
    return _hook


def _raising_hook(name: str, exc: Exception):
    async def _hook() -> tuple[bool, str | None]:
        raise exc

    _hook.__name__ = name
    return _hook


class TestDefaultEmptyConfig:
    """Empty hook lists ⇒ both endpoints always return 200 with checks=[]."""

    def test_health_default_returns_200_empty_checks(self):
        c = _bare_app(HealthEndpointConfig())
        r = c.get("/_health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["checks"] == []
        assert "timestamp" in body  # ISO string; format checked elsewhere

    def test_ready_default_returns_200_empty_checks(self):
        c = _bare_app(HealthEndpointConfig())
        r = c.get("/_ready")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["checks"] == []
        assert "timestamp" in body

    def test_default_config_dataclass_independent_lists(self):
        """Regression guard: each `HealthEndpointConfig()` instance must
        have its OWN list — `field(default_factory=list)` not `= []`. A
        bare default `[]` would share state across instances and let one
        product's hook leak into another's."""
        a = HealthEndpointConfig()
        b = HealthEndpointConfig()
        a.liveness_hooks.append(_ok_hook_named("noisy"))
        assert b.liveness_hooks == []
        assert a.readiness_hooks == []  # cross-list independence too


class TestLivenessHooks:
    def test_liveness_hook_ok_returns_200(self):
        c = _bare_app(HealthEndpointConfig(liveness_hooks=[_ok_hook_named("alive")]))
        r = c.get("/_health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert len(body["checks"]) == 1
        assert body["checks"][0] == {"name": "alive", "ok": True, "error": None}

    def test_liveness_hook_not_ok_returns_503_with_error(self):
        c = _bare_app(
            HealthEndpointConfig(
                liveness_hooks=[_failing_hook("dead_proc", "process unresponsive")]
            )
        )
        r = c.get("/_health")
        assert r.status_code == 503
        body = r.json()
        assert body["ok"] is False
        assert len(body["checks"]) == 1
        assert body["checks"][0] == {
            "name": "dead_proc",
            "ok": False,
            "error": "process unresponsive",
        }


class TestReadinessHooks:
    def test_multiple_readiness_hooks_all_ok_returns_200(self):
        c = _bare_app(
            HealthEndpointConfig(
                readiness_hooks=[
                    _ok_hook_named("db_ping"),
                    _ok_hook_named("redis_ping"),
                    _ok_hook_named("vendor_ping"),
                ]
            )
        )
        r = c.get("/_ready")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert len(body["checks"]) == 3
        assert {c["name"] for c in body["checks"]} == {
            "db_ping",
            "redis_ping",
            "vendor_ping",
        }
        assert all(c["ok"] is True for c in body["checks"])

    def test_one_readiness_hook_fails_returns_503_but_all_run(self):
        """Failure is sticky for the OVERALL ok flag — but every hook
        runs and is reported. Operators see exactly which probe failed
        AND that the others stayed green."""
        c = _bare_app(
            HealthEndpointConfig(
                readiness_hooks=[
                    _ok_hook_named("db_ping"),
                    _failing_hook("redis_ping", "ECONNREFUSED redis://localhost:6379"),
                    _ok_hook_named("vendor_ping"),
                ]
            )
        )
        r = c.get("/_ready")
        assert r.status_code == 503
        body = r.json()
        assert body["ok"] is False
        assert len(body["checks"]) == 3
        by_name = {c["name"]: c for c in body["checks"]}
        assert by_name["db_ping"]["ok"] is True
        assert by_name["db_ping"]["error"] is None
        assert by_name["redis_ping"]["ok"] is False
        assert "ECONNREFUSED" in by_name["redis_ping"]["error"]
        assert by_name["vendor_ping"]["ok"] is True


class TestRaisingHook:
    def test_hook_exception_is_caught_and_mapped_to_failure(self):
        c = _bare_app(
            HealthEndpointConfig(
                readiness_hooks=[_raising_hook("flaky_ping", RuntimeError("boom"))]
            )
        )
        r = c.get("/_ready")
        assert r.status_code == 503
        body = r.json()
        assert body["ok"] is False
        assert len(body["checks"]) == 1
        assert body["checks"][0] == {
            "name": "flaky_ping",
            "ok": False,
            "error": "boom",
        }

    def test_hook_exception_does_not_block_other_hooks(self):
        c = _bare_app(
            HealthEndpointConfig(
                readiness_hooks=[
                    _raising_hook("flaky_ping", ConnectionError("net down")),
                    _ok_hook_named("db_ping"),
                ]
            )
        )
        r = c.get("/_ready")
        assert r.status_code == 503
        body = r.json()
        names = [c["name"] for c in body["checks"]]
        assert names == ["flaky_ping", "db_ping"]
        assert body["checks"][1]["ok"] is True  # db_ping still ran


class TestMisshapenHookReturn:
    def test_hook_returning_non_tuple_is_treated_as_failure(self):
        async def bad_hook():
            return True  # forgot the tuple

        bad_hook.__name__ = "bad_hook"
        c = _bare_app(HealthEndpointConfig(liveness_hooks=[bad_hook]))
        r = c.get("/_health")
        assert r.status_code == 503
        body = r.json()
        assert body["ok"] is False
        assert body["checks"][0]["name"] == "bad_hook"
        assert body["checks"][0]["ok"] is False
        assert "expected tuple" in body["checks"][0]["error"]


class TestIdempotency:
    def test_double_mount_raises_clear_error(self):
        app = FastAPI()
        mount_health_endpoints(app, HealthEndpointConfig())
        with pytest.raises(RuntimeError) as excinfo:
            mount_health_endpoints(app, HealthEndpointConfig())
        # Error message names the function so an operator can grep.
        assert "mount_health_endpoints" in str(excinfo.value)
        assert "twice" in str(excinfo.value)


class TestProtocolConformance:
    """`HealthCheckHook` is `runtime_checkable` — sanity-check that a
    plain async fn with the right signature passes `isinstance`."""

    def test_async_fn_satisfies_protocol(self):
        async def ping() -> tuple[bool, str | None]:
            return (True, None)

        assert isinstance(ping, HealthCheckHook)


# ---------------------------------------------------------------------------
# Integration smoke through `create_product_app`
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_settings():
    """Smallest plausible settings shape that lets `create_product_app`
    finish without DB / vendor wiring. Mirrors `conftest.fake_settings`
    but adds the few extra knobs the factory now reads (consent_gating,
    llm_usage_tracking, redis_url)."""

    class _S:
        cors_origins = "http://localhost:3000"
        cors_origins_list = ["http://localhost:3000"]
        debug = True
        is_production = False
        sentry_dsn = None
        product_slug = "test"
        supabase_url = "http://localhost:54321"
        supabase_anon_key = "anon"
        supabase_service_role_key = "service"
        consent_gating = False  # don't need the consent module wired here
        llm_usage_tracking = False
        redis_url = None

    return _S()


def test_create_product_app_default_health_config(minimal_settings):
    """No `health_config=` kwarg → endpoints exist + return 200 empty."""
    from noctusai_seed import create_product_app

    app = create_product_app(
        name="Test",
        schema="test",
        settings=minimal_settings,
        routers=None,
        version="9.9.9",
    )
    client = TestClient(app)

    r = client.get("/_health")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["checks"] == []

    r = client.get("/_ready")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_create_product_app_with_health_config(minimal_settings):
    """`health_config=HealthEndpointConfig(readiness_hooks=[...])` wires
    real probes through the factory — what every product opting in
    actually does."""
    from noctusai_seed import HealthEndpointConfig, create_product_app

    async def db_ping() -> tuple[bool, str | None]:
        return (True, None)

    db_ping.__name__ = "db_ping"

    app = create_product_app(
        name="Test",
        schema="test",
        settings=minimal_settings,
        routers=None,
        version="9.9.9",
        health_config=HealthEndpointConfig(readiness_hooks=[db_ping]),
    )
    client = TestClient(app)

    r = client.get("/_ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["checks"] == [{"name": "db_ping", "ok": True, "error": None}]


def test_create_product_app_failing_readiness_returns_503(minimal_settings):
    from noctusai_seed import HealthEndpointConfig, create_product_app

    async def db_ping() -> tuple[bool, str | None]:
        return (False, "table 'foo' missing")

    db_ping.__name__ = "db_ping"

    app = create_product_app(
        name="Test",
        schema="test",
        settings=minimal_settings,
        routers=None,
        version="9.9.9",
        health_config=HealthEndpointConfig(readiness_hooks=[db_ping]),
    )
    client = TestClient(app)

    r = client.get("/_ready")
    assert r.status_code == 503
    assert r.json()["ok"] is False
    assert r.json()["checks"][0]["error"] == "table 'foo' missing"


class TestVersionEndpoint:
    """/_version — deploy provenance (seed sha + product + build sha)."""

    def test_version_returns_provenance_fields(self):
        c = _bare_app(HealthEndpointConfig())
        r = c.get("/_version")
        assert r.status_code == 200
        body = r.json()
        # Always-present keys — the provenance contract.
        for k in ("product", "product_version", "seed_sha", "build_sha", "timestamp"):
            assert k in body, k
        # seed_sha resolves (a sha or the documented fallbacks), never missing.
        assert body["seed_sha"]

    def test_version_reflects_app_title_and_version(self):
        app = FastAPI(title="ERP", version="1.2.3")
        mount_health_endpoints(app, HealthEndpointConfig())
        body = TestClient(app).get("/_version").json()
        assert body["product"] == "ERP"
        assert body["product_version"] == "1.2.3"

    def test_version_build_sha_reads_env(self, monkeypatch):
        monkeypatch.setenv("GIT_SHA", "abc123def")
        c = _bare_app(HealthEndpointConfig())
        assert c.get("/_version").json()["build_sha"] == "abc123def"

    def test_version_build_sha_none_when_unbaked(self, monkeypatch):
        monkeypatch.delenv("GIT_SHA", raising=False)
        monkeypatch.delenv("NOCTUS_BUILD_SHA", raising=False)
        c = _bare_app(HealthEndpointConfig())
        assert c.get("/_version").json()["build_sha"] is None
