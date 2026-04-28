"""
Webhook payload classification — LGPD-minimization layer.

Each `event_type` dispatched via `webhook_delivery.dispatch(...)` is mapped
to one of four classes that control what gets STORED in `webhook_deliveries`.
The HTTP POST to the endpoint always carries the full payload (that's what
the subscriber needs); the class only affects the persisted row.

Classes
-------
full          — store entire JSON payload. Retry supported.
redacted      — store payload with PII fields stripped. Retry works with reduced data.
hashed        — store SHA-256 of payload. Retry cannot reconstruct original.
metadata_only — store empty JSONB object. Retry fails loudly ("upgrade to full to enable").

Default policy (2026-04-24)
---------------------------
Every known event_type is classified `metadata_only`. This is the safest
LGPD posture — a 30-day retention window carrying no payload at all. To
enable retry for a specific event_type (e.g., a customer integration requires
replay), change its entry in WEBHOOK_EVENT_CLASSIFICATION to "full" and
document the reason inline.

Promotion rule
--------------
Elevate metadata_only → full when a concrete, documented consumer needs
retry. Never elevate preemptively. When 2+ events need elevation AND share
a redaction strategy, promote the shared strategy here rather than flipping
everything to "full".

Unknown event types
-------------------
Any event_type not in the registry is classified `metadata_only` by default
via `classify()`. This keeps LGPD-safety for new events added by forgetful
agents. A keeper-like detector could later enforce "every dispatched
event_type must be registered here" — not shipped today.
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Tuple

PayloadClass = Literal["full", "redacted", "hashed", "metadata_only"]


# Registry of known event_types → classification.
# Default-to-metadata_only per seed-core-consolidation §7.5 user directive.
WEBHOOK_EVENT_CLASSIFICATION: Dict[str, PayloadClass] = {
    # Team / identity events — carry PII (email, role)
    "team.invite_sent": "metadata_only",
    "team.member_removed": "metadata_only",

    # Subscription / licensing events — carry billing metadata
    "subscription.created": "metadata_only",
    "subscription.updated": "metadata_only",
    "license.granted": "metadata_only",
    "license.revoked": "metadata_only",

    # Stripe-forwarded events (via billing router) — carry billing metadata + IDs
    "checkout.session.completed": "metadata_only",
    "customer.subscription.updated": "metadata_only",
    "customer.subscription.deleted": "metadata_only",
    "invoice.payment_failed": "metadata_only",

    # Stripe "unknown" fallback in billing.py line 129 — classify to be safe
    "unknown": "metadata_only",
}


# Sentinel payload used when class == "metadata_only". The column is NOT NULL
# in schema; we store an empty JSONB object so the row exists but carries
# nothing. The `payload_class` column is the authoritative signal.
_METADATA_ONLY_PAYLOAD: Dict[str, Any] = {}


def classify(event_type: str) -> PayloadClass:
    """Return the classification for an event_type. Unknown events → 'metadata_only'."""
    return WEBHOOK_EVENT_CLASSIFICATION.get(event_type, "metadata_only")


def apply_classification(
    event_type: str, payload: Dict[str, Any]
) -> Tuple[Dict[str, Any], PayloadClass]:
    """Apply the class's transform to a payload. Returns (storable_payload, class).

    Today only `full` and `metadata_only` have concrete transforms. `redacted`
    and `hashed` are reserved in the type system for future events that need
    them — attempting to apply either today raises `NotImplementedError` so
    the gap is visible, not silent.
    """
    cls = classify(event_type)

    if cls == "full":
        return payload, cls

    if cls == "metadata_only":
        return dict(_METADATA_ONLY_PAYLOAD), cls

    if cls == "redacted":
        raise NotImplementedError(
            f"Redacted classification requested for {event_type!r} but no "
            f"redaction strategy is registered. Add one to "
            f"app/services/webhook_classification.py before using this class."
        )

    if cls == "hashed":
        raise NotImplementedError(
            f"Hashed classification requested for {event_type!r} but no "
            f"hashing strategy is registered. Add one to "
            f"app/services/webhook_classification.py before using this class."
        )

    # Defensive: classify() is typed Literal; this branch is unreachable.
    raise ValueError(f"Unknown payload class: {cls!r}")


class PayloadClassNotReplayable(Exception):
    """Raised when `retry_delivery` is called on a stored row whose payload
    class doesn't preserve enough data for a replay."""
