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
            {"slug": "daily-life", "ativo": True, "url_base": "http://localhost:8005"},
            {"slug": "erp-imobiliario", "ativo": True, "url_base": "http://localhost:8001"},
            {"slug": "adconnect", "ativo": True, "url_base": "http://localhost:8007"},
        ])

        async def fake_prober(targets):
            # targets is {slug: house_port}; iterating yields the slugs.
            up = {"daily-life", "erp-imobiliario"}
            return {s: s in up for s in targets}

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
        client.mock_supabase.set_table_data("products", [{"slug": "daily-life", "ativo": True, "url_base": "http://localhost:8005"}])

        calls = {"n": 0}

        async def counting_prober(targets):
            calls["n"] += 1
            return {s: True for s in targets}

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

        async def fake_prober(targets):
            return {s: True for s in targets}

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
    """Stand-in for httpx.AsyncClient — maps each slug to a status or raises.

    Also records the URLs it was asked to GET so tests can assert the probe
    targets the product's HOUSE port (not a uniform 8000).
    """

    def __init__(self, behavior: dict):
        self._behavior = behavior
        self.urls: list[str] = []

    async def get(self, url: str):
        self.urls.append(url)
        slug = url.split("://", 1)[1].split(":", 1)[0]
        outcome = self._behavior[slug]
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResp(outcome)


class TestHousePortFromUrlBase:
    def test_parses_house_port(self):
        assert ds.house_port_from_url_base("http://localhost:8004") == 8004
        assert ds.house_port_from_url_base("http://localhost:8011") == 8011

    def test_missing_or_portless_falls_back_to_8000(self):
        assert ds.house_port_from_url_base(None) == 8000
        assert ds.house_port_from_url_base("https://seed.noctusai.com") == 8000


class TestProbeLogic:
    def test_healthy_2xx_is_deployed(self):
        result = asyncio.run(
            ds.probe_one("daily-life", 8005, client=_FakeClient({"daily-life": 200}))
        )
        assert result is True

    def test_probe_targets_the_house_port_not_8000(self):
        fake = _FakeClient({"seed": 200})
        asyncio.run(ds.probe_one("seed", 8004, client=fake))
        assert fake.urls == ["http://seed:8004/api/health"]

    def test_5xx_is_not_deployed(self):
        result = asyncio.run(
            ds.probe_one("daily-life", 8005, client=_FakeClient({"daily-life": 503}))
        )
        assert result is False

    def test_connection_error_is_not_deployed(self):
        result = asyncio.run(
            ds.probe_one(
                "ghost",
                9999,
                client=_FakeClient({"ghost": httpx.ConnectError("down")}),
            )
        )
        assert result is False

    def test_probe_fleet_empty_is_empty(self):
        assert asyncio.run(ds.probe_fleet({})) == {}

    def test_probe_fleet_maps_each_target(self):
        # Real probe_fleet builds its own httpx client → point at unroutable
        # hosts so every probe fails fast; we assert shape, not reachability.
        result = asyncio.run(ds.probe_fleet({"ghost-a": 8004, "ghost-b": 8011}))
        assert set(result) == {"ghost-a", "ghost-b"}
        assert result == {"ghost-a": False, "ghost-b": False}
