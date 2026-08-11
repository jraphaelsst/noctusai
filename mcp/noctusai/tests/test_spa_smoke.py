"""`noctus.dev.spa_smoke` — the frontend gate no other deploy check covers.

WHY (2026-08-11). Every existing gate is blind to a broken JS bundle:
`deploy_image` proves the CONTAINER is up, `/api/health` proves the BACKEND
answers, and the public edge returns 200 for the HTML SHELL even when the bundle
is missing. All three stay green while every user sees a blank page. Under
PROD-ONLY there is no dev fleet to catch it first, and the react-router v6→v7
fleet migration was exactly this exposure.

The tests below are mostly NEGATIVE on purpose: a gate is only worth its cost if
it fails on the thing it exists to catch, and the live fleet is green, so a
happy-path-only suite would prove nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import spa_smoke as ss  # noqa: E402

SHELL = '<html><body><div id="root"></div><script src="/assets/index-abc.js"></script></body></html>'
BUNDLE = ("// app\n" + "x" * 20_000).encode()


def _responder(mapping):
    """Fake `_fetch`: maps a URL SUFFIX -> (status, body, content_type)."""
    def _fetch(url, timeout=25):
        for suffix, resp in mapping.items():
            if url.endswith(suffix):
                return resp
        return 404, b"", ""
    return _fetch


def _ok_map():
    return {
        "/assets/index-abc.js": (200, BUNDLE, "application/javascript"),
        "/login": (200, b"<html></html>", "text/html"),
        "/": (200, SHELL.encode(), "text/html"),
    }


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """🔴 Fail loudly if a test forgets to install a fake `_fetch`.

    Without this, a test that omits its `fetch(...)` call silently hits LIVE PROD
    and passes because the fleet is green — a false green that proves nothing.
    That happened while writing this file (test_bundle_404_is_caught).
    """
    def _boom(url, timeout=25):
        raise AssertionError(
            f"test attempted a REAL network call to {url} — install a fake first: fetch({{...}})"
        )
    monkeypatch.setattr(ss, "_fetch", _boom)


@pytest.fixture
def fetch(monkeypatch):
    def _install(mapping):
        monkeypatch.setattr(ss, "_fetch", _responder(mapping))
    return _install


class TestHappyPath:
    def test_all_checks_pass(self, fetch):
        fetch(_ok_map())
        r = ss.smoke_product("seed")
        assert r["ok"] is True, r["failures"]

    def test_sends_a_browser_user_agent(self):
        """CF WAF rule 1010 rejects programmatic UAs — a non-browser UA would make
        every product look broken."""
        assert "Mozilla/5.0" in ss._BROWSER_UA and "Chrome/" in ss._BROWSER_UA


class TestCatchesRealFailureModes:
    def test_bundle_404_is_caught(self, fetch):
        m = _ok_map(); m["/assets/index-abc.js"] = (404, b"", "")
        fetch(m)
        r = ss.smoke_product("seed")
        assert r["ok"] is False
        assert any("bundle_http" in f for f in r["failures"])

    def test_spa_fallback_served_as_the_asset_is_caught(self, fetch):
        """🔴 The silent killer: a missing asset rewritten to index.html returns
        200. A naive status check passes; the page is blank."""
        m = _ok_map()
        m["/assets/index-abc.js"] = (200, b"<!doctype html><html></html>", "text/html")
        fetch(m)
        r = ss.smoke_product("seed")
        assert r["ok"] is False
        assert any("bundle_is_js" in f for f in r["failures"])

    def test_truncated_bundle_is_caught(self, fetch):
        m = _ok_map(); m["/assets/index-abc.js"] = (200, b"tiny", "application/javascript")
        fetch(m)
        r = ss.smoke_product("seed")
        assert r["ok"] is False
        assert any("bundle_size" in f for f in r["failures"])

    def test_shell_without_a_bundle_tag_is_caught(self, fetch):
        m = _ok_map(); m["/"] = (200, b'<html><div id="root"></div></html>', "text/html")
        fetch(m)
        r = ss.smoke_product("seed")
        assert r["ok"] is False
        assert any("shell_bundle_tag" in f for f in r["failures"])

    def test_missing_mount_point_is_caught(self, fetch):
        m = _ok_map()
        m["/"] = (200, b'<html><script src="/assets/index-abc.js"></script></html>', "text/html")
        fetch(m)
        r = ss.smoke_product("seed")
        assert r["ok"] is False
        assert any("shell_root_div" in f for f in r["failures"])

    def test_broken_deep_link_is_caught(self, fetch):
        """SPA fallback not wired ⇒ the router never boots on a direct hit."""
        m = _ok_map(); m["/login"] = (404, b"", "")
        fetch(m)
        r = ss.smoke_product("seed")
        assert r["ok"] is False
        assert any("deep_link" in f for f in r["failures"])

    def test_unreachable_host_is_caught_not_raised(self, fetch):
        fetch({})  # everything 404s
        r = ss.smoke_product("seed")
        assert r["ok"] is False
        assert any("shell_http" in f for f in r["failures"])

    def test_shell_failure_short_circuits(self, fetch):
        """Don't report six confusing failures when the site is simply down."""
        fetch({"/": (503, b"", "")})
        r = ss.smoke_product("seed")
        assert len(r["failures"]) == 1


class TestVersionMarkers:
    def test_expect_absent_catches_a_stale_bundle(self, fetch):
        """How the react-router v7 migration was verified: `@remix-run/router` is
        v6-only, so its presence means the old bundle is still being served."""
        m = _ok_map()
        m["/assets/index-abc.js"] = (200, b"x" * 20_000 + b"@remix-run/router", "application/javascript")
        fetch(m)
        r = ss.smoke_product("seed", expect_absent=["@remix-run/router"])
        assert r["ok"] is False
        assert any("absent:@remix-run/router" in f for f in r["failures"])

    def test_expect_absent_passes_when_clean(self, fetch):
        fetch(_ok_map())
        assert ss.smoke_product("seed", expect_absent=["@remix-run/router"])["ok"] is True

    def test_expect_present_catches_a_missing_marker(self, fetch):
        fetch(_ok_map())
        r = ss.smoke_product("seed", expect_present=["createBrowserRouter"])
        assert r["ok"] is False


class TestFleetScope:
    def test_defaults_to_the_build_scope_active_set(self, fetch, monkeypatch):
        """Gate and build must never disagree about which products matter."""
        fetch(_ok_map())
        monkeypatch.setattr(ss, "_live_slugs", lambda: ["core", "seed"])
        assert ss.spa_smoke()["checked"] == 2

    def test_explicit_products_override_the_file(self, fetch):
        fetch(_ok_map())
        assert ss.spa_smoke(products=["orbity"])["checked"] == 1

    def test_one_bad_product_fails_the_whole_run_and_is_named(self, fetch, monkeypatch):
        monkeypatch.setattr(ss, "_live_slugs", lambda: ["core", "seed"])
        def _fetch(url, timeout=25):
            if "core." in url and url.endswith("/"):
                return 503, b"", ""
            return _responder(_ok_map())(url, timeout)
        monkeypatch.setattr(ss, "_fetch", _fetch)
        out = ss.spa_smoke()
        assert out["ok"] is False and out["failed"] == ["core"]

    def test_empty_scope_refuses_rather_than_reporting_success(self, monkeypatch):
        """Smoking zero products must never look like a pass."""
        monkeypatch.setattr(ss, "_live_slugs", lambda: [])
        out = ss.spa_smoke()
        assert out["ok"] is False and out["status"] == "error"
        assert "build-scope" in out["error"]


class TestWiring:
    def test_cli_flag_exists(self):
        cli = (Path(__file__).resolve().parents[1] / "cli.py").read_text()
        assert "--spa-smoke" in cli and "spa_smoke" in cli

    def test_tool_is_registered(self):
        init = (Path(__file__).resolve().parents[1] / "tools/noctus/dev/__init__.py").read_text()
        assert "spa_smoke.register(server)" in init

    def test_noc_ship_runs_it(self):
        """A gate nobody invokes is decoration."""
        skill = Path(__file__).resolve().parents[3] / ".claude/skills/noc-ship/SKILL.md"
        assert "spa_smoke" in skill.read_text()
