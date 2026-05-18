"""Real Gmail API v1 client.

Wraps `googleapiclient.discovery.build("gmail", "v1", ...)`.

**OAuth-only.** Unlike YouTube/Drive (which accept an API key for
read-only *public* data), Gmail's `users.messages.*` always act on a
*private user mailbox* — there is no API-key path. Constructing a
`RealGmailClient` without `oauth_credentials` raises `ValueError` at
construction time (fail loud, per the no-silent-errors rule) — never a
silent degrade to an empty mailbox.

Send builds a proper MIME message (multipart/alternative when an HTML
body is supplied) and submits the base64url-encoded `raw` per the
Gmail API contract. API errors are logged at WARN level before
re-raising — never silently swallowed.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from noctusai_lib.integrations.gmail.types import (
    SUBJECT_MAX_LEN,
    GmailListResult,
    GmailMessage,
    SendResult,
)

logger = logging.getLogger(__name__)


# ---- MIME helpers ----------------------------------------------------------


def _build_raw(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None,
    cc: str | None,
    bcc: str | None,
) -> str:
    """Build an RFC 5322 message and return the base64url `raw` string
    the Gmail API expects (`users.messages.send` body=`{"raw": ...}`).

    `EmailMessage` is the stdlib MIME builder — no third-party MIME
    dependency, no hand-rolled header concatenation. An HTML body is
    added as an `add_alternative` so the message is
    `multipart/alternative` (plain + html); plain-only otherwise."""
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject[:SUBJECT_MAX_LEN]
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def _header(headers: list[dict[str, Any]], name: str) -> str:
    """Case-insensitive lookup of a header value from the Gmail
    `payload.headers` list. Returns ``""`` when absent."""
    lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == lower:
            return h.get("value", "")
    return ""


def _decode_part(data: str) -> str:
    """Decode a Gmail base64url `body.data` blob to text. Gmail omits
    padding; `urlsafe_b64decode` needs it restored. Returns ``""`` on
    decode failure (logged at WARN — a malformed part must not poison
    the whole message)."""
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        logger.warning("gmail.body_part_decode_failed len=%d", len(data))
        return ""


def _extract_bodies(payload: dict[str, Any]) -> tuple[str, str]:
    """Walk a Gmail `payload` tree and return `(body_text, body_html)`.

    Gmail nests parts arbitrarily (`multipart/alternative` inside
    `multipart/mixed`, etc.); a recursive walk collects the first
    `text/plain` and first `text/html` leaf."""
    text = ""
    html = ""

    def _walk(part: dict[str, Any]) -> None:
        nonlocal text, html
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data", "")
        if mime == "text/plain" and not text and data:
            text = _decode_part(data)
        elif mime == "text/html" and not html and data:
            html = _decode_part(data)
        for sub in part.get("parts", []) or []:
            _walk(sub)

    _walk(payload)
    return text, html


def _message_from_api(item: dict[str, Any]) -> GmailMessage:
    payload = item.get("payload", {})
    headers = payload.get("headers", [])
    body_text, body_html = _extract_bodies(payload)
    internal_ms = item.get("internalDate")
    try:
        received_at = (
            datetime.fromtimestamp(int(internal_ms) / 1000, tz=timezone.utc)
            if internal_ms
            else datetime.min.replace(tzinfo=timezone.utc)
        )
    except (ValueError, TypeError):
        logger.warning(
            "gmail.internal_date_parse_failed value=%r", internal_ms
        )
        received_at = datetime.min.replace(tzinfo=timezone.utc)
    return GmailMessage(
        id=item.get("id", ""),
        thread_id=item.get("threadId", ""),
        from_=_header(headers, "From"),
        to=_header(headers, "To"),
        subject=_header(headers, "Subject"),
        snippet=item.get("snippet", ""),
        body_text=body_text,
        body_html=body_html,
        received_at=received_at,
        label_ids=tuple(item.get("labelIds", []) or []),
    )


# ---- RealGmailClient -------------------------------------------------------


class RealGmailClient:
    """Real Gmail API v1 client.

    **OAuth-only** — `oauth_credentials` (any
    `google.oauth2.credentials.Credentials`-shaped object) is
    REQUIRED. `api_key` is accepted in the signature purely for
    factory-shape parity with the youtube/drive adapters, but Gmail
    has no API-key path: an api-key-only construction raises
    `ValueError` (fail loud — never a silent degrade to an empty
    mailbox).

    Logs every API error at WARN+ before re-raising or returning
    None (per the no-silent-errors rule)."""

    def __init__(
        self,
        api_key: str | None = None,
        oauth_credentials: Any = None,
    ) -> None:
        if oauth_credentials is None:
            raise ValueError(
                "RealGmailClient requires oauth_credentials — Gmail has no "
                "API-key path for a user mailbox (users.messages.* act on a "
                "private mailbox; an api_key cannot authenticate one)"
            )
        self._api_key = api_key
        self._oauth_credentials = oauth_credentials

    def _service(self) -> Any:
        return build(
            "gmail",
            "v1",
            credentials=self._oauth_credentials,
            cache_discovery=False,
        )

    # ---- GmailClient surface --------------------------------------------

    async def send_message(
        self,
        *,
        to: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> SendResult:
        """100 quota units (`users.messages.send`). Requires the
        `gmail.send` scope — a readonly-only credential yields a 403
        which is logged at WARN and re-raised verbatim (no swallow)."""
        raw = _build_raw(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
        )
        try:
            response = (
                self._service()
                .users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "gmail.send_message_http_error to=%r status=%s",
                to,
                getattr(exc.resp, "status", "?"),
            )
            raise
        return SendResult(
            message_id=response.get("id", ""),
            thread_id=response.get("threadId", ""),
        )

    async def list_messages(
        self,
        *,
        query: str | None = None,
        label: str | None = None,
        page_token: str | None = None,
    ) -> GmailListResult[GmailMessage]:
        """5 quota units for the list page (`users.messages.list`)
        plus 5 units per message hydrated via `get_message`.

        `users.messages.list` returns only ids + thread ids, so each
        listed id is hydrated with a `get_message` call to honour the
        Protocol's "return full `GmailMessage`" contract. Requires the
        `gmail.readonly` scope."""
        kwargs: dict[str, Any] = {"userId": "me"}
        if query is not None:
            kwargs["q"] = query
        if label is not None:
            kwargs["labelIds"] = [label]
        if page_token is not None:
            kwargs["pageToken"] = page_token
        try:
            response = (
                self._service()
                .users()
                .messages()
                .list(**kwargs)
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "gmail.list_messages_http_error query=%r status=%s",
                query,
                getattr(exc.resp, "status", "?"),
            )
            raise

        stubs = response.get("messages", []) or []
        items: list[GmailMessage] = []
        for stub in stubs:
            msg = await self.get_message(stub.get("id", ""))
            if msg is not None:
                items.append(msg)
        return GmailListResult(
            items=items,
            next_page_token=response.get("nextPageToken"),
            result_size_estimate=int(response.get("resultSizeEstimate", 0) or 0),
        )

    async def get_message(self, message_id: str) -> GmailMessage | None:
        """5 quota units (`users.messages.get?format=full`). Requires
        the `gmail.readonly` scope. Returns `None` on a 404 (deleted /
        nonexistent); re-raises any other HTTP error after a WARN."""
        if not message_id:
            return None
        try:
            item = (
                self._service()
                .users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status == 404:
                return None
            logger.warning(
                "gmail.get_message_http_error message_id=%s status=%s",
                message_id,
                status if status is not None else "?",
            )
            raise
        return _message_from_api(item)


__all__ = ["RealGmailClient"]
