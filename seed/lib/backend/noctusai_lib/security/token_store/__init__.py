"""Per-(org, provider) encrypted credential store — Protocol+Fake+Real+factory.

THE seam OAuth-using products + integration adapters depend on. Pair
with `noctusai_lib.security.oauth.oauth_router`'s ``on_callback`` to
persist exchanged tokens, and read them back in each adapter.

Public surface (the contract concurrent engineers + Wave 2/3 depend on)
-----------------------------------------------------------------------
- ``StoredCredential`` — decrypted bundle value object
  (``org_id, provider, tokens, created_at, updated_at, metadata``).
- ``CredentialStore`` — the 4-method Protocol
  (``get / put / delete / list_providers``).
- ``CredentialDecryptError`` — raised on key mismatch (fail-loud; never
  a silent ``None``).
- ``FakeCredentialStore`` — in-memory; tests + FakeMode.
- ``SupabaseCredentialStore`` — Fernet-encrypted Supabase rows.
- ``make_credential_store(client=, fernet_key=, table=)`` — factory.
  Returns ``SupabaseCredentialStore`` when BOTH ``client`` and
  ``fernet_key`` are provided; otherwise ``FakeCredentialStore``
  (default-Fake mirrors `google_maps` / `google_calendar`).

Method contract (exact — do not drift):
- ``get(org_id, provider) -> StoredCredential | None`` — decrypt-on-read.
- ``put(org_id, provider, tokens, *, metadata=None) -> StoredCredential``
  — UPSERT on ``(org_id, provider)``; encrypt-before-write.
- ``delete(org_id, provider) -> bool`` — idempotent.
- ``list_providers(org_id) -> list[str]`` — no decrypt.
"""

from __future__ import annotations

from typing import Optional

from noctusai_lib.security.token_store.fake import FakeCredentialStore
from noctusai_lib.security.token_store.supabase_store import (
    DEFAULT_TABLE,
    SupabaseCredentialStore,
)
from noctusai_lib.security.token_store.types import (
    CredentialDecryptError,
    CredentialStore,
    StoredCredential,
)

__all__ = [
    "CredentialDecryptError",
    "CredentialStore",
    "DEFAULT_TABLE",
    "FakeCredentialStore",
    "StoredCredential",
    "SupabaseCredentialStore",
    "make_credential_store",
]


def make_credential_store(
    *,
    client=None,
    fernet_key: Optional[bytes] = None,
    table: str = DEFAULT_TABLE,
    metadata_column: Optional[str] = "metadata",
    metadata_columns: Optional[dict] = None,
) -> CredentialStore:
    """Real when ``client`` AND ``fernet_key`` are set; else Fake.

    Mirrors `get_routing_adapter` / `get_*_adapter` — the default is the
    Fake so a product that hasn't wired a key/client still boots and
    tests deterministically.

    ``metadata_column`` / ``metadata_columns`` configure the table-shape
    seam for absorbed products whose credentials table predates the seed
    contract (no ``metadata jsonb`` column, or denormalized metadata
    columns). Defaults reproduce the historical behavior exactly — the
    params are additive and zero-impact for existing consumers. Both the
    Real and the Fake honor them identically (test parity).
    """
    if client is not None and fernet_key:
        return SupabaseCredentialStore(
            client,
            fernet_key,
            table=table,
            metadata_column=metadata_column,
            metadata_columns=metadata_columns,
        )
    return FakeCredentialStore(
        metadata_column=metadata_column,
        metadata_columns=metadata_columns,
    )
