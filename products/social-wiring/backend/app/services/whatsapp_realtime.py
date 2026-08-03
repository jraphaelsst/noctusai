"""WhatsApp inbox ⇄ realtime bus wiring.

The seed's `noctusai_lib.realtime` is deliberately provider-neutral: it knows
about opaque *scopes* and nothing about WhatsApp, connections, or auth. This
module is the single place that maps this product's domain onto that bus, so
neither the webhook (write side) nor the chat router (read/stream side) has to
re-derive the scope key or re-spell an event name.

ONE PROCESS, ONE REDIS CLIENT
-----------------------------
The fleet convention is one `redis.Redis` per process shared across the
chatbot buffer, the webhook dedup and now the bus. `get_whatsapp_bus` caches
per `redis_url` so importing it from two routers cannot open a second client
path — the exact drift the seed factory's docstring warns about.

WHY EVENT NAMES ARE CONSTANTS
-----------------------------
The frontend reducer switches on these strings. A typo on either side fails
silently — the event simply never matches, the cache never patches, and the UI
looks "not realtime" with nothing in the logs. Naming them once here makes the
contract greppable across both sides.
"""
from __future__ import annotations

import logging
from typing import Any, Final
from uuid import UUID

from noctusai_lib.realtime import RealtimeBus, get_realtime_bus

logger = logging.getLogger(__name__)

# ── Event vocabulary (mirrors the contract appendix; a change here is a
#    contract bump that the FE reducer must land in the same breath) ────────
EVENT_MESSAGE_NEW: Final = "message.new"
EVENT_MESSAGE_ACK: Final = "message.ack"
EVENT_CHAT_READ: Final = "chat.read"
EVENT_CHAT_UPSERT: Final = "chat.upsert"
EVENT_SESSION_STATUS: Final = "session.status"

WHATSAPP_EVENTS: Final = frozenset(
    {
        EVENT_MESSAGE_NEW,
        EVENT_MESSAGE_ACK,
        EVENT_CHAT_READ,
        EVENT_CHAT_UPSERT,
        EVENT_SESSION_STATUS,
    }
)

_bus_cache: dict[str, RealtimeBus] = {}


def whatsapp_scope(connection_id: UUID | str) -> str:
    """Bus scope for one WhatsApp line.

    Scoped per CONNECTION, not per org: a connection is the smallest unit a
    viewer subscribes to, and it is already the authorization boundary every
    other live op uses (`_require_record` filters by org_id + user_id). Scoping
    wider would leak another line's traffic to a subscriber who is authorized
    for neither.
    """
    return f"wa:conn:{connection_id}"


def get_whatsapp_bus(redis_url: str | None) -> RealtimeBus:
    """Return the process-wide bus for a given Redis URL.

    Falls back to the seed's `FakeRealtimeBus` when `redis_url` is empty — the
    configured-vs-not factory shape. That fallback is real, not a stub: it
    keeps tests and single-process dev working with identical semantics, which
    is why the Fake ships with full parity.

    ⚠️ The Fake is per-process. With more than one uvicorn worker an unset
    `redis_url` means a publish in worker A is invisible to a subscriber in
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
            "WhatsApp realtime bus running in FAKE (in-process) mode — no "
            "redis_url configured. Events do NOT cross process boundaries; "
            "with >1 worker, SSE subscribers will miss messages published by "
            "another worker."
        )
    _bus_cache[key] = bus
    return bus


async def publish_whatsapp_event(
    bus: RealtimeBus,
    *,
    connection_id: UUID | str,
    event: str,
    payload: dict[str, Any],
) -> str | None:
    """Publish one inbox event, never letting a bus failure break ingest.

    Realtime is an ENHANCEMENT over a durable Postgres write that has already
    succeeded by the time we get here. If Redis is briefly unavailable the
    correct behaviour is to keep accepting the webhook (returning non-200 makes
    WAHA retry forever) and let the client's next reconnect replay from the
    stream or refetch from the DB.

    This is the one place that swallowing is correct, so it is explicit,
    logged at exception level with the event name, and returns `None` so the
    caller can tell "published" from "degraded" — not a bare `except: pass`.
    """
    if event not in WHATSAPP_EVENTS:
        raise ValueError(
            f"unknown WhatsApp realtime event {event!r}; "
            f"expected one of {sorted(WHATSAPP_EVENTS)}"
        )
    try:
        return await bus.publish(whatsapp_scope(connection_id), event, payload)
    except Exception:  # noqa: BLE001 — degrade realtime, never fail the write
        logger.exception(
            "realtime publish failed (connection=%s event=%s) — the DB write "
            "already succeeded; clients will recover on reconnect/refetch",
            connection_id,
            event,
        )
        return None


def reset_bus_cache() -> None:
    """Test seam — drop cached buses between tests so a Fake from one test
    cannot leak state into the next."""
    _bus_cache.clear()
