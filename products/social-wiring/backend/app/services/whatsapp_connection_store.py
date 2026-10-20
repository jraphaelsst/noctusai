# NOC-REMEDIATE[sw-consume-seed-wa-connections]: generic mechanism lifted to `noctusai_lib.integrations.whatsapp.connection_store` + `noctusai_seed.whatsapp_connections_router`; migrate this module to consume it — 2026-09-17
"""Per-ORG WAHA connection store — multi-session "lines" with the API key
Fernet-encrypted at rest.

Each row is one WhatsApp connection the org manages from the Conexão page: a
WAHA server URL + session name + API key. The API key is the only secret and
is encrypted with the SAME ``ENCRYPTION_KEY`` the ``credentials`` table uses
(via the product ``credential_vault`` seam over the seed Fernet primitive).

Rows are ORG-scoped (``org_id`` alone). The connection is a shared org asset —
one WhatsApp number serving every member, i.e. a platform-wide notification
line — not a personal per-user integration. ``user_id`` is retained as
CREATOR PROVENANCE (who set the line up) and is NEVER a scoping predicate:
filtering on it is what made a connection invisible to everyone but the
person who created it. Per-user lines *within* an org are a deliberate future
step; when that lands it needs its own explicit column/flag, not a silent
re-narrowing of this one. → migration 086.

WHY a dedicated table and NOT the seed ``CredentialStore``: that seam is
single-row per ``(org, provider)`` with a denormalized metadata shape. These
are MULTIPLE rows per user with distinct ``base_url`` / ``session_name``
columns and an editable label, so a dedicated table is the honest model. No
fork: the ENCRYPTION primitive is still consumed from the seed
(``cryptography.fernet`` + the shared ``ENCRYPTION_KEY``) through
``credential_vault.require_fernet``. (Seed-lift candidate at N=2 — see the
project findings.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.services.credential_vault import (
    CredentialStoreError,
    require_fernet,
)

__all__ = [
    "WhatsAppConnectionRecord",
    "WhatsAppConnectionStore",
    "build_whatsapp_connection_store",
]

_SCHEMA = "social_wiring"
_TABLE = "whatsapp_connections"

# Sentinel so update() can distinguish "clear webhook_url to NULL" from "leave
# webhook_url untouched" (both differ from passing a new value).
_UNSET: Any = object()


@dataclass(frozen=True)
class WhatsAppConnectionRecord:
    """One connection line. ``api_key`` is populated ONLY when a caller
    explicitly asks the store to decrypt it (live WAHA ops); it is ``None``
    on the listing path so the secret never rides a list response.

    ``webhook_token`` is the opaque routing token stored in the DB column added
    by migration 005. It is always populated (non-null after backfill). The
    public webhook URL is derived from this token by the router so it survives
    domain changes without a DB migration.

    ``auto_reply_enabled`` added by migration 014: per-connection toggle that
    gates the existing chatbot auto-reply.  Default OFF so operators can test
    the manual chat UI without the bot interfering.
    """

    id: UUID
    org_id: UUID
    user_id: UUID
    label: str
    base_url: str
    session_name: str
    webhook_url: Optional[str]
    created_at: Any
    updated_at: Any
    api_key: Optional[str] = None
    webhook_token: Optional[str] = None
    auto_reply_enabled: bool = False
    # Migration 016 — per-connection intake config.
    # authorized_numbers: empty list = nobody authorized (operator-only bot).
    # bound_chats: list of {"chat_id": str, "label": str} dicts; empty = all.
    authorized_numbers: list[str] = field(default_factory=list)
    bound_chats: list[dict] = field(default_factory=list)
    # Migration 017 — optional cliente ownership.
    # None = unassigned; UUID = the client this connection belongs to.
    marca_id: Optional[UUID] = None
    # Migration 258 — Julia (lead agent). Defensive reads: an un-migrated
    # row is "Julia off", never a crash and never "on".
    agente_leads_ativo: bool = False
    agente_leads_key: Optional[str] = None
    agente_leads_ativado_em: Optional[str] = None
    agente_handoff_notificar_user_id: Optional[UUID] = None
    # Migration 275 — transport per connection (waha | cloud). A defensive read: an un-migrated row is WAHA.
    transporte: str = "waha"
    cloud_phone_number_id: Optional[str] = None
    cloud_waba_id: Optional[str] = None


class WhatsAppConnectionStore:
    """CRUD over ``social_wiring.whatsapp_connections`` with field-level
    Fernet encryption of the API key. Backed by an admin/service-role
    Supabase client; every query filters ``org_id`` explicitly (defense in
    depth on top of the RLS policy — the service-role client bypasses RLS, so
    this filter is the real enforcement, not a redundancy)."""

    def __init__(self, client: Any, *, fernet: Fernet):
        self._client = client
        self._fernet = fernet

    # ─── helpers ──────────────────────────────────────────────────────
    def _table(self):
        return self._client.schema(_SCHEMA).table(_TABLE)

    def _encrypt(self, api_key: str) -> str:
        return self._fernet.encrypt(api_key.encode("utf-8")).decode("ascii")

    def _decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise CredentialStoreError(
                "WhatsApp connection API key could not be decrypted "
                "(ENCRYPTION_KEY mismatch or tampered ciphertext)."
            ) from exc

    @staticmethod
    def _record(row: dict[str, Any], *, api_key: Optional[str] = None) -> WhatsAppConnectionRecord:
        return WhatsAppConnectionRecord(
            id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            user_id=UUID(str(row["user_id"])),
            label=row["label"],
            base_url=row["base_url"],
            session_name=row.get("session_name") or "default",
            webhook_url=row.get("webhook_url"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            api_key=api_key,
            webhook_token=row.get("webhook_token"),
            auto_reply_enabled=bool(row.get("auto_reply_enabled", False)),
            # Migration 016 — defensive reads: un-migrated DB rows get empty
            # lists (= all allowed / all listened), never a crash.
            authorized_numbers=list(row.get("authorized_numbers") or []),
            bound_chats=list(row.get("bound_chats") or []),
            # Migration 017 — optional cliente FK; absent on un-migrated rows.
            marca_id=UUID(str(row["marca_id"])) if row.get("marca_id") else None,
            # Migration 258 — Julia.
            agente_leads_ativo=bool(row.get("agente_leads_ativo", False)),
            agente_leads_key=row.get("agente_leads_key"),
            agente_leads_ativado_em=row.get("agente_leads_ativado_em"),
            agente_handoff_notificar_user_id=(
                UUID(str(row["agente_handoff_notificar_user_id"]))
                if row.get("agente_handoff_notificar_user_id")
                else None
            ),
            transporte=row.get("transporte") or "waha",
            cloud_phone_number_id=row.get("cloud_phone_number_id"),
            cloud_waba_id=row.get("cloud_waba_id"),
        )

    # ─── reads ────────────────────────────────────────────────────────
    def list_connections(
        self,
        *,
        org_id: UUID,
        marca_id: Optional[UUID] = None,
    ) -> list[WhatsAppConnectionRecord]:
        """All of the ORG's lines, newest first.  Never decrypts the API key.

        ``marca_id`` (migration 017): when supplied, filters to only the
        connections owned by that cliente.  ``None`` returns all (no filter).
        """
        q = (
            self._table()
            .select("*")
            .eq("org_id", str(org_id))
        )
        if marca_id is not None:
            q = q.eq("marca_id", str(marca_id))
        resp = q.execute()
        rows = list(resp.data or [])
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return [self._record(r) for r in rows]

    def get_connection(
        self,
        *,
        connection_id: UUID,
        org_id: UUID,
        decrypt: bool = False,
    ) -> Optional[WhatsAppConnectionRecord]:
        """One line by id, ORG-scoped. ``decrypt=True`` populates
        ``record.api_key`` (only for the live-WAHA-ops path)."""
        resp = (
            self._table()
            .select("*")
            .eq("id", str(connection_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            return None
        row = rows[0]
        api_key = self._decrypt(row["encrypted_api_key"]) if decrypt else None
        return self._record(row, api_key=api_key)

    # ─── writes ───────────────────────────────────────────────────────
    def create_connection(
        self,
        *,
        org_id: UUID,
        user_id: UUID,  # creator provenance only — never a scoping predicate
        label: str,
        base_url: str,
        api_key: str,
        session_name: str = "default",
        webhook_url: Optional[str] = None,
        webhook_token: Optional[str] = None,
        marca_id: Optional[UUID] = None,
    ) -> WhatsAppConnectionRecord:
        """Create a new connection.  ``marca_id`` (migration 017) links the
        connection to a cliente at creation time — optional, default ``None``
        (unassigned).  The DB column is nullable so absent FK is safe.
        """
        payload: dict[str, Any] = {
            "org_id": str(org_id),
            "user_id": str(user_id),
            "label": label,
            "base_url": base_url.rstrip("/"),
            "session_name": session_name or "default",
            "encrypted_api_key": self._encrypt(api_key),
            "webhook_url": webhook_url,
            "webhook_token": webhook_token,
        }
        if marca_id is not None:
            payload["marca_id"] = str(marca_id)
        resp = self._table().insert(payload).execute()
        rows = list(resp.data or [])
        return self._record(rows[0] if rows else payload)

    def get_by_webhook_token(
        self, token: str
    ) -> Optional[WhatsAppConnectionRecord]:
        """Look up a connection by its opaque webhook token (service-role path).

        Used by the token-scoped inbound webhook receiver to resolve which
        connection (org / user / session) an incoming WAHA call belongs to.
        Unknown token returns ``None``; the caller must map that to a generic
        404 without leaking which tokens exist.
        """
        resp = (
            self._table()
            .select("*")
            .eq("webhook_token", token)
            .execute()
        )
        rows = list(resp.data or [])
        if not rows:
            return None
        return self._record(rows[0])

    def get_by_id(
        self, connection_id: UUID, *, decrypt: bool = False
    ) -> Optional[WhatsAppConnectionRecord]:
        """One line by id WITHOUT an org scope (service-role path).

        ONLY for callers that hold no org context but a connection id they
        minted themselves — the Julia worker resolves org + connection from its
        own buffer key (contract 10.2 B2). Never expose this to a request that
        carries a user-supplied id: those go through the ORG-scoped
        :meth:`get_connection`.
        """
        resp = self._table().select("*").eq("id", str(connection_id)).execute()
        rows = list(resp.data or [])
        if not rows:
            return None
        row = rows[0]
        api_key = self._decrypt(row["encrypted_api_key"]) if decrypt else None
        return self._record(row, api_key=api_key)

    def update_connection(
        self,
        *,
        connection_id: UUID,
        org_id: UUID,
        label: Optional[str] = None,
        base_url: Optional[str] = None,
        session_name: Optional[str] = None,
        api_key: Optional[str] = None,
        webhook_url: Any = _UNSET,
        authorized_numbers: Any = _UNSET,
        bound_chats: Any = _UNSET,
        marca_id: Any = _UNSET,
    ) -> Optional[WhatsAppConnectionRecord]:
        """Update a connection.

        Uses the ``_UNSET`` sentinel for nullable fields that can be explicitly
        cleared (``webhook_url``, ``authorized_numbers``, ``bound_chats``,
        ``marca_id``) to distinguish "not supplied → keep current value" from
        "supplied as ``None``/``[]`` → clear the value".
        """
        patch: dict[str, Any] = {}
        if label is not None:
            patch["label"] = label
        if base_url is not None:
            patch["base_url"] = base_url.rstrip("/")
        if session_name is not None:
            patch["session_name"] = session_name or "default"
        if api_key:
            patch["encrypted_api_key"] = self._encrypt(api_key)
        if webhook_url is not _UNSET:
            patch["webhook_url"] = webhook_url
        # Migration 016 — JSONB list fields.  _UNSET = keep current value;
        # an explicit [] (nobody authorized / listen to all chats) IS written.
        if authorized_numbers is not _UNSET:
            patch["authorized_numbers"] = list(authorized_numbers)
        if bound_chats is not _UNSET:
            patch["bound_chats"] = list(bound_chats)
        # Migration 017 — client FK.  _UNSET = keep current; None = clear.
        if marca_id is not _UNSET:
            patch["marca_id"] = str(marca_id) if marca_id is not None else None
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()

        resp = (
            self._table()
            .update(patch)
            .eq("id", str(connection_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = list(resp.data or [])
        return self._record(rows[0]) if rows else None

    def update_agente(
        self,
        *,
        connection_id: UUID,
        org_id: UUID,
        patch: dict[str, Any],
    ) -> Optional[WhatsAppConnectionRecord]:
        """Write the Julia columns (migration 258). ORG-scoped; the service owns
        which keys it may pass, the DB CHECK (H3) is the last line of defence."""
        allowed = {
            "agente_leads_ativo", "agente_leads_key", "agente_leads_ativado_em",
            "agente_handoff_notificar_user_id",
        }
        unknown = set(patch) - allowed
        if unknown:
            raise ValueError(f"not a Julia column: {sorted(unknown)}")
        body = {**patch, "updated_at": datetime.now(timezone.utc).isoformat()}
        resp = (
            self._table()
            .update(body)
            .eq("id", str(connection_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = list(resp.data or [])
        return self._record(rows[0]) if rows else None

    def update_transporte(
        self,
        *,
        connection_id: UUID,
        org_id: UUID,
        patch: dict[str, Any],
        access_token: Optional[str] = None,
    ) -> Optional[WhatsAppConnectionRecord]:
        """Write the transport columns (migration 275). ORG-scoped; for `cloud` the encrypted api_key
        holds the Meta access token, so a supplied `access_token` replaces it."""
        allowed = {"transporte", "cloud_phone_number_id", "cloud_waba_id"}
        unknown = set(patch) - allowed
        if unknown:
            raise ValueError(f"not a transport column: {sorted(unknown)}")
        body: dict[str, Any] = {**patch, "updated_at": datetime.now(timezone.utc).isoformat()}
        if access_token:
            body["encrypted_api_key"] = self._encrypt(access_token)
        resp = (
            self._table()
            .update(body)
            .eq("id", str(connection_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = list(resp.data or [])
        return self._record(rows[0]) if rows else None

    def delete_connection(self, *, connection_id: UUID, org_id: UUID) -> bool:
        resp = (
            self._table()
            .delete()
            .eq("id", str(connection_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        return bool(resp.data)

    def update_auto_reply(
        self,
        *,
        connection_id: UUID,
        org_id: UUID,
        enabled: bool,
    ) -> Optional[WhatsAppConnectionRecord]:
        """Toggle the per-connection auto-reply gate (migration 014).

        ORG-scoped — a connection outside the caller's org returns None
        (caller maps to 404). The router intentionally separates this from
        the general update_connection path to keep the intent explicit and
        the field surface narrow.
        """
        patch: dict[str, Any] = {
            "auto_reply_enabled": enabled,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = (
            self._table()
            .update(patch)
            .eq("id", str(connection_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        rows = list(resp.data or [])
        return self._record(rows[0]) if rows else None


def build_whatsapp_connection_store(
    client: Any, *, encryption_key: Optional[str] = None
) -> WhatsAppConnectionStore:
    """Build the connection store for ``client``.

    Validates the Fernet key loudly first (missing/malformed →
    :class:`EncryptionNotConfigured`, which routers map to a 503 config gap),
    mirroring ``build_credential_store``. The ``encryption_key`` kwarg is the
    DI seam (tests inject; production resolves ``settings.encryption_key``).
    """
    key = encryption_key if encryption_key is not None else settings.encryption_key
    fernet = require_fernet(key)
    return WhatsAppConnectionStore(client, fernet=fernet)
