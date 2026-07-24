"""Meta (Facebook + Instagram) — thin product seam over the seed.

The hand-rolled ~1.3k-LoC Meta fork (`_meta_api.py`, `oauth_adapter.py`,
`fake_adapter.py`, `mappers.py`, `types.py`) was retired by
`social-wiring-meta-seed-consume` — the product now consumes the canonical
`noctusai_lib.integrations.meta` (Protocol + Fake + Real(dual-auth) +
factory + `make_meta_router` + scope auto-discovery), exactly as the
Google-stack consume migration did for Calendar/Drive/YouTube.

This module is a **zero-API-logic shim**:

- It re-exports the seed value objects, adapters, factory, error type,
  OAuth helpers, mappers, and scope helpers under the seed's canonical
  names so existing app imports keep working.
- It provides one product-convention wrapper, :func:`get_meta_adapter`,
  that adapts the local call shape (`org_id`, `credential_store`,
  product `settings`) onto the seed factory (`system_user_token`,
  `credential_store`, `org_id`). The system-user-token is read from
  product ``settings`` (or env) — the seed factory takes it explicitly.
- ``META_PROVIDER`` is re-exported from the seed credential-resolvers
  module (the credential-vault storage key, ``"meta"``).

There is **no Graph URL, no httpx call, no token logic** here — all of
that lives in the seed. See ``KB § INTEGRATIONS/meta.md``.
"""
from __future__ import annotations

import logging
from uuid import UUID

from noctusai_lib.integrations.credential_resolvers import META_PROVIDER
from noctusai_lib.integrations.meta import (
    FacebookPage,
    FacebookPost,
    FakeMetaAdapter,
    InstagramAccount,
    InstagramMedia,
    MetaAdapter,
    MetaConnectionStatus,
    MetaGraphError,
    PostInsights,
)
from noctusai_lib.integrations.meta import get_meta_adapter as _seed_get_meta_adapter
from noctusai_lib.integrations.meta.oauth_adapter import MetaOAuthAdapter

from app.config import settings as default_settings
from app.dependencies import get_admin_client
from app.services.integration_account_service import IntegrationAccountNotFound
from app.utils import has_oauth_credential

logger = logging.getLogger(__name__)

__all__ = [
    "FacebookPage",
    "FacebookPost",
    "FakeMetaAdapter",
    "InstagramAccount",
    "InstagramMedia",
    "META_PROVIDER",
    "MetaAdapter",
    "MetaConnectionStatus",
    "MetaGraphError",
    "MetaOAuthAdapter",
    "PostInsights",
    "get_meta_adapter",
    "get_meta_adapter_for_account",
]


def get_meta_adapter(
    *,
    org_id: UUID | str | None = None,
    credential_store=None,
    settings=None,
) -> MetaAdapter:
    """Resolve the Meta adapter for this product's call convention.

    Adapts the local arguments onto the seed factory
    (``noctusai_lib.integrations.meta.get_meta_adapter``):

    - ``settings.meta_system_user_token`` → seed ``system_user_token``
      (Priority 1: production, Business-Portfolio-owned assets).
    - ``credential_store`` + ``org_id`` AND a stored ``(org, meta)`` row
      → the seed's convenience path, which builds a
      ``CredentialStoreMetaResolver`` internally (Priority 2: per-tenant
      user-OAuth credential).
    - Neither configured (or no stored row) → ``FakeMetaAdapter``.

    The **no-stored-row → Fake** short-circuit preserves the product's
    pre-seed-consume behavior: the seed factory would otherwise build a
    live ``MetaOAuthAdapter`` that raises ``MetaGraphError`` at call
    time, turning the chatbot's clean ``meta_not_connected`` ("connect
    at /api/meta/oauth/start") into a confusing graph error. The product
    seam keeps the friendly not-connected signal — never degrading the
    consumer.

    ``graph_version`` is pinned to the product's
    ``settings.meta_graph_api_version`` so the live adapter targets the
    same Graph version the OAuth router builds consent URLs against.
    """
    settings = settings or default_settings
    # System-User token resolves DB-first (prod: Fernet-encrypted in
    # `app_integration_config`) with env fallback (dev: root `.env`) — the
    # `feedback_dev_prod_key_storage_model` contract. Prod carries NO Meta
    # env vars, so an env-only read here would fall straight through to the
    # per-org OAuth path / the Fake and the whole Meta integration would
    # read as not-connected in prod.
    from app.services.app_config_store import resolve_meta_ads_config

    system_user_token, _acct, _org = resolve_meta_ads_config(settings=settings)
    graph_version = getattr(settings, "meta_graph_api_version", None) or None
    org_str = str(org_id) if org_id is not None else None

    # Priority 1 — System User Token (workspace-global; no org/store).
    if system_user_token:
        return _seed_get_meta_adapter(
            system_user_token=system_user_token, graph_version=graph_version
        )

    # Priority 2 — user-OAuth, but ONLY when a credential row exists for
    # this org (mirrors the retired product factory's `_has_oauth_credential`
    # gate). Absent → fall through to the Fake. App ID/secret resolve
    # DB-first (Settings-writable), env as fallback — see app_config_store.
    from app.services.app_config_store import resolve_meta_app_creds

    app_id, app_secret = resolve_meta_app_creds(settings=settings)
    if (
        org_str is not None
        and credential_store is not None
        and app_id
        and app_secret
        and has_oauth_credential(credential_store, org_str, META_PROVIDER, require_token=True)
    ):
        return _seed_get_meta_adapter(
            credential_store=credential_store,
            org_id=org_str,
            graph_version=graph_version,
        )

    return FakeMetaAdapter()


def get_meta_adapter_for_account(
    account_id: "UUID | str",
    org_id: "UUID | str",
    *,
    svc=None,
) -> MetaAdapter:
    """Build a user-OAuth :class:`MetaOAuthAdapter` bound to ONE per-client
    Meta ``integration_accounts`` row (store B — the Wave 2 per-client Meta
    connection; distinct from ``get_meta_adapter``'s org-level store-A
    credential + system-user-token resolution above).

    Resolves the account's decrypted long-lived token via
    :meth:`IntegrationAccountService.decrypt_credential` (through
    :class:`~app.services.account_credentials.MultiAccountCredentialStore`
    pinned to ``account_id``, the SAME seam ``resolve_account_by_id`` +
    the per-provider service factories use — no duplicated decrypt/adapter
    logic here) and constructs the seed adapter via the canonical
    ``noctusai_lib.integrations.meta.get_meta_adapter`` factory
    (``credential_store=`` path → ``auth_mode="user_oauth"``).

    Fails loud (mirrors every other per-account accessor in this product —
    ``account_credentials.resolve_account_by_id`` / ``run_for_account`` all
    take ``org_id`` alongside ``account_id``, defense-in-depth on top of
    RLS even though the caller here is already admin-scoped): raises
    ``IntegrationAccountNotFound`` when the row doesn't exist for that org,
    or ``ValueError`` when it exists but isn't a ``provider="meta"`` row —
    never a silently-degraded Fake (Wave 3 callers already know they're
    asking for a specific, previously-connected Meta account).

    ``svc`` is a DI seam (tests inject a
    :class:`~app.services.integration_account_service.IntegrationAccountService`
    built over a fake admin client) — defaults to the real
    ``build_integration_account_service(get_admin_client(), ...)``.
    """
    from app.services.account_credentials import MultiAccountCredentialStore
    from app.services.integration_account_service import (
        build_integration_account_service,
    )

    account_uuid = account_id if isinstance(account_id, UUID) else UUID(str(account_id))
    org_uuid = org_id if isinstance(org_id, UUID) else UUID(str(org_id))

    if svc is None:
        svc = build_integration_account_service(
            get_admin_client(), encryption_key=default_settings.encryption_key
        )

    account = svc.get_account(account_uuid, org_uuid)
    if account is None:
        raise IntegrationAccountNotFound(
            f"integration account {account_uuid} not found for org {org_uuid}"
        )
    if account.provider != META_PROVIDER:
        raise ValueError(
            f"integration account {account_uuid} is provider={account.provider!r}, "
            f"expected {META_PROVIDER!r}"
        )

    store = MultiAccountCredentialStore(svc, META_PROVIDER, account_id=account_uuid)
    graph_version = getattr(default_settings, "meta_graph_api_version", None) or None
    return _seed_get_meta_adapter(
        credential_store=store,
        org_id=str(org_uuid),
        graph_version=graph_version,
    )


