"""In-memory deterministic FakeGmailClient for dev + tests.

No network, no googleapiclient. Page size is deliberately small
(`PAGE_SIZE = 2`) so paging logic exercises in 3-4 messages rather
than Gmail's default 100.

Seed-data shape (via the factory's `fake_seed_data`):

```python
make_gmail_client(
    use_fake=True,
    fake_seed_data={
        "messages": [
            GmailMessage(id="m1", thread_id="t1", from_="a@x.com",
                         to="me@x.com", subject="Hi", snippet="...",
                         body_text="hello", body_html="",
                         received_at=datetime(2026, 5, 18),
                         label_ids=("INBOX", "UNREAD")),
        ],
    },
)
```

Every `send_message` call appends a `GmailMessage` (the sent copy,
labelled ``SENT``) to `.sent` AND into the in-memory store so a
subsequent `list_messages(label="SENT")` round-trips it — tests
assert against `.sent` without going near googleapiclient.

**Push-watch simulation.** The fake keeps a monotonically increasing
mailbox history id (starts at `INITIAL_HISTORY_ID`). Every
`add_fake_message` / `send_message` bumps it and records a
`messageAdded` event, so `list_history(start)` returns exactly the
messages added after `start` — the same contract Gmail serves.
`expire_history_before(history_id)` makes older cursors raise
`GmailHistoryExpiredError` (the resync path). `watch()` / `stop()` record
their calls on `.watches` / `.stop_calls` and expose `.active_watch`.
Sent messages carry a deterministic RFC `Message-ID`
(``<fake-sent-N@fake.gmail.local>``) and `add_fake_message(headers=...)`
accepts `In-Reply-To` / `References`, so a test can drive the whole
send → reply → `match_reply` loop without a network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from noctusai_lib.integrations.gmail.errors import GmailHistoryExpiredError
from noctusai_lib.integrations.gmail.types import (
    REPLY_MATCH_HEADERS,
    SUBJECT_MAX_LEN,
    WATCH_MAX_LIFETIME_DAYS,
    GmailHistoryResult,
    GmailListResult,
    GmailMessage,
    GmailMessageMetadata,
    GmailMessageRef,
    SendResult,
    WatchResult,
    validate_topic_name,
)

FAKE_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
"""Deterministic clock for the fake (watch expiration = FAKE_NOW + 7d)."""


class FakeGmailClient:
    """Deterministic in-memory `GmailClient` implementation.

    Messages page in insertion order. `send_message` is deterministic:
    ids are ``fake-sent-1``, ``fake-sent-2``, … in call order, each in
    its own thread ``fake-thread-1``, … ."""

    PAGE_SIZE: int = 2
    INITIAL_HISTORY_ID: int = 1000

    def __init__(
        self,
        messages: list[GmailMessage] | None = None,
    ) -> None:
        # Preserve insertion order; dedup by id keeping last.
        self._messages: dict[str, GmailMessage] = {}
        self._extra_headers: dict[str, dict[str, str]] = {}
        # (history_id, message_id) — one `messageAdded` event per add.
        self._history: list[tuple[int, str]] = []
        self._history_id: int = self.INITIAL_HISTORY_ID
        self._history_floor: int = 0
        for msg in messages or []:
            self._store(msg)
        self.sent: list[GmailMessage] = []
        """Every `send_message` call appends the sent `GmailMessage`
        here, in order — tests assert against it directly."""
        self._send_seq: int = 0
        self.watches: list[tuple[str, tuple[str, ...]]] = []
        """Every `watch()` call as `(topic_name, label_ids)`, in order."""
        self.stop_calls: int = 0
        self.active_watch: tuple[str, tuple[str, ...]] | None = None
        """The current `(topic_name, label_ids)`; `None` after `stop()`."""

    def _store(
        self, msg: GmailMessage, headers: dict[str, str] | None = None
    ) -> None:
        """Insert `msg`, bump the history id and record `messageAdded`."""
        self._messages[msg.id] = msg
        if headers:
            self._extra_headers[msg.id] = dict(headers)
        self._history_id += 1
        self._history.append((self._history_id, msg.id))

    @property
    def history_id(self) -> str:
        """The mailbox's current history id (string, like Gmail's)."""
        return str(self._history_id)

    def expire_history_before(self, history_id: str | int) -> None:
        """Fixture seam: cursors older than `history_id` now raise
        `GmailHistoryExpiredError` from `list_history` (Gmail's 404)."""
        self._history_floor = int(history_id)

    # ---- Fixture seam ----------------------------------------------------

    def add_fake_message(
        self,
        message_id: str,
        *,
        thread_id: str | None = None,
        from_: str = "sender@example.com",
        to: str = "me@example.com",
        subject: str = "",
        snippet: str = "",
        body_text: str = "",
        body_html: str = "",
        received_at: datetime | None = None,
        label_ids: tuple[str, ...] = ("INBOX",),
        headers: dict[str, str] | None = None,
    ) -> GmailMessage:
        """Seed a message into the fake inbox; returns the stored
        `GmailMessage` (also retrievable via `get_message`).

        `headers` carries extra RFC headers served by
        `get_message_metadata` (e.g. ``{"Message-ID": "<a@x>",
        "In-Reply-To": "<b@y>"}``). Each add bumps the history id and
        records a `messageAdded` event for `list_history`."""
        msg = GmailMessage(
            id=message_id,
            thread_id=thread_id or f"thread-{message_id}",
            from_=from_,
            to=to,
            subject=subject,
            snippet=snippet,
            body_text=body_text,
            body_html=body_html,
            received_at=received_at
            or datetime(2026, 1, 1, tzinfo=timezone.utc),
            label_ids=label_ids,
        )
        self._store(msg, headers)
        return msg

    # ---- Internal paging -------------------------------------------------

    def _page(
        self,
        items: list[GmailMessage],
        page_token: str | None,
    ) -> tuple[list[GmailMessage], str | None]:
        """Slice `items` into a page of size `PAGE_SIZE`. `page_token`
        is the integer offset (as a string), `None` for the first
        page. Returns `(page_items, next_page_token)` — the token is
        `None` on the last page."""
        offset = int(page_token) if page_token else 0
        end = offset + self.PAGE_SIZE
        page_items = items[offset:end]
        next_token = str(end) if end < len(items) else None
        return page_items, next_token

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
        """Deterministic send. Subject is clipped to `SUBJECT_MAX_LEN`
        exactly like the Real adapter so tests catch over-long
        subjects without a network round-trip. The sent copy is
        appended to `.sent` and stored (labelled ``SENT``) so a
        later `list_messages(label="SENT")` round-trips it."""
        self._send_seq += 1
        message_id = f"fake-sent-{self._send_seq}"
        thread_id = f"fake-thread-{self._send_seq}"
        sent = GmailMessage(
            id=message_id,
            thread_id=thread_id,
            from_="me@example.com",
            to=to,
            subject=subject[:SUBJECT_MAX_LEN],
            snippet=body_text[:100],
            body_text=body_text,
            body_html=body_html or "",
            received_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            label_ids=("SENT",),
        )
        self._store(
            sent, {"Message-ID": f"<{message_id}@fake.gmail.local>"}
        )
        self.sent.append(sent)
        return SendResult(message_id=message_id, thread_id=thread_id)

    async def list_messages(
        self,
        *,
        query: str | None = None,
        label: str | None = None,
        page_token: str | None = None,
    ) -> GmailListResult[GmailMessage]:
        """List stored messages (insertion order), filtered by `label`
        and a naive case-insensitive `query` substring on
        subject/snippet/body_text. Mirrors the Real adapter's
        list→hydrate contract by returning full `GmailMessage`
        objects (the fake serves them from memory for free)."""
        items = list(self._messages.values())
        if label is not None:
            items = [m for m in items if label in m.label_ids]
        if query is not None:
            q = query.lower()
            items = [
                m
                for m in items
                if q in m.subject.lower()
                or q in m.snippet.lower()
                or q in m.body_text.lower()
            ]
        page_items, next_token = self._page(items, page_token)
        return GmailListResult(
            items=page_items,
            next_page_token=next_token,
            result_size_estimate=len(items),
        )

    async def get_message(self, message_id: str) -> GmailMessage | None:
        """Return the stored message, or `None` when absent."""
        return self._messages.get(message_id)

    # ---- push-watch surface ---------------------------------------------

    async def watch(
        self,
        topic_name: str,
        label_ids: list[str] | None = None,
    ) -> WatchResult:
        """Record the watch; return the current history id and a
        deterministic expiration (`FAKE_NOW` + 7 days). Refuses a
        non-resource-name topic with the same `ValueError` the Real adapter
        raises before its API call."""
        validate_topic_name(topic_name)
        labels = tuple(label_ids if label_ids is not None else ["INBOX"])
        self.watches.append((topic_name, labels))
        self.active_watch = (topic_name, labels)
        return WatchResult(
            history_id=self.history_id,
            expiration=FAKE_NOW + timedelta(days=WATCH_MAX_LIFETIME_DAYS),
        )

    async def stop(self) -> None:
        """Clear the active watch (idempotent)."""
        self.stop_calls += 1
        self.active_watch = None

    async def list_history(
        self,
        start_history_id: str,
        history_types: list[str] | None = None,
        label_id: str | None = None,
    ) -> GmailHistoryResult:
        """`messageAdded` events with history id > `start_history_id`.
        Other history types are accepted and contribute nothing (the fake
        records additions only)."""
        start = int(start_history_id)
        if start < self._history_floor:
            raise GmailHistoryExpiredError(str(start_history_id))
        types = history_types if history_types is not None else ["messageAdded"]
        refs: list[GmailMessageRef] = []
        seen: set[str] = set()
        if "messageAdded" in types:
            for hid, mid in self._history:
                if hid <= start or mid in seen:
                    continue
                msg = self._messages.get(mid)
                if msg is None:
                    continue
                if label_id is not None and label_id not in msg.label_ids:
                    continue
                seen.add(mid)
                refs.append(
                    GmailMessageRef(
                        id=msg.id, thread_id=msg.thread_id, label_ids=msg.label_ids
                    )
                )
        return GmailHistoryResult(messages=refs, history_id=self.history_id)

    async def get_message_metadata(
        self,
        message_id: str,
        headers: list[str] | None = None,
    ) -> GmailMessageMetadata | None:
        """Serve the requested headers from the stored message's
        From/To/Subject plus any `add_fake_message(headers=...)` extras.
        Lookup is case-insensitive; absent headers map to ``""``."""
        msg = self._messages.get(message_id)
        if msg is None:
            return None
        available = {"from": msg.from_, "to": msg.to, "subject": msg.subject}
        for name, value in self._extra_headers.get(message_id, {}).items():
            available[name.lower()] = value
        wanted = list(headers) if headers is not None else list(REPLY_MATCH_HEADERS)
        return GmailMessageMetadata(
            id=msg.id,
            thread_id=msg.thread_id,
            label_ids=msg.label_ids,
            headers={name: available.get(name.lower(), "") for name in wanted},
            snippet=msg.snippet,
            received_at=msg.received_at,
        )


__all__ = ["FakeGmailClient"]
