"""Meta (Facebook + Instagram) Graph API package.

Three-tier factory:

1. **System User Token path** — when ``META_SYSTEM_USER_TOKEN`` is
   set in env. Production-grade backend automation against Business
   Portfolio-owned Pages + IG accounts. Token never expires, doesn't
   require user consent, and is the **only path that works for
   BM-owned assets in modern Meta dev mode**. Recommended for any
   server-to-server use case.

2. **User OAuth path** — when ``META_APP_ID`` / ``META_APP_SECRET``
   are configured AND the org has a stored credential row
   (provider=``meta``). Use this for end-user-facing flows where each
   user consents to read their OWN Pages (not Pages owned by a
   Business Portfolio).

3. **Fallback** — :class:`FakeMetaAdapter`. Local dev + tests; the
   chatbot tools treat it as "not connected" but still answer with
   a structured payload.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from app.config import settings as default_settings
from app.services.meta.fake_adapter import FakeMetaAdapter
from app.services.meta.oauth_adapter import META_PROVIDER, MetaOAuthAdapter
from app.services.meta.types import (
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    MetaAdapter,
    MetaConnectionStatus,
    PostInsights,
)

if TYPE_CHECKING:
    from app.services.credential_store import CredentialStore

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
    "MetaOAuthAdapter",
    "PostInsights",
    "get_meta_adapter",
]


def get_meta_adapter(
    *,
    org_id: UUID | None = None,
    credential_store: "CredentialStore | None" = None,
    settings=None,
) -> MetaAdapter:
    settings = settings or default_settings

    # Priority 1 — System User Token. Production path for BM-owned
    # assets; bypasses OAuth + credential store entirely. Works
    # without org_id / credential_store since the token is global to
    # the workspace (one System User serves all consumers).
    if getattr(settings, "meta_system_user_token", ""):
        logger.info("Meta adapter: MetaOAuthAdapter (system_user mode)")
        return MetaOAuthAdapter(
            credential_store=credential_store,
            org_id=org_id,
            settings=settings,
        )

    # Priority 2 — user OAuth credential. End-user-facing path.
    if (
        org_id is not None
        and credential_store is not None
        and getattr(settings, "meta_app_id", "")
        and getattr(settings, "meta_app_secret", "")
        and _has_oauth_credential(credential_store, org_id)
    ):
        logger.info("Meta adapter: MetaOAuthAdapter (user_oauth mode, org %s)", org_id)
        return MetaOAuthAdapter(
            credential_store=credential_store,
            org_id=org_id,
            settings=settings,
        )

    return FakeMetaAdapter()


def _has_oauth_credential(store: "CredentialStore", org_id: UUID) -> bool:
    try:
        return store.get(org_id=org_id, provider=META_PROVIDER) is not None
    except Exception:
        logger.exception("Meta OAuth credential lookup failed; skipping OAuth path")
        return False
