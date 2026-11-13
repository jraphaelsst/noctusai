"""Supabase real ``AudienceStore``: bare table names on a client already pinned to the product schema."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from .types import Subscriber, SubscriberEvent

SUBSCRIBERS = "subscribers"
SUPPRESSION = "suppression"
EVENTS = "subscriber_events"
_BATCH = 200


def _dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _sub(row: dict) -> Subscriber:
    return Subscriber(
        id=str(row["id"]), email=row["email"], email_hash=row["email_hash"], status=row["status"],
        consent_source=row.get("consent_source") or "", consent_at=_dt(row.get("consent_at")),
        confirmed_at=_dt(row.get("confirmed_at")), unsubscribed_at=_dt(row.get("unsubscribed_at")),
        created_at=_dt(row.get("created_at")),
    )


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


class SupabaseAudienceStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    @staticmethod
    def _rows(response: Any) -> list[dict]:
        return list(getattr(response, "data", None) or [])

    def add_subscriber(self, *, email, email_hash, status, consent_source):
        rows = self._rows(self._client.table(SUBSCRIBERS).insert(
            {"email": email, "email_hash": email_hash, "status": status, "consent_source": consent_source}).execute())
        if not rows:
            raise RuntimeError("insert into subscribers returned no row")
        return _sub(rows[0])

    def get_subscriber(self, subscriber_id):
        rows = self._rows(self._client.table(SUBSCRIBERS).select("*").eq("id", subscriber_id).limit(1).execute())
        return _sub(rows[0]) if rows else None

    def find_by_hash(self, email_hash):
        rows = self._rows(self._client.table(SUBSCRIBERS).select("*").eq("email_hash", email_hash).limit(1).execute())
        return _sub(rows[0]) if rows else None

    def update_subscriber(self, subscriber_id, **fields):
        rows = self._rows(self._client.table(SUBSCRIBERS).update({k: _iso(v) for k, v in fields.items()})
                          .eq("id", subscriber_id).execute())
        return _sub(rows[0]) if rows else None

    def add_suppression(self, email_hash, reason, source=""):
        # ignore_duplicates: idempotent, the first reason wins (never rewrites history).
        self._client.table(SUPPRESSION).upsert(
            {"email_hash": email_hash, "reason": reason, "source": source},
            on_conflict="email_hash", ignore_duplicates=True).execute()

    def suppressed_among(self, email_hashes: Iterable[str]) -> set[str]:
        hashes = list(dict.fromkeys(email_hashes))
        found: set[str] = set()
        for i in range(0, len(hashes), _BATCH):
            chunk = hashes[i:i + _BATCH]
            found.update(r["email_hash"] for r in self._rows(
                self._client.table(SUPPRESSION).select("email_hash").in_("email_hash", chunk).execute()))
        return found

    def append_event(self, subscriber_id, kind, detail=None):
        rows = self._rows(self._client.table(EVENTS).insert(
            {"subscriber_id": subscriber_id, "kind": kind, "detail": dict(detail or {})}).execute())
        row = rows[0] if rows else {}
        return SubscriberEvent(subscriber_id=subscriber_id, kind=kind, occurred_at=_dt(row.get("occurred_at")),
                               detail=dict(detail or {}))

    def list_events(self, subscriber_id):
        rows = self._rows(self._client.table(EVENTS).select("*").eq("subscriber_id", subscriber_id)
                          .order("occurred_at").execute())
        return [SubscriberEvent(subscriber_id=str(r["subscriber_id"]), kind=r["kind"],
                                occurred_at=_dt(r.get("occurred_at")), detail=r.get("detail") or {}) for r in rows]


__all__ = ["SupabaseAudienceStore"]
