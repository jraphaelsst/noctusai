"""``AudienceService``: the subscriber lifecycle (double opt-in, unsubscribe, bounce, complaint).

Every state change appends an immutable event in the same call (EOA). Consent is recorded as a
timestamp + a free-text ``source`` (e.g. ``"site-footer-form"``); an IP address is NOT stored
(IP-free by default, LGPD data minimisation).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from .hashing import hash_email, normalize_email
from .store import AudienceStore
from .tokens import (
    CONFIRM_TTL_SECONDS,
    issue_confirm_token,
    issue_unsubscribe_token,
    one_click_headers,
    verify_confirm_token,
    verify_unsubscribe_token,
)
from .types import (
    EVENT_BOUNCED, EVENT_COMPLAINED, EVENT_CONFIRMED, EVENT_SUBSCRIBED, EVENT_UNSUBSCRIBED,
    REASON_BOUNCED, REASON_COMPLAINED, REASON_UNSUBSCRIBED,
    STATUS_BOUNCED, STATUS_COMPLAINED, STATUS_CONFIRMED, STATUS_PENDING, STATUS_UNSUBSCRIBED,
    InvalidSubscriptionToken, RecipientSuppressed, Subscriber,
)

OUTCOME_CONFIRMED = "confirmed"
OUTCOME_UNSUBSCRIBED = "unsubscribed"
OUTCOME_ALREADY = "already"


@dataclass(frozen=True)
class SubscribeResult:
    subscriber: Subscriber
    confirm_token: Optional[str]  # None when the address is already confirmed (nothing to confirm)
    created: bool


class AudienceService:
    def __init__(self, store: AudienceStore, secret: str, *,
                 confirm_ttl_seconds: int = CONFIRM_TTL_SECONDS, now: Callable[[], float] = time.time) -> None:
        if not secret:
            raise ValueError("AudienceService needs a signing secret (an empty one makes every token forgeable)")
        self._store = store
        self._secret = secret
        self._ttl = confirm_ttl_seconds
        self._now = now

    # -- suppression -----------------------------------------------------
    def is_suppressed(self, email: str) -> bool:
        return hash_email(email) in self._store.suppressed_among([hash_email(email)])

    def check_confirm_token(self, token: str) -> None:
        """Validity only (no state change); raises ``InvalidSubscriptionToken``."""
        verify_confirm_token(self._secret, token, now=self._now)

    def check_unsubscribe_token(self, token: str) -> None:
        verify_unsubscribe_token(self._secret, token, now=self._now)

    # -- subscribe / confirm --------------------------------------------
    def subscribe(self, email: str, *, source: str) -> SubscribeResult:
        """Start (or resume) a double opt-in. A suppressed address raises ``RecipientSuppressed``."""
        address = normalize_email(email)
        h = hash_email(address)
        if self._store.suppressed_among([h]):
            raise RecipientSuppressed((h,))
        existing = self._store.find_by_hash(h)
        if existing is not None:
            token = None
            if existing.status == STATUS_PENDING:
                token = issue_confirm_token(self._secret, existing.id, h, ttl_seconds=self._ttl, now=self._now)
            return SubscribeResult(existing, token, created=False)
        sub = self._store.add_subscriber(email=address, email_hash=h, status=STATUS_PENDING, consent_source=source)
        self._store.append_event(sub.id, EVENT_SUBSCRIBED, {"source": source})
        token = issue_confirm_token(self._secret, sub.id, h, ttl_seconds=self._ttl, now=self._now)
        return SubscribeResult(sub, token, created=True)

    def confirm(self, token: str) -> str:
        data = verify_confirm_token(self._secret, token, now=self._now)
        sub = self._store.get_subscriber(data["subscriber_id"])
        if sub is None or sub.email_hash != data["email_hash"]:
            raise InvalidSubscriptionToken("subscriber not found for this token")
        if sub.status == STATUS_CONFIRMED:
            return OUTCOME_ALREADY
        if sub.status != STATUS_PENDING or self._store.suppressed_among([sub.email_hash]):
            raise InvalidSubscriptionToken("this address can no longer be confirmed")
        self._store.update_subscriber(sub.id, status=STATUS_CONFIRMED, confirmed_at=self._utcnow())
        self._store.append_event(sub.id, EVENT_CONFIRMED)
        return OUTCOME_CONFIRMED

    # -- unsubscribe -----------------------------------------------------
    def unsubscribe(self, token: str) -> str:
        data = verify_unsubscribe_token(self._secret, token, now=self._now)
        h = data["email_hash"]
        already = bool(self._store.suppressed_among([h]))
        self._store.add_suppression(h, REASON_UNSUBSCRIBED, "unsubscribe-link")
        sub = self._store.get_subscriber(data["subscriber_id"])
        if sub is not None and sub.email_hash == h and sub.status != STATUS_UNSUBSCRIBED:
            self._store.update_subscriber(sub.id, status=STATUS_UNSUBSCRIBED, unsubscribed_at=self._utcnow())
            self._store.append_event(sub.id, EVENT_UNSUBSCRIBED)
            return OUTCOME_UNSUBSCRIBED
        return OUTCOME_ALREADY if already else OUTCOME_UNSUBSCRIBED

    # -- ESP feedback ----------------------------------------------------
    def record_bounce(self, email: str, *, source: str = "esp-webhook") -> None:
        self._record_feedback(email, REASON_BOUNCED, STATUS_BOUNCED, EVENT_BOUNCED, source)

    def record_complaint(self, email: str, *, source: str = "esp-webhook") -> None:
        self._record_feedback(email, REASON_COMPLAINED, STATUS_COMPLAINED, EVENT_COMPLAINED, source)

    def _record_feedback(self, email: str, reason: str, status: str, event: str, source: str) -> None:
        h = hash_email(email)
        self._store.add_suppression(h, reason, source)
        sub = self._store.find_by_hash(h)
        if sub is not None and sub.status != status:
            self._store.update_subscriber(sub.id, status=status)
            self._store.append_event(sub.id, event, {"source": source})

    # -- links + headers -------------------------------------------------
    def confirm_url(self, subscriber: Subscriber, url_prefix: str, *, token: Optional[str] = None) -> str:
        token = token or issue_confirm_token(self._secret, subscriber.id, subscriber.email_hash,
                                             ttl_seconds=self._ttl, now=self._now)
        return f"{url_prefix.rstrip('/')}/{token}"

    def unsubscribe_url(self, subscriber: Subscriber, url_prefix: str) -> str:
        token = issue_unsubscribe_token(self._secret, subscriber.id, subscriber.email_hash, now=self._now)
        return f"{url_prefix.rstrip('/')}/{token}"

    def unsubscribe_headers(self, subscriber: Subscriber, url_prefix: str, *,
                            mailto: Optional[str] = None, allow_http: bool = False) -> dict[str, str]:
        """The List-Unsubscribe + List-Unsubscribe-Post pair for this subscriber's e-mails."""
        return one_click_headers(self.unsubscribe_url(subscriber, url_prefix), mailto=mailto, allow_http=allow_http)

    def _utcnow(self) -> datetime:
        return datetime.fromtimestamp(self._now(), tz=timezone.utc)


__all__ = ["AudienceService", "SubscribeResult", "OUTCOME_CONFIRMED", "OUTCOME_UNSUBSCRIBED", "OUTCOME_ALREADY"]
