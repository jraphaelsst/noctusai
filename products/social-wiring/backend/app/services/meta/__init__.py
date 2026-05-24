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
    system_user_token = getattr(settings, "meta_system_user_token", "") or None
    graph_version = getattr(settings, "meta_graph_api_version", None) or None
    org_str = str(org_id) if org_id is not None else None

    # Priority 1 — System User Token (workspace-global; no org/store).
    if system_user_token:
        return _seed_get_meta_adapter(
            system_user_token=system_user_token, graph_version=graph_version
        )

    # Priority 2 — user-OAuth, but ONLY when a credential row exists for
    # this org (mirrors the retired product factory's `_has_oauth_credential`
    # gate). Absent → fall through to the Fake.
    if (
        org_str is not None
        and credential_store is not None
        and getattr(settings, "meta_app_id", "")
        and getattr(settings, "meta_app_secret", "")
        and _has_oauth_credential(credential_store, org_str)
    ):
        return _seed_get_meta_adapter(
            credential_store=credential_store,
            org_id=org_str,
            graph_version=graph_version,
        )

    return FakeMetaAdapter()


def _has_oauth_credential(store, org_id: str) -> bool:
    """True when the vault holds a usable ``(org, meta)`` OAuth row.

    Matches the retired product factory's gate: a stored row with a
    non-empty ``access_token``. Lookup failures are logged and treated
    as not-connected (never a silent swallow)."""
    try:
        stored = store.get(org_id, META_PROVIDER)
    except Exception:
        logger.exception("Meta OAuth credential lookup failed; treating as not-connected")
        return False
    return bool(stored is not None and getattr(stored, "tokens", {}).get("access_token"))
