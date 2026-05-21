"""Smoke tests for the Cloudflare connector MCP.

No network: pure validation (confirm gate, settings, envelope handling)
or `unittest.mock.patch` on the external HTTP seam
(`cloudflare.api.request_json` / `request_envelope` / `urlopen`).
Patching an external service is sanctioned by CLAUDE.md §1; our own code
is never patched. Mirrors `mcp/hostinger/tests/test_smoke.py`.

NOTE — live validation deferred. There is no live Cloudflare token at
build (`mcp/cloudflare/.env` `CLOUDFLARE_API_TOKEN` is empty, pasted by
the user later). Shapes here were verified against the official
Cloudflare API v4 docs (codebase-is-source-of-truth applied to an
external API — shapes verified, not assumed); end-to-end live probing is
deferred until the user adds a scoped token.

Pins: the exact registered tool-name set, 3-segment dotted naming under
`cloudflare.*`, the confirm gate (ALL writes refuse + NO side-effect,
incl. the strongest gates `dns.delete_record` + `tunnel.delete`),
gated-capability honesty (not-configured ⇒ typed 424; the Cloudflare
`success:false` envelope ⇒ typed error carrying the cf_code; the
connection_status quad-state), the Cloudflare-clearing User-Agent
header, account-scoped-tunnel-needs-account-id, registry coherence.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively via `_kit`) must resolve to THIS
# worktree's seed — same editable-finder eviction mcp/hostinger/tests does.
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
    "cloudflare.zones.list",
    "cloudflare.zones.get",
    "cloudflare.zones.create",
    "cloudflare.dns.list_records",
    "cloudflare.dns.get_record",
    "cloudflare.dns.create_record",
    "cloudflare.dns.update_record",
    "cloudflare.dns.delete_record",
    "cloudflare.tunnel.list",
    "cloudflare.tunnel.get",
    "cloudflare.tunnel.get_config",
    "cloudflare.tunnel.create",
    "cloudflare.tunnel.delete",
    "cloudflare.tunnel.update_config",
    "cloudflare.diagnostics.connection_status",
}

_WRITE_GATES = {
    "cloudflare.zones.create",
    "cloudflare.dns.create_record",
    "cloudflare.dns.update_record",
    "cloudflare.dns.delete_record",
    "cloudflare.tunnel.create",
    "cloudflare.tunnel.delete",
    "cloudflare.tunnel.update_config",
}


def _configured_settings(**over):
    from cloudflare.settings import CloudflareConnectorSettings

    base = dict(api_token="tok", account_id="acct123")
    base.update(over)
    return CloudflareConnectorSettings(**base)


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from cloudflare import api, settings, types  # noqa: F401
    from cloudflare.tools import diagnostics, dns, tunnel, zones  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401

    assert hasattr(api, "request_json")
    assert hasattr(api, "request_envelope")


def test_registered_tool_name_set_is_pinned():
    from cloudflare.tools import all_handlers

    assert set(all_handlers().keys()) == _EXPECTED_TOOLS


def test_descriptors_match_handlers():
    from cloudflare.tools import all_descriptors, all_handlers

    assert {d.name for d in all_descriptors()} == set(all_handlers())


def test_dotted_naming_convention():
    from cloudflare.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"{name!r} not 3-segment dotted"
        assert parts[0] == "cloudflare", f"{name!r} not under cloudflare.*"


# ─── Settings ────────────────────────────────────────────────────────────


def test_settings_lenient_no_config():
    from cloudflare.settings import CloudflareConnectorSettings

    s = CloudflareConnectorSettings()
    assert s.configured is False
    # base_url defaults to the canonical Cloudflare v4 base.
    assert s.root == "https://api.cloudflare.com/client/v4"


def test_normalize_base_url_defaults_to_canonical_base():
    from cloudflare.api import DEFAULT_BASE_URL, normalize_base_url

    assert normalize_base_url("") == DEFAULT_BASE_URL
    assert normalize_base_url("https://x.test/") == "https://x.test"


# ─── Cloudflare-clearing User-Agent + Bearer (load-bearing header) ───────


def test_request_json_sends_browser_user_agent_and_bearer():
    """Cloudflare's WAF can 403 the default urllib UA; request_json MUST
    send a browser UA + Bearer auth. We patch urlopen (the stdlib
    boundary, an external service) and inspect the Request — our own code
    is never patched. The body is a valid CF envelope."""
    from cloudflare import api

    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b'{"success": true, "errors": [], "result": []}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        captured["url"] = req.full_url
        return _Resp()

    with patch("cloudflare.api.urllib.request.urlopen", side_effect=_fake_urlopen):
        out = api.request_json("GET", "/zones", api_token="tok")
    assert out == []
    # urllib title-cases header keys.
    assert captured["headers"]["Authorization"] == "Bearer tok"
    ua = captured["headers"]["User-agent"]
    assert "Mozilla/5.0" in ua and "Python-urllib" not in ua
    assert captured["url"].startswith("https://api.cloudflare.com/client/v4")


def test_request_json_no_token_is_typed_424():
    from cloudflare import api

    with pytest.raises(api.CloudflareApiError) as ei:
        api.request_json("GET", "/zones", api_token="")
    assert ei.value.status == 424


# ─── Cloudflare envelope handling (success:false ⇒ typed never-faked) ────


def test_envelope_success_false_raises_typed_with_cf_code():
    """A 200 transport with `success:false` is still a failure; the seam
    surfaces the first `errors[].code` + message — never a fabricated
    success."""
    from cloudflare import api

    class _Resp:
        status = 200

        def read(self):
            return (
                b'{"success": false, '
                b'"errors": [{"code": 1004, "message": "DNS Validation Error"}], '
                b'"result": null}'
            )

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("cloudflare.api.urllib.request.urlopen", return_value=_Resp()):
        with pytest.raises(api.CloudflareApiError) as ei:
            api.request_json("POST", "/zones/z/dns_records", api_token="tok")
    assert ei.value.cf_code == 1004
    assert "DNS Validation Error" in str(ei.value)


def test_request_json_unwraps_result_request_envelope_keeps_info():
    """request_json returns `result`; request_envelope keeps the full
    envelope incl. `result_info` (pagination)."""
    from cloudflare import api

    class _Resp:
        status = 200

        def read(self):
            return (
                b'{"success": true, "errors": [], '
                b'"result": [{"id": "z1"}], '
                b'"result_info": {"page": 1, "total_count": 1}}'
            )

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("cloudflare.api.urllib.request.urlopen", return_value=_Resp()):
        result = api.request_json("GET", "/zones", api_token="tok")
        env = api.request_envelope("GET", "/zones", api_token="tok")
    assert result == [{"id": "z1"}]
    assert env["result_info"]["total_count"] == 1


# ─── Confirm gate — ALL writes refuse + perform NO side-effect ───────────


def test_all_writes_confirm_gated_no_side_effect():
    from cloudflare.tools.zones import zones_create
    from cloudflare.tools.dns import (
        dns_create_record,
        dns_delete_record,
        dns_update_record,
    )
    from cloudflare.tools.tunnel import (
        tunnel_create,
        tunnel_delete,
        tunnel_update_config,
    )

    s = _configured_settings()
    cases = [
        (zones_create, {"name": "x.com"}, "cloudflare.tools.zones.get_settings"),
        (dns_create_record,
         {"zone_id": "z", "type": "A", "name": "a.x.com", "content": "1.2.3.4"},
         "cloudflare.tools.dns.get_settings"),
        (dns_update_record,
         {"zone_id": "z", "record_id": "r", "content": "5.6.7.8"},
         "cloudflare.tools.dns.get_settings"),
        (dns_delete_record, {"zone_id": "z", "record_id": "r"},
         "cloudflare.tools.dns.get_settings"),
        (tunnel_create, {"name": "t"}, "cloudflare.tools.tunnel.get_settings"),
        (tunnel_delete, {"tunnel_id": "tid"},
         "cloudflare.tools.tunnel.get_settings"),
        (tunnel_update_config,
         {"tunnel_id": "tid", "ingress": [{"service": "http_status:404"}]},
         "cloudflare.tools.tunnel.get_settings"),
    ]
    for fn, args, get_settings_path in cases:
        with patch(get_settings_path, return_value=s), patch(
            "cloudflare.api.request_json"
        ) as req:
            out = asyncio.run(fn(args))
        req.assert_not_called()  # gate fired before any HTTP
        assert out["error"]["error_class"] == "ConfirmationRequiredError", fn
        assert out["error"]["status"] == 412, fn


def test_delete_record_gate_message_states_irreversible():
    """The strongest DNS gate must spell out the destructive effect."""
    from cloudflare.tools.dns import dns_delete_record

    with patch("cloudflare.tools.dns.get_settings",
               return_value=_configured_settings()):
        out = asyncio.run(dns_delete_record({"zone_id": "z", "record_id": "r"}))
    assert out["error"]["status"] == 412
    assert "IRREVERSIBLE" in out["error"]["message"]


def test_tunnel_delete_gate_message_states_irreversible():
    from cloudflare.tools.tunnel import tunnel_delete

    with patch("cloudflare.tools.tunnel.get_settings",
               return_value=_configured_settings()):
        out = asyncio.run(tunnel_delete({"tunnel_id": "tid"}))
    assert out["error"]["status"] == 412
    assert "IRREVERSIBLE" in out["error"]["message"]


# ─── Confirmed writes hit the right verb + path ──────────────────────────


def test_dns_create_confirmed_posts_record():
    from cloudflare.tools.dns import dns_create_record

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return {"id": "rec1", "type": "A", "name": "a.x.com"}

    with patch("cloudflare.tools.dns.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(dns_create_record({
            "zone_id": "z1", "type": "A", "name": "a.x.com",
            "content": "1.2.3.4", "ttl": 3600, "proxied": False,
            "confirm": True,
        }))
    assert captured["method"] == "POST"
    assert captured["path"] == "/zones/z1/dns_records"
    assert captured["body"]["content"] == "1.2.3.4"
    assert captured["body"]["proxied"] is False
    assert out["ok"] is True
    assert out["record"]["id"] == "rec1"


def test_dns_delete_confirmed_calls_delete_verb():
    from cloudflare.tools.dns import dns_delete_record

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path)
        return {"id": "rec1"}

    with patch("cloudflare.tools.dns.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(dns_delete_record({
            "zone_id": "z1", "record_id": "rec1", "confirm": True,
        }))
    assert captured["method"] == "DELETE"
    assert captured["path"] == "/zones/z1/dns_records/rec1"
    assert out["ok"] is True


def test_zones_create_confirmed_uses_configured_account_id():
    from cloudflare.tools.zones import zones_create

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return {"id": "z1", "name": "x.com"}

    with patch("cloudflare.tools.zones.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(zones_create({"name": "x.com", "confirm": True}))
    assert captured["method"] == "POST"
    assert captured["path"] == "/zones"
    assert captured["body"]["account"]["id"] == "acct123"
    assert captured["body"]["type"] == "full"
    assert out["ok"] is True


def test_tunnel_update_config_confirmed_wraps_ingress_and_puts():
    from cloudflare.tools.tunnel import tunnel_update_config

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return {"config": {"ingress": []}}

    ingress = [
        {"hostname": "app.x.com", "service": "http://localhost:8000"},
        {"service": "http_status:404"},
    ]
    with patch("cloudflare.tools.tunnel.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(tunnel_update_config({
            "tunnel_id": "tid", "ingress": ingress, "confirm": True,
        }))
    assert captured["method"] == "PUT"
    assert captured["path"] == "/accounts/acct123/cfd_tunnel/tid/configurations"
    assert captured["body"] == {"config": {"ingress": ingress}}
    assert out["ok"] is True


# ─── Reads — shapes pinned to the documented CF v4 responses ─────────────


def test_zones_list_unwraps_result_and_filter():
    from cloudflare.tools.zones import zones_list

    captured = {}

    def _cap(method, path, **kw):
        captured.update(params=kw.get("params"))
        return {"success": True, "result": [{"id": "z1", "name": "x.com"}],
                "result_info": {"total_count": 1}}

    with patch("cloudflare.tools.zones.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_envelope", side_effect=_cap
    ):
        out = asyncio.run(zones_list({"name": "x.com"}))
    assert out["zones"] == [{"id": "z1", "name": "x.com"}]
    assert out["result_info"]["total_count"] == 1
    assert captured["params"]["name"] == "x.com"


def test_dns_list_records_passes_filters():
    from cloudflare.tools.dns import dns_list_records

    captured = {}

    def _cap(method, path, **kw):
        captured.update(path=path, params=kw.get("params"))
        return {"success": True, "result": [{"id": "r1", "type": "A"}],
                "result_info": {"count": 1}}

    with patch("cloudflare.tools.dns.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_envelope", side_effect=_cap
    ):
        out = asyncio.run(dns_list_records({
            "zone_id": "z1", "type": "A", "name": "a.x.com",
        }))
    assert captured["path"] == "/zones/z1/dns_records"
    assert captured["params"]["type"] == "A"
    assert captured["params"]["name"] == "a.x.com"
    assert out["records"] == [{"id": "r1", "type": "A"}]


def test_tunnel_get_extracts_status_and_uses_account_path():
    from cloudflare.tools.tunnel import tunnel_get

    captured = {}

    def _cap(method, path, **kw):
        captured.update(path=path)
        return {"id": "tid", "name": "t", "status": "inactive"}

    with patch("cloudflare.tools.tunnel.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(tunnel_get({"tunnel_id": "tid"}))
    assert captured["path"] == "/accounts/acct123/cfd_tunnel/tid"
    assert out["status"] == "inactive"
    assert out["tunnel"]["name"] == "t"


# ─── Account-scoped tunnel tools need the account id ─────────────────────


def test_tunnel_list_without_account_id_typed_424_not_fake():
    from cloudflare.tools.tunnel import tunnel_list

    # token present but NO account id ⇒ account-scoped path can't be built.
    with patch("cloudflare.tools.tunnel.get_settings",
               return_value=_configured_settings(account_id=None)):
        out = asyncio.run(tunnel_list({}))
    assert out["tunnels"] == []
    assert out["error"]["status"] == 424


def test_zones_create_without_account_id_typed_424_not_fake():
    from cloudflare.tools.zones import zones_create

    with patch("cloudflare.tools.zones.get_settings",
               return_value=_configured_settings(account_id=None)):
        out = asyncio.run(zones_create({"name": "x.com", "confirm": True}))
    assert out["error"]["status"] == 424


# ─── Gated-capability honesty ────────────────────────────────────────────


def test_dns_list_not_configured_typed_424_not_fake():
    from cloudflare.tools.dns import dns_list_records
    from cloudflare.settings import CloudflareConnectorSettings

    with patch("cloudflare.tools.dns.get_settings",
               return_value=CloudflareConnectorSettings()):
        out = asyncio.run(dns_list_records({"zone_id": "z"}))
    assert out["records"] == []
    assert out["error"]["status"] == 424


def test_dns_create_surfaces_cf_success_false_not_fake():
    """A success:false envelope reaches the tool as a CloudflareApiError
    (status 200, cf_code set); the tool surfaces it, never a fake record."""
    from cloudflare.tools.dns import dns_create_record
    from cloudflare import api

    err = api.CloudflareApiError(
        "success=false (code 1004): DNS Validation Error",
        status=200, cf_code=1004,
    )
    with patch("cloudflare.tools.dns.get_settings",
               return_value=_configured_settings()), patch(
        "cloudflare.api.request_json", side_effect=err
    ):
        out = asyncio.run(dns_create_record({
            "zone_id": "z", "type": "A", "name": "a.x.com",
            "content": "bad", "confirm": True,
        }))
    assert out["record"] is None
    assert out["error"]["status"] == 200


def test_connection_status_quad_state():
    from cloudflare.tools.diagnostics import connection_status
    from cloudflare.settings import CloudflareConnectorSettings
    from cloudflare import api

    s = _configured_settings()

    # not configured
    with patch("cloudflare.tools.diagnostics.get_settings",
               return_value=CloudflareConnectorSettings()):
        out = asyncio.run(connection_status({}))
    assert out["configured"] is False and out["error"]["status"] == 424

    # host down / unreachable (network failure → 502)
    with patch("cloudflare.tools.diagnostics.get_settings", return_value=s), patch(
        "cloudflare.api.request_json",
        side_effect=api.CloudflareApiError("unreachable", status=502),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is False and out["authenticated"] is False

    # token rejected (401 → reachable but not authenticated)
    with patch("cloudflare.tools.diagnostics.get_settings", return_value=s), patch(
        "cloudflare.api.request_json",
        side_effect=api.CloudflareApiError("HTTP 401", status=401),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is False
    assert out["error"]["status"] == 401

    # token rejected via success:false envelope (status 200 → not authed)
    with patch("cloudflare.tools.diagnostics.get_settings", return_value=s), patch(
        "cloudflare.api.request_json",
        side_effect=api.CloudflareApiError("success=false", status=200,
                                           cf_code=1000),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is False

    # ok (200 verified)
    with patch("cloudflare.tools.diagnostics.get_settings", return_value=s), patch(
        "cloudflare.api.request_json",
        return_value={"id": "tokid", "status": "active"},
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is True
    assert out["token_status"] == "active"
    assert out["account_id_present"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
