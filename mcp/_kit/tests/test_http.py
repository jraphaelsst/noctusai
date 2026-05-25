"""Unit tests for the shared `_kit.http` request seam + the confirm-message
helper. The external boundary patched is `_kit.http.urlopen` — the stable seam
consuming connectors also patch (no network)."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

# `mcp/` on path so `_kit` imports as a top-level package (same as connectors).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _kit import transport as http  # noqa: E402
from _kit.errors import confirmation_required_message  # noqa: E402


class _FakeResp:
    """Minimal context-manager response with a `.read()` like urlopen's."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _ok(body: bytes = b'{"ok": true}', cap: dict | None = None):
    def fake(req, timeout=None):
        if cap is not None:
            cap["req"] = req
            cap["timeout"] = timeout
        return _FakeResp(body)

    return patch.object(http, "urlopen", fake)


class _VendorErr(Exception):
    """Stand-in for a connector's `<Vendor>ApiError` — same ctor contract."""

    def __init__(self, message: str, *, status=None):
        super().__init__(message)
        self.status = status


def test_get_parses_json_injects_auth_ua_drops_none_params():
    cap: dict = {}
    with _ok(b'{"ok": true}', cap):
        out = http.request_json(
            "get",
            "https://api.example.com/x",
            auth_header=("X-Api-Key", "secret"),
            user_agent=http.BROWSER_USER_AGENT,
            params={"a": 1, "b": None, "c": "z"},
        )
    assert out == {"ok": True}
    req = cap["req"]
    assert req.get_method() == "GET"
    assert req.full_url == "https://api.example.com/x?a=1&c=z"  # None dropped
    assert req.get_header("X-api-key") == "secret"
    assert req.get_header("User-agent") == http.BROWSER_USER_AGENT
    assert req.get_header("Content-type") is None  # no body on GET


def test_post_sends_json_body_and_bearer_auth():
    cap: dict = {}
    with _ok(b'{"id": 7}', cap):
        out = http.request_json(
            "post",
            "https://api.example.com/x",
            auth_header=("Authorization", "Bearer tok"),
            body={"name": "n"},
        )
    assert out == {"id": 7}
    req = cap["req"]
    assert req.get_method() == "POST"
    assert json.loads(req.data) == {"name": "n"}
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("Authorization") == "Bearer tok"


def test_default_user_agent_when_unspecified():
    cap: dict = {}
    with _ok(b"{}", cap):
        http.request_json("get", "https://x/y")
    assert cap["req"].get_header("User-agent") == http.DEFAULT_USER_AGENT


def test_no_auth_header_when_none():
    cap: dict = {}
    with _ok(b"{}", cap):
        http.request_json("get", "https://x/y", auth_header=None)
    assert cap["req"].get_header("Authorization") is None


def test_http_error_raises_error_cls_with_upstream_status():
    err = urllib.error.HTTPError("u", 404, "NF", {}, io.BytesIO(b'{"e":1}'))
    with patch.object(http, "urlopen", side_effect=err):
        with pytest.raises(_VendorErr) as ei:
            http.request_json("get", "https://x/y", error_cls=_VendorErr)
    assert ei.value.status == 404


def test_url_error_raises_502():
    with patch.object(http, "urlopen", side_effect=urllib.error.URLError("down")):
        with pytest.raises(_VendorErr) as ei:
            http.request_json("get", "https://x/y", error_cls=_VendorErr)
    assert ei.value.status == 502


def test_timeout_raises_502():
    with patch.object(http, "urlopen", side_effect=TimeoutError()):
        with pytest.raises(_VendorErr) as ei:
            http.request_json("get", "https://x/y", error_cls=_VendorErr)
    assert ei.value.status == 502


def test_empty_body_returns_empty_result():
    with _ok(b""):
        assert http.request_json("get", "https://x/y", empty_result={}) == {}
    with _ok(b""):
        assert http.request_json("get", "https://x/y") is None


def test_non_json_raises_502():
    with _ok(b"<html>nope</html>"):
        with pytest.raises(_VendorErr) as ei:
            http.request_json("get", "https://x/y", error_cls=_VendorErr)
    assert ei.value.status == 502


def test_default_error_cls_is_connector_http_error():
    with patch.object(http, "urlopen", side_effect=urllib.error.URLError("down")):
        with pytest.raises(http.ConnectorHttpError):
            http.request_json("get", "https://x/y")


def test_normalize_base_url_trims_slashes():
    assert http.normalize_base_url("https://x/") == "https://x"
    assert http.normalize_base_url("https://x///") == "https://x"
    assert http.normalize_base_url("") == ""


def test_confirmation_required_message_shapes():
    m = confirmation_required_message("n8n.workflow.delete")
    assert "'n8n.workflow.delete' is a write action" in m
    assert "Re-call with confirm=true to perform it" in m
    assert "NO side-effect was performed" in m
    assert "— " not in m  # no effect clause when effect omitted

    m2 = confirmation_required_message("cf.dns.delete_record", "removes a public DNS record")
    assert "— removes a public DNS record" in m2

    m3 = confirmation_required_message("hostinger.vps.stop", noun="write/power action")
    assert "is a write/power action" in m3
