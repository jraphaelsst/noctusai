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
from typing import Generic, NamedTuple, TypeVar

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

GMAIL_METADATA_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"
"""Narrowest scope that can run the reply-watch loop: `users.watch`,
`users.history.list` and `users.messages.get?format=metadata` (headers +
labels, NO body). `gmail.readonly` is a superset and works too — a
mailbox already connected with `gmail.send + gmail.readonly` (the
social-wiring connect path) can watch without re-consent."""

PUBSUB_SCOPE = "https://www.googleapis.com/auth/pubsub"
"""Scope for the Pub/Sub REST API (`ensure_push_subscription`). This is
a PLATFORM-operator scope (a service account of the GCP project that owns
the topic), never requested from a tenant mailbox."""

GMAIL_PUSH_SERVICE_ACCOUNT = "gmail-api-push@system.gserviceaccount.com"
"""Google-owned identity that publishes Gmail change notifications. It
must hold `roles/pubsub.publisher` on the watch topic, else `users.watch`
fails with 403 "User not authorized to perform this action"."""

REPLY_MATCH_HEADERS: tuple[str, ...] = (
    "From",
    "Subject",
    "Message-ID",
    "In-Reply-To",
    "References",
)
"""Default header set for `get_message_metadata` — exactly what
`match_reply` + a reply-inbox row need, nothing more."""

WATCH_MAX_LIFETIME_DAYS = 7
"""`users.watch` expires after (at most) 7 days; Google recommends
re-calling it DAILY. Re-watching is idempotent (same topic → the
existing watch is refreshed), so a daily renewal job is safe."""


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


@dataclass(frozen=True)
class WatchResult:
    """Outcome of `users.watch`.

    `history_id` is the mailbox's CURRENT history id — persist it as the
    cursor for the first `list_history` call. `expiration` is when the
    watch lapses (tz-aware UTC; Google returns epoch-millis) — renew
    before it (see `WATCH_MAX_LIFETIME_DAYS`)."""

    history_id: str
    expiration: datetime


@dataclass(frozen=True)
class GmailMessageRef:
    """A message reference from `users.history.list` (`messagesAdded`).

    History carries ids + labels only; hydrate with
    `get_message_metadata` (5u) when the headers are needed."""

    id: str
    thread_id: str
    label_ids: tuple[str, ...] = ()


class GmailHistoryResult(NamedTuple):
    """`list_history` return — a NamedTuple so callers can both unpack
    `messages, new_history_id = await client.list_history(...)` and read
    it by name.

    `history_id` is the NEW cursor to persist (the mailbox's history id
    at response time — advance to it even when `messages` is empty)."""

    messages: list[GmailMessageRef]
    history_id: str


@dataclass(frozen=True)
class GmailMessageMetadata:
    """`users.messages.get?format=metadata` projection.

    `headers` maps each REQUESTED header name (in the caller's casing) to
    its value; a requested header absent from the message is present with
    ``""`` (so `headers["In-Reply-To"]` never KeyErrors). Tuple-of-pairs
    would be hashable, but a dict is what every consumer indexes — the
    dataclass is frozen, the dict is treated as read-only by convention."""

    id: str
    thread_id: str
    label_ids: tuple[str, ...]
    headers: dict[str, str]
    snippet: str = ""
    received_at: datetime | None = None


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


def validate_topic_name(topic_name: str) -> None:
    """`users.watch` needs the FULL resource name. Fail before the 100-unit
    call rather than on Gmail's opaque 400."""
    parts = topic_name.split("/")
    if len(parts) != 4 or parts[0] != "projects" or parts[2] != "topics" or not all(parts):
        raise ValueError(
            f"topic_name must be 'projects/<project>/topics/<topic>', got {topic_name!r}"
        )


__all__ = [
    "GMAIL_METADATA_SCOPE",
    "GMAIL_MODIFY_SCOPE",
    "GMAIL_PUSH_SERVICE_ACCOUNT",
    "GMAIL_READONLY_SCOPE",
    "GMAIL_SEND_SCOPE",
    "PUBSUB_SCOPE",
    "REPLY_MATCH_HEADERS",
    "SUBJECT_MAX_LEN",
    "WATCH_MAX_LIFETIME_DAYS",
    "GmailHistoryResult",
    "GmailLabel",
    "GmailListResult",
    "GmailMessage",
    "GmailMessageMetadata",
    "GmailMessageRef",
    "SendResult",
    "WatchResult",
    "validate_topic_name",
]
