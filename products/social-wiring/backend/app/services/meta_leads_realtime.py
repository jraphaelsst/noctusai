"""Meta Lead-Ads ⇄ realtime bus wiring.

The sibling of ``whatsapp_realtime.py``, for a different live surface. The
seed's ``noctusai_lib.realtime`` knows only about opaque *scopes*; this module
is the single place that maps Meta lead ingestion onto that bus, so neither
the webhook receiver (write side) nor the leads router (read/stream side) has
to re-derive the scope key or re-spell the event name.

WHY A SECOND LIVE SURFACE, NOT A SECOND TRANSPORT
─────────────────────────────────────────────────
Slice 5b was originally specified against Supabase Realtime
(``postgres_changes``). It was suspended precisely so this decision could be
made once: the WhatsApp inbox landed an SSE-over-Redis-Stream bus in the seed,
and adding Supabase Realtime beside it would have forked the platform's
realtime story in two — two reconnect models, two auth models, two things to
debug when "it's not updating". This surface therefore sits on the existing
seed primitive. The seed module needed no change to accept it, which is the
evidence that its scope abstraction was drawn in the right place.

SCOPE IS PER-ORG, NOT PER-FORM OR PER-PAGE
──────────────────────────────────────────
A viewer of the leads list watches EVERY lead their org receives; there is no
narrower unit they subscribe to, and org is already the RLS boundary the leads
tables enforce. Scoping per form or per page would mean a client opening one
EventSource per form — browsers cap concurrent connections per origin, and it
would silently miss leads from a form created after the page loaded.

⚠️ N=2 DUPLICATION, TRIAGED
───────────────────────────
``_bus_cache`` + the fake-mode warning below are the second instance of the
shape in ``whatsapp_realtime.get_whatsapp_bus``. Per the recurrence rule that
is a triage point, not yet a mandatory formalization: the honest resolution is
a shared ``get_product_bus(redis_url, *, label)`` helper, and it is logged as a
codification candidate rather than done here — refactoring a peer's
just-landed module in the hour before a production promotion trades a real
deployment risk for a cosmetic one. The THIRD live surface must extract it.
"""
from __future__ import annotations

import logging
from typing import Any, Final
from uuid import UUID

from noctusai_lib.realtime import RealtimeBus, get_realtime_bus

logger = logging.getLogger(__name__)

# ── Event vocabulary ──────────────────────────────────────────────────────
# The frontend switches on these strings, and `EventSource` only delivers a
# named event to a listener registered for that exact name — so a typo on
# either side fails SILENTLY: no error, no frame, the UI just never updates.
# Naming them once here makes the contract greppable across both halves.
EVENT_LEAD_NEW: Final = "lead.new"

META_LEAD_EVENTS: Final = frozenset({EVENT_LEAD_NEW})

_bus_cache: dict[str, RealtimeBus] = {}


def meta_leads_scope(org_id: UUID | str) -> str:
    """Bus scope for one org's Meta lead stream."""
    return f"meta:leads:{org_id}"


def get_meta_leads_bus(redis_url: str | None) -> RealtimeBus:
    """Return the process-wide bus for a given Redis URL.

    Falls back to the seed's ``FakeRealtimeBus`` when ``redis_url`` is empty.

    ⚠️ The Fake is per-process. With more than one uvicorn worker an unset
    ``redis_url`` means a publish in worker A is invisible to a subscriber in
    worker B — the stream silently delivers nothing. Logged loudly at
    construction rather than left to be discovered in production.
    """
    key = redis_url or ""
    cached = _bus_cache.get(key)
    if cached is not None:
        return cached

    bus = get_realtime_bus(redis_url or None)
    if not redis_url:
        logger.warning(
            "Meta leads realtime bus running in FAKE (in-process) mode — no "
            "redis_url configured. Events do NOT cross process boundaries; "
            "with >1 worker, SSE subscribers will miss leads published by "
            "another worker."
        )
    _bus_cache[key] = bus
    return bus


def lead_event_payload(lead: dict[str, Any]) -> dict[str, Any]:
    """Project a ``meta_ads_leads`` row into the frame the browser receives.

    Deliberately a PROJECTION, not the row: ``raw`` and ``answers`` carry the
    full free-text form submission, which is lead PII with no purpose on the
    wire — the list UI renders name / contact / campaign / time and nothing
    else. Sending the whole row would broadcast every answer to every open
    tab on the org, including fields the list never shows.

    Consumers must treat this as a HINT, not the source of truth: the client
    prepends it optimistically, and any subsequent refetch replaces it with
    the authoritative row.
    """
    return {
        "id": lead.get("id"),
        "full_name": lead.get("full_name"),
        "email": lead.get("email"),
        "phone": lead.get("phone"),
        "form_id": lead.get("form_id"),
        "form_name": lead.get("form_name"),
        "campaign_name": lead.get("campaign_name"),
        "platform": lead.get("platform"),
        "created_time": lead.get("created_time"),
    }


async def publish_lead_event(
    bus: RealtimeBus,
    *,
    org_id: UUID | str,
    event: str,
    payload: dict[str, Any],
) -> str | None:
    """Publish one lead event, never letting a bus failure break ingest.

    Realtime is an ENHANCEMENT over a durable Postgres write that has already
    succeeded by the time we get here. If Redis is briefly unavailable the
    correct behaviour is to keep the 200 (a non-2xx makes Meta retry and can
    cost us the subscription entirely) and let the client's next reconnect
    replay from the stream or refetch from the DB.

    This is one of the few places swallowing is correct, so it is explicit,
    logged at exception level with the event name, and returns ``None`` so the
    caller can tell "published" from "degraded" — not a bare ``except: pass``.
    """
    if event not in META_LEAD_EVENTS:
        raise ValueError(
            f"unknown Meta lead realtime event {event!r}; "
            f"expected one of {sorted(META_LEAD_EVENTS)}"
        )
    try:
        return await bus.publish(meta_leads_scope(org_id), event, payload)
    except Exception:  # noqa: BLE001 — degrade realtime, never fail the write
        logger.exception(
            "realtime publish failed (org=%s event=%s) — the lead is already "
            "stored; clients will recover on reconnect/refetch",
            org_id, event,
        )
        return None


async def publish_new_lead(*, org_id: UUID | str, lead: dict[str, Any]) -> str | None:
    """The receiver-facing entry point: announce one freshly-ingested lead."""
    from app.config import settings

    bus = get_meta_leads_bus(getattr(settings, "redis_url", "") or "")
    return await publish_lead_event(
        bus, org_id=org_id, event=EVENT_LEAD_NEW, payload=lead_event_payload(lead)
    )
