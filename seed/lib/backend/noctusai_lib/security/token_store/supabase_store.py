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
        metadata_column: name of the ``jsonb`` column that holds the
            (unmapped) plaintext metadata blob. Default ``"metadata"``
            reproduces the historical behavior exactly. Pass ``None`` for
            absorbed tables that have NO metadata column — ``put()`` then
            omits the column from the payload and ``get()`` does not read
            it (any unmapped metadata key with ``metadata_column is None``
            raises ``ValueError`` — fail-loud, never a silent drop).
        metadata_columns: optional ``{metadata_key: physical_column}`` map
            for absorbed tables that denormalized specific metadata keys
            into discrete columns (e.g.
            ``{"channel_id": "channel_id", "scopes": "scopes"}``).
            ``put()`` flattens mapped keys into their own columns (NOT the
            JSON blob); ``get()`` re-inflates those columns back into
            ``StoredCredential.metadata``. Default ``None`` = no mapping.
    """

    def __init__(
        self,
        client,
        fernet_key: bytes,
        *,
        table: str = DEFAULT_TABLE,
        metadata_column: Optional[str] = "metadata",
        metadata_columns: Optional[dict] = None,
    ) -> None:
        if not fernet_key:
            raise ValueError("SupabaseCredentialStore requires a non-empty fernet_key")
        self._client = client
        self._key = fernet_key
        self._table = table
        self._metadata_column = metadata_column
        self._metadata_columns = dict(metadata_columns or {})

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
        return self._row_to_stored(org_id, provider, tokens, row)

    def _row_to_stored(
        self, org_id: str, provider: str, tokens: dict, row: dict
    ) -> StoredCredential:
        """Re-inflate ``.metadata`` from the JSON blob + any mapped columns.

        The JSON blob is read only when ``metadata_column`` is set;
        ``metadata_columns`` entries are pulled back from their discrete
        physical columns. Mapped keys win over the JSON blob if both are
        somehow present (the mapped column is the canonical home).
        """
        metadata: dict = {}
        if self._metadata_column is not None:
            metadata.update(row.get(self._metadata_column) or {})
        for meta_key, col in self._metadata_columns.items():
            if col in row and row[col] is not None:
                metadata[meta_key] = row[col]
        return StoredCredential(
            org_id=org_id,
            provider=provider,
            tokens=tokens,
            created_at=_parse_ts(row.get("created_at")),
            updated_at=_parse_ts(row.get("updated_at")),
            metadata=metadata,
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
        meta = dict(metadata or {})
        payload = {
            "org_id": org_id,
            "provider": provider,
            "encrypted_tokens": encrypted,
            "updated_at": now.isoformat(),
        }
        # Flatten mapped metadata keys into their own discrete columns —
        # they do NOT also go into the JSON blob.
        unmapped: dict = {}
        for key, value in meta.items():
            col = self._metadata_columns.get(key)
            if col is not None:
                payload[col] = value
            else:
                unmapped[key] = value
        if self._metadata_column is not None:
            payload[self._metadata_column] = unmapped
        elif unmapped:
            # No JSON metadata column on this table and an unmapped key
            # was supplied — refuse to silently drop it (fail-loud).
            raise ValueError(
                "token_store: metadata keys "
                f"{sorted(unmapped)} have no destination — metadata_column "
                "is None and they are not in metadata_columns; either map "
                "them or configure a metadata_column"
            )
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
            metadata=meta,
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
