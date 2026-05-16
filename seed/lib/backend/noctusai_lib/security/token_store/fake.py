"""In-memory `CredentialStore` for tests + FakeMode.

Deterministic, network-free, no encryption (the in-memory dict IS the
storage substrate — there is nothing at rest to protect). Mirrors the
Real adapter's UPSERT + fail-loud-on-missing semantics so a test that
passes against the Fake behaves identically against the Real, modulo
the encryption boundary (covered by `test_token_store.py` against the
Real with a Fernet key).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from noctusai_lib.security.token_store.types import (
    CredentialStore,
    StoredCredential,
)


class FakeCredentialStore(CredentialStore):
    """Process-memory credential store keyed by ``(org_id, provider)``."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], StoredCredential] = {}

    def get(self, org_id: str, provider: str) -> Optional[StoredCredential]:
        return self._rows.get((org_id, provider))

    def put(
        self,
        org_id: str,
        provider: str,
        tokens: dict,
        *,
        metadata: Optional[dict] = None,
    ) -> StoredCredential:
        now = datetime.now(timezone.utc)
        existing = self._rows.get((org_id, provider))
        created_at = existing.created_at if existing else now
        record = StoredCredential(
            org_id=org_id,
            provider=provider,
            tokens=dict(tokens),
            created_at=created_at,
            updated_at=now,
            metadata=dict(metadata or {}),
        )
        self._rows[(org_id, provider)] = record
        return record

    def delete(self, org_id: str, provider: str) -> bool:
        return self._rows.pop((org_id, provider), None) is not None

    def list_providers(self, org_id: str) -> list[str]:
        return sorted(
            provider for (oid, provider) in self._rows if oid == org_id
        )
