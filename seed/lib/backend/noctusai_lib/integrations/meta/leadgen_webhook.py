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


@dataclass(frozen=True)
class LeadgenUpdateEvent:
    """One `leadgen_update` change entry — Meta's AI-agent qualification feed.

    A DIFFERENT event class from :class:`LeadgenEvent`, not a variant of it:

    * `leadgen` says "a new lead was submitted" — an immutable fact, fired
      once, and the lead's PII must then be fetched from Graph.
    * `leadgen_update` says "an EXISTING lead's qualification changed" —
      mutable state that can fire many times for the same `leadgen_id` as
      Meta's AI agent talks to the person and revises its assessment.

    Conflating them would let a qualification change create a duplicate lead.

    🔴 UNDOCUMENTED BY META. Absent from the Page webhook reference and from
    every lead-ads guide; four searches across StackOverflow, GitHub and
    vendor blogs on 2026-08-04 found no substantive public description. This
    shape is taken from Meta's OWN "Teste" sample payload, captured from the
    App Dashboard on 2026-08-04 — i.e. from the wire, not from prose:

        {"field": "leadgen_update", "value": {
            "adgroup_id": 123456789, "ad_id": 123456789,
            "leadgen_id": 987654321, "page_id": 111111111,
            "form_id": 222222222, "updated_time": "1704067200",
            "area": "ai_agent_updates",
            "event": "qualification_status_change",
            "updated_fields": ["qualification_details", "qualification_status"]}}

    `area` reads as a namespace (`ai_agent_updates` is one, so others likely
    exist) and `event` as the specific change within it. Neither is treated
    as an enum here — an unrecognised pair is preserved and surfaced, never
    dropped, because the vocabulary is Meta's to extend and ours to discover.

    🔴 Note the id types: this sample carries **integers** where the
    `leadgen` sample carries **strings**. Meta is inconsistent with itself,
    so every id is coerced through :func:`_stringify` rather than trusted.

    `updated_fields` names WHICH fields changed — it does NOT carry their
    values. Reading the new qualification data requires a Graph call, the
    same indirection `leadgen` uses for PII.
    """

    leadgen_id: str
    page_id: str | None
    form_id: str | None
    ad_id: str | None
    adgroup_id: str | None
    updated_time: datetime | None
    area: str | None
    event: str | None
    updated_fields: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


def parse_leadgen_update_webhook(
    payload: dict[str, Any],
) -> list[LeadgenUpdateEvent]:
    """Parse `leadgen_update` changes out of a Page webhook delivery.

    Same contract as :func:`parse_leadgen_webhook`: iterates **every**
    `entry[]` × **every** `changes[]`, skips anything whose `field` is not
    `leadgen_update`, and returns `[]` rather than raising on any malformed
    shape — a signature-verified body must degrade to "no events", never
    crash a receiver that owes Meta a 200.

    Deliberately a SEPARATE function from `parse_leadgen_webhook` rather
    than a `field` parameter: the two produce different types with different
    downstream meaning, and a shared parser would invite a caller to treat a
    qualification change as a new lead.
    """

    if not isinstance(payload, dict) or payload.get("object") != "page":
        return []

    entries = payload.get("entry")
    if not isinstance(entries, list):
        return []

    events: list[LeadgenUpdateEvent] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            if change.get("field") != "leadgen_update":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            leadgen_id = _stringify(value.get("leadgen_id"))
            if not leadgen_id:
                # Without it we cannot say WHICH lead changed, so the event
                # is unusable. Dropping is correct; the receiver still has
                # the raw delivery recorded upstream.
                continue
            fields_raw = value.get("updated_fields")
            updated_fields = tuple(
                str(f) for f in fields_raw if f
            ) if isinstance(fields_raw, list) else ()
            events.append(
                LeadgenUpdateEvent(
                    leadgen_id=leadgen_id,
                    page_id=_stringify(value.get("page_id")),
                    form_id=_stringify(value.get("form_id")),
                    ad_id=_stringify(value.get("ad_id")),
                    adgroup_id=_stringify(value.get("adgroup_id")),
                    updated_time=_parse_unix_seconds(value.get("updated_time")),
                    area=_stringify(value.get("area")),
                    event=_stringify(value.get("event")),
                    updated_fields=updated_fields,
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
