"""Link an inbound message to a message WE sent — pure, no I/O.

A product that sends something (an orçamento, a proposal) and wants to
know when the recipient answered stores, per sent message, its RFC
`Message-ID` (and/or Gmail thread id). When the watch loop sees a new
inbound message it fetches `get_message_metadata(...)` and asks
`match_reply` which of our sent messages it answers.

**Precedence** (strongest evidence first):

1. `In-Reply-To` — the direct parent, set by every mainstream client.
2. `References` — the ancestor chain, scanned NEWEST-first (last token
   first), so a reply deep in a conversation links to the most recent
   of OUR messages it descends from.
3. Gmail thread id — fallback for clients that drop the headers. Gmail
   threads by subject + headers, so this is weaker; it only fires when
   the caller supplies `known_threads`.

**Getting our sent message's `Message-ID`.** `users.messages.send`
returns Gmail's opaque id + thread id, NOT the RFC header. Fetch it once
after sending — ``(await client.get_message_metadata(sent.message_id,
["Message-ID"])).headers["Message-ID"]`` — and persist it next to
`sent.thread_id`.

Message-ids are compared after stripping whitespace and the ``<>``
brackets; the local part is case-sensitive per RFC 5322 so case is kept,
the domain part is case-folded (domains are case-insensitive).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_MSGID_TOKEN = re.compile(r"<([^<>\s]+)>")


def normalize_message_id(value: str) -> str:
    """``" <Abc@Mail.Example.COM> "`` → ``"Abc@mail.example.com"``.

    Returns ``""`` for an empty/whitespace value."""
    raw = value.strip()
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1].strip()
    local, sep, domain = raw.rpartition("@")
    if not sep:
        return raw
    return f"{local}@{domain.lower()}"


def _header(headers: Mapping[str, str], name: str) -> str:
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value or ""
    return ""


def _ids_in(value: str) -> list[str]:
    """All message-ids in a header value, in order. Falls back to
    whitespace tokens when the value carries no bracketed ids (some
    clients emit bare ids)."""
    found = _MSGID_TOKEN.findall(value)
    tokens = found if found else value.split()
    return [n for n in (normalize_message_id(t) for t in tokens) if n]


def match_reply(
    message_headers: Mapping[str, str],
    known_message_ids: Iterable[str],
    *,
    thread_id: str | None = None,
    known_threads: Mapping[str, str] | None = None,
) -> str | None:
    """Return the entry of `known_message_ids` (verbatim, as the caller
    stored it) that `message_headers` replies to, else `None`.

    `message_headers` is looked up case-insensitively (e.g.
    `GmailMessageMetadata.headers`). `known_threads` maps a Gmail thread
    id → the known message-id to return for it; consulted only when the
    headers match nothing and `thread_id` is given.

    A message whose OWN `Message-ID` is a known id is our sent copy, not a
    reply — it never matches (the watch also reports our SENT messages)."""
    by_normal: dict[str, str] = {}
    for known in known_message_ids:
        normal = normalize_message_id(known)
        if normal:
            by_normal.setdefault(normal, known)

    own = normalize_message_id(_header(message_headers, "Message-ID"))
    if own and own in by_normal:
        return None

    for candidate in _ids_in(_header(message_headers, "In-Reply-To")):
        if candidate in by_normal:
            return by_normal[candidate]
    for candidate in reversed(_ids_in(_header(message_headers, "References"))):
        if candidate in by_normal:
            return by_normal[candidate]

    if thread_id and known_threads:
        return known_threads.get(thread_id)
    return None


__all__ = ["match_reply", "normalize_message_id"]
