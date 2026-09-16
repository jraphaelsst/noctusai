"""Service-side ``pk_*`` product-token administration — mint / look up / revoke
a token in ANY product's ``<schema>.api_tokens`` table.

WHY
---
The seed route ``POST /api/settings/api-tokens`` (``noctusai_seed.
auth_router``) mints a token for a HUMAN org admin of the product that
serves the route. A control plane that must RENEW the token it holds for
another product (``agents`` holds ``pk_`` tokens for academia-de-reciclagem
and social-wiring) cannot use that route: product tokens may not mint by
design, and the operator's browser session is scoped to ``agents``' origin.

Every product's ``api_tokens`` table lives in the ONE shared Supabase
project, and a product container already holds that project's service-role
key — so a service-side insert into ``<target_schema>.api_tokens`` adds no
new trust. This module is that insert, with the SAME semantics as the seed
route: :func:`mint_token_secret` and :func:`build_api_token_row` are the
single source for both (``auth_router`` calls them too), and the stored
digest is :func:`~noctusai_lib.api.auth.session.api_tokens.hash_token`.

Guard rails a caller MUST keep (this module cannot know them):
- scopes / principal / issuer come from the caller's server-side registry,
  never from request input — a UI "renew" must not be a scope-escalation
  path;
- the caller authorizes the human (platform admin) before calling.

Shape: Protocol + Fake + Real + factory
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from uuid import UUID, uuid4

from noctusai_lib.api.auth.session.api_tokens import hash_token

logger = logging.getLogger(__name__)

__all__ = [
    "API_TOKENS_TABLE",
    "ApiTokenInfo",
    "FakeProductTokenAdmin",
    "MintedApiToken",
    "ProductTokenAdmin",
    "SupabaseProductTokenAdmin",
    "build_api_token_row",
    "make_product_token_admin",
    "mint_token_secret",
    "token_prefix",
]

API_TOKENS_TABLE = "api_tokens"
_PREFIX_LEN = 11  # ``pk_`` + 8 hex chars — the UI-display prefix


def token_prefix(secret: str) -> str:
    """The display prefix the seed stores in ``api_tokens.token_prefix``."""
    return secret[:_PREFIX_LEN]


def mint_token_secret() -> tuple[str, str]:
    """Return ``(raw_secret, prefix)`` for a fresh ``pk_*`` token (256 bits)."""
    raw = f"pk_{secrets.token_hex(32)}"
    return raw, token_prefix(raw)


def build_api_token_row(
    *,
    token_id: UUID,
    raw_secret: str,
    org_id: UUID,
    label: str,
    scopes: list[str],
    expires_at: datetime,
    created_at: datetime,
    principal_agent_id: Optional[UUID] = None,
    human_personal: bool = False,
    minted_by: Optional[UUID] = None,
    issuer: Optional[str] = None,
) -> dict[str, Any]:
    """The ``api_tokens`` insert payload (SEED-1 columns, contract §B.0).

    ``issuer`` is only included when set — the column exists on every
    SEED-1 table, but the seed route never set it, and omitting a ``None``
    keeps that route's payload byte-identical to before.
    """
    minted = str(minted_by) if minted_by else None
    row: dict[str, Any] = {
        "id": str(token_id),
        "org_id": str(org_id),
        "label": label,
        "token_hash": hash_token(raw_secret),
        "token_prefix": token_prefix(raw_secret),
        "scopes": list(scopes),
        "created_by": minted,
        "created_at": created_at.isoformat(),
        "last_used_at": None,
        "revoked_at": None,
        "expires_at": expires_at.isoformat(),
        "principal_agent_id": str(principal_agent_id) if principal_agent_id else None,
        "human_personal": human_personal,
        "minted_by": minted,
    }
    if issuer is not None:
        row["issuer"] = issuer
    return row


@dataclass(frozen=True)
class ApiTokenInfo:
    """Non-secret projection of one ``api_tokens`` row."""

    id: UUID
    org_id: UUID
    label: str
    prefix: str
    scopes: tuple[str, ...]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]
    principal_agent_id: Optional[UUID]
    issuer: Optional[str]


@dataclass(frozen=True)
class MintedApiToken:
    """Returned once by :meth:`ProductTokenAdmin.mint`. ``secret`` is the
    raw ``pk_*`` value — the caller stores it and never echoes it."""

    info: ApiTokenInfo
    secret: str


class ProductTokenAdmin(Protocol):
    def find_by_secret(self, schema: str, secret: str) -> Optional[ApiTokenInfo]:
        """The row whose ``token_hash`` matches ``secret`` (revoked or not),
        or ``None``."""
        ...

    def mint(
        self,
        schema: str,
        *,
        org_id: UUID,
        label: str,
        scopes: list[str],
        expires_at: datetime,
        principal_agent_id: Optional[UUID] = None,
        issuer: Optional[str] = None,
        minted_by: Optional[UUID] = None,
    ) -> MintedApiToken:
        """Insert a new token row. Raises on any write failure."""
        ...

    def revoke(self, schema: str, token_id: UUID, *, org_id: UUID) -> bool:
        """Stamp ``revoked_at``. ``True`` when a row was updated."""
        ...


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _info(row: dict[str, Any]) -> ApiTokenInfo:
    principal = row.get("principal_agent_id")
    return ApiTokenInfo(
        id=UUID(str(row["id"])),
        org_id=UUID(str(row["org_id"])),
        label=row.get("label") or "",
        prefix=row.get("token_prefix") or "",
        scopes=tuple(row.get("scopes") or ()),
        expires_at=_ts(row.get("expires_at")),
        last_used_at=_ts(row.get("last_used_at")),
        revoked_at=_ts(row.get("revoked_at")),
        principal_agent_id=UUID(str(principal)) if principal else None,
        issuer=row.get("issuer"),
    )


_INFO_COLUMNS = (
    "id, org_id, label, token_prefix, scopes, expires_at, last_used_at, "
    "revoked_at, principal_agent_id, issuer"
)


class FakeProductTokenAdmin:
    """In-memory :class:`ProductTokenAdmin`, rows keyed by schema.

    ``fail_mint`` / ``fail_revoke`` simulate a write failure.
    """

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.fail_mint = False
        self.fail_revoke = False

    def seed(self, schema: str, secret: str, **fields: Any) -> ApiTokenInfo:
        """Test helper — register an existing token for ``secret``."""
        now = datetime.now(timezone.utc)
        row = build_api_token_row(
            token_id=fields.pop("token_id", uuid4()),
            raw_secret=secret,
            org_id=fields.pop("org_id"),
            label=fields.pop("label", "seeded"),
            scopes=list(fields.pop("scopes", [])),
            expires_at=fields.pop("expires_at"),
            created_at=now,
            principal_agent_id=fields.pop("principal_agent_id", None),
            issuer=fields.pop("issuer", None),
        )
        row.update({k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in fields.items()})
        self.rows.setdefault(schema, []).append(row)
        return _info(row)

    def find_by_secret(self, schema: str, secret: str) -> Optional[ApiTokenInfo]:
        digest = hash_token(secret)
        for row in self.rows.get(schema, []):
            if row["token_hash"] == digest:
                return _info(row)
        return None

    def mint(
        self,
        schema: str,
        *,
        org_id: UUID,
        label: str,
        scopes: list[str],
        expires_at: datetime,
        principal_agent_id: Optional[UUID] = None,
        issuer: Optional[str] = None,
        minted_by: Optional[UUID] = None,
    ) -> MintedApiToken:
        if self.fail_mint:
            raise RuntimeError("fake mint failure")
        raw, _ = mint_token_secret()
        row = build_api_token_row(
            token_id=uuid4(),
            raw_secret=raw,
            org_id=org_id,
            label=label,
            scopes=scopes,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
            principal_agent_id=principal_agent_id,
            issuer=issuer,
            minted_by=minted_by,
        )
        self.rows.setdefault(schema, []).append(row)
        return MintedApiToken(info=_info(row), secret=raw)

    def revoke(self, schema: str, token_id: UUID, *, org_id: UUID) -> bool:
        if self.fail_revoke:
            raise RuntimeError("fake revoke failure")
        for row in self.rows.get(schema, []):
            if row["id"] == str(token_id) and row["org_id"] == str(org_id):
                row["revoked_at"] = datetime.now(timezone.utc).isoformat()
                return True
        return False


class SupabaseProductTokenAdmin:
    """Real :class:`ProductTokenAdmin` over a service-role Supabase client.

    ``admin_client`` must be able to address other schemas via
    ``.schema(name)`` (the supabase-py ``Client``); the target schema must be
    exposed to PostgREST — it already is for every product that serves
    ``pk_*`` tokens through ``SupabaseApiTokenResolver``.
    """

    def __init__(self, admin_client: Any) -> None:
        self._sb = admin_client

    def _table(self, schema: str):
        return self._sb.schema(schema).table(API_TOKENS_TABLE)

    def find_by_secret(self, schema: str, secret: str) -> Optional[ApiTokenInfo]:
        resp = (
            self._table(schema)
            .select(_INFO_COLUMNS)
            .eq("token_hash", hash_token(secret))
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return _info(rows[0]) if rows else None

    def mint(
        self,
        schema: str,
        *,
        org_id: UUID,
        label: str,
        scopes: list[str],
        expires_at: datetime,
        principal_agent_id: Optional[UUID] = None,
        issuer: Optional[str] = None,
        minted_by: Optional[UUID] = None,
    ) -> MintedApiToken:
        raw, _ = mint_token_secret()
        row = build_api_token_row(
            token_id=uuid4(),
            raw_secret=raw,
            org_id=org_id,
            label=label,
            scopes=scopes,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
            principal_agent_id=principal_agent_id,
            issuer=issuer,
            minted_by=minted_by,
        )
        self._table(schema).insert(row).execute()
        logger.info(
            "product_token_minted schema=%s token_id=%s prefix=%s",
            schema, row["id"], row["token_prefix"],
        )
        return MintedApiToken(info=_info(row), secret=raw)

    def revoke(self, schema: str, token_id: UUID, *, org_id: UUID) -> bool:
        resp = (
            self._table(schema)
            .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(token_id))
            .eq("org_id", str(org_id))
            .execute()
        )
        revoked = bool(resp.data)
        logger.info(
            "product_token_revoked schema=%s token_id=%s revoked=%s",
            schema, token_id, revoked,
        )
        return revoked


def make_product_token_admin(admin_client: Any = None) -> ProductTokenAdmin:
    """Real when a service-role client is supplied; the Fake otherwise."""
    if admin_client is None:
        return FakeProductTokenAdmin()
    return SupabaseProductTokenAdmin(admin_client)
