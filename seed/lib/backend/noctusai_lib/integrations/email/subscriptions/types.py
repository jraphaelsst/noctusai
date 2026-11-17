"""Value objects, closed vocabularies and typed errors of the e-mail audience mechanism."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..errors import EmailError

#: Subscriber lifecycle states (the CHECK enum of ``subscribers.status``).
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_UNSUBSCRIBED = "unsubscribed"
STATUS_BOUNCED = "bounced"
STATUS_COMPLAINED = "complained"
STATUSES = (STATUS_PENDING, STATUS_CONFIRMED, STATUS_UNSUBSCRIBED, STATUS_BOUNCED, STATUS_COMPLAINED)

#: Append-only lifecycle event kinds (the CHECK enum of ``subscriber_events.kind``).
EVENT_SUBSCRIBED = "subscribed"
EVENT_CONFIRMED = "confirmed"
EVENT_UNSUBSCRIBED = "unsubscribed"
EVENT_BOUNCED = "bounced"
EVENT_COMPLAINED = "complained"
EVENT_KINDS = (EVENT_SUBSCRIBED, EVENT_CONFIRMED, EVENT_UNSUBSCRIBED, EVENT_BOUNCED, EVENT_COMPLAINED)

#: Why an address is on the suppression list (CHECK enum of ``suppression.reason``).
REASON_UNSUBSCRIBED = "unsubscribed"
REASON_BOUNCED = "bounced"
REASON_COMPLAINED = "complained"
SUPPRESSION_REASONS = (REASON_UNSUBSCRIBED, REASON_BOUNCED, REASON_COMPLAINED)


class SubscriptionError(EmailError):
    """Base for audience-mechanism failures."""


class RecipientSuppressed(SubscriptionError):
    """A send (or a re-subscribe) targeted an address on the suppression list.

    Typed and loud on purpose: a suppressed send is never silently dropped, the
    caller must see it. Carries only the HASHES, never the addresses."""

    def __init__(self, hashes: tuple[str, ...]):
        self.hashes = tuple(hashes)
        super().__init__(f"{len(self.hashes)} recipient(s) on the suppression list; send refused")


class InvalidSubscriptionToken(SubscriptionError):
    """Tampered, expired, wrong-purpose or malformed token (the router answers 400)."""


class InvalidEmailAddress(SubscriptionError):
    """The address does not look like an e-mail address."""


@dataclass
class Subscriber:
    id: str
    email: str
    email_hash: str
    status: str = STATUS_PENDING
    consent_source: str = ""
    consent_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    unsubscribed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class SubscriberEvent:
    subscriber_id: str
    kind: str
    occurred_at: Optional[datetime] = None
    detail: dict = field(default_factory=dict)


__all__ = [
    "STATUS_PENDING", "STATUS_CONFIRMED", "STATUS_UNSUBSCRIBED", "STATUS_BOUNCED", "STATUS_COMPLAINED", "STATUSES",
    "EVENT_SUBSCRIBED", "EVENT_CONFIRMED", "EVENT_UNSUBSCRIBED", "EVENT_BOUNCED", "EVENT_COMPLAINED", "EVENT_KINDS",
    "REASON_UNSUBSCRIBED", "REASON_BOUNCED", "REASON_COMPLAINED", "SUPPRESSION_REASONS",
    "SubscriptionError", "RecipientSuppressed", "InvalidSubscriptionToken", "InvalidEmailAddress",
    "Subscriber", "SubscriberEvent",
]
