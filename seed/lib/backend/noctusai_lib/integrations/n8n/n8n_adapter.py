"""HttpxN8nClient — real n8n public API v1 adapter.

Two distinct base URLs derived from one stored ``base_url`` (the
instance root):

- API calls → ``{root}/api/v1`` (``mappers.normalize_base_url``),
  authenticated via the ``X-N8N-API-KEY`` header.
- Webhook dispatch (``run_via_webhook``) → ``{root}/webhook/{path}``
  (``mappers.instance_root`` / ``mappers.webhook_url``) — a DIFFERENT,
  unauthenticated (by n8n default) surface outside the versioned API.

Error mapping (``_translate``):
- 401 / 403  → ``N8nAuthError``
- 404        → ``N8nNotFoundError``
- 429        → ``N8nRateLimitedError``
- 400 / 422  → ``N8nRejectedError``
- 5xx / network / TLS → ``N8nUnreachableError``

🔴 **Cloudflare WAF 403s the default httpx/urllib User-Agent** on a
WAF-fronted n8n instance (measured live 2026-07-16; the same class
``mcp/_kit/transport.py:32-34`` already documents for other
WAF-fronted connectors). ``_BROWSER_USER_AGENT`` is LOAD-BEARING on
every request this adapter sends, including webhook dispatch.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from noctusai_lib.integrations.n8n.mappers import (
    extract_error_message,
    instance_root,
    normalize_base_url,
    raw_to_credential,
    raw_to_execution,
    raw_to_tag,
    raw_to_workflow,
    sanitize_workflow_put_body,
    tag_refs_body,
    webhook_url,
)
from noctusai_lib.integrations.n8n.types import (
    Credential,
    Execution,
    N8nAuthError,
    N8nError,
    N8nNotFoundError,
    N8nRateLimitedError,
    N8nRejectedError,
    N8nUnreachableError,
    N8nWorkflowNotRunnableError,
    RunResult,
    Tag,
    Workflow,
)

# Same string as `mcp/_kit/transport.py::BROWSER_USER_AGENT` — kept as an
# independent constant (the seed cannot depend on `mcp/_kit`; the connector
# depends on the seed, never the reverse) but MUST stay a real browser UA.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_MAX_LIST_PAGES = 50  # 50 * 250 = 12500 workflows — unbounded in practice


def _not_runnable_reason(workflow: Workflow) -> str:
    if not workflow.has_webhook_node:
        return "no webhook trigger node"
    if not workflow.active:
        return "workflow is inactive (a webhook only fires while active)"
    if workflow.archived:
        return "workflow is archived"
    return "not runnable"  # unreachable in practice; can_run implies one of the above


class HttpxN8nClient:
    """Real n8n public API v1 client backed by ``httpx.AsyncClient``.

    Instantiate via the ``get_n8n_client(base_url=, api_key=)`` factory;
    don't construct directly in product code.

    Thread-safety: the underlying ``httpx.AsyncClient`` is not
    thread-safe; use one instance per request or per coroutine chain.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_root = normalize_base_url(base_url)
        self._instance_root = instance_root(base_url)
        self._api_key = api_key
        self._timeout = timeout
        # Test seam: an httpx.MockTransport here lets suites exercise the
        # REAL _request path without monkey-patching. None → httpx default.
        self._transport = transport

    # ------------------------------------------------------------------
    # Internal HTTP primitive — versioned API calls
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: object | None = None,
    ) -> Any:
        """Execute one authenticated ``{api_root}{path}`` request and
        return the parsed JSON body. Empty 2xx responses (e.g. DELETE
        204) return ``{}``. All non-2xx responses raise the typed
        error hierarchy."""
        url = f"{self._api_root}{path}"
        headers = {
            "X-N8N-API-KEY": self._api_key,
            "User-Agent": _BROWSER_USER_AGENT,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(transport=self._transport) as http:
                response = await http.request(
                    method,
                    url,
                    params={k: v for k, v in (params or {}).items() if v is not None},
                    json=json,
                    headers=headers,
                    timeout=self._timeout,
                )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise N8nUnreachableError(str(exc), status=0) from exc

        return self._translate(response)

    @staticmethod
    def _translate(response: httpx.Response) -> Any:
        """Map an httpx Response to parsed JSON or raise the typed
        error hierarchy."""
        status = response.status_code

        if 200 <= status < 300:
            body = response.content
            if not body or not body.strip():
                return {}
            try:
                return response.json()
            except ValueError:
                return {}

        try:
            err_body = response.json()
        except ValueError:
            err_body = None
        title, detail = extract_error_message(err_body)
        message = detail or title or f"HTTP {status}"

        if status in (401, 403):
            raise N8nAuthError(message, status=status, title=title, detail=detail)
        if status == 404:
            raise N8nNotFoundError(message, status=status, title=title, detail=detail)
        if status == 429:
            raise N8nRateLimitedError(message, status=status, title=title, detail=detail)
        if status in (400, 422):
            raise N8nRejectedError(message, status=status, title=title, detail=detail)
        if status >= 500:
            raise N8nUnreachableError(message, status=status, title=title, detail=detail)
        raise N8nError(message, status=status, title=title, detail=detail)

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    async def _list_all_workflows_raw(self) -> list[dict[str, Any]]:
        """Follow ``nextCursor`` to a bounded depth so the caller sees
        every workflow, not just the first page (mirrors
        ``mcp/n8n/tools/diagnostics.py``'s cursor-follow — the
        ``limit=1``-style truncation bug it fixed)."""
        items: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        pages = 0
        while True:
            params: dict[str, Any] = {"limit": 250}
            if cursor:
                params["cursor"] = cursor
            data = await self._request("GET", "/workflows", params=params)
            page_items = data.get("data", []) if isinstance(data, dict) else []
            items.extend(page_items)
            cursor = data.get("nextCursor") if isinstance(data, dict) else None
            pages += 1
            if not cursor or pages >= _MAX_LIST_PAGES:
                break
        return items

    async def list_workflows(
        self, *, tag: Optional[str] = None, include_archived: bool = False
    ) -> list[Workflow]:
        raw_items = await self._list_all_workflows_raw()
        workflows = [raw_to_workflow(w) for w in raw_items]
        if not include_archived:
            workflows = [w for w in workflows if not w.archived]
        if tag:
            workflows = [
                w for w in workflows
                if any(t.id == tag or t.name == tag for t in w.tags)
            ]
        return workflows

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/workflows/{workflow_id}")
        return data if isinstance(data, dict) else {}

    async def activate(self, workflow_id: str) -> Workflow:
        await self._request("POST", f"/workflows/{workflow_id}/activate")
        return raw_to_workflow(await self.get_workflow(workflow_id))

    async def deactivate(self, workflow_id: str) -> Workflow:
        await self._request("POST", f"/workflows/{workflow_id}/deactivate")
        return raw_to_workflow(await self.get_workflow(workflow_id))

    async def create_workflow(self, workflow: dict[str, Any]) -> Workflow:
        body = sanitize_workflow_put_body(workflow)
        created = await self._request("POST", "/workflows", json=body)
        if isinstance(created, dict) and created.get("id"):
            return raw_to_workflow(created)
        return raw_to_workflow(body)

    async def update_workflow(
        self, workflow_id: str, workflow: dict[str, Any]
    ) -> Workflow:
        body = sanitize_workflow_put_body(workflow)
        updated = await self._request("PUT", f"/workflows/{workflow_id}", json=body)
        if isinstance(updated, dict) and updated.get("id"):
            return raw_to_workflow(updated)
        return raw_to_workflow({**body, "id": workflow_id})

    async def rename(self, workflow_id: str, name: str) -> Workflow:
        current = await self.get_workflow(workflow_id)
        return await self.update_workflow(workflow_id, {**current, "name": name})

    async def delete_workflow(self, workflow_id: str) -> None:
        await self._request("DELETE", f"/workflows/{workflow_id}")

    async def set_workflow_tags(
        self, workflow_id: str, tag_ids: list[str]
    ) -> list[Tag]:
        data = await self._request(
            "PUT", f"/workflows/{workflow_id}/tags", json=tag_refs_body(tag_ids)
        )
        raw_tags = data if isinstance(data, list) else (data or {}).get("tags", [])
        return [raw_to_tag(t) for t in raw_tags if isinstance(t, dict) and t.get("id")]

    # ------------------------------------------------------------------
    # Executions
    # ------------------------------------------------------------------

    async def list_executions(
        self,
        *,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[Execution]:
        data = await self._request(
            "GET",
            "/executions",
            params={
                "workflowId": workflow_id,
                "status": status,
                "limit": limit,
                "includeData": "false",
            },
        )
        items = data.get("data", []) if isinstance(data, dict) else []
        return [raw_to_execution(e) for e in items]

    async def get_execution(
        self, execution_id: int, *, include_data: bool = True
    ) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/executions/{execution_id}",
            params={"includeData": "true" if include_data else "false"},
        )
        return data if isinstance(data, dict) else {}

    async def delete_execution(self, execution_id: int) -> None:
        await self._request("DELETE", f"/executions/{execution_id}")

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    async def list_tags(self) -> list[Tag]:
        data = await self._request("GET", "/tags", params={"limit": 250})
        items = data.get("data", []) if isinstance(data, dict) else []
        return [raw_to_tag(t) for t in items]

    async def create_tag(self, name: str) -> Tag:
        data = await self._request("POST", "/tags", json={"name": name})
        return raw_to_tag(data if isinstance(data, dict) else {})

    # ------------------------------------------------------------------
    # Credentials (write-only)
    # ------------------------------------------------------------------

    async def create_credential(
        self, *, name: str, type: str, data: dict[str, Any]
    ) -> Credential:
        response = await self._request(
            "POST", "/credentials", json={"name": name, "type": type, "data": data}
        )
        return raw_to_credential(response if isinstance(response, dict) else {})

    async def delete_credential(self, credential_id: str) -> None:
        await self._request("DELETE", f"/credentials/{credential_id}")

    async def get_credential_schema(self, credential_type_name: str) -> dict[str, Any]:
        data = await self._request("GET", f"/credentials/schema/{credential_type_name}")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # Run (webhook-only)
    # ------------------------------------------------------------------

    async def run_via_webhook(self, workflow: Workflow) -> RunResult:
        if not workflow.can_run:
            raise N8nWorkflowNotRunnableError(
                f"Workflow {workflow.id!r} ({workflow.name!r}) is not "
                f"webhook-runnable: {_not_runnable_reason(workflow)}",
                status=409,
            )
        url = webhook_url(self._base_url, workflow.webhook_path or "")
        method = workflow.webhook_method or "GET"
        try:
            async with httpx.AsyncClient(transport=self._transport) as http:
                response = await http.request(
                    method,
                    url,
                    headers={"User-Agent": _BROWSER_USER_AGENT},
                    timeout=self._timeout,
                )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise N8nUnreachableError(str(exc), status=0) from exc

        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        return RunResult(
            workflow_id=workflow.id,
            dispatched=200 <= response.status_code < 300,
            http_status=response.status_code,
            raw=body,
        )

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        await self._request("GET", "/workflows", params={"limit": 1})
        return True


__all__ = ["HttpxN8nClient"]
