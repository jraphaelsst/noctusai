"""Pydantic In/Out models for every `trello.*` tool.

Contract-tool Out models return `dict[str, Any]` for the vendor-shaped
sub-objects (spec fragments, schema property maps) — those ARE the
vendored spec's own shape, not something worth re-typing. Live-tool Out
models stay similarly loose for the same reason `mcp/olx/types.py`
documents: the vendor payload is authoritative, and hand-typing it would
encode a transcription as truth.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class _In(BaseModel):
    """Base for inputs — reject unknown keys so a typo'd argument is a
    loud 422 rather than a silently-ignored option."""

    model_config = {"extra": "forbid"}


# ── contract (zero IO, no credentials) ─────────────────────────────────


class ListEndpointsInput(_In):
    resource: Optional[str] = Field(
        default=None,
        description="Filter to one root resource, e.g. 'cards', 'boards', "
        "'checklists'. Case-sensitive, matches the spec's own casing "
        "(customFields, not customfields).",
    )
    method: Optional[str] = Field(
        default=None, description="Filter to one HTTP method, e.g. 'GET'."
    )
    q: Optional[str] = Field(
        default=None, description="Substring match against path + summary."
    )


class ListEndpointsOutput(BaseModel):
    endpoints: list[dict[str, Any]] = Field(
        description="Each: method, path, resource, operation_id, summary."
    )
    count: int


class DescribeOperationInput(_In):
    method: Optional[str] = Field(default=None, description="e.g. 'PUT'. Requires `path`.")
    path: Optional[str] = Field(default=None, description="e.g. '/cards/{id}'. Requires `method`.")
    operation_id: Optional[str] = Field(
        default=None,
        description="e.g. 'put-cards-id'. Alternative to method+path — "
        "either this OR both method and path must be set.",
    )


class DescribeOperationOutput(BaseModel):
    operation: Optional[dict[str, Any]] = Field(
        default=None,
        description="method, path, summary, description, parameters "
        "(name/in/type/required/description each), request_body (raw "
        "schema when present), response_schema_ref (the 2xx body's "
        "named schema, if any).",
    )
    error: Optional[dict[str, Any]] = None


class DescribeModelInput(_In):
    name: str = Field(description="Exact schema name, e.g. 'Card', 'Checklist', "
                       "'CheckItem', 'Label', 'Attachment', 'Action', "
                       "'CustomField', 'Member', 'Board', 'TrelloList'.")


class DescribeModelOutput(BaseModel):
    model: Optional[dict[str, Any]] = Field(
        default=None,
        description="name, properties (each: type, description, and for "
        "object-shaped or $ref properties a nested_properties list — "
        "one level of flattening, so badges.* is visible), required.",
    )
    error: Optional[dict[str, Any]] = None


class CardSurfaceInput(_In):
    pass


class CardSurfaceOutput(BaseModel):
    groups: dict[str, list[dict[str, Any]]] = Field(
        description="The 42 /cards/* operations grouped by affordance: "
        "core, comments_activity, attachments, checklists, check_items, "
        "labels, members, votes, stickers, custom_fields.",
    )
    operation_count: int
    card_schema: dict[str, Any] = Field(
        description="describe_model('Card') output, inline — badges.* "
        "flattened, since the card-face reproduction is exactly what "
        "asked for this tool.",
    )
    put_writable_fields: list[str] = Field(
        description="The exact `PUT /cards/{id}` parameter name list, in "
        "spec order — the full writable surface of an existing card.",
    )


class CapabilityMapInput(_In):
    pass


class CapabilityMapOutput(BaseModel):
    mappings: list[dict[str, Any]] = Field(
        description="Each: trello_affordance, card_hub_equivalent, status "
        "(exists|build-new|no-equivalent), substrate (the roadmap's own "
        "words), trello_schema_ref (cross-reference into the Card/Action/"
        "etc. schema, when there is a direct one).",
    )
    source: str = Field(
        description="Where this mapping was transcribed FROM — the "
        "roadmap doc is the source of truth; a change there must be "
        "reflected here by hand, not silently drift.",
    )


# ── diagnostics ──────────────────────────────────────────────────────


class ConnectionStatusInput(_In):
    pass


class ConnectionStatusOutput(BaseModel):
    ok: bool
    configured: bool
    has_api_key: bool
    has_token: bool
    base_url: str
    next_step: Optional[str] = None


class ProbeInput(_In):
    pass


class ProbeOutput(BaseModel):
    probed: bool = Field(description="False when unconfigured and nothing was called.")
    member: Optional[dict[str, Any]] = Field(
        default=None, description="GET /members/me on success — proves the "
        "key+token pair actually authenticates."
    )
    error: Optional[dict[str, Any]] = None


# ── live reads ───────────────────────────────────────────────────────


class BoardsListInput(_In):
    member_id: str = Field(default="me", description="Trello member id, or 'me'.")


class BoardsListOutput(BaseModel):
    boards: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class ListsListInput(_In):
    board_id: str


class ListsListOutput(BaseModel):
    lists: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class CardsListInput(_In):
    board_id: Optional[str] = Field(default=None, description="Exactly one of board_id/list_id.")
    list_id: Optional[str] = Field(default=None, description="Exactly one of board_id/list_id.")


class CardsListOutput(BaseModel):
    cards: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class CardsGetInput(_In):
    card_id: str
    include: Optional[list[str]] = Field(
        default=None,
        description="Any of 'attachments', 'checklists', 'members', 'actions'.",
    )


class CardsGetOutput(BaseModel):
    card: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class ChecklistsGetInput(_In):
    checklist_id: str


class ChecklistsGetOutput(BaseModel):
    checklist: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class LabelsListInput(_In):
    board_id: str


class LabelsListOutput(BaseModel):
    labels: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


class ActionsListInput(_In):
    card_id: str
    filter: Optional[str] = Field(
        default=None,
        description="Trello action-type filter, e.g. 'commentCard'. Unset = all.",
    )


class ActionsListOutput(BaseModel):
    actions: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[dict[str, Any]] = None


# ── live writes (confirm-gated) ─────────────────────────────────────


class CardsCreateInput(_In):
    id_list: str = Field(description="The List to create the card on.")
    name: str
    desc: Optional[str] = None
    due: Optional[str] = Field(default=None, description="ISO 8601, or null.")
    id_members: Optional[list[str]] = None
    id_labels: Optional[list[str]] = None
    confirm: bool = Field(default=False, description="Must be true — this creates a real card.")


class CardsCreateOutput(BaseModel):
    created: bool
    card: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class CardsUpdateInput(_In):
    card_id: str
    fields: dict[str, Any] = Field(
        description="Keys MUST be from the documented `PUT /cards/{id}` "
        "writable-param list (see trello.contract.card_surface). An "
        "unknown key is rejected before any network call.",
    )
    confirm: bool = Field(default=False, description="Must be true — this mutates a real card.")


class CardsUpdateOutput(BaseModel):
    updated: bool
    card: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class CardsCommentAddInput(_In):
    card_id: str
    text: str
    confirm: bool = Field(default=False, description="Must be true — this posts a real comment.")


class CardsCommentAddOutput(BaseModel):
    added: bool
    action: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class ChecklistsCreateInput(_In):
    card_id: str
    name: str
    confirm: bool = Field(default=False, description="Must be true — this creates a real checklist.")


class ChecklistsCreateOutput(BaseModel):
    created: bool
    checklist: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


__all__ = [
    "ActionsListInput", "ActionsListOutput",
    "BoardsListInput", "BoardsListOutput",
    "CapabilityMapInput", "CapabilityMapOutput",
    "CardSurfaceInput", "CardSurfaceOutput",
    "CardsCommentAddInput", "CardsCommentAddOutput",
    "CardsCreateInput", "CardsCreateOutput",
    "CardsGetInput", "CardsGetOutput",
    "CardsListInput", "CardsListOutput",
    "CardsUpdateInput", "CardsUpdateOutput",
    "ChecklistsCreateInput", "ChecklistsCreateOutput",
    "ChecklistsGetInput", "ChecklistsGetOutput",
    "ConnectionStatusInput", "ConnectionStatusOutput",
    "DescribeModelInput", "DescribeModelOutput",
    "DescribeOperationInput", "DescribeOperationOutput",
    "LabelsListInput", "LabelsListOutput",
    "ListEndpointsInput", "ListEndpointsOutput",
    "ListsListInput", "ListsListOutput",
    "ProbeInput", "ProbeOutput",
]
