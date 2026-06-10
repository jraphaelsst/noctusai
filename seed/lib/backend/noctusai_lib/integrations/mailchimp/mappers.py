"""Pure-function mappers for the Mailchimp Marketing API v3 adapter.

Provides:
- ``subscriber_hash(email)`` — MD5 of the lower-cased, stripped email,
  the Mailchimp-canonical member identifier.
- ``parse_server_prefix(api_key)`` — extract the datacenter slug from
  an API key of the form ``<token>-<dc>`` (e.g. ``xxxx-us6`` → ``us6``).
- ``template_edit_url(server_prefix, template_id)`` — deep-link into
  the Mailchimp drag-and-drop template editor.
- ``raw_to_audience``, ``raw_to_member``, ``raw_to_segment``,
  ``raw_to_template``, ``raw_to_campaign`` — minimal raw→dataclass
  translators, always preserving the full ``raw`` dict.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.mailchimp.types import (
    Audience,
    Campaign,
    Member,
    Segment,
    Template,
)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def subscriber_hash(email: str) -> str:
    """Return the MD5 hex digest of the lowercase-stripped email.

    This is Mailchimp's canonical member identifier for member-level
    API calls (GET/PUT/DELETE /lists/{id}/members/{hash}).

    >>> subscriber_hash("  Test@Example.COM  ")
    '55502f40dc8b7c769880b10874abc9d0'
    """
    normalised = email.strip().lower()
    return hashlib.md5(normalised.encode()).hexdigest()  # noqa: S324  (MD5 required by Mailchimp API)


def parse_server_prefix(api_key: str) -> str:
    """Extract the datacenter prefix from a Mailchimp API key.

    Mailchimp API keys have the form ``<token>-<dc>`` where ``<dc>``
    is a short datacenter slug such as ``us6``, ``us19``, or ``eu1``.

    Raises ``ValueError`` when the key is empty or lacks the ``-<dc>``
    suffix (e.g. a raw UUID without a datacenter).

    >>> parse_server_prefix("abc123def456-us6")
    'us6'
    >>> parse_server_prefix("abc123def456-eu1")
    'eu1'
    """
    if not api_key or "-" not in api_key:
        raise ValueError(
            f"Malformed Mailchimp API key — expected '<token>-<dc>' suffix, got: {api_key!r}"
        )
    dc = api_key.rsplit("-", 1)[-1].strip()
    if not dc:
        raise ValueError(
            f"Malformed Mailchimp API key — datacenter suffix is empty: {api_key!r}"
        )
    return dc


def template_edit_url(server_prefix: str, template_id: int) -> str:
    """Build the Mailchimp admin deep-link to the template editor.

    The URL is best-effort for drag-and-drop templates; the Mailchimp
    web UI uses the same pattern for all template types.

    >>> template_edit_url("us6", 12345)
    'https://us6.admin.mailchimp.com/templates/edit?id=12345'
    """
    return f"https://{server_prefix}.admin.mailchimp.com/templates/edit?id={template_id}"


# ---------------------------------------------------------------------------
# Datetime helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 / Mailchimp timestamp string to a timezone-aware
    ``datetime``.  Returns ``None`` when ``value`` is falsy.

    Mailchimp uses UTC but the strings end in ``+00:00`` or ``Z``.
    """
    if not value:
        return None
    # Python 3.11+ fromisoformat handles 'Z', but earlier versions do not.
    normalised = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalised)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Raw → dataclass translators
# ---------------------------------------------------------------------------


def raw_to_audience(raw: dict[str, Any]) -> Audience:
    """Translate a Mailchimp /lists item dict into an ``Audience``."""
    stats = raw.get("stats", {})
    return Audience(
        id=raw["id"],
        name=raw.get("name", ""),
        member_count=stats.get("member_count", 0),
        raw=raw,
    )


def raw_to_member(raw: dict[str, Any]) -> Member:
    """Translate a Mailchimp /lists/{id}/members item into a ``Member``."""
    merge_fields = raw.get("merge_fields", {})
    tags_raw = raw.get("tags", [])
    # Tags come as [{"id": N, "name": "..."}, ...] or plain strings.
    tags: list[str] = []
    for t in tags_raw:
        if isinstance(t, dict):
            name = t.get("name", "")
            if name:
                tags.append(name)
        elif isinstance(t, str):
            tags.append(t)

    return Member(
        email=raw.get("email_address", ""),
        status=raw.get("status", ""),
        first_name=merge_fields.get("FNAME", ""),
        last_name=merge_fields.get("LNAME", ""),
        tags=tags,
        vip=raw.get("vip", False),
        last_changed=_parse_dt(raw.get("last_changed")),
        raw=raw,
    )


def raw_to_segment(raw: dict[str, Any]) -> Segment:
    """Translate a Mailchimp /lists/{id}/segments item into a ``Segment``."""
    return Segment(
        id=raw["id"],
        name=raw.get("name", ""),
        member_count=raw.get("member_count", 0),
        created_at=_parse_dt(raw.get("created_at")),
        updated_at=_parse_dt(raw.get("updated_at")),
        raw=raw,
    )


def raw_to_template(raw: dict[str, Any], *, server_prefix: str = "") -> Template:
    """Translate a Mailchimp /templates item into a ``Template``.

    ``server_prefix`` is used to compute ``edit_url``; pass it from
    the connection record so the URL is always correct.
    """
    template_id: int = raw["id"]
    edit_url = template_edit_url(server_prefix, template_id) if server_prefix else ""
    return Template(
        id=template_id,
        name=raw.get("name", ""),
        category=raw.get("category", ""),
        type=raw.get("type", "user"),
        drag_and_drop=raw.get("drag_and_drop", False),
        preview_image=raw.get("thumbnail", ""),
        date_created=_parse_dt(raw.get("date_created")),
        date_edited=_parse_dt(raw.get("date_edited")),
        edit_url=edit_url,
        raw=raw,
    )


def raw_to_campaign(raw: dict[str, Any]) -> Campaign:
    """Translate a Mailchimp /campaigns item into a ``Campaign``.

    Extracts:
    - ``segment_id`` from ``recipients.segment_opts.saved_segment_id``
    - ``template_id`` from ``settings.template_id``
    - ``opens`` / ``clicks`` flattened from ``report_summary`` (null pre-send)
    """
    settings = raw.get("settings", {})
    recipients = raw.get("recipients", {})
    segment_opts = recipients.get("segment_opts", {})
    report = raw.get("report_summary", {})

    return Campaign(
        id=raw["id"],
        web_id=raw.get("web_id", 0),
        title=settings.get("title", ""),
        status=raw.get("status", ""),
        subject_line=settings.get("subject_line", ""),
        preview_text=settings.get("preview_text", ""),
        from_name=settings.get("from_name", ""),
        reply_to=settings.get("reply_to", ""),
        segment_id=segment_opts.get("saved_segment_id") or None,
        template_id=settings.get("template_id") or None,
        send_time=_parse_dt(raw.get("send_time")),
        create_time=_parse_dt(raw.get("create_time")),
        emails_sent=raw.get("emails_sent"),
        opens=report.get("opens") if report else None,
        clicks=report.get("clicks") if report else None,
        archive_url=raw.get("archive_url", ""),
        raw=raw,
    )
