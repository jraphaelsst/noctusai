"""Tests for GET /api/products/deployment-status + the deployment probe.

The "deployed" signal drives the launcher's "dev" badge. A product is deployed
iff its container answers /api/health on noctus-net. We never reach the network
in tests: the endpoint's prober is a DI seam (overridden via
app.dependency_overrides), and probe_one is exercised with a fake httpx client.
"""
import asyncio

import httpx
import pytest

from app.routers.products import get_fleet_prober
from app.services import deployment_status as ds


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with an empty deployment cache (module-level state)."""
    ds.reset_cache()
    yield
    ds.reset_cache()


# ---------------------------------------------------------------------------
# GET /api/products/deployment-status
# ---------------------------------------------------------------------------

class TestDeploymentStatusEndpoint:
    def test_maps_each_slug_to_prober_result(self, client):
        client.mock_supabase.set_table_data("products", [
            {"slug": "daily-life", "ativo": True},
            {"slug": "erp-imobiliario", "ativo": True},
            {"slug": "adconnect", "ativo": True},
        ])

        async def fake_prober(slugs):
            up = {"daily-life", "erp-imobiliario"}
            return {s: s in up for s in slugs}

        app = client.raw().app
        app.dependency_overrides[get_fleet_prober] = lambda: fake_prober
        try:
            resp = client.get("/api/products/deployment-status")
        finally:
            app.dependency_overrides.pop(get_fleet_prober, None)

        assert resp.status_code == 200
        assert resp.json()["deployed"] == {
            "daily-life": True,
            "erp-imobiliario": True,
            "adconnect": False,
        }

    def test_caches_within_ttl_so_fleet_probed_once(self, client):
        client.mock_supabase.set_table_data("products", [{"slug": "daily-life", "ativo": True}])

        calls = {"n": 0}

        async def counting_prober(slugs):
            calls["n"] += 1
            return {s: True for s in slugs}

        app = client.raw().app
        app.dependency_overrides[get_fleet_prober] = lambda: counting_prober
        try:
            first = client.get("/api/products/deployment-status")
            second = client.get("/api/products/deployment-status")
        finally:
            app.dependency_overrides.pop(get_fleet_prober, None)

        assert first.status_code == second.status_code == 200
        assert calls["n"] == 1  # second call served from the TTL cache

    def test_empty_catalog_returns_empty_map(self, client):
        client.mock_supabase.set_table_data("products", [])

        async def fake_prober(slugs):
            return {s: True for s in slugs}

        app = client.raw().app
        app.dependency_overrides[get_fleet_prober] = lambda: fake_prober
        try:
            resp = client.get("/api/products/deployment-status")
        finally:
            app.dependency_overrides.pop(get_fleet_prober, None)

        assert resp.status_code == 200
        assert resp.json()["deployed"] == {}

    def test_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/products/deployment-status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# probe_one / probe_fleet — the real probe logic (fake httpx client, no network)
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeClient:
    """Stand-in for httpx.AsyncClient — maps each slug to a status or raises."""

    def __init__(self, behavior: dict):
        self._behavior = behavior

    async def get(self, url: str):
        slug = url.split("://", 1)[1].split(":", 1)[0]
        outcome = self._behavior[slug]
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResp(outcome)


class TestProbeLogic:
    def test_healthy_2xx_is_deployed(self):
        result = asyncio.run(
            ds.probe_one("daily-life", client=_FakeClient({"daily-life": 200}))
        )
        assert result is True

    def test_5xx_is_not_deployed(self):
        result = asyncio.run(
            ds.probe_one("daily-life", client=_FakeClient({"daily-life": 503}))
        )
        assert result is False

    def test_connection_error_is_not_deployed(self):
        result = asyncio.run(
            ds.probe_one(
                "ghost",
                client=_FakeClient({"ghost": httpx.ConnectError("down")}),
            )
        )
        assert result is False

    def test_probe_fleet_empty_is_empty(self):
        assert asyncio.run(ds.probe_fleet([])) == {}
