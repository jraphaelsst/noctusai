"""Smoke tests for the Meta connector MCP — WhatsApp slice.

No network: tools run against the seed `FakeWahaClient` (returned by
`get_whatsapp_client` when no `WAHA_BASE_URL` is set — the deferred-config
rule). Mirrors `mcp/vista/tests/test_smoke.py`.

Pins, per the brief:
- the exact registered tool-name set,
- the confirm-gate (send_text without confirm → typed error, no send),
- the dotted-naming convention.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Put `mcp/` on sys.path so `from meta.X import ...` + `from _kit.X
# import ...` resolve — same trick mcp/vista/tests uses.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` MUST resolve against THIS worktree's seed (the tree
# under test). The repo's editable `noctusai_lib` install registers a
# `MetaPathFinder` that hard-maps `noctusai_lib` to whichever worktree
# `pip install -e` last ran in — which can be a *different, older*
# worktree predating the social-wiring absorption (no `meta` package).
# `sys.meta_path` finders run before `sys.path`, so a plain
# `sys.path.insert` cannot win. Deterministically rebind by dropping
# the stale editable finder + any already-imported stale modules, then
# prepending this worktree's seed so the regular PathFinder resolves
# it. This is NOT a monkeypatch (no function/class is replaced) — it
# corrects a mis-pointed package *locator* so the suite exercises the
# branch under test, per "codebase is source of truth".
_SEED = _REPO_ROOT / "seed" / "lib" / "backend"
_seed_lib = _SEED / "noctusai_lib"


def _resolves_to_this_worktree() -> bool:
    try:
        import noctusai_lib  # noqa
    except ModuleNotFoundError:
        return False
    f = getattr(noctusai_lib, "__file__", "") or ""
    return str(_seed_lib) in f


if not _resolves_to_this_worktree():
    # The editable finders are registered as *class objects* (not
    # instances), so probe via getattr(..., "__module__"/"__name__").
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


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from meta import settings, types  # noqa: F401
    from meta.tools import whatsapp  # noqa: F401
    # The shipped slice's seed dependency must genuinely ship.
    from noctusai_lib.integrations import whatsapp as wa_seed  # noqa: F401

    assert hasattr(wa_seed, "get_whatsapp_client")
    assert hasattr(wa_seed, "build_send_text_body")
    assert hasattr(wa_seed, "parse_waha_inbound_message")


def test_registered_tool_name_set_is_pinned():
    """Exact tool surface this wave — guards against silent additions."""
    from meta.tools import all_handlers

    assert set(all_handlers().keys()) == {
        "meta.whatsapp.send_text",
        "meta.whatsapp.parse_inbound",
        "meta.facebook.list_pages",
        "meta.facebook.list_page_posts",
        "meta.facebook.post_insights",
        "meta.instagram.list_accounts",
        "meta.instagram.list_media",
        "meta.instagram.media_insights",
        "meta.diagnostics.connection_status",
        "meta.diagnostics.discover_scopes",
    }


def test_all_handlers_aggregates_every_leaf():
    from meta.tools import all_descriptors, all_handlers

    descriptor_names = {d.name for d in all_descriptors()}
    handler_names = set(all_handlers().keys())
    assert descriptor_names == handler_names, (
        f"mismatch — descriptors only: {descriptor_names - handler_names}; "
        f"handlers only: {handler_names - descriptor_names}"
    )


def test_dotted_naming_convention():
    """KB § PATTERNS/mcp-tool-conventions.md § 1: 3-segment dotted names."""
    from meta.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"tool {name!r} not 3-segment dotted"
        assert parts[0] == "meta", f"tool {name!r} not under meta.* umbrella"


# ─── Settings ────────────────────────────────────────────────────────────


def test_settings_lenient_construction_no_config():
    from meta.settings import MetaConnectorSettings

    s = MetaConnectorSettings()
    assert s.configured is False
    assert s.waha_base_url is None


def test_settings_configured_tracks_waha_base_url():
    from meta.settings import MetaConnectorSettings

    assert MetaConnectorSettings(waha_base_url="http://waha:3000").configured is True


# ─── meta.whatsapp.send_text — the confirm gate ──────────────────────────


def test_send_text_without_confirm_blocks_and_typed_errors():
    """No `confirm` → typed error, sent=False, status 412, NO side-effect."""
    from meta.tools.whatsapp import send_text

    out = asyncio.run(
        send_text({"phone": "5511999998888", "text": "hello"})
    )
    assert out["sent"] is False
    assert out["error"] is not None
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412
    assert out["provider_response"] is None


def test_send_text_confirm_false_explicit_also_blocks():
    from meta.tools.whatsapp import send_text

    out = asyncio.run(
        send_text({"phone": "5511999998888", "text": "hi", "confirm": False})
    )
    assert out["sent"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"


def test_send_text_with_confirm_sends_via_fake_client():
    """confirm=true → routes through FakeWahaClient (no network)."""
    from meta.tools.whatsapp import send_text

    out = asyncio.run(
        send_text(
            {"phone": "5511999998888", "text": "confirmed hello", "confirm": True}
        )
    )
    assert out["sent"] is True
    assert out["chat_id"] == "5511999998888@c.us"
    assert out["error"] is None
    assert isinstance(out["provider_response"], dict)


# ─── meta.whatsapp.parse_inbound — pure, no confirm ──────────────────────


def test_parse_inbound_decodes_valid_waha_payload():
    from meta.tools.whatsapp import parse_inbound

    payload = {
        "event": "message",
        "session": "default",
        "payload": {
            "from": "5511988887777@c.us",
            "body": "ola",
            "id": "ABC123",
        },
    }
    out = asyncio.run(parse_inbound({"payload": payload}))
    assert out["error"] is None
    assert out["chat_id"] == "5511988887777@c.us"
    # seed `phone_from_chat_id` returns E.164 with the leading '+'.
    assert out["from_phone"] == "+5511988887777"
    assert out["text"] == "ola"
    assert out["provider_message_id"] == "ABC123"


def test_parse_inbound_missing_chat_id_typed_errors():
    from meta.tools.whatsapp import parse_inbound

    out = asyncio.run(
        parse_inbound({"payload": {"event": "message", "payload": {"body": "x"}}})
    )
    assert out["error"] is not None
    assert out["error"]["error_class"] == "WhatsAppPayloadError"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
