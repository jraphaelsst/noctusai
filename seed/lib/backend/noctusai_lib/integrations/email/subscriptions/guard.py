"""Suppression gate in front of every send: a suppressed recipient is REFUSED, never silently dropped."""
from __future__ import annotations

from typing import Iterable

from ..types import EmailSender, OutgoingEmail, SentEmail
from .hashing import hash_email
from .store import AudienceStore
from .types import RecipientSuppressed


def ensure_not_suppressed(store: AudienceStore, addresses: Iterable[str]) -> None:
    """Raise ``RecipientSuppressed`` (hashes only) if ANY address is on the suppression list."""
    hashes = [hash_email(a) for a in addresses]
    hit = store.suppressed_among(hashes)
    if hit:
        raise RecipientSuppressed(tuple(h for h in dict.fromkeys(hashes) if h in hit))


class SuppressionGuardedSender:
    """An ``EmailSender`` that checks to + cc + bcc against the suppression list before delegating.

    Wrap the real sender once at composition time so no code path can skip the check."""

    def __init__(self, inner: EmailSender, store: AudienceStore) -> None:
        self._inner = inner
        self._store = store

    async def send(self, email: OutgoingEmail) -> SentEmail:
        ensure_not_suppressed(self._store, [*email.to, *email.cc, *email.bcc])
        return await self._inner.send(email)


__all__ = ["ensure_not_suppressed", "SuppressionGuardedSender"]
