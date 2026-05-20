"""Pydantic schemas for the YouTube Settings tab.

Split out of ``app/schemas/settings.py`` in Phase 8 alongside the
modularization of the YouTube footprint. The non-YouTube settings
schemas (Recipients / KeysStatus / Vista / Waha / Email) stay in
``app/schemas/settings.py`` because they back cross-domain endpoints
(``/api/settings/keys/status`` enumerates secrets for every integration,
not just YouTube).

Boundary types — never let the credential bundle (refresh_token,
access_token) leak into a response model. The ``YouTubeStatus`` shape is
deliberately read-only.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class YouTubeStatus(BaseModel):
    """Connection state for the Settings → YouTube tab."""

    connected: bool
    channel_id: str | None = None
    channel_title: str | None = None
    subscriber_count: int | None = None
    video_count: int | None = None
    view_count: int | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None


class YouTubeAuthURL(BaseModel):
    """Response for GET /settings/youtube/auth-url."""

    auth_url: str
    state: str
