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
"""

from __future__ import annotations

from datetime import datetime, timezone

from noctusai_lib.integrations.gmail.types import (
    SUBJECT_MAX_LEN,
    GmailMessage,
    GmailListResult,
    SendResult,
)


class FakeGmailClient:
    """Deterministic in-memory `GmailClient` implementation.

    Messages page in insertion order. `send_message` is deterministic:
    ids are ``fake-sent-1``, ``fake-sent-2``, … in call order, each in
    its own thread ``fake-thread-1``, … ."""

    PAGE_SIZE: int = 2

    def __init__(
        self,
        messages: list[GmailMessage] | None = None,
    ) -> None:
        # Preserve insertion order; dedup by id keeping last.
        self._messages: dict[str, GmailMessage] = {}
        for msg in messages or []:
            self._messages[msg.id] = msg
        self.sent: list[GmailMessage] = []
        """Every `send_message` call appends the sent `GmailMessage`
        here, in order — tests assert against it directly."""
        self._send_seq: int = 0

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
    ) -> GmailMessage:
        """Seed a message into the fake inbox; returns the stored
        `GmailMessage` (also retrievable via `get_message`)."""
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
        self._messages[message_id] = msg
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
        self._messages[message_id] = sent
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


__all__ = ["FakeGmailClient"]
