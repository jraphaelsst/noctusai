"""DB-first / env-fallback credential resolution for the agents control plane.

WHY the seed `AppConfigStore` seam and NOT `resolve_credential`
--------------------------------------------------------------
`noctusai_lib.config.credentials.resolve_credential` walks
``override → org_settings → platform_settings → env``. Its tier 2
(`public.platform_settings`) is the platform-WIDE default — a row
``anthropic_api_key`` there is a key other products share, and it would be
served to Julia BEFORE her dedicated env key. Contract §E.5 forbids exactly
that ("a dedicated, spend-capped key ... never shared"). So this module uses
the seed's other credential-resolution seam — the encrypted app-wide store
(`noctusai_lib.security.app_config`, the one social-wiring uses for its Meta
app keys) with `resolve_app_config_value`: this product's own row wins, the
env value is the fallback, nothing else is consulted.

Freshness: the store is wrapped in `CachedAppConfigStore`
(`credential_cache_ttl_seconds`, default 30 s) and every consumer resolves
at USE time (per request / per turn), so an in-app change is live in this
process at once and in every other worker within the TTL — no redeploy.

§E.5 invariant: nothing here touches `os.environ`; the only secret that
reaches the Julia CLI is the Anthropic key, handed to the `env -i` wrapper
through `ClaudeAgentOptions.env` (app/runtime/claude_runtime.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet

from noctusai_lib.config.deploy_config import MissingProdConfigError, is_deploy_context
from noctusai_lib.security.app_config import (
    AppConfigStore,
    CachedAppConfigStore,
    FakeAppConfigStore,
    RealAppConfigStore,
    resolve_app_config_value,
)
from noctusai_lib.security.key_ring import KeyRing, resolve_key_ring

from app.credentials.registry import (
    ACADEMIA_API_TOKEN,
    ANTHROPIC_API_KEY,
    APPROVAL_RING,
    JULIA_AGENT_ID,
    SOCIAL_WIRING_API_TOKEN,
    CredentialSpec,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigStoreHandle",
    "CredentialResolver",
    "get_config_store_handle",
    "get_credential_resolver",
    "install_config_store_handle",
    "require_resolved_prod_config",
    "reset_for_testing",
]

_TABLE = "app_integration_config"


@dataclass(frozen=True)
class ConfigStoreHandle:
    """The store plus whether writes to it are durable.

    ``persistent`` is False when no service-role key or no valid
    ``ENCRYPTION_KEY`` is configured — the store is then an in-memory Fake:
    fine for dev, but a write in a deploy context would vanish on restart,
    so the service refuses it (503) instead.
    """

    store: AppConfigStore
    persistent: bool
    reason: str | None = None


class _LazyAgentsTable:
    """``.table()`` resolved per call against the product's admin client
    (schema ``agents``) — nothing is built at import, and a test that swaps
    the database module's client is honoured."""

    def table(self, name: str):
        from app.dependencies import get_admin_client

        return get_admin_client().table(name)


#: One handle per settings object (the app's is a process singleton — the
#: TTL cache must be shared to be useful). Keyed like the seed's session
#: store, so an ad-hoc settings object never inherits the app's store.
_handles: dict[int, ConfigStoreHandle] = {}


def install_config_store_handle(settings: Any, handle: ConfigStoreHandle) -> None:
    """Explicit DI seam: bind ``handle`` to ``settings`` (tests install a
    Fake so the suite never reaches a real database via a local `.env`)."""
    _handles[id(settings)] = handle


def get_config_store_handle(settings: Any) -> ConfigStoreHandle:
    handle = _handles.get(id(settings))
    if handle is None:
        ttl = float(getattr(settings, "credential_cache_ttl_seconds", 30) or 0)
        key = getattr(settings, "encryption_key", "") or ""
        reason: str | None = None
        inner: AppConfigStore
        if not getattr(settings, "supabase_service_role_key", ""):
            reason = "SUPABASE_SERVICE_ROLE_KEY ausente"
        elif not key:
            reason = "ENCRYPTION_KEY ausente"
        else:
            try:
                Fernet(key.encode("utf-8"))
            except (ValueError, TypeError):
                reason = "ENCRYPTION_KEY inválida"
        if reason is None:
            inner = RealAppConfigStore(_LazyAgentsTable(), key.encode("utf-8"), table=_TABLE)
        else:
            inner = FakeAppConfigStore()
            log = logger.error if is_deploy_context() else logger.info
            log("agents.credential_store.disabled reason=%s — env values only", reason)
        handle = ConfigStoreHandle(
            store=CachedAppConfigStore(inner, ttl_seconds=ttl),
            persistent=reason is None,
            reason=reason,
        )
        _handles[id(settings)] = handle
    return handle


def reset_for_testing() -> None:
    _handles.clear()


class CredentialResolver:
    """Reads one credential at a time; never caches beyond the store's TTL."""

    def __init__(self, store: AppConfigStore, settings: Any) -> None:
        self._store = store
        self._settings = settings

    def _env(self, spec: CredentialSpec) -> str | None:
        return (getattr(self._settings, spec.settings_attr, "") or "") or None

    def resolve(self, spec: CredentialSpec) -> tuple[str | None, str | None]:
        """``(value, source)`` with ``source`` in ``{"db", "env", None}``."""
        return resolve_app_config_value(self._store, spec.store_key, env_value=self._env(spec))

    def value(self, spec: CredentialSpec) -> str | None:
        return self.resolve(spec)[0]

    # ── typed accessors the runtime uses ───────────────────────────────

    def anthropic_api_key(self) -> str | None:
        return self.value(ANTHROPIC_API_KEY)

    def academia_api_token(self) -> str | None:
        return self.value(ACADEMIA_API_TOKEN)

    def social_wiring_api_token(self) -> str | None:
        return self.value(SOCIAL_WIRING_API_TOKEN)

    def approval_ring(self) -> KeyRing:
        return resolve_key_ring(self._store, APPROVAL_RING.store_key, env_value=self._env(APPROVAL_RING))

    def approval_signing_secret(self, now: datetime | None = None) -> str | None:
        key = self.approval_ring().signing_key(now or datetime.now(timezone.utc))
        return key.secret if key else None

    def julia_agent_id(self) -> UUID | None:
        raw = self.value(JULIA_AGENT_ID)
        if not raw:
            return None
        try:
            return UUID(raw)
        except ValueError:
            logger.error("agents.julia_agent_id_malformed — ignoring the configured value")
            return None


def get_credential_resolver(settings: Any) -> CredentialResolver:
    return CredentialResolver(get_config_store_handle(settings).store, settings)


def require_resolved_prod_config(resolver: CredentialResolver) -> None:
    """Deploy-context guard over RESOLVED values (DB or env) — the
    DB-aware successor of `require_prod_config([...])` for the four keys
    the Julia runtime needs. Lists every gap at once."""
    if not is_deploy_context():
        return
    missing = [
        env
        for env, present in (
            ("ANTHROPIC_API_KEY", bool(resolver.anthropic_api_key())),
            ("APPROVAL_ASSERTION_SECRETS", bool(resolver.approval_signing_secret())),
            ("ACADEMIA_API_TOKEN", bool(resolver.academia_api_token())),
            ("JULIA_AGENT_ID", resolver.julia_agent_id() is not None),
        )
        if not present
    ]
    if missing:
        raise MissingProdConfigError(missing)
