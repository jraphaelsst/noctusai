"""Smoke tests for the WAHA connector MCP.

No network: pure validation (confirm gate, chatId resolution,
settings) or `unittest.mock.patch` on the external HTTP seam
(`waha.api.request_json`). Patching an external service is sanctioned
by CLAUDE.md §1; our own code is never patched. Mirrors
`mcp/n8n/tests/test_smoke.py`.

Pins: the exact registered tool-name set, 3-segment dotted naming
under `waha.*`, the confirm gate (writes refuse + NO side-effect,
incl. the outward-facing send_text), gated-capability honesty
(not-configured ⇒ typed 424; the ping/auth tri-state), chatId
resolution, registry coherence.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively via `_kit`) must resolve to THIS
# worktree's seed — same editable-finder eviction mcp/n8n/tests does.
_SEED = _REPO_ROOT / "seed" / "lib" / "backend"
_seed_lib = _SEED / "noctusai_lib"


def _resolves_to_this_worktree() -> bool:
    try:
        import noctusai_lib  # noqa
    except ModuleNotFoundError:
        return False
    return str(_seed_lib) in (getattr(noctusai_lib, "__file__", "") or "")


if not _resolves_to_this_worktree():
    def _is_noctus_editable_finder(mp) -> bool:
        mod = getattr(mp, "__module__", "") or ""
        nm = getattr(mp, "__name__", "") or ""
        return "__editable__" in mod and nm == "_EditableFinder"

    sys.meta_path = [
        mp for mp in sys.meta_path if not _is_noctus_editable_finder(mp)
    ]
    for _name in list(sys.modules):
        if _name == "noctusai_lib" or _name.startswith("noctusai_lib."):
            del sys.modules[_name]

sys.path.insert(0, str(_SEED))

import pytest

_EXPECTED_TOOLS = {
    "waha.session.list",
    "waha.session.get",
    "waha.session.me",
    "waha.session.start",
    "waha.session.stop",
    "waha.session.restart",
    "waha.session.logout",
    "waha.message.send_text",
    "waha.message.list",
    "waha.chat.list",
    "waha.server.version",
    "waha.server.status",
    "waha.server.ping",
    "waha.diagnostics.connection_status",
}


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from waha import api, settings, types  # noqa: F401
    from waha.tools import diagnostics, message, server, session  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401

    assert hasattr(api, "request_json")


def test_registered_tool_name_set_is_pinned():
    from waha.tools import all_handlers

    assert set(all_handlers().keys()) == _EXPECTED_TOOLS


def test_descriptors_match_handlers():
    from waha.tools import all_descriptors, all_handlers

    assert {d.name for d in all_descriptors()} == set(all_handlers())


def test_dotted_naming_convention():
    from waha.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"{name!r} not 3-segment dotted"
        assert parts[0] == "waha", f"{name!r} not under waha.* umbrella"


# ─── Settings + chatId resolution ────────────────────────────────────────


def test_settings_lenient_no_config():
    from waha.settings import WahaConnectorSettings

    s = WahaConnectorSettings()
    assert s.configured is False
    assert s.default_session == "default"
    assert s.root == ""


def test_resolve_chat_id():
    from waha.types import resolve_chat_id

    assert resolve_chat_id("5511999@c.us", None) == "5511999@c.us"
    assert resolve_chat_id(None, "+55 (11) 99999-0000") == "5511999990000@c.us"
    with pytest.raises(ValueError):
        resolve_chat_id(None, None)


# ─── Confirm gate — writes refuse + perform NO side-effect ───────────────


def test_all_writes_confirm_gated_no_side_effect():
    from waha.tools.session import (
        session_start, session_stop, session_restart, session_logout,
    )
    from waha.tools.message import send_text

    cases = [
        (session_start, {}),
        (session_stop, {}),
        (session_restart, {}),
        (session_logout, {}),
        (send_text, {"text": "hi", "phone": "5511999"}),
    ]
    for fn, args in cases:
        with patch("waha.api.request_json") as req:
            out = asyncio.run(fn(args))
        req.assert_not_called()  # gate fired before any HTTP
        assert out["error"]["error_class"] == "ConfirmationRequiredError"
        assert out["error"]["status"] == 412


def test_send_text_requires_a_target():
    """No chat_id/phone ⇒ Pydantic rejects at input parse. It raises
    (the `_kit` server-level catch envelopes it, same as n8n/github);
    crucially NO HTTP call happens — no message can leak on bad input."""
    from waha.tools.message import send_text
    from pydantic import ValidationError

    with patch("waha.api.request_json") as req:
        with pytest.raises(ValidationError):
            asyncio.run(send_text({"text": "hi", "confirm": True}))
    req.assert_not_called()


def test_send_text_confirmed_posts_resolved_chatid():
    from waha.tools.message import send_text
    from waha.settings import WahaConnectorSettings

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return {"id": "true_ABCD"}

    s = WahaConnectorSettings(base_url="https://w.x", api_key="k")
    with patch("waha.tools.message.get_settings", return_value=s), patch(
        "waha.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(send_text(
            {"text": "oi", "phone": "5511988887777", "confirm": True}
        ))
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/sendText"
    assert captured["body"]["chatId"] == "5511988887777@c.us"
    assert captured["body"]["session"] == "default"
    assert out["sent"] is True
    assert out["message_id"] == "true_ABCD"


def test_session_restart_confirmed_posts_restart_verb():
    from waha.tools.session import session_restart
    from waha.settings import WahaConnectorSettings

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path)
        return {"status": "STARTING"}

    s = WahaConnectorSettings(base_url="https://w.x", api_key="k")
    with patch("waha.tools.session.get_settings", return_value=s), patch(
        "waha.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(
            session_restart({"session": "default", "confirm": True})
        )
    assert captured == {"method": "POST", "path": "/api/sessions/default/restart"}
    assert out["ok"] is True
    assert out["status"] == "STARTING"


# ─── Gated-capability honesty ────────────────────────────────────────────


def test_session_list_not_configured_typed_424_not_fake():
    from waha.tools.session import session_list
    from waha.settings import WahaConnectorSettings

    with patch("waha.tools.session.get_settings",
               return_value=WahaConnectorSettings()):
        out = asyncio.run(session_list({}))
    assert out["sessions"] == []
    assert out["error"]["status"] == 424


def test_connection_status_host_down_vs_key_bad_tristate():
    from waha.tools.diagnostics import connection_status
    from waha.settings import WahaConnectorSettings
    from waha import api

    s = WahaConnectorSettings(base_url="https://w.x", api_key="k")

    # not configured
    with patch("waha.tools.diagnostics.get_settings",
               return_value=WahaConnectorSettings()):
        out = asyncio.run(connection_status({}))
    assert out["configured"] is False and out["error"]["status"] == 424

    # host down — unauth /ping fails
    with patch("waha.tools.diagnostics.get_settings", return_value=s), patch(
        "waha.api.request_json",
        side_effect=api.WahaApiError("unreachable", status=502),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is False and out["authenticated"] is False

    # host up but key rejected — ping ok, authed call 401
    def _seq(method, path, **kw):
        if path == "/ping":
            return {"message": "pong"}
        raise api.WahaApiError("HTTP 401", status=401)

    with patch("waha.tools.diagnostics.get_settings", return_value=s), patch(
        "waha.api.request_json", side_effect=_seq
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is False
    assert out["error"]["status"] == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
