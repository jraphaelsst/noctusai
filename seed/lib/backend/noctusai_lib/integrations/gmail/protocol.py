"""Gmail API v1 client Protocol.

Gmail's quota model differs from YouTube's: there is no daily
"unit" budget per call — instead a **per-user rate limit of 250
quota units / user / second** (a moving-average burst budget) and a
**1,000,000,000 units / day project ceiling**. The per-method unit
costs (documented per-method below) matter for *burst* sizing, not a
daily countdown like YouTube. Consumers reading this surface size
their batch loops against the 250/user/sec ceiling.

Scopes (all are Google *restricted* scopes → require App Review for
production verification — see `types.GMAIL_*_SCOPE`):
- `send_message` → `gmail.send`.
- `list_messages` / `get_message` → `gmail.readonly`.

The Protocol's docstrings document the per-method unit cost + the
scope so any consumer reading the surface budgets and requests
consent correctly.
"""

from __future__ import annotations

from typing import Protocol

from noctusai_lib.integrations.gmail.types import (
    GmailListResult,
    GmailMessage,
    SendResult,
)


class GmailClient(Protocol):
    """Gmail API v1 client contract.

    Two concrete implementations ship in the seed:
    - `FakeGmailClient` — deterministic in-memory dev/test default.
      Records every send on `.sent`; `add_fake_message(...)` seeds
      the inbox; pages with a small `PAGE_SIZE` for testable paging.
    - `RealGmailClient` — wraps
      `googleapiclient.discovery.build("gmail", "v1", ...)`. Logs API
      errors at WARN level before re-raising. **OAuth-only** — Gmail
      has no API-key path for a user mailbox; constructing a Real
      client without OAuth credentials raises `ValueError`.

    Build via `make_gmail_client(...)`. The factory routes on the
    `use_fake` flag and on credential presence — see `factory.py`.

    **Quota cost (Gmail per-user budget = 250 units / user / second):**

    | Method | Cost | Notes |
    |---|---|---|
    | `send_message` | **100** | `users.messages.send`. Requires `gmail.send`. |
    | `list_messages` | **5** | `users.messages.list` (one page; ids + thread ids only). Requires `gmail.readonly`. |
    | `get_message` | **5** | `users.messages.get?format=full`. Requires `gmail.readonly`. |

    A naive "list then get each" loop costs ``5 + 5·N`` — at the
    250/user/sec ceiling that is ~50 messages/second of hydration;
    batch and back off accordingly."""

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
        """Send an email from the authenticated user's mailbox.

        **Quota cost: 100 units.** **Requires the `gmail.send` scope**
        (`types.GMAIL_SEND_SCOPE`) — a `gmail.readonly`-only credential
        cannot send; the Real adapter surfaces the API's 403 verbatim
        (logged at WARN) rather than swallowing it.

        Args:
            to: `To:` header. One or more comma-separated addresses.
            subject: `Subject:` header. **Truncated to
                `SUBJECT_MAX_LEN` (998)** by the adapter — RFC 5322
                rejects longer single header lines.
            body_text: `text/plain` body. Always sent (a plain part
                is the safe baseline for every client).
            body_html: optional `text/html` body. When supplied the
                message is built `multipart/alternative` (plain +
                html); `None` → plain-only.
            cc: optional `Cc:` header (comma-separated). `None` → no Cc.
            bcc: optional `Bcc:` header (comma-separated). `None` → no
                Bcc. Bcc recipients are NOT written into the visible
                headers — they go on the envelope only.

        Returns a `SendResult` with the new `message_id` + `thread_id`."""
        ...

    async def list_messages(
        self,
        *,
        query: str | None = None,
        label: str | None = None,
        page_token: str | None = None,
    ) -> GmailListResult[GmailMessage]:
        """List messages in the authenticated user's mailbox.

        **Quota cost: 5 units per page.** **Requires the
        `gmail.readonly` scope** (`types.GMAIL_READONLY_SCOPE`).

        Note: Gmail's `users.messages.list` returns only message ids +
        thread ids — NOT full message bodies. To keep the contract
        useful (a `GmailMessage`, not a bare id), both adapters hydrate
        each listed id via `get_message` (the Real adapter pays the
        extra 5 units / message; the Fake serves from memory for free).
        For large mailboxes prefer a tighter `query` to bound the page.

        Args:
            query: Gmail search syntax (e.g. ``"is:unread from:foo@x"``)
                or `None` for no filter.
            label: restrict to a single label id (e.g. ``"INBOX"``,
                ``"SENT"``). `None` → all mail.
            page_token: opaque `nextPageToken` from a prior page;
                `None` for the first page.

        Returns a `GmailListResult[GmailMessage]`; `next_page_token`
        is `None` on the last page."""
        ...

    async def get_message(self, message_id: str) -> GmailMessage | None:
        """Fetch a single message by id, fully hydrated.

        **Quota cost: 5 units** (`users.messages.get?format=full`).
        **Requires the `gmail.readonly` scope.**

        Returns `None` when the message doesn't exist or was deleted."""
        ...


__all__ = ["GmailClient"]
