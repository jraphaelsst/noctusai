"""Pydantic schemas for the n8n Settings tab — GET/PUT /api/n8n/settings.

Boundary types — the decrypted ``api_key`` never appears in a response
model (``has_api_key: bool`` only), same discipline
``youtube/schemas/settings.py`` applies to the OAuth token bundle.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.modules.n8n.schemas.common import N8nTagOut

__all__ = ["N8nSettingsOut", "N8nSettingsUpdateIn"]


class N8nSettingsOut(BaseModel):
    """Connection state for the Settings → n8n tab.

    ``status`` is DERIVED (see routers/settings.py's GET handler
    docstring) — never a raw passthrough of the stored ``status``
    column, which can lie for pre-reshape rows. ``reachable`` is
    ``None`` on every GET (never pings n8n on a page load — same rule
    ``youtube/routers/settings.py``'s ``get_youtube_status`` follows);
    PUT actively pings and reports the real outcome.
    """

    account_id: UUID
    base_url: Optional[str] = None
    has_api_key: bool
    tag: Optional[N8nTagOut] = None
    status: str
    reachable: Optional[bool] = None


class N8nSettingsUpdateIn(BaseModel):
    """PUT /api/n8n/settings body. All fields besides ``account_id``
    are optional — a partial update (e.g. rotating just the api_key,
    or only picking a tag) leaves the other stored fields untouched.
    """

    account_id: UUID
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    tag_id: Optional[str] = None

    class Config:
        extra = "forbid"
