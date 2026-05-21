"""Smoke tests for the Hostinger connector MCP.

No network: pure validation (confirm gate, settings) or
`unittest.mock.patch` on the external HTTP seam
(`hostinger.api.request_json`). Patching an external service is
sanctioned by CLAUDE.md §1; our own code is never patched. Mirrors
`mcp/waha/tests/test_smoke.py` / `mcp/n8n/tests/test_smoke.py`.

Pins: the exact registered tool-name set, 3-segment dotted naming
under `hostinger.*`, the confirm gate (power writes refuse + NO
side-effect, incl. the strongest-gate `stop` whose message states it
takes the server down), gated-capability honesty (not-configured ⇒
typed 424; the connection_status quad-state), the Cloudflare-clearing
User-Agent header, registry coherence.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively via `_kit`) must resolve to THIS
# worktree's seed — same editable-finder eviction mcp/waha/tests does.
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
    "hostinger.vps.list",
    "hostinger.vps.get",
    "hostinger.vps.metrics",
    "hostinger.vps.actions",
    "hostinger.vps.restart",
    "hostinger.vps.start",
    "hostinger.vps.stop",
    "hostinger.diagnostics.connection_status",
}


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from hostinger import api, settings, types  # noqa: F401
    from hostinger.tools import diagnostics, vps  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401

    assert hasattr(api, "request_json")


def test_registered_tool_name_set_is_pinned():
    from hostinger.tools import all_handlers

    assert set(all_handlers().keys()) == _EXPECTED_TOOLS


def test_descriptors_match_handlers():
    from hostinger.tools import all_descriptors, all_handlers

    assert {d.name for d in all_descriptors()} == set(all_handlers())


def test_dotted_naming_convention():
    from hostinger.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"{name!r} not 3-segment dotted"
        assert parts[0] == "hostinger", f"{name!r} not under hostinger.*"


# ─── Settings ────────────────────────────────────────────────────────────


def test_settings_lenient_no_config():
    from hostinger.settings import HostingerConnectorSettings

    s = HostingerConnectorSettings()
    assert s.configured is False
    # base_url defaults to the canonical Hostinger host.
    assert s.root == "https://developers.hostinger.com"


def test_normalize_base_url_defaults_to_canonical_host():
    from hostinger.api import DEFAULT_BASE_URL, normalize_base_url

    assert normalize_base_url("") == DEFAULT_BASE_URL
    assert normalize_base_url("https://x.test/") == "https://x.test"


# ─── Cloudflare-clearing User-Agent (load-bearing header) ────────────────


def test_request_json_sends_browser_user_agent_and_bearer():
    """The host sits behind Cloudflare which 403s the default urllib UA;
    request_json MUST send a browser UA + Bearer auth. We patch urlopen
    (the stdlib boundary, an external service) and inspect the Request —
    our own code is never patched."""
    from hostinger import api

    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        captured["url"] = req.full_url
        return _Resp()

    with patch("hostinger.api.urllib.request.urlopen", side_effect=_fake_urlopen):
        out = api.request_json("GET", "/api/vps/v1/virtual-machines",
                               api_token="tok")
    assert out == []
    # urllib title-cases header keys.
    assert captured["headers"]["Authorization"] == "Bearer tok"
    ua = captured["headers"]["User-agent"]
    assert "Mozilla/5.0" in ua and "Python-urllib" not in ua
    assert captured["url"].startswith("https://developers.hostinger.com")


def test_request_json_no_token_is_typed_424():
    from hostinger import api

    with pytest.raises(api.HostingerApiError) as ei:
        api.request_json("GET", "/api/vps/v1/virtual-machines", api_token="")
    assert ei.value.status == 424


# ─── Confirm gate — power writes refuse + perform NO side-effect ─────────


def test_all_power_writes_confirm_gated_no_side_effect():
    from hostinger.tools.vps import vps_restart, vps_start, vps_stop

    cases = [vps_restart, vps_start, vps_stop]
    for fn in cases:
        with patch("hostinger.api.request_json") as req:
            out = asyncio.run(fn({"vm_id": 1303151}))
        req.assert_not_called()  # gate fired before any HTTP
        assert out["error"]["error_class"] == "ConfirmationRequiredError"
        assert out["error"]["status"] == 412


def test_stop_gate_message_states_server_goes_down():
    """The strongest gate must spell out the destructive effect so the
    operator understands what confirm=true authorizes."""
    from hostinger.tools.vps import vps_stop

    out = asyncio.run(vps_stop({"vm_id": 1303151}))
    assert out["error"]["status"] == 412
    assert "TAKES THE SERVER DOWN" in out["error"]["message"]


def test_stop_confirmed_posts_stop_verb():
    from hostinger.tools.vps import vps_stop
    from hostinger.settings import HostingerConnectorSettings

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path)
        return {"id": 999, "state": "stopping"}

    s = HostingerConnectorSettings(api_token="tok")
    with patch("hostinger.tools.vps.get_settings", return_value=s), patch(
        "hostinger.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(vps_stop({"vm_id": 1303151, "confirm": True}))
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/vps/v1/virtual-machines/1303151/stop"
    assert out["ok"] is True
    assert out["action"] == "stop"


# ─── Reads — shapes pinned to the live-verified responses ────────────────


def test_vps_list_unwraps_array():
    from hostinger.tools.vps import vps_list
    from hostinger.settings import HostingerConnectorSettings

    s = HostingerConnectorSettings(api_token="tok")
    payload = [{"id": 1303151, "state": "running"}]
    with patch("hostinger.tools.vps.get_settings", return_value=s), patch(
        "hostinger.api.request_json", return_value=payload
    ):
        out = asyncio.run(vps_list({}))
    assert out["virtual_machines"] == payload
    assert out["error"] is None


def test_vps_get_extracts_state():
    from hostinger.tools.vps import vps_get
    from hostinger.settings import HostingerConnectorSettings

    s = HostingerConnectorSettings(api_token="tok")
    payload = {"id": 1303151, "state": "running", "hostname": "srv.test"}
    with patch("hostinger.tools.vps.get_settings", return_value=s), patch(
        "hostinger.api.request_json", return_value=payload
    ):
        out = asyncio.run(vps_get({"vm_id": 1303151}))
    assert out["virtual_machine"] == payload
    assert out["state"] == "running"


def test_vps_actions_unwraps_data_and_meta():
    from hostinger.tools.vps import vps_actions
    from hostinger.settings import HostingerConnectorSettings

    s = HostingerConnectorSettings(api_token="tok")
    payload = {"data": [{"id": 1, "name": "backup_create"}], "meta": {"total": 1}}
    with patch("hostinger.tools.vps.get_settings", return_value=s), patch(
        "hostinger.api.request_json", return_value=payload
    ):
        out = asyncio.run(vps_actions({"vm_id": 1303151}))
    assert out["actions"] == payload["data"]
    assert out["meta"] == {"total": 1}


def test_vps_metrics_passes_date_params():
    from hostinger.tools.vps import vps_metrics
    from hostinger.settings import HostingerConnectorSettings

    captured = {}

    def _cap(method, path, **kw):
        captured.update(path=path, params=kw.get("params"))
        return {"cpu_usage": {"unit": "%", "usage": {}}}

    s = HostingerConnectorSettings(api_token="tok")
    with patch("hostinger.tools.vps.get_settings", return_value=s), patch(
        "hostinger.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(vps_metrics({
            "vm_id": 1303151,
            "date_from": "2026-05-20T00:00:00Z",
            "date_to": "2026-05-21T00:00:00Z",
        }))
    assert captured["path"] == "/api/vps/v1/virtual-machines/1303151/metrics"
    assert captured["params"]["date_from"] == "2026-05-20T00:00:00Z"
    assert captured["params"]["date_to"] == "2026-05-21T00:00:00Z"
    assert "cpu_usage" in out["metrics"]


def test_vps_metrics_missing_dates_surfaces_typed_422_not_fake():
    """Omitting the API-required dates ⇒ upstream 422; surfaced as a
    typed never-faked error, never a fabricated empty series."""
    from hostinger.tools.vps import vps_metrics
    from hostinger.settings import HostingerConnectorSettings
    from hostinger import api

    s = HostingerConnectorSettings(api_token="tok")
    with patch("hostinger.tools.vps.get_settings", return_value=s), patch(
        "hostinger.api.request_json",
        side_effect=api.HostingerApiError("HTTP 422", status=422),
    ):
        out = asyncio.run(vps_metrics({"vm_id": 1303151}))
    assert out["metrics"] is None
    assert out["error"]["status"] == 422


# ─── Gated-capability honesty ────────────────────────────────────────────


def test_vps_list_not_configured_typed_424_not_fake():
    from hostinger.tools.vps import vps_list
    from hostinger.settings import HostingerConnectorSettings

    with patch("hostinger.tools.vps.get_settings",
               return_value=HostingerConnectorSettings()):
        out = asyncio.run(vps_list({}))
    assert out["virtual_machines"] == []
    assert out["error"]["status"] == 424


def test_connection_status_quad_state():
    from hostinger.tools.diagnostics import connection_status
    from hostinger.settings import HostingerConnectorSettings
    from hostinger import api

    s = HostingerConnectorSettings(api_token="tok")

    # not configured
    with patch("hostinger.tools.diagnostics.get_settings",
               return_value=HostingerConnectorSettings()):
        out = asyncio.run(connection_status({}))
    assert out["configured"] is False and out["error"]["status"] == 424

    # host down / unreachable (network failure → 502)
    with patch("hostinger.tools.diagnostics.get_settings", return_value=s), patch(
        "hostinger.api.request_json",
        side_effect=api.HostingerApiError("unreachable", status=502),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is False and out["authenticated"] is False

    # token rejected (401/403 → reachable but not authenticated)
    with patch("hostinger.tools.diagnostics.get_settings", return_value=s), patch(
        "hostinger.api.request_json",
        side_effect=api.HostingerApiError("HTTP 401", status=401),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is False
    assert out["error"]["status"] == 401

    # ok (200)
    with patch("hostinger.tools.diagnostics.get_settings", return_value=s), patch(
        "hostinger.api.request_json", return_value=[{"id": 1303151}],
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is True
    assert out["vm_count"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
