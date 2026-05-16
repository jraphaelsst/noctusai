"""Tests for the `serve_spa` single-container seam on `create_product_app`.

Phase 1 of `projects/containerization-single-container/`. The seam lets
uvicorn serve the built SPA bundle alongside the API so each product is
one container on one port.

Contract under test:
  - seam OFF (default, no param, no env) → no mount; `/` is a plain 404,
    API/ops routes unchanged.
  - seam ON → `/` + real files served; unknown *extension-less* path →
    `index.html` (client-side routing); unknown *asset* path (has a file
    extension) → real 404 (broken bundles surface, no HTML-as-JS).
  - API/ops routes (`/_health`) keep priority over the `/` mount.
  - `SERVE_SPA_DIR` env is honoured; the `serve_spa=` param beats the env.
  - misconfigured dir (no `index.html`) → WARNING + API still served, no
    crash, no silent pass.

Network-free: no DB / Redis / Supabase. SPA bundle is a `tmp_path` fixture.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from noctusai_seed import create_product_app


class _S:
    """Minimal settings shape (mirrors test_health.minimal_settings)."""

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


@pytest.fixture
def settings():
    return _S()


@pytest.fixture
def spa_dir(tmp_path):
    """A minimal built-SPA bundle: index.html + one hashed asset."""
    (tmp_path / "index.html").write_text("<!doctype html><title>SPA-ROOT</title>")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app-abc123.js").write_text("console.log('real-asset');")
    return tmp_path


def _app(settings, **kwargs):
    return create_product_app(
        name="Test", schema="test", settings=settings, version="9.9.9", **kwargs
    )


# ---------------------------------------------------------------------------
# Seam OFF — default behaviour unchanged
# ---------------------------------------------------------------------------


def test_seam_off_root_is_404_and_api_unchanged(settings, monkeypatch):
    monkeypatch.delenv("SERVE_SPA_DIR", raising=False)
    client = TestClient(_app(settings))

    r = client.get("/")
    assert r.status_code == 404  # no SPA mount, no root route

    r = client.get("/_health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# Seam ON — SPA served, fallback rules, API priority
# ---------------------------------------------------------------------------


def test_root_serves_index(settings, spa_dir):
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/")
    assert r.status_code == 200
    assert "SPA-ROOT" in r.text


def test_real_asset_is_served(settings, spa_dir):
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert "real-asset" in r.text


def test_unknown_client_route_falls_back_to_index(settings, spa_dir):
    """Extension-less unknown path → index.html so the SPA router runs."""
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/dashboard/clients")
    assert r.status_code == 200
    assert "SPA-ROOT" in r.text


def test_missing_asset_is_real_404_not_index(settings, spa_dir):
    """Path with a file extension → real 404 (never HTML-as-JS)."""
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/assets/does-not-exist.js")
    assert r.status_code == 404
    assert "SPA-ROOT" not in r.text


def test_api_route_wins_over_spa_mount(settings, spa_dir):
    """`/_health` is registered before the `/` mount → API still answers."""
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/_health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# Env fallback + precedence
# ---------------------------------------------------------------------------


def test_env_var_is_honoured(settings, spa_dir, monkeypatch):
    monkeypatch.setenv("SERVE_SPA_DIR", str(spa_dir))
    client = TestClient(_app(settings))  # no param — env supplies it
    r = client.get("/")
    assert r.status_code == 200
    assert "SPA-ROOT" in r.text


def test_param_beats_env(settings, spa_dir, tmp_path, monkeypatch):
    """A bogus env must not override an explicit good param."""
    monkeypatch.setenv("SERVE_SPA_DIR", str(tmp_path / "nonexistent"))
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/")
    assert r.status_code == 200
    assert "SPA-ROOT" in r.text


# ---------------------------------------------------------------------------
# Fail-soft — misconfigured dir
# ---------------------------------------------------------------------------


def test_missing_index_is_fail_soft(settings, tmp_path):
    """serve_spa pointed at a dir with no index.html → no crash, API alive,
    `/` stays a plain 404 (nothing mounted).

    The seam also logs a WARNING (verified by eye in captured stdout). We
    do NOT assert on the log record here: the seed's `configure_logging()`
    reconfigures handler/propagation, so pytest's `caplog` can't see the
    `noctusai_seed.app` logger without monkeypatching our logging config —
    which the methodology forbids. The *observable* fail-soft contract (no
    crash + API still served + no SPA mount) is the real guarantee and is
    fully asserted below."""
    empty = tmp_path / "empty"
    empty.mkdir()
    client = TestClient(_app(settings, serve_spa=str(empty)))  # must not raise

    r = client.get("/_health")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get("/")
    assert r.status_code == 404  # nothing mounted
