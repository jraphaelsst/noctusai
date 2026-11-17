"""The audience store Protocol + the in-memory Fake (parity tested against the Supabase real)."""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable, Optional, Protocol, runtime_checkable

from .types import Subscriber, SubscriberEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


@runtime_checkable
class AudienceStore(Protocol):
    """Per-product-schema storage of subscribers, the HASHED suppression list and the append-only events."""

    def add_subscriber(self, *, email: str, email_hash: str, status: str, consent_source: str) -> Subscriber: ...
    def get_subscriber(self, subscriber_id: str) -> Optional[Subscriber]: ...
    def find_by_hash(self, email_hash: str) -> Optional[Subscriber]: ...
    def update_subscriber(self, subscriber_id: str, **fields) -> Optional[Subscriber]: ...
    def add_suppression(self, email_hash: str, reason: str, source: str = "") -> None: ...
    def suppressed_among(self, email_hashes: Iterable[str]) -> set[str]: ...
    def append_event(self, subscriber_id: str, kind: str, detail: Optional[dict] = None) -> SubscriberEvent: ...
    def list_events(self, subscriber_id: str) -> list[SubscriberEvent]: ...


class FakeAudienceStore:
    def __init__(self) -> None:
        self._subs: dict[str, Subscriber] = {}
        self._suppression: dict[str, dict] = {}
        self._events: list[SubscriberEvent] = []

    def add_subscriber(self, *, email, email_hash, status, consent_source):
        if self.find_by_hash(email_hash):
            raise ValueError("subscriber already exists")  # parity with UNIQUE(email_hash)
        now = _now()
        sub = Subscriber(id=str(uuid.uuid4()), email=email, email_hash=email_hash, status=status,
                         consent_source=consent_source, consent_at=now, created_at=now)
        self._subs[sub.id] = sub
        return replace(sub)

    def get_subscriber(self, subscriber_id):
        sub = self._subs.get(subscriber_id)
        return replace(sub) if sub else None

    def find_by_hash(self, email_hash):
        for sub in self._subs.values():
            if sub.email_hash == email_hash:
                return replace(sub)
        return None

    def update_subscriber(self, subscriber_id, **fields):
        sub = self._subs.get(subscriber_id)
        if not sub:
            return None
        self._subs[subscriber_id] = replace(sub, **fields)
        return replace(self._subs[subscriber_id])

    def add_suppression(self, email_hash, reason, source=""):
        self._suppression.setdefault(email_hash, {"reason": reason, "source": source})  # idempotent: first reason wins

    def suppressed_among(self, email_hashes):
        return {h for h in email_hashes if h in self._suppression}

    def append_event(self, subscriber_id, kind, detail=None):
        event = SubscriberEvent(subscriber_id=subscriber_id, kind=kind, occurred_at=_now(), detail=dict(detail or {}))
        self._events.append(event)
        return event

    def list_events(self, subscriber_id):
        return [e for e in self._events if e.subscriber_id == subscriber_id]


__all__ = ["AudienceStore", "FakeAudienceStore"]
