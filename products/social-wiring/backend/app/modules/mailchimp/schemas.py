"""Pydantic schemas for the Mailchimp module — request/response models.

All inbound models use StrictHttpModel (extra='forbid') per
KB § PATTERNS/backend/pydantic-strict-http.md. Outbound models use
standard BaseModel.

``parse_server_prefix`` is defined here for import by store / connection
router. The regex matches the ``xxxx-us6`` Mailchimp API key format:
  <random>-<dc_prefix>   e.g. abc123-us6, abc123-us21, abc123-eu1
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from noctusai_lib.api import StrictHttpModel

# ── server_prefix parser ──────────────────────────────────────────────────────
_SERVER_PREFIX_RE = re.compile(r"^[a-z]{2,3}\d+$")


def parse_server_prefix(api_key: str) -> str:
    """Extract and validate the datacenter prefix from a Mailchimp API key.

    Mailchimp API keys end with ``-<dc>`` e.g. ``xxxx-us6`` or ``xxxx-eu1``.
    The ``dc`` suffix is 2-3 lowercase letters followed by digits.

    Raises ``ValueError`` if the key is malformed (no dash, or the suffix
    doesn't match the pattern). The router maps ValueError → 400.
    """
    if "-" not in api_key:
        raise ValueError(
            f"Malformed Mailchimp API key: expected 'xxxx-dc' suffix, got {api_key!r}"
        )
    suffix = api_key.rsplit("-", 1)[-1]
    if not _SERVER_PREFIX_RE.match(suffix):
        raise ValueError(
            f"Malformed Mailchimp API key suffix {suffix!r}: expected pattern "
            f"like 'us6', 'eu1', 'us21' (2-3 lowercase letters + digits)"
        )
    return suffix


# ── Connection ────────────────────────────────────────────────────────────────

class ConnectionPutBody(StrictHttpModel):
    """PUT /connection — write-only api_key + optional audience_id.

    ``client_id`` scopes the connection to a cliente (migration 019). Omit /
    None → the org-level default connection. When set, it must belong to the
    calling org (validated in the router)."""
    api_key: str
    audience_id: Optional[str] = None
    client_id: Optional[UUID] = None


class ConnectionPatchBody(StrictHttpModel):
    """PATCH /connection — update audience only (key cannot be patched here)."""
    audience_id: str


class ConnectionOut(BaseModel):
    """GET /connection shape — always 200, nulls when disconnected.

    ``client_id`` echoes the scope probed/written: None for the org-level
    default, or the owning cliente's id (migration 019)."""
    connected: bool
    client_id: Optional[UUID] = None
    server_prefix: Optional[str] = None
    audience_id: Optional[str] = None
    audience_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Audiences ────────────────────────────────────────────────────────────────

class AudienceOut(BaseModel):
    id: str
    name: str
    member_count: int


class AudienceListOut(BaseModel):
    items: list[AudienceOut]
    total: int


# ── Contacts ─────────────────────────────────────────────────────────────────

class ContactPutBody(StrictHttpModel):
    """PUT /contacts/{email} — upsert a member."""
    status: str = "subscribed"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    tags: Optional[list[str]] = None


class MemberOut(BaseModel):
    email: str
    status: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    tags: list[str] = []
    vip: bool = False
    last_changed: Optional[datetime] = None


class ContactListOut(BaseModel):
    items: list[MemberOut]
    total: int


# ── Segments ─────────────────────────────────────────────────────────────────

class SegmentCreateBody(StrictHttpModel):
    name: str


class SegmentPatchBody(StrictHttpModel):
    name: str


class SegmentMemberAddBody(StrictHttpModel):
    email: str


class SegmentOut(BaseModel):
    id: int
    name: str
    member_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SegmentListOut(BaseModel):
    items: list[SegmentOut]
    total: int


class SegmentMemberListOut(BaseModel):
    items: list[MemberOut]
    total: int


# ── Templates ────────────────────────────────────────────────────────────────

class TemplateCreateBody(StrictHttpModel):
    name: str
    html: str


class TemplatePatchBody(StrictHttpModel):
    name: Optional[str] = None
    html: Optional[str] = None


class TemplateOut(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    type: Optional[str] = None
    drag_and_drop: bool = False
    preview_image: Optional[str] = None
    date_created: Optional[datetime] = None
    date_edited: Optional[datetime] = None
    edit_url: Optional[str] = None


class TemplateListOut(BaseModel):
    items: list[TemplateOut]
    total: int


# ── Campaigns ────────────────────────────────────────────────────────────────

class CampaignCreateBody(StrictHttpModel):
    title: str
    subject_line: str
    preview_text: Optional[str] = None
    from_name: str
    reply_to: str
    segment_id: Optional[int] = None
    template_id: Optional[int] = None


class CampaignPatchBody(StrictHttpModel):
    title: Optional[str] = None
    subject_line: Optional[str] = None
    preview_text: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    segment_id: Optional[int] = None
    template_id: Optional[int] = None


class CampaignScheduleBody(StrictHttpModel):
    schedule_time: str  # ISO8601 UTC


class CampaignTestBody(StrictHttpModel):
    emails: list[str]


class CampaignOut(BaseModel):
    id: str
    web_id: Optional[int] = None
    title: Optional[str] = None
    status: Optional[str] = None
    subject_line: Optional[str] = None
    preview_text: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    segment_id: Optional[int] = None
    template_id: Optional[int] = None
    send_time: Optional[datetime] = None
    create_time: Optional[datetime] = None
    emails_sent: Optional[int] = None
    opens: Optional[int] = None
    clicks: Optional[int] = None
    archive_url: Optional[str] = None


class CampaignListOut(BaseModel):
    items: list[CampaignOut]
    total: int
