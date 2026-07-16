"""Shared value shapes reused across the n8n module's three routers.

``N8nTagOut`` backs both the workflows tags surface (GET/POST
/api/n8n/tags, and each workflow's ``tags`` list) and the Settings
tab's configured client-tag. ``N8nFolderOut`` backs both the folder
tree endpoints and ``N8nWorkflowListResponse.folders``. Pulled out
here (rather than duplicated per schema file, or left to import from
whichever file happened to define it first) so neither workflows.py
nor settings.py nor folders.py owns the other's value type.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class N8nTagOut(BaseModel):
    """An n8n workflow tag. n8n tag ids are opaque strings (not UUIDs)."""

    id: str
    name: str


class N8nFolderOut(BaseModel):
    """A local (product-side) workflow-organization folder.

    Distinct from n8n tags — folders are NOT synced to n8n; they live
    entirely in ``social_wiring.n8n_folders`` (migration 024, shipped
    by a sibling unmerged branch this slice codes against without
    re-authoring)."""

    id: UUID
    name: str
    parent_id: Optional[UUID] = None
    position: int = 0


__all__ = ["N8nTagOut", "N8nFolderOut"]
