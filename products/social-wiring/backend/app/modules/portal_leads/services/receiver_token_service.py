"""Per-advertiser receiver tokens — mint, resolve, list, revoke.

The token is the path segment in the URL an advertiser pastes into their
portal's CRM-integration field:

    https://social-wiring.noctusai.com/api/portals/olx/leads/rcv_<opaque>
                                                             ^^^^^^^^^^^^

Resolving it IS the tenant-identification step, which is why every
function here takes an **admin** client: at resolve time there is no org
context yet, so RLS would block the read.

Two properties are load-bearing, both about not confusing this with the
`api_tokens` bearer credential it deliberately is not (see the header of
migration `053_portal_receiver_tokens.sql`):

* the prefix is ``rcv_``, never ``pk_``. `SupabaseApiTokenResolver`
  hard-rejects anything not starting with ``pk_``, so a receiver token
  can never authenticate as a bearer even by accident;
* only the SHA-256 digest is stored. The plaintext is returned once, by
  :func:`mint_receiver_token`, and is unrecoverable afterwards.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.api.auth.session import hash_token

logger = logging.getLogger(__name__)

#: Every function here takes the **schema-scoped admin** client that
#: `app.modules.leads.deps.get_leads_client` hands out — already
#: `.schema("social_wiring")`, so calls are `.table(...)` directly. That is
#: the convention the rest of `portal_leads` follows; re-scoping here would
#: raise at request time, not at import.
_TABLE = "portal_receiver_tokens"

#: The `rcv_` prefix is not decoration. It is the cheap pre-filter that
#: makes "a bearer token pasted into a receiver URL" and "a receiver
#: token sent as a bearer" both fail closed, at zero DB cost.
RECEIVER_TOKEN_PREFIX = "rcv_"

#: Providers a receiver token may route. Mirrors the CHECK constraint in
#: migration 053 — a value absent here is rejected before it reaches the
#: database, so the caller gets a typed error instead of a 23514.
RECEIVER_TOKEN_PROVIDERS: tuple[str, ...] = ("olx", "imovelweb")

#: Displayed-prefix length. Enough to tell two tokens apart in a list,
#: far too little to reconstruct one (the secret carries ≥256 bits).
_PREFIX_CHARS = 8


class UnknownReceiverProvider(ValueError):
    """Raised for a provider outside :data:`RECEIVER_TOKEN_PROVIDERS`."""


@dataclass(frozen=True)
class MintedReceiverToken:
    """The one and only time the plaintext exists outside a URL.

    `plaintext` is not stored anywhere and cannot be recovered from the
    row — losing it means minting a replacement, which is the intended
    cost of never keeping a live routing credential in the database.
    """

    id: UUID
    org_id: UUID
    provider: str
    label: str
    plaintext: str
    token_prefix: str


def _require_known_provider(provider: str) -> None:
    if provider not in RECEIVER_TOKEN_PROVIDERS:
        raise UnknownReceiverProvider(
            f"unknown receiver provider {provider!r}; "
            f"expected one of {RECEIVER_TOKEN_PROVIDERS}"
        )


def generate_receiver_token() -> str:
    """A fresh opaque token: ``rcv_`` + 32 random bytes, url-safe.

    `token_urlsafe` is used rather than a UUID because this value is a
    URL path segment: it must survive being pasted into a vendor form,
    and it must not be mistakable for an identifier someone can look up.
    """
    return f"{RECEIVER_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def mint_receiver_token(
    client: Any,
    *,
    org_id: UUID,
    provider: str,
    label: str,
    created_by: Optional[UUID] = None,
) -> MintedReceiverToken:
    """Issue a new receiver token for `org_id` on `provider`.

    Does **not** revoke existing tokens. Rotation is deliberately
    issue-new → paste-new → confirm-traffic-moved → revoke-old: the
    Canal Pro field can only be changed by a human, so any order that
    revokes first drops every lead delivered in the gap, and Grupo OLX
    discards a lead permanently after 14 days with no replay API.
    """
    _require_known_provider(provider)

    plaintext = generate_receiver_token()
    # The id is generated HERE, not left to the column's
    # `DEFAULT gen_random_uuid()`. The default stays for hand-written
    # inserts, but relying on it would make this function depend on what
    # the driver returns from `INSERT ... RETURNING`, which is exactly the
    # kind of behaviour a test double gets to decide for itself — and
    # `MockSupabaseClient` returns a synthetic string id, not a UUID.
    # Generating it client-side makes the mock and Postgres agree by
    # construction instead of by coincidence.
    token_id = uuid4()
    row = {
        "id": str(token_id),
        "org_id": str(org_id),
        "provider": provider,
        "token_hash": hash_token(plaintext),
        "token_prefix": plaintext[:_PREFIX_CHARS],
        "label": label,
        "created_by": str(created_by) if created_by else None,
    }

    client.table(_TABLE).insert(row).execute()

    return MintedReceiverToken(
        id=token_id,
        org_id=org_id,
        provider=provider,
        label=label,
        plaintext=plaintext,
        token_prefix=row["token_prefix"],
    )


def resolve_receiver_token(
    client: Any, *, provider: str, token: str
) -> Optional[UUID]:
    """Resolve a URL path segment to the org it routes to.

    Returns ``None`` for every failure mode — wrong prefix, unknown
    provider, no match, revoked, malformed row, DB error. The caller
    decides what a ``None`` means, and for the lead receiver that is
    emphatically **not** a 4xx: an unresolvable token still arrived with
    a valid CRM secret, so it is far more likely a rotated token than an
    attack, and refusing it would ask Grupo OLX to redeliver three times
    and then throw a real customer away.
    """
    if not token or not token.startswith(RECEIVER_TOKEN_PREFIX):
        return None
    if provider not in RECEIVER_TOKEN_PROVIDERS:
        # Not raised: this is the receive path, and a typed exception
        # here would surface as a 500 on a delivery we could otherwise
        # park cleanly.
        logger.warning(
            "receiver-token: unknown provider %r on resolve", provider
        )
        return None

    digest = hash_token(token)

    try:
        response = (
            client.table(_TABLE)
            .select("id, org_id")
            .eq("token_hash", digest)
            .eq("provider", provider)
            .is_("revoked_at", None)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception(
            "receiver-token: lookup failed provider=%s digest_prefix=%s",
            provider,
            digest[:8],
        )
        return None

    rows = list(response.data or [])
    if not rows:
        return None

    row = rows[0]
    try:
        token_id = UUID(str(row["id"]))
        org_id = UUID(str(row["org_id"]))
    except (KeyError, ValueError, TypeError):
        logger.warning(
            "receiver-token: row malformed digest_prefix=%s keys=%s",
            digest[:8],
            list(row.keys()) if isinstance(row, dict) else type(row).__name__,
        )
        return None

    _touch_last_seen(client, token_id)
    return org_id


def _touch_last_seen(client: Any, token_id: UUID) -> None:
    """Best-effort `last_seen_at` bump.

    Failure is logged and swallowed **here and only here**: this is a
    statistics write on the delivery hot path, and letting it fail a
    delivery would trade a real lead for a timestamp. Every other
    swallow in this module is a documented `None` return, not silence.
    """
    try:
        (
            client.table(_TABLE)
            .update({"last_seen_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(token_id))
            .execute()
        )
    except Exception:
        logger.warning(
            "receiver-token: last_seen_at bump failed token_id=%s", token_id
        )


def list_receiver_tokens(
    client: Any, *, org_id: UUID, provider: Optional[str] = None
) -> list[dict]:
    """Rows for the operator card. Never includes a plaintext token."""
    if provider is not None:
        _require_known_provider(provider)

    query = (
        client.table(_TABLE)
        .select("id, provider, label, token_prefix, created_at, last_seen_at, revoked_at")
        .eq("org_id", str(org_id))
    )
    if provider is not None:
        query = query.eq("provider", provider)

    response = query.order("created_at", desc=True).execute()
    return list(response.data or [])


def revoke_receiver_token(client: Any, *, org_id: UUID, token_id: UUID) -> bool:
    """Revoke one token. Returns whether a row was actually revoked.

    The `org_id` filter is not redundant with RLS: this runs on the admin
    client in the router, so it is the only thing standing between an
    org-scoped caller and another org's token.
    """
    response = (
        client.table(_TABLE)
        .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", str(token_id))
        .eq("org_id", str(org_id))
        .is_("revoked_at", None)
        .execute()
    )
    return bool(response.data)


__all__ = [
    "MintedReceiverToken",
    "RECEIVER_TOKEN_PREFIX",
    "RECEIVER_TOKEN_PROVIDERS",
    "UnknownReceiverProvider",
    "generate_receiver_token",
    "list_receiver_tokens",
    "mint_receiver_token",
    "resolve_receiver_token",
    "revoke_receiver_token",
]
