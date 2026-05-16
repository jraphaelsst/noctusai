"""Supabase-backed `CredentialStore` — Fernet-encrypted rows at rest.

Composes `noctusai_lib.security.encrypted_tokens` (the crypto primitive)
for the at-rest boundary. One row per ``(org_id, provider)``; the token
bundle is JSON-serialized then Fernet-encrypted into a single TEXT
column. UPSERT on the ``(org_id, provider)`` natural key. Decrypt on
read; fail loud (``CredentialDecryptError``) on key mismatch.

Lifted 2026-05-16 by `projects/social-wiring-absorption/` Wave 1 from
the sibling workspace's single-product
``app/services/credential_store.py`` (OAUTH-PATTERNS-FOR-NOC.md
Pattern 5). The sibling copy was a single-product implementation; the
N=2 trigger to formalize fired the moment the consolidated CMS + every
other OAuth-using product needed it — this module IS that
formalization.

Expected table shape (consumers own the migration — the store is
schema-agnostic beyond these columns)::

    create table <schema>.oauth_credentials (
      org_id          text not null,
      provider        text not null,
      encrypted_tokens text not null,   -- Fernet(JSON(bundle))
      metadata        jsonb not null default '{}'::jsonb,
      created_at      timestamptz not null default now(),
      updated_at      timestamptz not null default now(),
      primary key (org_id, provider)
    );
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from noctusai_lib.security.encrypted_tokens import decrypt, encrypt
from noctusai_lib.security.token_store.types import (
    CredentialDecryptError,
    CredentialStore,
    StoredCredential,
)

logger = logging.getLogger(__name__)

DEFAULT_TABLE = "oauth_credentials"


class SupabaseCredentialStore(CredentialStore):
    """Encrypted-at-rest credential persistence over a Supabase client.

    Args:
        client: a Supabase client (service-role / admin) the store uses
            for reads + writes. The store does NOT manage RLS — it is an
            admin-context persistence layer; per-org isolation is the
            natural-key, not a row policy.
        fernet_key: the Fernet key (``bytes``) the at-rest encryption
            uses. Source it from the product's secret manager / env
            (``ENCRYPTION_KEY`` / ``FERNET_KEY``) — NEVER hardcode.
        table: physical table name. Defaults to ``oauth_credentials``.
            Pass a schema-qualified name (``"social_wiring.oauth_credentials"``)
            if the client is not already schema-bound.
    """

    def __init__(self, client, fernet_key: bytes, *, table: str = DEFAULT_TABLE) -> None:
        if not fernet_key:
            raise ValueError("SupabaseCredentialStore requires a non-empty fernet_key")
        self._client = client
        self._key = fernet_key
        self._table = table

    def get(self, org_id: str, provider: str) -> Optional[StoredCredential]:
        resp = (
            self._client.table(self._table)
            .select("*")
            .eq("org_id", org_id)
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        try:
            tokens = json.loads(decrypt(row["encrypted_tokens"], self._key))
        except ValueError as exc:
            # decrypt() raises ValueError on tamper / wrong key. A stored
            # row that won't decrypt is NEVER returned as None / empty —
            # that would fail every downstream adapter far from the root
            # cause. Fail loud, here.
            logger.error(
                "token_store: credential row exists for (%s, %s) but failed to "
                "decrypt — key mismatch or tampered ciphertext",
                org_id,
                provider,
            )
            raise CredentialDecryptError(
                f"cannot decrypt stored credential for ({org_id}, {provider})"
            ) from exc
        return StoredCredential(
            org_id=org_id,
            provider=provider,
            tokens=tokens,
            created_at=_parse_ts(row.get("created_at")),
            updated_at=_parse_ts(row.get("updated_at")),
            metadata=row.get("metadata") or {},
        )

    def put(
        self,
        org_id: str,
        provider: str,
        tokens: dict,
        *,
        metadata: Optional[dict] = None,
    ) -> StoredCredential:
        now = datetime.now(timezone.utc)
        encrypted = encrypt(json.dumps(tokens, separators=(",", ":")), self._key)
        payload = {
            "org_id": org_id,
            "provider": provider,
            "encrypted_tokens": encrypted,
            "metadata": dict(metadata or {}),
            "updated_at": now.isoformat(),
        }
        # UPSERT on the (org_id, provider) natural key — re-consent
        # overwrites in place rather than accumulating rows.
        (
            self._client.table(self._table)
            .upsert(payload, on_conflict="org_id,provider")
            .execute()
        )
        return StoredCredential(
            org_id=org_id,
            provider=provider,
            tokens=dict(tokens),
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )

    def delete(self, org_id: str, provider: str) -> bool:
        resp = (
            self._client.table(self._table)
            .delete()
            .eq("org_id", org_id)
            .eq("provider", provider)
            .execute()
        )
        return bool(resp.data)

    def list_providers(self, org_id: str) -> list[str]:
        resp = (
            self._client.table(self._table)
            .select("provider")
            .eq("org_id", org_id)
            .execute()
        )
        return sorted(r["provider"] for r in (resp.data or []))


def _parse_ts(value) -> Optional[datetime]:
    """Best-effort ISO-8601 → datetime; returns None on absent/unparseable.

    Supabase returns timestamps as ISO strings; tests may inject real
    ``datetime`` objects. Both are tolerated; anything else degrades to
    ``None`` (a missing timestamp is not load-bearing for callers).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
