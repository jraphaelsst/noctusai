"""Mailchimp Marketing API v3 — value objects, error hierarchy, and Protocol.

Covers audiences, members, static segments, templates, campaigns,
and paginated list results.  All errors carry the HTTP status plus
the ``title`` / ``detail`` from Mailchimp's problem+json shape so
callers can build precise user-facing messages.

Per ``KB § PATTERNS/seed-fake-real-adapter.md``: the ``MailchimpClient``
Protocol is the surface both ``HttpxMailchimpClient`` (real) and
``FakeMailchimpClient`` (in-memory deterministic) satisfy structurally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Protocol, Sequence, TypeVar, runtime_checkable


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class MailchimpError(Exception):
    """Base for all Mailchimp adapter errors.

    ``status`` mirrors the HTTP status code Mailchimp returned (or
    0 for transport / connection failures).  ``title`` and ``detail``
    are taken verbatim from Mailchimp's problem+json body when available.
    """

    def __init__(
        self,
        message: str = "",
        *,
        status: int = 0,
        title: str = "",
        detail: str = "",
    ) -> None:
        super().__init__(message or title or detail or f"Mailchimp error (status={status})")
        self.status = status
        self.title = title
        self.detail = detail


class MailchimpAuthError(MailchimpError):
    """401 / 403 — bad API key or insufficient permissions."""


class MailchimpNotFoundError(MailchimpError):
    """404 — resource does not exist."""


class MailchimpRateLimitedError(MailchimpError):
    """429 — request rate exceeded."""


class MailchimpRejectedError(MailchimpError):
    """400 / 422 — Mailchimp rejected the payload (validation failure).

    ``detail`` carries Mailchimp's human-readable explanation; callers
    should surface it verbatim (e.g. "add_segment_member: email not
    subscribed to audience").
    """


class MailchimpUnreachableError(MailchimpError):
    """Network / TLS / 5xx — transient infrastructure failure.

    ``status`` is 0 for transport-level failures; 5xx for server errors.
    """


# ---------------------------------------------------------------------------
# Paginated page wrapper
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    """Thin wrapper around a paginated Mailchimp list response."""

    items: Sequence[T]
    total: int
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Audience:
    """Mailchimp audience (list) summary."""

    id: str
    name: str
    member_count: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Member:
    """Mailchimp audience member."""

    email: str
    status: str          # subscribed | unsubscribed | cleaned | pending | archived
    first_name: str
    last_name: str
    tags: list[str]
    vip: bool
    last_changed: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Segment:
    """Mailchimp static segment (saved segment)."""

    id: int
    name: str
    member_count: int
    created_at: datetime | None
    updated_at: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Template:
    """Mailchimp template."""

    id: int
    name: str
    category: str
    type: str            # user | base | gallery
    drag_and_drop: bool
    preview_image: str
    date_created: datetime | None
    date_edited: datetime | None
    edit_url: str        # computed server-side; see mappers.template_edit_url
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Campaign:
    """Mailchimp campaign."""

    id: str
    web_id: int
    title: str
    status: str          # save | paused | schedule | sending | sent
    subject_line: str
    preview_text: str
    from_name: str
    reply_to: str
    segment_id: int | None
    template_id: int | None
    send_time: datetime | None
    create_time: datetime | None
    emails_sent: int | None
    opens: int | None
    clicks: int | None
    archive_url: str
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class MailchimpClient(Protocol):
    """Async Mailchimp Marketing API v3 adapter.

    Both ``HttpxMailchimpClient`` (real, httpx-backed) and
    ``FakeMailchimpClient`` (in-memory deterministic) satisfy this
    Protocol structurally.  All methods are ``async``.

    Per ``KB § PATTERNS/seed-fake-real-adapter.md``: the Protocol is the
    gold-standard contract the ``get_mailchimp_client(...)`` factory
    returns.  Slices B and C build against these exact names/signatures.
    """

    # -- Connectivity --------------------------------------------------------

    async def ping(self) -> dict[str, Any]:
        """GET /ping — returns {"health_status": "Everything's Chimpy!"} on success."""
        ...

    # -- Audiences -----------------------------------------------------------

    async def list_audiences(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Audience]:
        """GET /lists"""
        ...

    async def get_audience(self, audience_id: str) -> Audience:
        """GET /lists/{id}"""
        ...

    # -- Members -------------------------------------------------------------

    async def list_members(
        self,
        audience_id: str,
        *,
        status: str | None = None,
        count: int = 25,
        offset: int = 0,
    ) -> Page[Member]:
        """GET /lists/{id}/members"""
        ...

    async def get_member(self, audience_id: str, email: str) -> Member:
        """GET /lists/{id}/members/{subscriber_hash}"""
        ...

    async def upsert_member(
        self,
        audience_id: str,
        email: str,
        *,
        status: str = "subscribed",
        first_name: str = "",
        last_name: str = "",
        status_if_new: str = "subscribed",
    ) -> Member:
        """PUT /lists/{id}/members/{subscriber_hash} — upsert.

        ``status_if_new`` is sent only in the request body so Mailchimp
        subscribes new contacts but does not force-resubscribe existing ones.
        """
        ...

    async def set_member_tags(
        self,
        audience_id: str,
        email: str,
        *,
        active_tags: list[str],
        inactive_tags: list[str] | None = None,
    ) -> None:
        """POST /lists/{id}/members/{hash}/tags — declarative tag update."""
        ...

    async def archive_member(self, audience_id: str, email: str) -> None:
        """DELETE /lists/{id}/members/{subscriber_hash} (archives the member)."""
        ...

    # -- Segments ------------------------------------------------------------

    async def list_segments(
        self, audience_id: str, *, count: int = 25, offset: int = 0
    ) -> Page[Segment]:
        """GET /lists/{id}/segments"""
        ...

    async def create_static_segment(
        self, audience_id: str, *, name: str
    ) -> Segment:
        """POST /lists/{id}/segments  {type: "static", name: name}"""
        ...

    async def update_segment(
        self, audience_id: str, segment_id: int, *, name: str
    ) -> Segment:
        """PATCH /lists/{id}/segments/{segment_id}"""
        ...

    async def delete_segment(self, audience_id: str, segment_id: int) -> None:
        """DELETE /lists/{id}/segments/{segment_id}"""
        ...

    async def list_segment_members(
        self, audience_id: str, segment_id: int, *, count: int = 25, offset: int = 0
    ) -> Page[Member]:
        """GET /lists/{id}/segments/{segment_id}/members"""
        ...

    async def add_segment_member(
        self, audience_id: str, segment_id: int, email: str
    ) -> None:
        """POST /lists/{id}/segments/{segment_id}/members.

        Raises ``MailchimpRejectedError`` when the email is not subscribed
        to the audience (mirrors the real API's behaviour).
        """
        ...

    async def remove_segment_member(
        self, audience_id: str, segment_id: int, email: str
    ) -> None:
        """DELETE /lists/{id}/segments/{segment_id}/members/{subscriber_hash}"""
        ...

    # -- Templates -----------------------------------------------------------

    async def list_templates(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Template]:
        """GET /templates?type=user"""
        ...

    async def get_template(self, template_id: int) -> Template:
        """GET /templates/{id}"""
        ...

    async def create_template(self, *, name: str, html: str) -> Template:
        """POST /templates  {name, html}"""
        ...

    async def update_template(
        self, template_id: int, *, name: str | None = None, html: str | None = None
    ) -> Template:
        """PATCH /templates/{id}"""
        ...

    async def delete_template(self, template_id: int) -> None:
        """DELETE /templates/{id}"""
        ...

    async def get_template_default_content(self, template_id: int) -> dict[str, Any]:
        """GET /templates/{id}/default-content"""
        ...

    # -- Campaigns -----------------------------------------------------------

    async def list_campaigns(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Campaign]:
        """GET /campaigns"""
        ...

    async def get_campaign(self, campaign_id: str) -> Campaign:
        """GET /campaigns/{id}"""
        ...

    async def create_campaign(
        self,
        *,
        title: str,
        subject_line: str,
        preview_text: str = "",
        from_name: str,
        reply_to: str,
        audience_id: str,
        segment_id: int | None = None,
        template_id: int | None = None,
    ) -> Campaign:
        """POST /campaigns  {type: "regular", settings, recipients}

        When ``template_id`` is given also calls ``set_campaign_content``.
        """
        ...

    async def update_campaign(
        self,
        campaign_id: str,
        *,
        title: str | None = None,
        subject_line: str | None = None,
        preview_text: str | None = None,
        from_name: str | None = None,
        reply_to: str | None = None,
        segment_id: int | None = None,
        template_id: int | None = None,
    ) -> Campaign:
        """PATCH /campaigns/{id}"""
        ...

    async def delete_campaign(self, campaign_id: str) -> None:
        """DELETE /campaigns/{id}"""
        ...

    async def set_campaign_content(
        self, campaign_id: str, *, template_id: int | None = None
    ) -> dict[str, Any]:
        """PUT /campaigns/{id}/content"""
        ...

    async def send_campaign(self, campaign_id: str) -> Campaign:
        """POST /campaigns/{id}/actions/send — re-reads campaign after action."""
        ...

    async def schedule_campaign(
        self, campaign_id: str, *, schedule_time: str
    ) -> Campaign:
        """POST /campaigns/{id}/actions/schedule  {schedule_time: ISO8601 UTC}"""
        ...

    async def unschedule_campaign(self, campaign_id: str) -> Campaign:
        """POST /campaigns/{id}/actions/unschedule"""
        ...

    async def send_test(
        self, campaign_id: str, *, test_emails: list[str]
    ) -> dict[str, Any]:
        """POST /campaigns/{id}/actions/test  {test_emails, send_type: "html"}"""
        ...
