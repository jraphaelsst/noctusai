"""HttpxN8nClient tests — httpx.MockTransport, no network.

Covers:
- Auth header: `X-N8N-API-KEY` on every API request.
- User-Agent: the browser UA is sent on every request (API AND
  webhook dispatch) — load-bearing for the Cloudflare-WAF-fronted
  live instance.
- Error mapping: every status-code → exact exception class.
- `list_workflows`: cursor-follow pagination, `include_archived`
  filtering, `tag` filtering (id or name).
- `get_workflow`: full raw fidelity (nodes kept).
- `activate`/`deactivate`: POST the verb, then re-GET for a
  never-fabricated `Workflow`.
- `rename`: GET → sanitize → PUT round-trip.
- `delete_workflow`: DELETE, no return value.
- `set_workflow_tags`: PUT body is `[{"id": ...}]`, never names.
- `list_executions`/`get_execution`: params forwarded, int id.
- `list_tags`/`create_tag`.
- `run_via_webhook`: dispatches to the INSTANCE ROOT (not `/api/v1`),
  uses the workflow's own method; raises
  `N8nWorkflowNotRunnableError` with **zero HTTP calls** for a
  non-runnable workflow.
- `ping`.

Pattern mirrors `tests/integrations/mailchimp/test_client.py`.
"""

from __future__ import annotations

import asyncio
import json as json_lib
from typing import Any, Callable

import httpx
import pytest

from noctusai_lib.integrations.n8n.mappers import raw_to_workflow
from noctusai_lib.integrations.n8n.n8n_adapter import HttpxN8nClient
from noctusai_lib.integrations.n8n.types import (
    N8nAuthError,
    N8nNotFoundError,
    N8nRateLimitedError,
    N8nRejectedError,
    N8nUnreachableError,
    N8nWorkflowNotRunnableError,
)


# ---------------------------------------------------------------------------
# MockTransport helpers
# ---------------------------------------------------------------------------


def _json_transport(status: int = 200, body: dict[str, Any] | None = None) -> httpx.MockTransport:
    raw = json_lib.dumps(body if body is not None else {}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=raw)

    return httpx.MockTransport(handler)


def _capturing_transport(
    status: int = 200, body: dict[str, Any] | None = None
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    captured: list[httpx.Request] = []
    raw = json_lib.dumps(body if body is not None else {}).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, content=raw)

    return httpx.MockTransport(handler), captured


def _routing_transport(
    routes: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]],
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """Route by (method, path) — for multi-endpoint flows (activate then
    re-GET; rename's GET-then-PUT; …)."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        key = (request.method, request.url.path)
        fn = routes.get(key)
        if fn is None:
            raise AssertionError(f"unexpected request: {key}")
        return fn(request)

    return httpx.MockTransport(handler), captured


def _client(
    *, transport: httpx.MockTransport | None = None, base_url: str = "https://n8n.x.com"
) -> HttpxN8nClient:
    return HttpxN8nClient(base_url, "test-api-key", transport=transport)


_WORKFLOW_RAW: dict[str, Any] = {
    "id": "wf1",
    "name": "My Flow",
    "active": True,
    "isArchived": False,
    "tags": [{"id": "t1", "name": "prod"}],
    "nodes": [
        {
            "type": "n8n-nodes-base.webhook",
            "parameters": {"httpMethod": "POST", "path": "my-hook"},
        }
    ],
    "connections": {},
    "settings": {},
    "createdAt": "2026-07-16T00:00:00.000Z",
    "updatedAt": "2026-07-16T00:00:00.000Z",
}


# ---------------------------------------------------------------------------
# Auth header + User-Agent
# ---------------------------------------------------------------------------


def test_api_key_header_sent() -> None:
    transport, captured = _capturing_transport(status=200, body={"data": [], "nextCursor": None})
    client = _client(transport=transport)
    asyncio.run(client.list_workflows())
    assert captured[0].headers.get("x-n8n-api-key") == "test-api-key"


def test_browser_user_agent_sent_on_api_calls() -> None:
    """Load-bearing for the Cloudflare-WAF-fronted live instance — the
    default httpx UA is 403'd."""
    transport, captured = _capturing_transport(status=200, body={"data": [], "nextCursor": None})
    client = _client(transport=transport)
    asyncio.run(client.list_workflows())
    ua = captured[0].headers.get("user-agent", "")
    assert "Mozilla" in ua and "python-httpx" not in ua.lower()


def test_browser_user_agent_sent_on_webhook_dispatch() -> None:
    """The WAF sits in front of the whole instance, not just /api/v1 —
    webhook dispatch needs the same browser UA."""
    transport, captured = _capturing_transport(status=200, body={"ok": True})
    client = _client(transport=transport)
    workflow = raw_to_workflow(_WORKFLOW_RAW)
    asyncio.run(client.run_via_webhook(workflow))
    ua = captured[0].headers.get("user-agent", "")
    assert "Mozilla" in ua


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_auth_error(status: int) -> None:
    client = _client(transport=_json_transport(status=status, body={"message": "bad key"}))
    with pytest.raises(N8nAuthError) as exc_info:
        asyncio.run(client.ping())
    assert exc_info.value.status == status


def test_not_found_error() -> None:
    client = _client(transport=_json_transport(status=404, body={"message": "not found"}))
    with pytest.raises(N8nNotFoundError) as exc_info:
        asyncio.run(client.get_workflow("missing"))
    assert exc_info.value.status == 404


def test_rate_limited_error() -> None:
    client = _client(transport=_json_transport(status=429, body={"message": "slow down"}))
    with pytest.raises(N8nRateLimitedError):
        asyncio.run(client.ping())


@pytest.mark.parametrize("status", [400, 422])
def test_rejected_error(status: int) -> None:
    """PUT /workflows/{id} 400s on additional properties — the exact
    class this maps to."""
    client = _client(
        transport=_json_transport(status=status, body={"message": "additional properties not allowed"})
    )
    with pytest.raises(N8nRejectedError) as exc_info:
        asyncio.run(client.delete_workflow("wf1"))
    assert exc_info.value.detail == "additional properties not allowed"


def test_unreachable_error_on_500() -> None:
    client = _client(transport=_json_transport(status=500, body={"message": "boom"}))
    with pytest.raises(N8nUnreachableError):
        asyncio.run(client.ping())


def test_transport_error_raises_unreachable() -> None:
    def fail_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = _client(transport=httpx.MockTransport(fail_handler))
    with pytest.raises(N8nUnreachableError) as exc_info:
        asyncio.run(client.ping())
    assert exc_info.value.status == 0


# ---------------------------------------------------------------------------
# list_workflows — cursor-follow + filtering
# ---------------------------------------------------------------------------


def test_list_workflows_follows_cursor() -> None:
    pages = [
        {"data": [{**_WORKFLOW_RAW, "id": f"wf{i}"} for i in range(250)], "nextCursor": "c1"},
        {"data": [{**_WORKFLOW_RAW, "id": "wf250"}], "nextCursor": None},
    ]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        page = pages[calls["n"]]
        calls["n"] += 1
        return httpx.Response(200, content=json_lib.dumps(page).encode())

    client = _client(transport=httpx.MockTransport(handler))
    workflows = asyncio.run(client.list_workflows(include_archived=True))
    assert len(workflows) == 251
    assert calls["n"] == 2


def test_list_workflows_excludes_archived_by_default() -> None:
    data = {
        "data": [
            {**_WORKFLOW_RAW, "id": "active-wf", "isArchived": False},
            {**_WORKFLOW_RAW, "id": "archived-wf", "isArchived": True},
        ],
        "nextCursor": None,
    }
    client = _client(transport=_json_transport(status=200, body=data))
    workflows = asyncio.run(client.list_workflows())
    assert {w.id for w in workflows} == {"active-wf"}


def test_list_workflows_filters_by_tag() -> None:
    data = {
        "data": [
            {**_WORKFLOW_RAW, "id": "tagged", "tags": [{"id": "t1", "name": "prod"}]},
            {**_WORKFLOW_RAW, "id": "untagged", "tags": []},
        ],
        "nextCursor": None,
    }
    client = _client(transport=_json_transport(status=200, body=data))
    workflows = asyncio.run(client.list_workflows(tag="t1"))
    assert {w.id for w in workflows} == {"tagged"}


# ---------------------------------------------------------------------------
# get_workflow — full raw fidelity
# ---------------------------------------------------------------------------


def test_get_workflow_returns_full_raw_with_nodes() -> None:
    client = _client(transport=_json_transport(status=200, body=_WORKFLOW_RAW))
    raw = asyncio.run(client.get_workflow("wf1"))
    assert raw["nodes"] == _WORKFLOW_RAW["nodes"]


# ---------------------------------------------------------------------------
# create_workflow / update_workflow — the general forms rename() builds on
# ---------------------------------------------------------------------------


def test_create_workflow_posts_sanitized_body() -> None:
    transport, captured = _capturing_transport(
        status=200, body={**_WORKFLOW_RAW, "id": "new-wf"}
    )
    client = _client(transport=transport)
    dirty = {**_WORKFLOW_RAW, "active": True}  # active not in the allowlist
    workflow = asyncio.run(client.create_workflow(dirty))
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/api/v1/workflows"
    body = json_lib.loads(captured[0].content)
    assert set(body.keys()) == {"name", "nodes", "connections", "settings"}
    assert workflow.id == "new-wf"


def test_update_workflow_puts_sanitized_body_at_given_id() -> None:
    transport, captured = _capturing_transport(status=200, body=_WORKFLOW_RAW)
    client = _client(transport=transport)
    asyncio.run(client.update_workflow("wf1", {**_WORKFLOW_RAW, "id": "wf1"}))
    assert captured[0].method == "PUT"
    assert captured[0].url.path == "/api/v1/workflows/wf1"
    body = json_lib.loads(captured[0].content)
    assert "id" not in body


# ---------------------------------------------------------------------------
# activate / deactivate — POST verb then re-GET (never fabricated)
# ---------------------------------------------------------------------------


def test_activate_posts_verb_then_re_reads() -> None:
    routes = {
        ("POST", "/api/v1/workflows/wf1/activate"): lambda r: httpx.Response(200, content=b"{}"),
        ("GET", "/api/v1/workflows/wf1"): lambda r: httpx.Response(
            200, content=json_lib.dumps({**_WORKFLOW_RAW, "active": True}).encode()
        ),
    }
    transport, captured = _routing_transport(routes)
    client = _client(transport=transport)
    workflow = asyncio.run(client.activate("wf1"))
    assert workflow.active is True
    assert [ (r.method, r.url.path) for r in captured ] == [
        ("POST", "/api/v1/workflows/wf1/activate"),
        ("GET", "/api/v1/workflows/wf1"),
    ]


def test_deactivate_posts_verb_then_re_reads() -> None:
    routes = {
        ("POST", "/api/v1/workflows/wf1/deactivate"): lambda r: httpx.Response(200, content=b"{}"),
        ("GET", "/api/v1/workflows/wf1"): lambda r: httpx.Response(
            200, content=json_lib.dumps({**_WORKFLOW_RAW, "active": False}).encode()
        ),
    }
    transport, _ = _routing_transport(routes)
    client = _client(transport=transport)
    workflow = asyncio.run(client.deactivate("wf1"))
    assert workflow.active is False


# ---------------------------------------------------------------------------
# rename — GET → sanitize → PUT
# ---------------------------------------------------------------------------


def test_rename_gets_then_puts_sanitized_body() -> None:
    put_bodies: list[dict] = []

    def get_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json_lib.dumps(_WORKFLOW_RAW).encode())

    def put_handler(request: httpx.Request) -> httpx.Response:
        body = json_lib.loads(request.content)
        put_bodies.append(body)
        return httpx.Response(200, content=json_lib.dumps({**body, "id": "wf1"}).encode())

    routes = {
        ("GET", "/api/v1/workflows/wf1"): get_handler,
        ("PUT", "/api/v1/workflows/wf1"): put_handler,
    }
    transport, _ = _routing_transport(routes)
    client = _client(transport=transport)
    workflow = asyncio.run(client.rename("wf1", "New Name"))
    assert workflow.name == "New Name"
    assert set(put_bodies[0].keys()) == {"name", "nodes", "connections", "settings"}
    assert put_bodies[0]["name"] == "New Name"
    assert "id" not in put_bodies[0]  # id stripped — n8n 400s on extra keys


# ---------------------------------------------------------------------------
# delete_workflow
# ---------------------------------------------------------------------------


def test_delete_workflow_sends_delete() -> None:
    transport, captured = _capturing_transport(status=200, body={})
    client = _client(transport=transport)
    asyncio.run(client.delete_workflow("wf1"))
    assert captured[0].method == "DELETE"
    assert captured[0].url.path == "/api/v1/workflows/wf1"


# ---------------------------------------------------------------------------
# set_workflow_tags — ids, not names
# ---------------------------------------------------------------------------


def test_set_workflow_tags_sends_id_objects() -> None:
    transport, captured = _capturing_transport(
        status=200, body=[{"id": "t1", "name": "prod"}, {"id": "t2", "name": "dev"}]
    )
    client = _client(transport=transport)
    tags = asyncio.run(client.set_workflow_tags("wf1", ["t1", "t2"]))
    body = json_lib.loads(captured[0].content)
    assert body == [{"id": "t1"}, {"id": "t2"}]
    assert [t.name for t in tags] == ["prod", "dev"]


# ---------------------------------------------------------------------------
# Executions
# ---------------------------------------------------------------------------


def test_list_executions_forwards_params() -> None:
    transport, captured = _capturing_transport(status=200, body={"data": [], "nextCursor": None})
    client = _client(transport=transport)
    asyncio.run(client.list_executions(workflow_id="wf1", status="error", limit=5))
    params = dict(captured[0].url.params)
    assert params["workflowId"] == "wf1"
    assert params["status"] == "error"
    assert params["limit"] == "5"
    assert params["includeData"] == "false"


def test_get_execution_int_id_and_include_data_param() -> None:
    transport, captured = _capturing_transport(
        status=200, body={"id": 42, "workflowId": "wf1", "data": {"resultData": {}}}
    )
    client = _client(transport=transport)
    raw = asyncio.run(client.get_execution(42, include_data=True))
    assert raw["id"] == 42
    assert dict(captured[0].url.params)["includeData"] == "true"


def test_delete_execution_sends_delete() -> None:
    transport, captured = _capturing_transport(status=200, body={})
    client = _client(transport=transport)
    asyncio.run(client.delete_execution(42))
    assert captured[0].method == "DELETE"
    assert captured[0].url.path == "/api/v1/executions/42"


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_list_tags() -> None:
    data = {"data": [{"id": "t1", "name": "prod"}], "nextCursor": None}
    client = _client(transport=_json_transport(status=200, body=data))
    tags = asyncio.run(client.list_tags())
    assert [t.name for t in tags] == ["prod"]


def test_create_tag_posts_name() -> None:
    transport, captured = _capturing_transport(status=200, body={"id": "t9", "name": "staging"})
    client = _client(transport=transport)
    tag = asyncio.run(client.create_tag("staging"))
    assert tag.id == "t9"
    body = json_lib.loads(captured[0].content)
    assert body == {"name": "staging"}


# ---------------------------------------------------------------------------
# Credentials — write-only (no list/get; the secret never round-trips)
# ---------------------------------------------------------------------------


def test_create_credential_posts_body_output_never_carries_data() -> None:
    transport, captured = _capturing_transport(
        status=200, body={"id": "9xZ", "name": "hdr", "type": "httpHeaderAuth"}
    )
    client = _client(transport=transport)
    cred = asyncio.run(
        client.create_credential(
            name="hdr", type="httpHeaderAuth", data={"name": "X-Api-Key", "value": "s3cr3t"}
        )
    )
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/api/v1/credentials"
    body = json_lib.loads(captured[0].content)
    assert body == {
        "name": "hdr",
        "type": "httpHeaderAuth",
        "data": {"name": "X-Api-Key", "value": "s3cr3t"},
    }
    assert cred.id == "9xZ"
    assert not hasattr(cred, "data")  # n8n never echoes it; the VO has no such field


def test_delete_credential_sends_delete() -> None:
    transport, captured = _capturing_transport(status=200, body={})
    client = _client(transport=transport)
    asyncio.run(client.delete_credential("cred1"))
    assert captured[0].method == "DELETE"
    assert captured[0].url.path == "/api/v1/credentials/cred1"


def test_get_credential_schema_gets_type_path() -> None:
    schema_payload = {"type": "object", "required": ["name", "value"]}
    transport, captured = _capturing_transport(status=200, body=schema_payload)
    client = _client(transport=transport)
    schema = asyncio.run(client.get_credential_schema("httpHeaderAuth"))
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/api/v1/credentials/schema/httpHeaderAuth"
    assert schema == schema_payload


# ---------------------------------------------------------------------------
# run_via_webhook — dispatches to the INSTANCE ROOT, honest refusal
# ---------------------------------------------------------------------------


def test_run_via_webhook_hits_instance_root_not_api_v1() -> None:
    transport, captured = _capturing_transport(status=200, body={"ok": True})
    client = _client(transport=transport, base_url="https://n8n.x.com/api/v1")
    workflow = raw_to_workflow(_WORKFLOW_RAW)
    asyncio.run(client.run_via_webhook(workflow))
    req = captured[0]
    assert str(req.url) == "https://n8n.x.com/webhook/my-hook"
    assert req.method == "POST"  # workflow's own httpMethod


def test_run_via_webhook_no_auth_key_header() -> None:
    """Webhook dispatch is a DIFFERENT, unauthenticated (by n8n default)
    surface — the X-N8N-API-KEY header must NOT be attached."""
    transport, captured = _capturing_transport(status=200, body={"ok": True})
    client = _client(transport=transport)
    workflow = raw_to_workflow(_WORKFLOW_RAW)
    asyncio.run(client.run_via_webhook(workflow))
    assert "x-n8n-api-key" not in captured[0].headers


def test_run_via_webhook_not_runnable_raises_with_zero_http_calls() -> None:
    def fail_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not make any HTTP call")

    client = _client(transport=httpx.MockTransport(fail_handler))
    not_runnable = raw_to_workflow({**_WORKFLOW_RAW, "active": False})
    with pytest.raises(N8nWorkflowNotRunnableError) as exc_info:
        asyncio.run(client.run_via_webhook(not_runnable))
    assert exc_info.value.status == 409


def test_run_via_webhook_dispatched_reflects_real_status() -> None:
    transport, _ = _capturing_transport(status=500, body={})
    client = _client(transport=transport)
    workflow = raw_to_workflow(_WORKFLOW_RAW)
    result = asyncio.run(client.run_via_webhook(workflow))
    assert result.dispatched is False
    assert result.http_status == 500


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------


def test_ping_succeeds_on_2xx() -> None:
    client = _client(transport=_json_transport(status=200, body={"data": [], "nextCursor": None}))
    assert asyncio.run(client.ping()) is True


def test_ping_forwards_limit_1() -> None:
    transport, captured = _capturing_transport(status=200, body={"data": [], "nextCursor": None})
    client = _client(transport=transport)
    asyncio.run(client.ping())
    assert dict(captured[0].url.params)["limit"] == "1"
