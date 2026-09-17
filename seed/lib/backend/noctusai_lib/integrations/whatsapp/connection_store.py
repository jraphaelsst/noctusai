"""Multi-session, org-scoped WAHA connection store — field-level Fernet
encryption over a per-product ``whatsapp_connections`` table.

Lifted 2026-09-17 (`community uses social-wiring's mechanisms`, Slice A)
from `social-wiring`'s ``app/services/whatsapp_connection_store.py`` — a
PURE, behaviour-preserving extraction of the CORE columns every
WhatsApp-connections product needs. `social-wiring` is NOT modified in
this slice (its own module keeps working unchanged) — see the
``NOC-REMEDIATE[sw-consume-seed-wa-connections]`` marker left at the top
of that file.

WHY a dedicated table and NOT ``noctusai_lib.security.token_store``:
that seam is single-row per ``(org, provider)`` with a denormalized
metadata shape. A WAHA connection is MULTIPLE rows per org with distinct
``base_url`` / ``session_name`` / ``label`` columns, so a dedicated
table is the honest model. No fork on the crypto primitive: encryption
is still the shared Fernet key resolved through
``noctusai_lib.security.api_keys.require_fernet`` (the SAME check + the
SAME ``ENCRYPTION_KEY`` the credentials store in that module uses).

CORE columns only — this module knows nothing about `social-wiring`'s
own ``auto_reply_enabled`` / ``authorized_numbers`` / ``bound_chats`` /
``marca_id`` columns (chatbot-intake concerns, product-specific). A
product that needs those attaches them via the ``record_extension`` /
``extra_fields`` seams below rather than this module growing
product-specific columns.

Rows are ORG-scoped (``org_id`` alone — migration 086's shape). The
connection is a shared org asset: one WhatsApp number serving every
member, not a personal per-user integration. ``user_id`` is CREATOR
PROVENANCE only, never a scoping predicate (filtering reads on it is
what made a connection invisible to everyone but its creator on
`social-wiring` before migration 086 — see that migration's own header
for the incident).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from noctusai_lib.domain.sql_templates import rls_subquery_policy, service_role_bypass
from noctusai_lib.security.api_keys import EncryptionNotConfigured, require_fernet

__all__ = [
    "WhatsAppConnectionRecord",
    "WhatsAppConnectionStore",
    "WhatsAppConnectionStoreError",
    "build_whatsapp_connection_store",
    "resolve_by_webhook_token",
    "whatsapp_connections_table_ddl",
]

DEFAULT_TABLE = "whatsapp_connections"

# Sentinel so update_connection() can distinguish "clear webhook_url to
# NULL" from "leave webhook_url untouched" (both differ from passing a
# new value).
_UNSET: Any = object()


class WhatsAppConnectionStoreError(RuntimeError):
    """A stored API key could not be decrypted (ENCRYPTION_KEY mismatch
    or tampered ciphertext) — fail-loud, never a silent ``None``."""


@dataclass(frozen=True)
class WhatsAppConnectionRecord:
    """One connection "line". ``api_key`` is populated ONLY when a
    caller explicitly asks the store to decrypt it (live WAHA ops); it
    is ``None`` on the listing path so the secret never rides a list
    response.

    ``webhook_token`` is the opaque routing token for the per-connection
    inbound webhook path (``POST .../webhook/{token}``) — see
    :func:`resolve_by_webhook_token`. Always populated after creation.

    ``extra`` carries any product-specific columns a
    ``record_extension`` hook chose to surface (empty by default — see
    :class:`WhatsAppConnectionStore`).
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
    extra: dict[str, Any] = field(default_factory=dict)


class WhatsAppConnectionStore:
    """CRUD over ``<schema>.<table>`` with field-level Fernet encryption
    of the API key. Backed by an admin/service-role Supabase client;
    every query filters ``org_id`` explicitly (defense in depth on top
    of the RLS policy — a service-role client bypasses RLS, so this
    filter is the real enforcement)."""

    def __init__(
        self,
        client: Any,
        *,
        fernet: Fernet,
        schema: str,
        table: str = DEFAULT_TABLE,
        record_extension: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    ) -> None:
        """
        Args:
            client: an admin/service-role Supabase client.
            fernet: the built Fernet cipher (see :func:`build_whatsapp_
                connection_store` — validates ``ENCRYPTION_KEY`` loudly).
            schema: the product's schema (e.g. ``"social_wiring"``).
            table: physical table name within ``schema``.
            record_extension: optional ``row -> {extra_key: value}``
                hook. Lets a product fold its OWN columns (e.g.
                `social-wiring`'s ``auto_reply_enabled`` /
                ``authorized_numbers`` / ``bound_chats`` / ``marca_id``)
                into ``WhatsAppConnectionRecord.extra`` without this
                module needing to know their names. Default: no
                extension (``extra`` is always ``{}``).
        """
        self._client = client
        self._fernet = fernet
        self._schema = schema
        self._table_name = table
        self._record_extension = record_extension or (lambda row: {})

    # ─── helpers ──────────────────────────────────────────────────────
    def _table(self):
        return self._client.schema(self._schema).table(self._table_name)

    def _encrypt(self, api_key: str) -> str:
        return self._fernet.encrypt(api_key.encode("utf-8")).decode("ascii")

    def _decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise WhatsAppConnectionStoreError(
                "WhatsApp connection API key could not be decrypted "
                "(ENCRYPTION_KEY mismatch or tampered ciphertext)."
            ) from exc

    def _record(self, row: dict[str, Any], *, api_key: Optional[str] = None) -> WhatsAppConnectionRecord:
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
            extra=self._record_extension(row),
        )

    # ─── reads ────────────────────────────────────────────────────────
    def list_connections(self, *, org_id: UUID) -> list[WhatsAppConnectionRecord]:
        """All of the ORG's lines, newest first. Never decrypts the API key."""
        resp = self._table().select("*").eq("org_id", str(org_id)).execute()
        rows = list(resp.data or [])
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return [self._record(r) for r in rows]

    def get_connection(
        self, *, connection_id: UUID, org_id: UUID, decrypt: bool = False
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

    def get_by_webhook_token(self, token: str) -> Optional[WhatsAppConnectionRecord]:
        """Look up a connection by its opaque webhook token (service-role
        path — see :func:`resolve_by_webhook_token`). Unknown token
        returns ``None``; the caller must map that to a generic 404
        without leaking which tokens exist."""
        resp = self._table().select("*").eq("webhook_token", token).execute()
        rows = list(resp.data or [])
        if not rows:
            return None
        return self._record(rows[0])

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
        extra_fields: Optional[dict[str, Any]] = None,
    ) -> WhatsAppConnectionRecord:
        """Create a new connection. ``extra_fields`` is written verbatim
        into the insert payload — the write-side of the
        ``record_extension`` extension seam."""
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
        if extra_fields:
            payload.update(extra_fields)
        resp = self._table().insert(payload).execute()
        rows = list(resp.data or [])
        return self._record(rows[0] if rows else payload)

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
        extra_fields: Optional[dict[str, Any]] = None,
    ) -> Optional[WhatsAppConnectionRecord]:
        """Update a connection. ``_UNSET`` (the default for
        ``webhook_url``) means "not supplied -> keep current value";
        pass ``None`` explicitly to clear it. ``extra_fields`` is
        written verbatim into the patch — the write-side of the
        ``record_extension`` extension seam (a product wanting its own
        "not supplied vs explicit clear" semantics on an extra column
        resolves that itself before calling, then passes the resolved
        value here)."""
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
        if extra_fields:
            patch.update(extra_fields)
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

    def delete_connection(self, *, connection_id: UUID, org_id: UUID) -> bool:
        resp = (
            self._table()
            .delete()
            .eq("id", str(connection_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        return bool(resp.data)


def build_whatsapp_connection_store(
    client: Any,
    *,
    encryption_key: Optional[str],
    schema: str,
    table: str = DEFAULT_TABLE,
    record_extension: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
) -> WhatsAppConnectionStore:
    """Build the connection store for ``client``.

    Validates the Fernet key loudly first (missing/malformed raises
    :class:`~noctusai_lib.security.api_keys.EncryptionNotConfigured`,
    which callers map to a 503 config gap) via the SAME
    ``require_fernet`` check the api-keys store uses — one place, one
    ``ENCRYPTION_KEY`` contract across both mechanisms.
    """
    fernet = require_fernet(encryption_key)
    return WhatsAppConnectionStore(
        client, fernet=fernet, schema=schema, table=table, record_extension=record_extension
    )


def resolve_by_webhook_token(
    store: WhatsAppConnectionStore, token: str
) -> Optional[WhatsAppConnectionRecord]:
    """Resolve a connection by its opaque webhook-routing token.

    Named seam a product mounts its OWN inbound webhook handler on
    (``POST /api/whatsapp/webhook/{token}``) — thin pass-through to
    :meth:`WhatsAppConnectionStore.get_by_webhook_token`, kept as a
    module-level function so the "never log the token value; unknown
    token -> generic 404, no token enumeration" contract has one named
    call site instead of being re-derived per product. The actual
    webhook BODY-processing pipeline (chatbot intake, message
    persistence, realtime fan-out) is deliberately NOT lifted here —
    that is product-specific business logic, not a generic mechanism.
    """
    return store.get_by_webhook_token(token)


def whatsapp_connections_table_ddl(schema: str, *, table: str = DEFAULT_TABLE) -> str:
    """DDL template for the org-scoped ``whatsapp_connections`` table.

    Mirrors `social-wiring` migrations 004 + 005 + 086 (org-scoped,
    NOT per-user — see 086's header for why the per-user leg was
    dropped) — the CORE columns only. A product wanting the chatbot-
    intake extension columns (``auto_reply_enabled`` /
    ``authorized_numbers`` / ``bound_chats`` / ``marca_id``) adds them
    in its OWN follow-up migration, same as `social-wiring` did across
    migrations 014/016/017. A product copies this into its own
    migration file (authoring-time helper, not a live-apply tool) —
    reuses the canonical ``noctusai_lib.domain.sql_templates`` policy
    shapes so the RLS convention can't drift.

    Assumes ``public.current_org_id()`` already exists on the target
    Supabase project (see
    :func:`noctusai_lib.security.api_keys.credentials_table_ddl`'s
    docstring for the same prerequisite).
    """
    select_policy = rls_subquery_policy(
        schema, table, f"{table}_select_own_org", "SELECT",
        using="org_id = current_org_id()",
    )
    bypass_policy = service_role_bypass(table, schema=schema)
    return (
        f"CREATE TABLE {schema}.{table} (\n"
        f"    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
        f"    org_id UUID NOT NULL,\n"
        f"    user_id UUID NOT NULL,\n"
        f"    label TEXT NOT NULL,\n"
        f"    base_url TEXT NOT NULL,\n"
        f"    session_name TEXT NOT NULL DEFAULT 'default',\n"
        f"    encrypted_api_key TEXT NOT NULL,\n"
        f"    webhook_url TEXT,\n"
        f"    webhook_token TEXT NOT NULL,\n"
        f"    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        f"    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        f"    UNIQUE (org_id, label)\n"
        f");\n\n"
        f"ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;\n\n"
        f"{select_policy}\n\n"
        f"{bypass_policy}\n\n"
        f"CREATE INDEX idx_{schema}_{table}_org ON {schema}.{table}(org_id, created_at DESC);\n"
        f"CREATE UNIQUE INDEX idx_{schema}_{table}_webhook_token "
        f"ON {schema}.{table}(webhook_token);"
    )
