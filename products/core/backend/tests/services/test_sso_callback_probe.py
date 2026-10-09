"""probe_sso_callback: fail-closed bundle probe via httpx.MockTransport (no network)."""
import asyncio

import httpx

from app.services.sso_callback_probe import SSO_CALLBACK_MARKER, probe_sso_callback

_SHELL = '<html><script type="module" src="/assets/index-abc.js"></script><div id="root"></div></html>'


def _run(handler):
    return asyncio.run(probe_sso_callback("http://p.test", transport=httpx.MockTransport(handler)))


def test_marker_in_entry_bundle_is_ok():
    def h(req):
        if req.url.path == "/":
            return httpx.Response(200, text=_SHELL)
        return httpx.Response(200, text=f'x="{SSO_CALLBACK_MARKER}";')
    assert _run(h).ok is True


def test_old_bundle_without_marker_is_refused():
    def h(req):
        return httpx.Response(200, text=_SHELL if req.url.path == "/" else "old callback")
    res = _run(h)
    assert res.ok is False and "marker" in res.detail


def test_shell_404_and_no_bundle_are_refused():
    assert _run(lambda r: httpx.Response(404)).ok is False
    assert _run(lambda r: httpx.Response(200, text="<html></html>")).ok is False


def test_unreachable_is_refused():
    def h(req):
        raise httpx.ConnectError("down")
    assert _run(h).ok is False
