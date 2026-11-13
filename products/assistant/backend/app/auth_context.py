"""The Assistant's `get_auth_context`: a PRODUCT-TOKEN door (the platform grant receiver), nothing more.

The Assistant's own UI keeps its Supabase-JWT dependency (`app.dependencies.get_current_user_org`); this one exists for the
`PUT/DELETE /api/platform/grants/agents` call `agents` makes with a one-shot delivery token minted into `assistant.api_tokens`
(KB § PATTERNS/backend/platform-grants.md). No legacy-JWT bridge is wired: a JWT bearer is a strict 401 here, and so is no
credential at all. The resolver and the session store are lazy (the admin client must not resolve at import time).
"""
from __future__ import annotations

from noctusai_lib.api.auth.session import SupabaseApiTokenResolver, make_get_auth_context
from noctusai_seed.auth_router import get_session_store as _seed_get_session_store

from app.config import settings
from app.dependencies import get_admin_client

_resolver: SupabaseApiTokenResolver | None = None


def _get_resolver() -> SupabaseApiTokenResolver:
    global _resolver
    if _resolver is None:
        _resolver = SupabaseApiTokenResolver(get_admin_client(), schema="assistant")
    return _resolver


class _LazyApiTokenResolver:
    async def resolve(self, token_secret):
        return await _get_resolver().resolve(token_secret)


class _LazySessionStore:
    """Same process-local store the seed auth composition uses (no cookie is ever minted for this door)."""

    async def create(self, **kwargs):
        return await _seed_get_session_store(settings).create(**kwargs)

    async def lookup(self, session_id):
        return await _seed_get_session_store(settings).lookup(session_id)

    async def refresh_ttl(self, session_id, ttl_seconds=86400):
        return await _seed_get_session_store(settings).refresh_ttl(session_id, ttl_seconds)

    async def delete(self, session_id):
        return await _seed_get_session_store(settings).delete(session_id)


get_auth_context = make_get_auth_context(
    session_store=_LazySessionStore(),
    api_token_resolver=_LazyApiTokenResolver(),
    legacy_jwt_resolver=None,
    session_cookie_name="nai_session",
)
