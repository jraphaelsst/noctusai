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
    """Process-memory credential store keyed by ``(org_id, provider)``.

    Mirrors `SupabaseCredentialStore`'s ``metadata_column`` /
    ``metadata_columns`` semantics so a test that round-trips metadata
    through discrete columns behaves identically against Fake and Real.
    Because the substrate is an in-memory ``StoredCredential`` (not a
    physical row), the mapping is exercised by *simulating* the
    flatten-on-write / inflate-on-read split: an unmapped key when
    ``metadata_column is None`` raises ``ValueError`` exactly like the
    Real adapter (fail-loud parity).
    """

    def __init__(
        self,
        *,
        metadata_column: Optional[str] = "metadata",
        metadata_columns: Optional[dict] = None,
    ) -> None:
        self._rows: dict[tuple[str, str], StoredCredential] = {}
        self._metadata_column = metadata_column
        self._metadata_columns = dict(metadata_columns or {})

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
        meta = dict(metadata or {})
        # Parity with the Real adapter: an unmapped metadata key with no
        # JSON metadata column has no destination — fail loud, do not
        # silently drop it.
        if self._metadata_column is None:
            unmapped = [k for k in meta if k not in self._metadata_columns]
            if unmapped:
                raise ValueError(
                    "token_store: metadata keys "
                    f"{sorted(unmapped)} have no destination — metadata_column "
                    "is None and they are not in metadata_columns; either map "
                    "them or configure a metadata_column"
                )
        existing = self._rows.get((org_id, provider))
        created_at = existing.created_at if existing else now
        record = StoredCredential(
            org_id=org_id,
            provider=provider,
            tokens=dict(tokens),
            created_at=created_at,
            updated_at=now,
            metadata=meta,
        )
        self._rows[(org_id, provider)] = record
        return record

    def delete(self, org_id: str, provider: str) -> bool:
        return self._rows.pop((org_id, provider), None) is not None

    def list_providers(self, org_id: str) -> list[str]:
        return sorted(
            provider for (oid, provider) in self._rows if oid == org_id
        )
