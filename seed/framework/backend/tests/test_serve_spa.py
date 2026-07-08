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
    """A minimal built-SPA bundle: index.html + one hashed asset + a PWA
    service-worker trio (sw.js / registerSW.js / workbox-*.js)."""
    (tmp_path / "index.html").write_text("<!doctype html><title>SPA-ROOT</title>")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app-abc123.js").write_text("console.log('real-asset');")
    # Service-worker files live at the ROOT (scope "/") — mirror a vite-plugin-pwa build.
    (tmp_path / "sw.js").write_text("/* service worker */")
    (tmp_path / "registerSW.js").write_text("/* register */")
    (tmp_path / "workbox-abc123.js").write_text("/* workbox runtime */")
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


def test_unknown_api_path_is_real_404_not_index(settings, spa_dir):
    """Unknown ``/api/...`` path → real 404, NEVER ``index.html``.

    Regression guard for the 2026-05-20 incident: a stale FE bundle calling
    ``GET /api/profiles/me/roles`` against a deployed image that didn't have
    the route landed in the SPA fallback. The 200 + HTML response made
    every shared-api-client ``response.json()`` throw ``SyntaxError:
    Unexpected token '<', "<!doctype "...`` and tripped the global
    QueryCache.onError toast ``Erro ao carregar dados`` on every Dashboard
    query. The fix in ``_mount_spa`` carves ``/api/...`` (and ``/_*`` ops
    surfaces) out of the extension-less SPA fallback so unknown API paths
    always 404.
    """
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/api/this-route-does-not-exist")
    assert r.status_code == 404
    assert "SPA-ROOT" not in r.text
    # Nested unknown api path too
    r = client.get("/api/profiles/me/roles")
    assert r.status_code == 404
    assert "SPA-ROOT" not in r.text


def test_unknown_ops_path_is_real_404_not_index(settings, spa_dir):
    """Unknown ``/_<ops>`` path → real 404, NEVER ``index.html``.

    Registered ops endpoints like ``/_health`` already win via route order
    (covered by ``test_api_route_wins_over_spa_mount``). This guards the
    *missing* ops case — e.g. probing ``/_metrics`` against a product that
    doesn't ship it must not return HTML.
    """
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))
    r = client.get("/_does-not-exist")
    assert r.status_code == 404
    assert "SPA-ROOT" not in r.text


def test_spa_shell_is_no_cache_but_assets_stay_cacheable(settings, spa_dir):
    """The index.html SHELL must be served ``Cache-Control: no-cache`` — it
    references content-hashed asset filenames, so a browser-cached shell loads
    a STALE bundle after a deploy (the new route silently misses → the auth
    gate redirects to /landing; observed on noctusai.com after a deploy). The
    hashed assets are immutable (new build ⇒ new filename) and must NOT be
    no-cached, or every visit re-downloads the whole bundle."""
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))

    root = client.get("/")
    assert "no-cache" in root.headers.get("cache-control", "").lower()

    # SPA client-route fallback also serves the shell → no-cache.
    fallback = client.get("/dashboard/clients")
    assert "no-cache" in fallback.headers.get("cache-control", "").lower()

    # Content-hashed asset → NOT no-cache (stays cacheable).
    asset = client.get("/assets/app-abc123.js")
    assert "no-cache" not in asset.headers.get("cache-control", "").lower()


def test_service_worker_scripts_are_no_cache(settings, spa_dir):
    """The service-worker script (and its registration/workbox helpers) must be
    served ``Cache-Control: no-cache`` — it is a PWA's ONLY update path and its
    FILENAME is stable across builds (unlike a hashed asset). If an intermediary
    (CloudFlare) pins a stale ``sw.js``, the SW update check never sees the new
    worker and the client is stuck on the old precached bundle forever — the
    erp-imobiliario / Marina incident (2026-07-08), and what defeats a
    ``selfDestroying`` retirement worker. Regression guard for the
    ``_is_service_worker`` no-cache carve-out in ``_mount_spa``."""
    client = TestClient(_app(settings, serve_spa=str(spa_dir)))

    for sw_path in ("/sw.js", "/registerSW.js", "/workbox-abc123.js"):
        r = client.get(sw_path)
        assert r.status_code == 200, sw_path
        assert "no-cache" in r.headers.get("cache-control", "").lower(), (
            f"{sw_path} must be no-cache (PWA update path)"
        )

    # A normal hashed asset stays cacheable (guards against over-broad matching).
    asset = client.get("/assets/app-abc123.js")
    assert "no-cache" not in asset.headers.get("cache-control", "").lower()


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
    `/` returns an honest 503 ("SPA bundle not yet built").

    The seam mounts the dir even when index.html is absent at startup
    (``check_dir=False``) so a vite ``--watch`` build that hasn't emitted the
    dist yet self-heals on the next request. When index.html is absent at
    REQUEST time the shell path returns **503** ("build in progress"), which is
    honest and retryable, rather than a bare 404 that reads like a routing bug.
    (Updated 2026-07-08: this test previously asserted 404 / "nothing mounted",
    the pre-``--watch`` contract — stale drift vs the shipped 503 branch in
    ``_mount_spa``.)

    The seam also logs a WARNING (verified by eye in captured stdout). We do
    NOT assert on the log record here: the seed's ``configure_logging()``
    reconfigures handler/propagation, so pytest's ``caplog`` can't see the
    ``noctusai_seed.app`` logger without monkeypatching our logging config —
    which the methodology forbids. The *observable* fail-soft contract (no
    crash + API still served + honest shell status) is the real guarantee and
    is fully asserted below."""
    empty = tmp_path / "empty"
    empty.mkdir()
    client = TestClient(_app(settings, serve_spa=str(empty)))  # must not raise

    r = client.get("/_health")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Shell requested but no index.html built yet → honest 503, not a crash.
    r = client.get("/")
    assert r.status_code == 503
    assert "not yet built" in r.text.lower()
