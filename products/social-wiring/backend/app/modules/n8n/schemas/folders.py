"""Pydantic schemas for the n8n folder-tree surface.

``N8nFolderOut`` lives in ``schemas/common.py`` (shared with
``N8nWorkflowListResponse.folders``) — this file only carries the
request bodies.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = ["N8nFolderCreateIn", "N8nFolderUpdateIn"]


class N8nFolderCreateIn(BaseModel):
    account_id: UUID
    name: str = Field(min_length=1)
    parent_id: Optional[UUID] = None

    class Config:
        extra = "forbid"


class N8nFolderUpdateIn(BaseModel):
    """PATCH /api/n8n/folders/{folder_id} body — deliberately carries
    NO ``account_id`` (the contract's shape): the folder row itself
    carries ``org_id``/``account_id``, so the router derives ownership
    from the row rather than a caller-supplied id (can't be spoofed to
    a different account this way).

    ``parent_id`` uses ``model_fields_set`` at the router to
    distinguish "not supplied" (leave parent unchanged) from
    "explicitly null" (reparent to root) — same tri-state pattern as
    ``N8nWorkflowPatchIn.folder_id``.
    """

    name: Optional[str] = Field(default=None, min_length=1)
    parent_id: Optional[UUID] = None
    position: Optional[int] = Field(default=None, ge=0)

    class Config:
        extra = "forbid"
