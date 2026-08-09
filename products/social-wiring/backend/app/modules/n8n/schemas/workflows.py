"""Pydantic schemas for the n8n workflows + tags + executions surface.

Bare typed responses (no envelope), concrete ``response_model`` on
every route — mirrors ``app/modules/youtube/schemas/video.py``'s
shape. ``N8nWorkflowOut`` deliberately never carries ``nodes`` /
``connections`` — those are the seed adapter's ``Workflow`` value
object's own design (heavy payload; see
``noctusai_lib.integrations.n8n.types.Workflow`` docstring) and this
schema mirrors that omission on the HTTP boundary too.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.n8n.schemas.common import N8nFolderOut, N8nTagOut

__all__ = [
    "N8nWorkflowOut",
    "N8nWorkflowListResponse",
    "N8nExecutionOut",
    "N8nExecutionListResponse",
    "N8nRunResult",
    "N8nAccountIdIn",
    "N8nWorkflowPatchIn",
    "N8nTagCreateIn",
]


class N8nWorkflowOut(BaseModel):
    """A workflow projected for the FE — run-eligibility + local
    folder placement pre-computed so the FE never re-derives
    ``can_run`` from raw node data."""

    id: str
    name: str
    active: bool
    archived: bool
    tags: list[N8nTagOut] = Field(default_factory=list)
    folder_id: Optional[UUID] = None
    can_run: bool
    run_blocked_reason: Optional[str] = None
    open_url: str
    updated_at: Optional[datetime] = None


class N8nWorkflowListResponse(BaseModel):
    """GET /api/n8n/workflows response. ``folders`` is the account's
    FULL folder tree (not scope-filtered) — the FE renders the tree
    navigation independent of which bucket (client/unassigned) is
    selected."""

    workflows: list[N8nWorkflowOut]
    folders: list[N8nFolderOut]


class N8nExecutionOut(BaseModel):
    id: int
    status: Optional[str] = None
    mode: Optional[str] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None


class N8nExecutionListResponse(BaseModel):
    executions: list[N8nExecutionOut]


class N8nRunResult(BaseModel):
    """Response for POST /api/n8n/workflows/{id}/run. Never fabricated
    — mirrors the seed adapter's ``RunResult`` (``raw`` is dropped;
    the FE only needs dispatched/http_status)."""

    workflow_id: str
    dispatched: bool
    http_status: Optional[int] = None


class N8nAccountIdIn(BaseModel):
    """Shared body shape for the account-scoped mutation endpoints
    that take no other fields (assign / unassign / delete / run)."""

    account_id: UUID

    class Config:
        extra = "forbid"


class N8nWorkflowPatchIn(BaseModel):
    """PATCH /api/n8n/workflows/{id} body. All fields besides
    ``account_id`` are optional; ``folder_id`` uses
    ``model_fields_set`` at the router to distinguish "not supplied"
    (leave placement unchanged) from "explicitly null" (move to
    root) — same tri-state pattern as
    ``integration_accounts_router.IntegrationAccountUpdate.marca_id``.
    """

    account_id: UUID
    name: Optional[str] = Field(default=None, min_length=1)
    active: Optional[bool] = None
    folder_id: Optional[UUID] = None

    class Config:
        extra = "forbid"


class N8nTagCreateIn(BaseModel):
    account_id: UUID
    name: str = Field(min_length=1)

    class Config:
        extra = "forbid"
