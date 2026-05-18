"""Gmail API v1 client value objects.

Frozen dataclasses make up the public type surface:

- `GmailMessage` — flattened projection of `users.messages.get`
  (`format=full`). `body_text` / `body_html` are the decoded text and
  HTML parts (whichever the message carries; either may be ``""``).
  `received_at` is parsed from the internal `internalDate` epoch-millis.
- `GmailLabel` — minimal projection of `users.labels` (id + name +
  whether it's a Gmail system label like ``INBOX`` / ``SENT``).
- `SendResult` — outcome of `users.messages.send`: the new message id
  + thread id (Gmail threads the reply if `In-Reply-To` is set; v1
  does not, so a fresh thread is the norm).
- `GmailListResult[T]` — paginated `users.messages.list` wrapper.
  `next_page_token` is `None` on the last page.

The types are deliberately shallow (no nested raw-API blobs) so callers
get a stable contract that survives a hypothetical googleapiclient
version bump. Real / Fake adapters both produce identical instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar

SUBJECT_MAX_LEN = 998
"""RFC 5322 hard limit on a single unfolded header line (998 octets).
A `Subject:` longer than this is rejected by strict MTAs; the Real
adapter truncates before building the MIME message so a caller's
over-long subject fails loud-at-clip rather than at send time."""

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
"""Minimal scope for `users.messages.send`. App-Review-gated as a
*restricted* scope by Google — narrowest surface that still sends."""

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
"""Scope for `users.messages.list` / `.get` / `users.labels.list`.
Restricted scope; read-only — cannot send or modify."""

GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
"""Broader scope (read + write labels/state, still no full-account
delete). Not required by this v1 surface — documented so consumers
that later need label mutation know which scope to request."""


@dataclass(frozen=True)
class GmailLabel:
    """Gmail label — minimal projection of `users.labels.list`.

    `system` is True for Gmail-managed labels (``INBOX``, ``SENT``,
    ``SPAM``, ``TRASH``, ``UNREAD``, …); False for user-created
    labels. Mirrors the API's `type` field
    (``"system"`` vs ``"user"``)."""

    id: str
    name: str
    system: bool = False


@dataclass(frozen=True)
class GmailMessage:
    """Gmail message — flattened projection of `users.messages.get`.

    `to` is the raw `To:` header value (may contain multiple
    comma-separated addresses; not split — callers parse if needed).
    `snippet` is Gmail's own short preview string. `body_text` /
    `body_html` are the decoded `text/plain` / `text/html` parts;
    either may be ``""`` when the message lacks that part."""

    id: str
    thread_id: str
    from_: str
    """The `From:` header. Named `from_` because `from` is a Python
    keyword; the Real/Fake adapters both populate it identically."""
    to: str
    subject: str
    snippet: str
    body_text: str
    body_html: str
    received_at: datetime
    label_ids: tuple[str, ...] = ()
    """Gmail label ids attached to the message (e.g. ``("INBOX",
    "UNREAD")``). Tuple (hashable) so `GmailMessage` stays frozen."""


@dataclass(frozen=True)
class SendResult:
    """Result of `users.messages.send`.

    `message_id` is the newly-created Gmail message id; `thread_id`
    is the thread it landed in (a fresh thread for a brand-new
    message)."""

    message_id: str
    thread_id: str


T = TypeVar("T")


@dataclass(frozen=True)
class GmailListResult(Generic[T]):
    """Paginated list response.

    `next_page_token` is `None` when the underlying API stops
    returning `nextPageToken` (i.e. the last page). `result_size_estimate`
    echoes Gmail's `resultSizeEstimate` (approximate total; not exact)."""

    items: list[T] = field(default_factory=list)
    next_page_token: str | None = None
    result_size_estimate: int = 0


__all__ = [
    "GMAIL_MODIFY_SCOPE",
    "GMAIL_READONLY_SCOPE",
    "GMAIL_SEND_SCOPE",
    "SUBJECT_MAX_LEN",
    "GmailLabel",
    "GmailListResult",
    "GmailMessage",
    "SendResult",
]
