"""Meta Lead-Ads webhook parsing — pure functions, zero IO.

Meta's Lead-Ads webhook delivers ONLY a `leadgen_id` per submitted
lead — never the lead's actual answers (PII). A receiver parses the
delivery via `parse_leadgen_webhook`, then calls back to Graph
(`MetaAdapter.get_lead(leadgen_id)`) to fetch the real record. This
module is the parsing half only — no FastAPI, no network, no
adapter dependency, so it is trivially unit-testable and reusable by
any product's webhook router.

Sibling of the app-level webhook-verification handshake
(`leadgen_challenge_response`) Meta's `GET /webhooks` callback uses
during subscription setup — distinct from the `POST /webhooks`
delivery `parse_leadgen_webhook` parses.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class LeadgenEvent:
    """One `leadgen` change entry from a Lead-Ads webhook delivery.

    `raw` is the `value` object verbatim (lossless — the product
    persists it as-received alongside the typed fields, since Meta may
    carry additional fields this dataclass doesn't name). `created_time`
    is Meta's unix-seconds timestamp, parsed to a tz-aware UTC
    `datetime`; `None` when absent or unparseable — never guessed."""

    leadgen_id: str
    page_id: str | None
    form_id: str | None
    ad_id: str | None
    adgroup_id: str | None
    created_time: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


def _stringify(value: Any) -> str | None:
    """`None`/falsy → `None`; else the string form. Meta's webhook
    payload mixes numeric-looking strings and (rarely) raw numbers
    across fields — callers get a stable `str | None`, never a stray
    `int`."""

    if not value:
        return None
    return str(value)


def _parse_unix_seconds(value: Any) -> datetime | None:
    """Unix seconds (int/float/numeric-string) → aware UTC `datetime`.
    `None` on anything missing or unparseable — never raises, never
    guesses (the webhook body is untrusted input)."""

    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def parse_leadgen_webhook(payload: dict[str, Any]) -> list[LeadgenEvent]:
    """Parse a Meta Lead-Ads webhook `POST` body into `LeadgenEvent`s.

    Iterates **every** `entry[]` × **every** `changes[]` — Meta batches
    multiple entries/changes into a single delivery, and the anti-shape
    to avoid is reading only `entry[0].changes[0]`
    (`products/erp-imobiliario/backend/app/services/meta_api_service.py:139`),
    which silently drops the rest of a batched delivery. Skips any
    change whose `field != "leadgen"` and any whose `value.leadgen_id`
    is falsy. Returns `[]` (never raises) when `payload.get("object")
    != "page"`, or when `entry`/`changes` are missing or not lists —
    a malformed-but-signature-verified body must degrade to "no
    events", not crash the receiver."""

    if not isinstance(payload, dict) or payload.get("object") != "page":
        return []

    entries = payload.get("entry")
    if not isinstance(entries, list):
        return []

    events: list[LeadgenEvent] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "leadgen":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            leadgen_id = value.get("leadgen_id")
            if not leadgen_id:
                continue
            events.append(
                LeadgenEvent(
                    leadgen_id=str(leadgen_id),
                    page_id=_stringify(value.get("page_id")),
                    form_id=_stringify(value.get("form_id")),
                    ad_id=_stringify(value.get("ad_id")),
                    adgroup_id=_stringify(value.get("adgroup_id")),
                    created_time=_parse_unix_seconds(value.get("created_time")),
                    raw=dict(value),
                )
            )
    return events


def leadgen_challenge_response(
    *,
    mode: str | None,
    verify_token: str | None,
    challenge: str | None,
    expected_token: str | None,
) -> str | None:
    """Meta's webhook-verification handshake (`GET /webhooks` with
    `hub.mode` / `hub.verify_token` / `hub.challenge` query params).

    Returns `challenge` iff `mode == "subscribe"` AND `expected_token`
    is configured (non-empty) AND `verify_token` matches it. The
    compare is constant-time (`hmac.compare_digest`) — this is a
    public, unauthenticated endpoint guarding a shared secret, and a
    variable-time `==` would leak the token one byte at a time through
    response-time measurement. Returns `None` on any mismatch (wrong
    mode, unconfigured/empty expected token, or a token mismatch) —
    never raises."""

    if mode != "subscribe":
        return None
    if not expected_token:
        return None
    if not verify_token:
        return None
    if not hmac.compare_digest(str(verify_token), str(expected_token)):
        return None
    return challenge


__all__ = [
    "LeadgenEvent",
    "leadgen_challenge_response",
    "parse_leadgen_webhook",
]
