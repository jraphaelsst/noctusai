"""Value objects + Protocol for the per-(org, provider) credential store.

The store persists OAuth/token bundles encrypted-at-rest, one row per
``(org_id, provider)`` tuple. It is the canonical persistence layer for
every OAuth-using product: pair it with
`noctusai_lib.security.oauth.oauth_router`'s ``on_callback`` hook to write
the exchanged tokens, and read them back inside each integration adapter.

WHY a seam (Protocol + Fake + Real + factory)
---------------------------------------------
This module touches IO (Postgres rows via Supabase) — per
`KB § PATTERNS/seed-fake-real-adapter.md` it ships in the canonical
Protocol+Fake+Real+factory shape. A Fake here exercises genuinely
different code than the Real (in-memory dict vs. encrypted Supabase
UPSERT), so it is NOT crypto-exempt the way `encrypted_tokens` is — the
crypto *primitive* is exempt; the *persistence layer that composes it*
is a real IO seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol


@dataclass(frozen=True)
class StoredCredential:
    """A decrypted credential bundle for one ``(org_id, provider)`` pair.

    ``tokens`` is the provider-shaped JSON bundle the consumer wrote
    (e.g. ``{"access_token": ..., "refresh_token": ..., "scope": ...}``).
    The store is bundle-agnostic — it encrypts the JSON blob as opaque
    text and never inspects its keys. Consumers own the bundle schema.
    """

    org_id: str
    provider: str
    tokens: dict
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


class CredentialStore(Protocol):
    """Per-(org, provider) encrypted credential persistence.

    Contract (every implementation MUST honor this exactly — concurrent
    engineers + Wave 2/3 consumers depend on these signatures):

    - ``get(org_id, provider)`` → ``StoredCredential`` or ``None``.
      Decrypts on read. Raises ``CredentialDecryptError`` (NOT ``None``,
      NOT a silent empty bundle) when a row exists but cannot be
      decrypted with the configured key — fail-loud on key mismatch.
    - ``put(org_id, provider, tokens, *, metadata=None)`` →
      ``StoredCredential``. UPSERT semantics on the
      ``(org_id, provider)`` natural key: a second call for the same
      pair overwrites (re-consent path). Encrypts before write.
      ``metadata`` is an OPTIONAL small non-secret dict stored
      plaintext (e.g. ``{"auth_mode": "system_user"}``) — never put
      secrets here.
    - ``delete(org_id, provider)`` → ``bool``. True if a row existed and
      was removed, False if nothing was there (idempotent).
    - ``list_providers(org_id)`` → ``list[str]``. Providers this org has
      stored credentials for. Does NOT decrypt (cheap; for status UIs).
    """

    def get(self, org_id: str, provider: str) -> Optional[StoredCredential]: ...

    def put(
        self,
        org_id: str,
        provider: str,
        tokens: dict,
        *,
        metadata: Optional[dict] = None,
    ) -> StoredCredential: ...

    def delete(self, org_id: str, provider: str) -> bool: ...

    def list_providers(self, org_id: str) -> list[str]: ...


class CredentialDecryptError(RuntimeError):
    """Raised when a stored row exists but cannot be decrypted.

    Signals a key mismatch / rotation gap / tampered ciphertext. The
    store NEVER returns ``None`` or an empty bundle in this case — a
    silent empty credential would make every downstream adapter fail
    obscurely far from the root cause. Fail loud, here.
    """
