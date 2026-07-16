"""n8n public API v1 — value objects, error hierarchy, and Protocol.

Covers workflows, executions, tags, and the webhook-only run path. All
errors carry the HTTP status plus a best-effort ``title``/``detail``
extracted from n8n's error body so callers can build precise
user-facing messages.

Per ``KB § PATTERNS/backend/seed-fake-real-adapter.md``: the
``N8nClient`` Protocol is the surface both ``HttpxN8nClient`` (real)
and ``FakeN8nClient`` (in-memory deterministic) satisfy structurally.

**Hard-won facts, measured against a live instance 2026-07-16 —
encoded here so they are never re-derived by trial and error:**

- ``GET /workflows`` returns FULL workflow objects including ``nodes``
  (36 nodes on the largest of 9 live workflows). Eligibility
  (``can_run``) is therefore computable on the list with **no N+1**
  — but the payload is heavy, so ``Workflow`` (the list/summary value
  object) does NOT retain ``nodes``/``connections``/``staticData``/
  ``pinData`` beyond what the mapper needs to compute the derived
  fields below. ``get_workflow()`` is the one method that returns the
  full raw object (nodes included) — GET → mutate → PUT needs it.
- ``isArchived`` exists and was true on 2 of 9 live workflows.
  ``list_workflows(include_archived=False)`` is the default.
- A production webhook only fires while the workflow is ``active``.
  ⇒ ``can_run = has_webhook_node AND active AND NOT archived``. Live
  truth on 2026-07-16: exactly 1 of 9 workflows qualified.
- The webhook trigger node type is ``n8n-nodes-base.webhook``, with
  ``parameters = {httpMethod, path, options}`` plus a node-level
  ``webhookId``. ``path`` is either a friendly slug
  (``matricula-extractor``) or a bare UUID. Other trigger flavors seen
  live (``formTrigger``, ``executeWorkflowTrigger``, ``manualTrigger``)
  are NOT webhook-runnable.
- Execution ids are ``int``; workflow ids are ``str``. Never unified.
- Credentials are write-only — the public API has no list/get
  credential endpoint (mirrors the Mailchimp adapter's write-only
  secret handling).
- ``GET /projects`` → 403 (license-gated on community edition). Do not
  build anything on projects; a client "tag" is the only viable
  scoping key for a multi-tenant consumer.
- There is NO public execute-workflow endpoint. ``run_via_webhook()``
  is the only sanctioned dispatch path and raises
  ``N8nWorkflowNotRunnableError`` — never a faked dispatch — when the
  workflow does not satisfy ``can_run``.

``create_workflow``/``update_workflow``/``delete_execution``/the three
``*_credential``/``get_credential_schema`` methods were added when
``mcp/n8n`` was refactored to consume this Protocol directly (rather
than its own HTTP client) — every one of ``mcp/n8n``'s 16 tools now
routes through an ``N8nClient`` built by ``get_n8n_client()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class N8nError(Exception):
    """Base for all n8n seed-adapter errors.

    ``status`` mirrors the HTTP status n8n returned (0 for transport /
    connection failures). ``title``/``detail`` are a best-effort
    extraction from n8n's error body (n8n's error shape is less
    uniform than Mailchimp's problem+json; several common keys are
    tried — see ``mappers.extract_error_message``).
    """

    def __init__(
        self,
        message: str = "",
        *,
        status: int = 0,
        title: str = "",
        detail: str = "",
    ) -> None:
        super().__init__(message or title or detail or f"n8n error (status={status})")
        self.status = status
        self.title = title
        self.detail = detail


class N8nAuthError(N8nError):
    """401 / 403 — bad API key or insufficient permissions."""


class N8nNotFoundError(N8nError):
    """404 — resource does not exist."""


class N8nRateLimitedError(N8nError):
    """429 — request rate exceeded."""


class N8nRejectedError(N8nError):
    """400 / 422 — n8n rejected the payload (e.g. PUT with additional
    properties, malformed body)."""


class N8nUnreachableError(N8nError):
    """Network / TLS / 5xx — transient infrastructure failure.

    ``status`` is 0 for transport-level failures; 5xx for server
    errors.
    """


class N8nWorkflowNotRunnableError(N8nError):
    """``run_via_webhook()`` called on a workflow that does not satisfy
    ``can_run`` (no webhook trigger, inactive, or archived).

    A local validation failure, not an upstream HTTP error — no
    request is ever sent. Never fake a dispatch; this is the typed,
    loud alternative.
    """


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tag:
    """An n8n workflow tag — the only viable multi-tenant scoping key
    on a community-edition instance (``GET /projects`` is license-gated)."""

    id: str
    name: str


@dataclass(frozen=True)
class Workflow:
    """A workflow list/summary value object.

    Deliberately does NOT retain ``nodes``/``connections`` — those are
    heavy (36 nodes on the largest of 9 live workflows) and
    ``list_workflows()`` may return many of these at once. Only the
    derived run-eligibility facts survive the mapping; call
    ``get_workflow(id)`` for the full raw object when nodes/connections
    are actually needed (editing, GET→mutate→PUT).
    """

    id: str
    name: str
    active: bool
    archived: bool
    tags: List[Tag] = field(default_factory=list)
    has_webhook_node: bool = False
    webhook_method: Optional[str] = None
    webhook_path: Optional[str] = None
    can_run: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class Execution:
    """An execution summary (list item — ``includeData=false``).

    ``get_execution(..., include_data=True)`` returns the raw dict
    instead — the full per-node run-data (incl. the error object) is
    the entire point of that call for debugging; wrapping it in a
    value object would either lose fidelity or duplicate the raw dict.
    """

    id: int
    workflow_id: Optional[str]
    status: Optional[str]
    mode: Optional[str]
    finished: Optional[bool]
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    retry_of: Optional[Any] = None


@dataclass(frozen=True)
class Credential:
    """A created credential's public handle. n8n stores the secret
    ``data`` write-only — it is never echoed back, not even to this
    value object; only ``id``/``name``/``type`` survive create."""

    id: str
    name: str
    type: str


@dataclass(frozen=True)
class RunResult:
    """Result of ``run_via_webhook()``. Never fabricated — ``dispatched``
    reflects the real webhook response status; ``raw`` is best-effort
    (``None`` when the webhook response body isn't JSON)."""

    workflow_id: str
    dispatched: bool
    http_status: Optional[int]
    raw: Any = None


# ---------------------------------------------------------------------------
# Client Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class N8nClient(Protocol):
    """Async n8n public API v1 adapter.

    Both ``HttpxN8nClient`` (real, httpx-backed) and ``FakeN8nClient``
    (in-memory deterministic) satisfy this Protocol structurally. All
    methods are ``async``.

    Per ``KB § PATTERNS/backend/seed-fake-real-adapter.md``: the
    Protocol is the gold-standard contract the ``get_n8n_client(...)``
    factory returns.
    """

    # -- Workflows -------------------------------------------------------

    async def list_workflows(
        self, *, tag: Optional[str] = None, include_archived: bool = False
    ) -> List[Workflow]:
        """GET /workflows (paginated, cursor-followed) → filtered client-side.

        ``tag`` matches against either a tag id or a tag name on the
        workflow (n8n's own ``tags`` query-param semantics for the
        public API were not verified against the live instance, so
        filtering happens locally against the already-fetched full
        objects — correct by construction, no upstream-shape guess).
        ``include_archived=False`` is the default (2 of 9 live
        workflows were archived; a page showing them by default is
        the wrong default).
        """
        ...

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        """GET /workflows/{id} — the RAW object, nodes/connections
        included verbatim. The one method that keeps full fidelity;
        use for GET→mutate→PUT flows (rename, workflow editing)."""
        ...

    async def create_workflow(self, workflow: dict[str, Any]) -> Workflow:
        """POST /workflows — ``workflow`` is sanitized to
        ``mappers.WORKFLOW_PUT_ALLOWED_KEYS`` internally (n8n 400s on
        additional properties, same allowlist ``update_workflow``/
        ``rename`` use)."""
        ...

    async def update_workflow(
        self, workflow_id: str, workflow: dict[str, Any]
    ) -> Workflow:
        """PUT /workflows/{id} — ``workflow`` is sanitized to
        ``mappers.WORKFLOW_PUT_ALLOWED_KEYS`` internally. The general
        form: accepts an arbitrary (possibly full) workflow dict.
        ``rename()`` is a convenience wrapper built on this (GET
        current → set ``name`` → ``update_workflow``)."""
        ...

    async def activate(self, workflow_id: str) -> Workflow:
        """POST /workflows/{id}/activate, then re-read via
        ``get_workflow`` so the returned ``Workflow`` is never a
        partially-fabricated guess."""
        ...

    async def deactivate(self, workflow_id: str) -> Workflow:
        """POST /workflows/{id}/deactivate, then re-read (see ``activate``)."""
        ...

    async def rename(self, workflow_id: str, name: str) -> Workflow:
        """GET → set ``name`` → sanitize to the PUT-accepted key-set
        (``mappers.WORKFLOW_PUT_ALLOWED_KEYS`` — ``PUT /workflows/{id}``
        400s on additional properties) → PUT. The only supported
        workflow-editing verb this Protocol exposes."""
        ...

    async def delete_workflow(self, workflow_id: str) -> None:
        """DELETE /workflows/{id} — hard-to-reverse, not API-undoable."""
        ...

    async def set_workflow_tags(
        self, workflow_id: str, tag_ids: List[str]
    ) -> List[Tag]:
        """PUT /workflows/{id}/tags — takes tag **ids**, not names."""
        ...

    # -- Executions --------------------------------------------------------

    async def list_executions(
        self,
        *,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Execution]:
        """GET /executions (``includeData=false`` — list items stay light)."""
        ...

    async def get_execution(
        self, execution_id: int, *, include_data: bool = True
    ) -> dict[str, Any]:
        """GET /executions/{id} — RAW object. ``include_data=True``
        pulls the full run payload (the error lives here); the
        debugging entry point."""
        ...

    async def delete_execution(self, execution_id: int) -> None:
        """DELETE /executions/{id} — history cleanup, not API-undoable."""
        ...

    # -- Tags ----------------------------------------------------------------

    async def list_tags(self) -> List[Tag]:
        """GET /tags"""
        ...

    async def create_tag(self, name: str) -> Tag:
        """POST /tags {name}"""
        ...

    # -- Credentials (write-only — n8n has no list/get endpoint) ------------

    async def create_credential(
        self, *, name: str, type: str, data: dict[str, Any]
    ) -> Credential:
        """POST /credentials {name, type, data} → ``Credential``
        (id/name/type only — ``data`` is NEVER echoed back; n8n stores
        credential secrets write-only by design)."""
        ...

    async def delete_credential(self, credential_id: str) -> None:
        """DELETE /credentials/{id} — hard-to-reverse; the secret is
        gone, no API undo, no read-back."""
        ...

    async def get_credential_schema(
        self, credential_type_name: str
    ) -> dict[str, Any]:
        """GET /credentials/schema/{type} — discovers the required
        ``data`` keys for a credential type (e.g. ``httpHeaderAuth`` ⇒
        {name, value}). The only credential-discovery surface — there
        is no list/get-credentials endpoint."""
        ...

    # -- Run (webhook-only — there is NO public execute endpoint) -----------

    async def run_via_webhook(self, workflow: Workflow) -> RunResult:
        """Dispatch to ``{instance_root}/webhook/{workflow.webhook_path}``
        via ``workflow.webhook_method``.

        Raises ``N8nWorkflowNotRunnableError`` — never a faked
        dispatch — when ``workflow.can_run`` is False. This is the
        ONLY sanctioned run path: the n8n public API has no execute
        endpoint, and the UI's internal ``/rest/workflows/run`` is
        session-auth and MUST NOT be emulated.
        """
        ...

    # -- Connectivity ----------------------------------------------------

    async def ping(self) -> bool:
        """Reachability probe (n8n's public API has no dedicated
        ``/ping``): a cheap bounded read (``GET /workflows?limit=1``).
        Returns True on success; raises the typed error hierarchy on
        failure — reachability is never fabricated."""
        ...


__all__ = [
    # Error hierarchy
    "N8nError",
    "N8nAuthError",
    "N8nNotFoundError",
    "N8nRateLimitedError",
    "N8nRejectedError",
    "N8nUnreachableError",
    "N8nWorkflowNotRunnableError",
    # Value objects
    "Tag",
    "Workflow",
    "Execution",
    "Credential",
    "RunResult",
    # Protocol
    "N8nClient",
]
