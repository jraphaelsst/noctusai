"""Smoke tests for the n8n connector MCP.

No network: every handler is exercised via dependency injection —
`n8n.client.configure_client(...)` swaps in the seed's
`FakeN8nClient` (deterministic in-memory) or a small local test double,
never a network call. This is NOT monkeypatching: `n8n.client.py`'s
override slot is a first-class DI seam (mirrors
`mcp/google/tools/youtube.py`'s `configure_upload_client`), and every
connector symbol involved (`api.N8nApiError`, `api.require_configured`,
`api.map_seed_error`, the tool handlers themselves) runs for real —
nothing about OUR code is neutered. `n8n.settings.get_settings` /
`n8n.client.get_settings` ARE still occasionally patched below — that
is a config-boundary substitution (same class as the codebase's
allowlisted `get_*_config`/`get_*_client` env-readers), not a patch of
business logic.

Pins, per the connector contract:
- the exact registered tool-name set (guards silent additions),
- 3-segment dotted naming under the `n8n.*` umbrella,
- the confirm gate (write tools refuse + perform NO side-effect —
  proven by injecting a client that raises on ANY method call),
- gated-capability honesty (not-configured ⇒ typed 424, never faked),
- best-effort error extraction from real-shaped run-data,
- descriptors/handlers aggregation coherence.

Wire-shape assertions (exact PUT body, exact tag-body shape, exact
DELETE path, …) live in the SEED's own test corpus
(`seed/lib/backend/tests/integrations/n8n/{test_mappers,test_client}.py`)
— this file only proves the MCP handler layer (confirm-gate → client
call → error mapping → Out shaping) is wired correctly.
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


class _PoisonClient:
    """An `N8nClient` stand-in that raises on ANY method call.

    Injected before a confirm-gated write to prove the gate fires
    BEFORE the client is ever touched — the DI-seam equivalent of the
    old `req.assert_not_called()` mock assertion, but louder: a gate
    that regresses to "check confirm after building the client" fails
    this test immediately instead of merely leaving an unasserted mock.
    """

    def __getattr__(self, name):
        async def _boom(*args, **kwargs):
            raise AssertionError(
                f"client.{name}() must not be called before confirm=true"
            )
        return _boom


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from n8n import api, client, settings, types  # noqa: F401
    from n8n.tools import diagnostics, execution, workflow  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401

    assert hasattr(api, "normalize_base_url")
    assert hasattr(api, "require_configured")
    assert hasattr(api, "map_seed_error")
    assert hasattr(client, "get_client")
    assert hasattr(client, "configure_client")
    # Locks in the refactor: the sync urllib HTTP seam is GONE — every
    # tool now goes through `client.get_client()` + the seed's
    # `N8nClient` Protocol.
    assert not hasattr(api, "request_json")


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
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_activate

    n8n_client.configure_client(_PoisonClient())
    try:
        out = asyncio.run(workflow_activate({"id": "abc"}))
    finally:
        n8n_client.configure_client(None)
    assert out["changed"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412


def test_workflow_deactivate_confirm_false_explicit_also_blocks():
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_deactivate

    n8n_client.configure_client(_PoisonClient())
    try:
        out = asyncio.run(
            workflow_deactivate({"id": "abc", "confirm": False})
        )
    finally:
        n8n_client.configure_client(None)
    assert out["error"]["status"] == 412


def test_workflow_update_without_confirm_blocks_no_side_effect():
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_update

    n8n_client.configure_client(_PoisonClient())
    try:
        out = asyncio.run(
            workflow_update({"id": "abc", "workflow": {"name": "x"}})
        )
    finally:
        n8n_client.configure_client(None)
    assert out["updated"] is False
    assert out["error"]["status"] == 412


def test_workflow_update_reports_sanitized_sent_keys():
    """Read-only keys (id/active/tags/timestamps) are stripped before
    the PUT so n8n does not 400 on additional properties (the exact
    allowlist — `seed/lib/backend/tests/integrations/n8n/test_mappers
    .py::test_sanitize_strips_readonly_keys` pins the pure function;
    this test pins that the HANDLER reports the same key-set it sent)."""
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_update
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    n8n_client.configure_client(fake)
    dirty = {
        "id": "fake-wf-1",
        "name": "Flow",
        "active": True,
        "tags": [{"id": "1", "name": "prod"}],
        "createdAt": "2026-01-01",
        "updatedAt": "2026-05-19",
        "versionId": "v9",
        "triggerCount": 3,
        "nodes": [{"type": "n8n-nodes-base.manualTrigger"}],
        "connections": {"Webhook": {}},
    }
    try:
        out = asyncio.run(
            workflow_update({"id": "fake-wf-1", "workflow": dirty, "confirm": True})
        )
    finally:
        n8n_client.configure_client(None)
    assert out["updated"] is True
    assert out["sent_keys"] == ["connections", "name", "nodes", "settings"]
    assert out["name"] == "Flow"


def test_hardening_writes_all_confirm_gated_no_side_effect():
    """create/delete/set_tags/execution.delete all refuse without
    confirm and never touch the injected (poison) client."""
    from n8n import client as n8n_client
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
    n8n_client.configure_client(_PoisonClient())
    try:
        for fn, args, flag in cases:
            out = asyncio.run(fn(args))
            assert out[flag] is False
            assert out["error"]["status"] == 412
    finally:
        n8n_client.configure_client(None)


def test_workflow_delete_confirmed_removes_and_reports_deleted():
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_delete
    from noctusai_lib.integrations.n8n import FakeN8nClient, N8nNotFoundError

    fake = FakeN8nClient()
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(workflow_delete({"id": "fake-wf-2", "confirm": True}))
    finally:
        n8n_client.configure_client(None)
    assert out == {"id": "fake-wf-2", "deleted": True, "error": None}
    with pytest.raises(N8nNotFoundError):
        asyncio.run(fake.get_workflow("fake-wf-2"))


def test_workflow_set_tags_updates_and_shapes_tag_summaries():
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_set_tags
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(
            workflow_set_tags(
                {"id": "fake-wf-2", "tag_ids": ["fake-tag-1"], "confirm": True}
            )
        )
    finally:
        n8n_client.configure_client(None)
    assert out["updated"] is True
    assert out["tags"] == [{"id": "fake-tag-1", "name": "prod"}]


def test_tag_list_maps_seed_client_output():
    from n8n import client as n8n_client
    from n8n.tools.tag import tag_list
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    asyncio.run(fake.create_tag("dev"))
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(tag_list({}))
    finally:
        n8n_client.configure_client(None)
    assert out["error"] is None
    assert [t["name"] for t in out["tags"]] == ["prod", "dev"]


# ─── Read path — DI-injected FakeN8nClient (no network) ──────────────────


def test_workflow_list_maps_seed_client_output():
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_list
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(workflow_list({"active": True}))
    finally:
        n8n_client.configure_client(None)
    assert out["error"] is None
    # `n8n.workflow.list` deliberately fetches `include_archived=True`
    # (the pre-refactor tool never had an archived concept at all — this
    # preserves that exact "show everything" behavior) then filters
    # client-side by `active`. All three seeded workflows are active,
    # so all three appear here (archived-filtering is a seed capability
    # this tool doesn't expose as a parameter).
    ids = {w["id"] for w in out["workflows"]}
    assert ids == {"fake-wf-1", "fake-wf-2", "fake-wf-3"}
    tagged = next(w for w in out["workflows"] if w["id"] == "fake-wf-1")
    assert tagged["tags"] == ["prod"]  # tag names, not id objects


def test_workflow_list_filters_by_name_and_limit():
    from n8n import client as n8n_client
    from n8n.tools.workflow import workflow_list
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(
            workflow_list({"name": "Fake Runnable Webhook Flow", "limit": 50})
        )
    finally:
        n8n_client.configure_client(None)
    assert [w["id"] for w in out["workflows"]] == ["fake-wf-1"]


def test_execution_get_extracts_top_level_error():
    from n8n import client as n8n_client
    from n8n.tools.execution import execution_get
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    fake.executions[99] = {
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
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(execution_get({"id": 99}))
    finally:
        n8n_client.configure_client(None)
    assert out["error"] is None
    assert out["error_summary"]["node"] == "HTTP Request"
    assert out["error_summary"]["message"] == "Forbidden - 403"
    assert out["execution"]["id"] == 99  # raw kept as source of truth


def test_execution_get_extracts_per_node_run_data_error():
    from n8n import client as n8n_client
    from n8n.tools.execution import execution_get
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    fake.executions[7] = {
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
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(execution_get({"id": 7}))
    finally:
        n8n_client.configure_client(None)
    assert out["error_summary"]["node"] == "Code"
    assert out["error_summary"]["message"] == "boom"


def test_execution_get_no_error_yields_none_summary_not_fabricated():
    from n8n import client as n8n_client
    from n8n.tools.execution import execution_get
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    fake.executions[1] = {"id": 1, "status": "success", "data": {"resultData": {}}}
    n8n_client.configure_client(fake)
    try:
        out = asyncio.run(execution_get({"id": 1}))
    finally:
        n8n_client.configure_client(None)
    assert out["error_summary"] is None  # never fabricated


# ─── Gated-capability honesty — not configured ⇒ typed 424, never faked ──


def test_workflow_list_not_configured_returns_typed_424_not_fake():
    from n8n.tools.workflow import workflow_list
    from n8n.settings import N8nConnectorSettings

    with patch("n8n.client.get_settings",
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
    """Configured, but the client raises 401 ⇒ reachable=false, honest."""
    from n8n.tools.diagnostics import connection_status
    from n8n.settings import N8nConnectorSettings
    from n8n import client as n8n_client
    from noctusai_lib.integrations.n8n import N8nAuthError

    s = N8nConnectorSettings(base_url="https://n8n.x.com", api_key="bad")

    class _AuthRejectingClient:
        async def list_workflows(self, **kw):
            raise N8nAuthError("HTTP 401", status=401)

    n8n_client.configure_client(_AuthRejectingClient())
    try:
        with patch("n8n.tools.diagnostics.get_settings", return_value=s):
            out = asyncio.run(connection_status({}))
    finally:
        n8n_client.configure_client(None)
    assert out["configured"] is True
    assert out["reachable"] is False
    assert out["error"]["status"] == 401


def test_connection_status_workflow_count_is_true_total():
    """Regression: workflow_count must be the TRUE total, not `min(total,
    1)` (the old `limit=1` bug). The seed client already exhausts
    pagination internally (proven at the seed level —
    `test_client.py::test_list_workflows_follows_cursor`); this test
    pins that `connection_status` trusts `len(workflows)` verbatim."""
    from n8n.tools.diagnostics import connection_status
    from n8n.settings import N8nConnectorSettings
    from n8n import client as n8n_client
    from noctusai_lib.integrations.n8n import Workflow

    synthetic = [
        Workflow(id=str(i), name=f"w{i}", active=True, archived=False)
        for i in range(257)
    ]

    class _StubClient:
        async def list_workflows(self, **kw):
            return synthetic

    s = N8nConnectorSettings(base_url="https://n8n.x.com", api_key="ok")
    n8n_client.configure_client(_StubClient())
    try:
        with patch("n8n.tools.diagnostics.get_settings", return_value=s):
            out = asyncio.run(connection_status({}))
    finally:
        n8n_client.configure_client(None)
    assert out["configured"] is True
    assert out["reachable"] is True
    assert out["workflow_count"] == 257  # 250 + 7 shape, NOT 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
