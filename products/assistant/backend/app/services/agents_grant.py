"""The platform grant that wires an org to the `agents` product (KB § PATTERNS/backend/platform-grants.md), product half.

`agents` MINTS the owner-assistant agent's personal channel token and DELIVERS it (`PUT /api/platform/grants/agents`, a one-shot
delivery token); nobody pastes it. This module is what the Assistant does with it:

* `on_grant`  -> the credential is stored Fernet-encrypted in `assistant.agent_grants` (the seed `CredentialStore`, key
  `ENCRYPTION_KEY`, one row per org) with its non-secret metadata (grant id, agent key, token prefix); a re-grant replaces it.
  The append-only `agent_grants_eventos` row (concedido / rotacionado) is written by a trigger in the same transaction.
* `on_revoke` -> the row is deleted (idempotent); the trigger writes `revogado`.
* `acesso_do_org(org_id)` -> what the live reply needs for ONE org: the channel client + the agent key, or `None` when the org
  has no live grant. A missing grant is a declared refusal to reply, never a Fake and never a boot failure.

The credential is a secret: it is never logged, never echoed. Only its prefix (metadata) is ever shown.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.agents_channel import AgentsClient, make_agents_client
from noctusai_lib.security.api_keys import require_fernet
from noctusai_lib.security.token_store import make_credential_store
from noctusai_seed.platform_grants_router import GrantReceived, GrantRevoked, create_platform_grants_router

from app.config import settings

logger = logging.getLogger(__name__)

#: `provider` of the row (the CHECK in migration 023 allows only this one); `table` of the seed credential store.
PROVIDER = "agents"
TABLE = "agent_grants"
_META_FIELDS = ("grant_id", "agent_key", "token_prefix", "scopes", "expires_at")

# DI slot (never an import-time singleton): ``None`` = build the real encrypted store per call.
_store_factory: Optional[Callable[[], Any]] = None


def configure_grant_store(store_factory: Optional[Callable[[], Any]] = None) -> None:
    """Set (or, with ``None``, reset) the credential-store factory."""
    global _store_factory
    _store_factory = store_factory


def _store() -> Any:
    if _store_factory is not None:
        return _store_factory()
    from app.dependencies import get_admin_client

    # Raises EncryptionNotConfigured when ENCRYPTION_KEY is unusable: a deploy gap, never a plaintext write.
    require_fernet(settings.encryption_key)
    return make_credential_store(client=get_admin_client(), fernet_key=settings.encryption_key.encode("utf-8"), table=TABLE)


def on_grant(grant: GrantReceived) -> None:
    store = _store()
    meta: dict[str, Any] = {k: grant.metadata.get(k) for k in _META_FIELDS if grant.metadata.get(k) is not None}
    meta["agent_id"] = grant.agent_id
    store.put(str(grant.org_id), PROVIDER, {"value": grant.credential}, metadata=meta)
    logger.info("assistant: agents grant stored org=%s grant_id=%s", grant.org_id, meta.get("grant_id"))


def on_revoke(revoked: GrantRevoked) -> None:
    removed = _store().delete(str(revoked.org_id), PROVIDER)
    logger.info("assistant: agents grant revoked org=%s existed=%s", revoked.org_id, removed)


def build_router(get_auth_context: Callable[..., Any]):
    """The seed receiver (`PUT/DELETE /api/platform/grants/agents`) wired to this sink."""
    return create_platform_grants_router(
        get_auth_context=get_auth_context, on_grant=on_grant, on_revoke=on_revoke, issuer="agents",
    )


# ── what the live reply reads ─────────────────────────────────────────────────
@dataclass(frozen=True)
class AgentsAccess:
    """The agents channel for ONE org: its client (bearer = the org's grant token) and the agent the grant names."""

    client: AgentsClient
    agent_key: str


def _expirada(expires_at: Any) -> bool:
    if not expires_at:
        return False
    try:
        when = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("assistant: unparseable agents grant expires_at -- treated as expired")
        return True  # fail closed: an expiry we cannot read is not a live grant
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= datetime.now(timezone.utc)


def agents_base_url() -> Optional[str]:
    try:
        return resolve_product_url("agents")
    except ValueError:
        logger.warning("assistant: cannot resolve the agents base URL (PRODUCT_URL_AGENTS unset)")
        return None


def acesso_do_org(org_id: UUID | str, *, store: Any = None) -> Optional[AgentsAccess]:
    """The org's live agents access, or ``None`` (no grant / expired / no agent key / no agents URL). A store that cannot be
    READ (decrypt error, DB down) raises: the caller records an error, it must not read as "not granted"."""
    row = (store or _store()).get(str(org_id), PROVIDER)
    if row is None:
        return None
    token = (row.tokens or {}).get("value")
    meta = row.metadata or {}
    agent_key = meta.get("agent_key")
    if not token or not agent_key or _expirada(meta.get("expires_at")):
        return None
    client = make_agents_client(token=token, base_url=agents_base_url(), allow_fake=False)
    return AgentsAccess(client=client, agent_key=str(agent_key)) if client is not None else None
