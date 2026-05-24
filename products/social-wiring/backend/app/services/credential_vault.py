"""Credential persistence — thin seed-consume seam over ``token_store``.

Replaces the former product-local ``credential_store.py`` fork. The
encrypt-at-rest persistence layer now lives in the seed
(``noctusai_lib.security.token_store``); this module is the product's
named consume seam: it (a) keeps the loud "ENCRYPTION_KEY not configured
→ refuse to write plaintext" check the product's routers map to a 503,
and (b) wires the Phase-1 ``metadata_columns`` table-shape seam so the
absorbed ``social_wiring.credentials`` table's denormalized
``channel_id / channel_title / scopes`` columns keep working without a
schema migration.

WHY a product helper and not 27 inline ``make_credential_store(...)``
calls: the loud-key-check is needed at every one of the ~27 construction
sites. Inlining it 27× is exactly the N≥3 recurrence the seed-consume
project exists to remove — so the construction is funnelled through
``build_credential_store`` (one place owns the loud check + the
metadata-column map), which itself consumes the seed factory through its
named seam. No fork: zero crypto / DB code lives here.

Consumers read denormalized metadata off ``StoredCredential.metadata``
(``stored.metadata["channel_id"]`` etc.) — the Phase-1 column map keeps
those physically in the same ``channel_id / channel_title / scopes``
columns, so this is behavior-preserving.
"""
from __future__ import annotations

from typing import Optional

from cryptography.fernet import Fernet
from noctusai_lib.security.token_store import (
    CredentialDecryptError,
    CredentialStore,
    StoredCredential,
    make_credential_store,
)

from app.config import settings

__all__ = [
    "CredentialDecryptError",
    "CredentialStore",
    "CredentialStoreError",
    "EncryptionNotConfigured",
    "StoredCredential",
    "build_credential_store",
]

# Backwards-compatible product alias. The seed raises
# ``CredentialDecryptError`` on key-mismatch / tampered ciphertext; the
# product's router-level handlers historically caught
# ``CredentialStoreError`` for the same fail-loud case, so alias it.
CredentialStoreError = CredentialDecryptError

# The denormalized columns the absorbed ``social_wiring.credentials``
# table predates the seed ``metadata jsonb`` contract with. The seed
# store flattens these metadata keys into their own physical columns on
# write and re-inflates them into ``StoredCredential.metadata`` on read.
_METADATA_COLUMNS = {
    "channel_id": "channel_id",
    "channel_title": "channel_title",
    "scopes": "scopes",
}


class EncryptionNotConfigured(RuntimeError):
    """ENCRYPTION_KEY missing or invalid — refuse to write plaintext.

    Product-local (the seed factory silently returns a Fake when the key
    is absent; the product instead fails loud so routers can surface a
    503 config gap rather than silently degrading to an in-memory store).
    """


def build_credential_store(client, *, encryption_key: Optional[str]=None) -> CredentialStore:
    """Build the seed-backed credential store for ``client``.

    Validates ``settings.encryption_key`` loudly first (a missing /
    malformed Fernet key raises :class:`EncryptionNotConfigured`, exactly
    as the former product fork did at construction time — preserving the
    routers' 503-on-config-gap behavior), then delegates persistence to
    the seed factory wired with the Phase-1 table-shape seam.
    """
    # DI seam: tests inject `encryption_key=...`; production resolves
    # the module singleton. `settings.encryption_key` stays the
    # canonical runtime source so the 503-on-config-gap behavior is
    # unchanged. See KB § PATTERNS/di-test-seam.md (Class-B kwarg).
    key = encryption_key if encryption_key is not None else settings.encryption_key
    if not key:
        raise EncryptionNotConfigured(
            "ENCRYPTION_KEY is empty. Generate with `python -c \"from "
            "cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it in the "
            "product's .env."
        )
    try:
        Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise EncryptionNotConfigured(
            f"ENCRYPTION_KEY is not a valid Fernet key: {exc}. "
            "Regenerate with the snippet in .env.example."
        ) from exc
    return make_credential_store(
        client=client,
        fernet_key=key.encode("utf-8"),
        table="credentials",
        metadata_column=None,
        metadata_columns=_METADATA_COLUMNS,
    )
