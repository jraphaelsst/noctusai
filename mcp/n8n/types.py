"""Pydantic In/Out schemas for the n8n connector MCP tools.

One In + one Out model per tool (github/vista `types.py` shape). Out
models keep the raw n8n object as a `dict` where the host LLM needs
full fidelity (workflow nodes, execution run-data — debugging needs
*everything*, lossy normalization would hide the bug), plus a flat
summary list for the list endpoints and a best-effort extracted
`error_summary` for a failed execution.

`n8n` imports as a top-level package (the PyPI-`mcp`-shadow trick, see
`mcp/_kit/README.md`), so `types.py` is a safe module name here.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

# ─── Shared write-gate field (mirrors github/types.py `_CONFIRM`) ────────

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE GATE — must be explicitly true. False/omitted returns a "
        "typed error (status 412) and performs NO side-effect. This is "
        "the confirm-then-execute gate for a state-changing action."
    ),
)


# ─── n8n.workflow.list ───────────────────────────────────────────────────


class WorkflowSummary(BaseModel):
    id: str
    name: str
    active: bool = False
    tags: List[str] = Field(default_factory=list)
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class WorkflowListInput(BaseModel):
    """List workflows. PURE read — no side-effect, no confirm gate."""

    active: Optional[bool] = Field(
        None, description="Filter by active state. Omit ⇒ all."
    )
    name: Optional[str] = Field(
        None, description="Filter by workflow name (n8n exact match)."
    )
    limit: int = Field(50, ge=1, le=250, description="Max workflows.")


class WorkflowListOutput(BaseModel):
    workflows: List[WorkflowSummary] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    error: Optional[dict] = None


# ─── n8n.workflow.get ────────────────────────────────────────────────────


class WorkflowGetInput(BaseModel):
    """Fetch one workflow incl. nodes + connections. PURE read.

    `id` is the string id from the workflow URL
    (`/workflow/<id>`), e.g. `dKXJgslv7_N4w9v1fDqUe`.
    """

    id: str = Field(..., min_length=1, description="The workflow id.")


class WorkflowGetOutput(BaseModel):
    workflow: Optional[dict] = Field(
        None, description="Raw n8n workflow object (nodes/connections kept "
        "verbatim — debugging needs full fidelity)."
    )
    error: Optional[dict] = None


# ─── n8n.workflow.activate / deactivate (WRITE — confirm-gated) ──────────


class WorkflowActivateInput(BaseModel):
    """Activate a workflow. WRITE — confirm-gated."""

    id: str = Field(..., min_length=1, description="The workflow id.")
    confirm: bool = _CONFIRM


class WorkflowDeactivateInput(BaseModel):
    """Deactivate a workflow. WRITE — confirm-gated."""

    id: str = Field(..., min_length=1, description="The workflow id.")
    confirm: bool = _CONFIRM


class WorkflowActiveStateOutput(BaseModel):
    id: Optional[str] = None
    active: Optional[bool] = None
    changed: bool = False
    error: Optional[dict] = None


# ─── n8n.workflow.update (WRITE — confirm-gated) ─────────────────────────


class WorkflowUpdateInput(BaseModel):
    """Replace a workflow's definition. WRITE / hard-to-reverse —
    confirm-gated.

    `workflow` is the full workflow object (typically a
    `n8n.workflow.get` result, mutated). The handler sanitizes it to
    the n8n public-API PUT-accepted keys (`name`, `nodes`,
    `connections`, `settings`) — read-only/managed keys (`id`,
    `active`, `tags`, `createdAt`, `updatedAt`, `versionId`,
    `triggerCount`, `pinData`, `staticData`, …) are dropped so n8n does
    not 400 on additional properties. Activation state is managed
    separately via `n8n.workflow.activate`/`deactivate`.
    """

    id: str = Field(..., min_length=1, description="The workflow id.")
    workflow: dict = Field(
        ..., description="Full workflow object (get → mutate → pass back)."
    )
    confirm: bool = _CONFIRM


class WorkflowUpdateOutput(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    updated: bool = False
    sent_keys: List[str] = Field(default_factory=list)
    error: Optional[dict] = None


# ─── n8n.workflow.create (WRITE — confirm-gated) ─────────────────────────


class WorkflowCreateInput(BaseModel):
    """Create a new workflow. WRITE — confirm-gated.

    `workflow` is sanitized to the n8n public-API POST-accepted keys
    (`name`, `nodes`, `connections`, `settings`) — same key-set as
    update; read-only/managed keys are dropped.
    """

    workflow: dict = Field(
        ..., description="New workflow object (name + nodes + connections "
        "+ settings; extra keys auto-stripped)."
    )
    confirm: bool = _CONFIRM


class WorkflowCreateOutput(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    created: bool = False
    error: Optional[dict] = None


# ─── n8n.workflow.delete (WRITE — confirm-gated, hard-to-reverse) ─────────


class WorkflowDeleteInput(BaseModel):
    """Delete a workflow. WRITE / HARD-TO-REVERSE — confirm-gated.

    `n8n.workflow.get` first and keep the JSON — deletion is not
    undoable via the API.
    """

    id: str = Field(..., min_length=1, description="The workflow id.")
    confirm: bool = _CONFIRM


class WorkflowDeleteOutput(BaseModel):
    id: Optional[str] = None
    deleted: bool = False
    error: Optional[dict] = None


# ─── n8n.execution.delete (WRITE — confirm-gated) ────────────────────────


class ExecutionDeleteInput(BaseModel):
    """Delete one execution record (history cleanup). WRITE —
    confirm-gated."""

    id: int = Field(..., description="The execution id (integer).")
    confirm: bool = _CONFIRM


class ExecutionDeleteOutput(BaseModel):
    id: Optional[int] = None
    deleted: bool = False
    error: Optional[dict] = None


# ─── n8n.tag.list ────────────────────────────────────────────────────────


class TagSummary(BaseModel):
    id: str
    name: str


class TagListInput(BaseModel):
    """List tags. PURE read."""

    limit: int = Field(100, ge=1, le=250, description="Max tags.")


class TagListOutput(BaseModel):
    tags: List[TagSummary] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    error: Optional[dict] = None


# ─── n8n.workflow.set_tags (WRITE — confirm-gated) ───────────────────────


class WorkflowSetTagsInput(BaseModel):
    """Replace the tag set on a workflow. WRITE — confirm-gated.

    `tag_ids` are tag *ids* (from `n8n.tag.list`), not names — the n8n
    `PUT /workflows/{id}/tags` contract.
    """

    id: str = Field(..., min_length=1, description="The workflow id.")
    tag_ids: List[str] = Field(
        ..., description="Tag ids to set (replaces existing). [] clears all."
    )
    confirm: bool = _CONFIRM


class WorkflowSetTagsOutput(BaseModel):
    id: Optional[str] = None
    tags: List[TagSummary] = Field(default_factory=list)
    updated: bool = False
    error: Optional[dict] = None


# ─── n8n.execution.list ──────────────────────────────────────────────────


class ExecutionSummary(BaseModel):
    id: int
    finished: Optional[bool] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    retryOf: Optional[Any] = None
    startedAt: Optional[str] = None
    stoppedAt: Optional[str] = None
    workflowId: Optional[str] = None


class ExecutionListInput(BaseModel):
    """List executions (newest first). PURE read.

    The debugging entry point: filter `workflow_id` + `status="error"`
    to find recent failures, then `n8n.execution.get` one for the full
    error payload.
    """

    workflow_id: Optional[str] = Field(
        None, description="Restrict to one workflow id."
    )
    status: Optional[str] = Field(
        None,
        description="Filter: 'error' | 'success' | 'waiting'. Omit ⇒ all.",
    )
    limit: int = Field(20, ge=1, le=100, description="Max executions.")


class ExecutionListOutput(BaseModel):
    executions: List[ExecutionSummary] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    error: Optional[dict] = None


# ─── n8n.execution.get ───────────────────────────────────────────────────


class ExecutionGetInput(BaseModel):
    """Fetch one execution. PURE read — the failure-diagnosis core.

    `include_data=True` (default) pulls the full run payload (per-node
    input/output + the error object) — that is *the point* of this tool
    for debugging. Set False for a lightweight status-only check.
    """

    id: int = Field(..., description="The execution id (integer).")
    include_data: bool = Field(
        True, description="Include the full run-data payload (error lives here)."
    )


class ExecutionGetOutput(BaseModel):
    execution: Optional[dict] = Field(
        None, description="Raw n8n execution object (run-data verbatim)."
    )
    error_summary: Optional[dict] = Field(
        None,
        description="Best-effort extraction of {node, message, name, "
        "stack?} from the run-data. None when no error found or shape "
        "unrecognized — never fabricated; trust `execution` as the "
        "source of truth.",
    )
    error: Optional[dict] = None


# ─── n8n.credential.schema (READ-ONLY) ───────────────────────────────────


class CredentialSchemaInput(BaseModel):
    """Fetch a credential type's JSON schema. PURE read — no confirm.

    Discovers the required `data` keys for a type (e.g.
    `httpHeaderAuth` ⇒ {name, value}) so `n8n.credential.create` can be
    called with the right shape. There is NO list/get-credentials
    endpoint in the n8n public API (secrets are write-only by design) —
    this is the only credential-discovery surface.
    """

    credential_type_name: str = Field(
        ...,
        min_length=1,
        description="n8n credential type name, e.g. 'httpHeaderAuth', "
        "'httpBasicAuth', 'oAuth2Api'.",
    )


class CredentialSchemaOutput(BaseModel):
    credential_type_name: Optional[str] = None
    # `json_schema` not `schema` — a bare `schema` field shadows
    # pydantic.BaseModel.schema (deprecation/UserWarning); the wire key
    # stays `schema` via the serialization alias so the LLM-facing
    # shape is unchanged.
    json_schema: Optional[dict] = Field(
        None,
        alias="schema",
        serialization_alias="schema",
        description="Raw n8n credential-type JSON schema (verbatim — the "
        "host LLM needs the full required/properties shape).",
    )
    error: Optional[dict] = None

    model_config = {"populate_by_name": True}


# ─── n8n.credential.create (WRITE — confirm-gated) ───────────────────────


class CredentialCreateInput(BaseModel):
    """Create a credential. WRITE — confirm-gated.

    `data` is the secret payload whose required keys depend on `type`
    (use `n8n.credential.schema` to discover them). n8n stores it
    write-only and never echoes the secret back — only id/name/type
    are returned at create time.
    """

    name: str = Field(
        ..., min_length=1, description="Human-readable credential name."
    )
    type: str = Field(
        ...,
        min_length=1,
        description="n8n credential type name (see n8n.credential.schema).",
    )
    data: dict = Field(
        ...,
        description="Secret payload — shape depends on `type`. Write-only; "
        "n8n never echoes it back.",
    )
    confirm: bool = _CONFIRM


class CredentialCreateOutput(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    created: bool = False
    error: Optional[dict] = None


# ─── n8n.credential.delete (WRITE — confirm-gated, hard-to-reverse) ──────


class CredentialDeleteInput(BaseModel):
    """Delete a credential by id. WRITE / HARD-TO-REVERSE — confirm-gated.

    The secret is unrecoverable after delete (no API undo, no
    read-back); any workflow node referencing this credential id will
    fail until re-pointed.
    """

    id: str = Field(..., min_length=1, description="The credential id.")
    confirm: bool = _CONFIRM


class CredentialDeleteOutput(BaseModel):
    id: Optional[str] = None
    deleted: bool = False
    error: Optional[dict] = None


# ─── n8n.diagnostics.connection_status ───────────────────────────────────


class ConnectionStatusInput(BaseModel):
    """Introspect the n8n dependency. PURE read.

    Gated-capability honesty: surfaces whether the connector is
    configured AND the instance is reachable/authenticated, so a query
    that 'succeeds empty' because the key is wrong is never silently
    misread as 'no data'.
    """


class ConnectionStatusOutput(BaseModel):
    configured: bool = False
    api_root: Optional[str] = None
    reachable: Optional[bool] = None
    workflow_count: Optional[int] = None
    error: Optional[dict] = None


__all__ = [
    "WorkflowSummary",
    "WorkflowListInput",
    "WorkflowListOutput",
    "WorkflowGetInput",
    "WorkflowGetOutput",
    "WorkflowActivateInput",
    "WorkflowDeactivateInput",
    "WorkflowActiveStateOutput",
    "WorkflowUpdateInput",
    "WorkflowUpdateOutput",
    "WorkflowCreateInput",
    "WorkflowCreateOutput",
    "WorkflowDeleteInput",
    "WorkflowDeleteOutput",
    "ExecutionDeleteInput",
    "ExecutionDeleteOutput",
    "TagSummary",
    "TagListInput",
    "TagListOutput",
    "WorkflowSetTagsInput",
    "WorkflowSetTagsOutput",
    "ExecutionSummary",
    "ExecutionListInput",
    "ExecutionListOutput",
    "ExecutionGetInput",
    "ExecutionGetOutput",
    "CredentialSchemaInput",
    "CredentialSchemaOutput",
    "CredentialCreateInput",
    "CredentialCreateOutput",
    "CredentialDeleteInput",
    "CredentialDeleteOutput",
    "ConnectionStatusInput",
    "ConnectionStatusOutput",
]
