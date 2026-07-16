"""Pure-function mappers for the n8n public API v1 adapter.

Provides:
- ``normalize_base_url(raw)`` / ``instance_root(raw)`` — the two
  derived URLs a stored ``base_url`` (the instance root) produces:
  API = ``{root}/api/v1``, webhook = ``{root}/webhook/{path}``.
- ``WORKFLOW_PUT_ALLOWED_KEYS`` / ``sanitize_workflow_put_body`` — n8n's
  ``PUT /workflows/{id}`` 400s on additional properties; this is the
  single canonical allowlist (``name``/``nodes``/``connections``/
  ``settings``). ``mcp/n8n/tools/workflow.py`` imports this instead of
  keeping its own copy (Leg B — the fork this slice exists to prevent).
- ``tag_refs_body(tag_ids)`` — n8n's ``PUT /workflows/{id}/tags`` body
  shape: tag **ids**, not names.
- ``extract_webhook_trigger(nodes)`` — finds the
  ``n8n-nodes-base.webhook`` node (if any) and returns its
  ``(method, path)``; other trigger flavors (``formTrigger``,
  ``executeWorkflowTrigger``, ``manualTrigger``) are not webhook-runnable.
- ``raw_to_workflow``, ``raw_to_tag``, ``raw_to_execution``,
  ``raw_to_credential`` — raw dict → dataclass translators.
- ``extract_error_message(body)`` — best-effort title/detail pull from
  an n8n error response (n8n's error shape is less uniform than
  Mailchimp's problem+json).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

from noctusai_lib.integrations.n8n.types import Credential, Execution, Tag, Workflow

# n8n public-API PUT /workflows/{id} (and POST /workflows) reject additional
# properties — only these four keys are accepted. Activation state and tags
# are managed via their own endpoints, never the workflow body. Measured live
# 2026-07-16 (`mcp/n8n/tools/workflow.py:48` pre-lift copy).
WORKFLOW_PUT_ALLOWED_KEYS = ("name", "nodes", "connections", "settings")

# The one trigger-node type that can actually be dispatched via a public
# webhook URL. `formTrigger` / `executeWorkflowTrigger` / `manualTrigger`
# were all observed live on the same instance and are NOT webhook-runnable.
_WEBHOOK_NODE_TYPE = "n8n-nodes-base.webhook"


# ---------------------------------------------------------------------------
# URL derivation
# ---------------------------------------------------------------------------


def normalize_base_url(raw: str) -> str:
    """Return the API root ending in ``/api/v1``, no trailing slash.

    Accepts either the instance root (``https://n8n.example.com``) or
    an already-suffixed URL (``https://n8n.example.com/api/v1``) —
    both normalize to the same value so an operator-entered value
    can't get it subtly wrong.

    >>> normalize_base_url("https://n8n.x.com")
    'https://n8n.x.com/api/v1'
    >>> normalize_base_url("https://n8n.x.com/")
    'https://n8n.x.com/api/v1'
    >>> normalize_base_url("https://n8n.x.com/api/v1")
    'https://n8n.x.com/api/v1'
    >>> normalize_base_url("")
    ''
    """
    base = (raw or "").rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/v1"):
        return base
    return f"{base}/api/v1"


def instance_root(raw: str) -> str:
    """Return the bare instance root (no ``/api/v1`` suffix) — the base
    for webhook URLs, which live outside the versioned API
    (``{root}/webhook/{path}``, NOT ``{root}/api/v1/webhook/{path}``).

    >>> instance_root("https://n8n.x.com/api/v1")
    'https://n8n.x.com'
    >>> instance_root("https://n8n.x.com/")
    'https://n8n.x.com'
    >>> instance_root("")
    ''
    """
    base = (raw or "").rstrip("/")
    if base.endswith("/api/v1"):
        base = base[: -len("/api/v1")]
    return base


def webhook_url(base_url: str, path: str) -> str:
    """Build the run-dispatch URL for a webhook-triggered workflow.

    >>> webhook_url("https://n8n.x.com", "matricula-extractor")
    'https://n8n.x.com/webhook/matricula-extractor'
    """
    return f"{instance_root(base_url)}/webhook/{path}"


# ---------------------------------------------------------------------------
# PUT-sanitize allowlist
# ---------------------------------------------------------------------------


def sanitize_workflow_put_body(workflow: dict[str, Any]) -> dict[str, Any]:
    """Strip a workflow dict to the PUT/POST-accepted key-set.

    Read-only/managed keys (``id``, ``active``, ``tags``, timestamps,
    ``versionId``, ``triggerCount``, ``pinData``, ``staticData``, …)
    are dropped so n8n does not 400 on additional properties.
    ``settings`` always ends up present (defaulted to ``{}`` when the
    source omitted it) — n8n's PUT body requires it.
    """
    body = {k: workflow[k] for k in WORKFLOW_PUT_ALLOWED_KEYS if k in workflow}
    body.setdefault("settings", workflow.get("settings") or {})
    return body


# ---------------------------------------------------------------------------
# Tag-ids-not-names
# ---------------------------------------------------------------------------


def tag_refs_body(tag_ids: Sequence[str]) -> list[dict[str, str]]:
    """n8n ``PUT /workflows/{id}/tags`` body shape: ``[{"id": "<tagId>"}, ...]``
    — tag **ids**, never names."""
    return [{"id": tid} for tid in tag_ids]


# ---------------------------------------------------------------------------
# Webhook-trigger extraction
# ---------------------------------------------------------------------------


def extract_webhook_trigger(
    nodes: Optional[List[dict[str, Any]]],
) -> Optional[tuple[str, str]]:
    """Find the first ``n8n-nodes-base.webhook`` node and return its
    ``(method, path)``. ``None`` when no webhook trigger is present
    (e.g. ``formTrigger``/``executeWorkflowTrigger``/``manualTrigger``
    workflows — all observed live, none webhook-runnable).
    """
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        if node.get("type") != _WEBHOOK_NODE_TYPE:
            continue
        params = node.get("parameters") or {}
        path = params.get("path")
        if not path:
            continue
        method = str(params.get("httpMethod") or "GET").upper()
        return method, str(path)
    return None


# ---------------------------------------------------------------------------
# Datetime helper
# ---------------------------------------------------------------------------


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 n8n timestamp to a timezone-aware ``datetime``.
    Returns ``None`` when ``value`` is falsy. n8n uses UTC, strings end
    in ``Z``."""
    if not value:
        return None
    normalised = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalised)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Raw → dataclass translators
# ---------------------------------------------------------------------------


def raw_to_tag(raw: dict[str, Any]) -> Tag:
    """Translate an n8n /tags item into a ``Tag``."""
    return Tag(id=str(raw.get("id", "")), name=raw.get("name", ""))


def raw_to_workflow(raw: dict[str, Any]) -> Workflow:
    """Translate a full n8n /workflows item into a ``Workflow`` summary.

    Deliberately does NOT retain ``nodes``/``connections`` on the
    returned value object (see ``types.Workflow`` docstring) — only the
    derived ``has_webhook_node``/``webhook_method``/``webhook_path``/
    ``can_run`` facts survive.
    """
    nodes = raw.get("nodes") or []
    trigger = extract_webhook_trigger(nodes)
    webhook_method, webhook_path = trigger if trigger else (None, None)
    has_webhook = trigger is not None
    active = bool(raw.get("active", False))
    archived = bool(raw.get("isArchived", False))
    tags = [
        raw_to_tag(t)
        for t in (raw.get("tags") or [])
        if isinstance(t, dict) and t.get("id")
    ]
    return Workflow(
        id=str(raw.get("id", "")),
        name=raw.get("name", ""),
        active=active,
        archived=archived,
        tags=tags,
        has_webhook_node=has_webhook,
        webhook_method=webhook_method,
        webhook_path=webhook_path,
        can_run=has_webhook and active and not archived,
        created_at=_parse_dt(raw.get("createdAt")),
        updated_at=_parse_dt(raw.get("updatedAt")),
    )


def raw_to_execution(raw: dict[str, Any]) -> Execution:
    """Translate an n8n /executions item (``includeData=false`` shape)
    into an ``Execution`` summary."""
    workflow_id = raw.get("workflowId")
    return Execution(
        id=int(raw["id"]),
        workflow_id=str(workflow_id) if workflow_id is not None else None,
        status=raw.get("status"),
        mode=raw.get("mode"),
        finished=raw.get("finished"),
        started_at=_parse_dt(raw.get("startedAt")),
        stopped_at=_parse_dt(raw.get("stoppedAt")),
        retry_of=raw.get("retryOf"),
    )


def raw_to_credential(raw: dict[str, Any]) -> Credential:
    """Translate an n8n /credentials create-response into a
    ``Credential``. Never carries ``data`` — n8n does not echo the
    secret back, not even at create time."""
    return Credential(
        id=str(raw.get("id", "")),
        name=raw.get("name", ""),
        type=raw.get("type", ""),
    )


# ---------------------------------------------------------------------------
# Error-body extraction
# ---------------------------------------------------------------------------


def extract_error_message(body: Any) -> tuple[str, str]:
    """Best-effort ``(title, detail)`` extraction from an n8n error
    response body.

    n8n's error shape is less uniform than Mailchimp's problem+json —
    a plain ``{"message": "..."}`` is the common case, but ``title``/
    ``detail``/``error`` have also been seen across n8n versions.
    Returns ``("", "")`` when nothing recognizable is found — never
    fabricated.
    """
    if not isinstance(body, dict):
        return "", ""
    title = body.get("title") or body.get("error") or ""
    detail = body.get("detail") or body.get("message") or ""
    return str(title), str(detail)


__all__ = [
    "WORKFLOW_PUT_ALLOWED_KEYS",
    "normalize_base_url",
    "instance_root",
    "webhook_url",
    "sanitize_workflow_put_body",
    "tag_refs_body",
    "extract_webhook_trigger",
    "raw_to_tag",
    "raw_to_workflow",
    "raw_to_execution",
    "raw_to_credential",
    "extract_error_message",
]
