"""Smoke tests for the n8n connector MCP.

No network: every test either exercises pure validation (confirm gate,
settings) or `unittest.mock.patch`-es the external HTTP seam
(`n8n.api.request_json`). Patching an external service is sanctioned by
CLAUDE.md §1; our own code is never patched. Mirrors
`mcp/github/tests/test_smoke.py`.

Pins, per the connector contract:
- the exact registered tool-name set (guards silent additions),
- 3-segment dotted naming under the `n8n.*` umbrella,
- the confirm gate (write tools refuse + perform NO side-effect),
- gated-capability honesty (not-configured ⇒ typed 424, never faked),
- best-effort error extraction from real-shaped run-data,
- descriptors/handlers aggregation coherence.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

# Put `mcp/` on sys.path so `from n8n.X import ...` + `from _kit.X
# import ...` resolve — same trick mcp/github/tests uses.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively pulled by `_kit`) MUST resolve against
# THIS worktree's seed — same editable-finder eviction mcp/github/tests
# performs (see that file's comment for the full rationale).
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
    "n8n.workflow.list",
    "n8n.workflow.get",
    "n8n.workflow.activate",
    "n8n.workflow.deactivate",
    "n8n.workflow.update",
    "n8n.workflow.create",
    "n8n.workflow.delete",
    "n8n.workflow.set_tags",
    "n8n.execution.list",
    "n8n.execution.get",
    "n8n.execution.delete",
    "n8n.tag.list",
    "n8n.credential.create",
    "n8n.credential.delete",
    "n8n.credential.schema",
    "n8n.diagnostics.connection_status",
}


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from n8n import api, settings, types  # noqa: F401
    from n8n.tools import diagnostics, execution, workflow  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401

    assert hasattr(api, "request_json")
    assert hasattr(api, "normalize_base_url")


def test_registered_tool_name_set_is_pinned():
    from n8n.tools import all_handlers

    assert set(all_handlers().keys()) == _EXPECTED_TOOLS


def test_all_handlers_aggregates_every_leaf():
    from n8n.tools import all_descriptors, all_handlers

    descriptor_names = {d.name for d in all_descriptors()}
    handler_names = set(all_handlers().keys())
    assert descriptor_names == handler_names, (
        f"mismatch — descriptors only: {descriptor_names - handler_names}; "
        f"handlers only: {handler_names - descriptor_names}"
    )


def test_dotted_naming_convention():
    """KB § PATTERNS/mcp-tool-conventions.md § 1: 3-segment dotted names."""
    from n8n.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"tool {name!r} not 3-segment dotted"
        assert parts[0] == "n8n", f"tool {name!r} not under n8n.* umbrella"


# ─── Settings + URL normalization ────────────────────────────────────────


def test_settings_lenient_construction_no_config():
    from n8n.settings import N8nConnectorSettings

    s = N8nConnectorSettings()
    assert s.base_url is None
    assert s.configured is False
    assert s.api_root == ""


def test_base_url_normalization_idempotent():
    from n8n.api import normalize_base_url

    assert normalize_base_url("https://n8n.x.com") == "https://n8n.x.com/api/v1"
    assert (
        normalize_base_url("https://n8n.x.com/") == "https://n8n.x.com/api/v1"
    )
    assert (
        normalize_base_url("https://n8n.x.com/api/v1")
        == "https://n8n.x.com/api/v1"
    )
    assert normalize_base_url("") == ""


# ─── Confirm gate — writes refuse + perform NO side-effect ───────────────


def test_workflow_activate_without_confirm_blocks_no_side_effect():
    from n8n.tools.workflow import workflow_activate

    with patch("n8n.api.request_json") as req:
        out = asyncio.run(workflow_activate({"id": "abc"}))
    req.assert_not_called()  # NO HTTP — the gate fired first
    assert out["changed"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412


def test_workflow_deactivate_confirm_false_explicit_also_blocks():
    from n8n.tools.workflow import workflow_deactivate

    with patch("n8n.api.request_json") as req:
        out = asyncio.run(
            workflow_deactivate({"id": "abc", "confirm": False})
        )
    req.assert_not_called()
    assert out["error"]["status"] == 412


def test_workflow_update_without_confirm_blocks_no_side_effect():
    from n8n.tools.workflow import workflow_update

    with patch("n8n.api.request_json") as req:
        out = asyncio.run(
            workflow_update({"id": "abc", "workflow": {"name": "x"}})
        )
    req.assert_not_called()
    assert out["updated"] is False
    assert out["error"]["status"] == 412


def test_workflow_update_sanitizes_to_put_keys():
    """Read-only keys (id/active/tags/timestamps) are stripped so n8n
    does not 400 on additional properties; settings always present."""
    from n8n.tools.workflow import workflow_update

    captured = {}

    def _cap(method, path, **kw):
        captured["method"] = method
        captured["path"] = path
        captured["body"] = kw.get("body")
        return {"id": "abc", "name": "Flow"}

    dirty = {
        "id": "abc",
        "name": "Flow",
        "active": True,
        "tags": [{"id": "1", "name": "prod"}],
        "createdAt": "2026-01-01",
        "updatedAt": "2026-05-19",
        "versionId": "v9",
        "triggerCount": 3,
        "nodes": [{"name": "Webhook"}],
        "connections": {"Webhook": {}},
    }
    with patch("n8n.api.request_json", side_effect=_cap):
        out = asyncio.run(
            workflow_update({"id": "abc", "workflow": dirty, "confirm": True})
        )
    assert captured["method"] == "PUT"
    assert captured["path"] == "/workflows/abc"
    assert set(captured["body"].keys()) == {
        "name", "nodes", "connections", "settings"
    }
    assert captured["body"]["settings"] == {}  # defaulted, source omitted it
    assert out["updated"] is True
    assert out["sent_keys"] == ["connections", "name", "nodes", "settings"]


def test_hardening_writes_all_confirm_gated_no_side_effect():
    """create/delete/set_tags/execution.delete all refuse without
    confirm and perform NO HTTP call."""
    from n8n.tools.workflow import (
        workflow_create, workflow_delete, workflow_set_tags,
    )
    from n8n.tools.execution import execution_delete

    cases = [
        (workflow_create, {"workflow": {"name": "x"}}, "created"),
        (workflow_delete, {"id": "abc"}, "deleted"),
        (workflow_set_tags, {"id": "abc", "tag_ids": ["t1"]}, "updated"),
        (execution_delete, {"id": 5}, "deleted"),
    ]
    for fn, args, flag in cases:
        with patch("n8n.api.request_json") as req:
            out = asyncio.run(fn(args))
        req.assert_not_called()
        assert out[flag] is False
        assert out["error"]["status"] == 412


def test_workflow_delete_confirmed_calls_delete_verb():
    from n8n.tools.workflow import workflow_delete

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path)
        return {}

    with patch("n8n.api.request_json", side_effect=_cap):
        out = asyncio.run(
            workflow_delete({"id": "wf9", "confirm": True})
        )
    assert captured == {"method": "DELETE", "path": "/workflows/wf9"}
    assert out["deleted"] is True


def test_workflow_set_tags_sends_id_object_array():
    from n8n.tools.workflow import workflow_set_tags

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return [{"id": "t1", "name": "prod"}]

    with patch("n8n.api.request_json", side_effect=_cap):
        out = asyncio.run(
            workflow_set_tags(
                {"id": "wf9", "tag_ids": ["t1", "t2"], "confirm": True}
            )
        )
    assert captured["method"] == "PUT"
    assert captured["path"] == "/workflows/wf9/tags"
    assert captured["body"] == [{"id": "t1"}, {"id": "t2"}]
    assert out["updated"] is True
    assert out["tags"][0]["name"] == "prod"


def test_tag_list_maps_api_json():
    from n8n.tools.tag import tag_list

    fake = {"data": [{"id": "t1", "name": "prod"},
                     {"id": "t2", "name": "dev"}], "nextCursor": None}
    with patch("n8n.api.request_json", return_value=fake):
        out = asyncio.run(tag_list({}))
    assert out["error"] is None
    assert [t["name"] for t in out["tags"]] == ["prod", "dev"]


# ─── Read path — patched HTTP seam (no network) ──────────────────────────


def test_workflow_list_maps_api_json():
    from n8n.tools.workflow import workflow_list

    fake = {
        "data": [
            {
                "id": "dKXJgslv7_N4w9v1fDqUe",
                "name": "My Flow",
                "active": True,
                "tags": [{"id": "1", "name": "prod"}],
                "updatedAt": "2026-05-19T00:00:00.000Z",
            }
        ],
        "nextCursor": None,
    }
    with patch("n8n.api.request_json", return_value=fake):
        out = asyncio.run(workflow_list({"active": True}))
    assert out["error"] is None
    assert out["workflows"][0]["id"] == "dKXJgslv7_N4w9v1fDqUe"
    assert out["workflows"][0]["tags"] == ["prod"]  # tag-object flattened


def test_execution_get_extracts_top_level_error():
    from n8n.tools.execution import execution_get

    fake = {
        "id": 99,
        "status": "error",
        "data": {
            "resultData": {
                "lastNodeExecuted": "HTTP Request",
                "error": {
                    "name": "NodeApiError",
                    "message": "Forbidden - 403",
                    "stack": "Error: Forbidden\n at ...",
                },
            }
        },
    }
    with patch("n8n.api.request_json", return_value=fake):
        out = asyncio.run(execution_get({"id": 99}))
    assert out["error"] is None
    assert out["error_summary"]["node"] == "HTTP Request"
    assert out["error_summary"]["message"] == "Forbidden - 403"
    assert out["execution"]["id"] == 99  # raw kept as source of truth


def test_execution_get_extracts_per_node_run_data_error():
    from n8n.tools.execution import execution_get

    fake = {
        "id": 7,
        "data": {
            "resultData": {
                "runData": {
                    "Code": [
                        {"error": {"name": "NodeOperationError",
                                   "message": "boom"}}
                    ]
                }
            }
        },
    }
    with patch("n8n.api.request_json", return_value=fake):
        out = asyncio.run(execution_get({"id": 7}))
    assert out["error_summary"]["node"] == "Code"
    assert out["error_summary"]["message"] == "boom"


def test_execution_get_no_error_yields_none_summary_not_fabricated():
    from n8n.tools.execution import execution_get

    fake = {"id": 1, "status": "success", "data": {"resultData": {}}}
    with patch("n8n.api.request_json", return_value=fake):
        out = asyncio.run(execution_get({"id": 1}))
    assert out["error_summary"] is None  # never fabricated


# ─── Gated-capability honesty — not configured ⇒ typed 424, never faked ──


def test_workflow_list_not_configured_returns_typed_424_not_fake():
    from n8n.tools.workflow import workflow_list
    from n8n.settings import N8nConnectorSettings

    with patch("n8n.tools.workflow.get_settings",
               return_value=N8nConnectorSettings()):
        out = asyncio.run(workflow_list({}))
    assert out["workflows"] == []
    assert out["error"]["status"] == 424  # never a fabricated success


def test_connection_status_not_configured():
    from n8n.tools.diagnostics import connection_status
    from n8n.settings import N8nConnectorSettings

    with patch("n8n.tools.diagnostics.get_settings",
               return_value=N8nConnectorSettings()):
        out = asyncio.run(connection_status({}))
    assert out["configured"] is False
    assert out["reachable"] is False
    assert out["error"]["status"] == 424


def test_connection_status_configured_but_key_rejected():
    """Configured, but the API returns 401 ⇒ reachable=false, honest."""
    from n8n.tools.diagnostics import connection_status
    from n8n.settings import N8nConnectorSettings
    from n8n import api

    s = N8nConnectorSettings(base_url="https://n8n.x.com", api_key="bad")
    with patch("n8n.tools.diagnostics.get_settings", return_value=s), patch(
        "n8n.api.request_json",
        side_effect=api.N8nApiError("HTTP 401", status=401),
    ):
        out = asyncio.run(connection_status({}))
    assert out["configured"] is True
    assert out["reachable"] is False
    assert out["error"]["status"] == 401


def test_connection_status_workflow_count_is_true_total():
    """Regression: workflow_count must be the TRUE total across pages.

    The old `limit=1` probe made a multi-workflow instance report
    `workflow_count=1`. The diagnostic now follows `nextCursor`.
    """
    from n8n.tools.diagnostics import connection_status
    from n8n.settings import N8nConnectorSettings

    pages = [
        {"data": [{"id": str(i)} for i in range(250)], "nextCursor": "c1"},
        {"data": [{"id": str(i)} for i in range(7)], "nextCursor": None},
    ]
    calls = {"n": 0}

    def fake_request_json(method, path, **kw):
        i = calls["n"]
        calls["n"] += 1
        return pages[i]

    s = N8nConnectorSettings(base_url="https://n8n.x.com", api_key="ok")
    with patch("n8n.tools.diagnostics.get_settings", return_value=s), patch(
        "n8n.api.request_json", side_effect=fake_request_json
    ):
        out = asyncio.run(connection_status({}))
    assert out["configured"] is True
    assert out["reachable"] is True
    assert out["workflow_count"] == 257  # 250 + 7, NOT 1
    assert calls["n"] == 2  # followed the cursor


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
