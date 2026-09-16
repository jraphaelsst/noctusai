"""Credential management for the agents control plane (contract §B.0 /
§D / §E.5 notes, 2026-09-16).

- ``registry``  — the fixed credential set (scopes/targets are server-side).
- ``resolver``  — DB-first / env-fallback reads, short-TTL cached.
- ``prober``    — live "Testar" health checks.
- ``service``   — status / set / import / renew / §D ring rotation / alerts.
- ``alerts``    — 30-day expiry notifications for platform admins.
"""
from __future__ import annotations

from typing import Any

from app.credentials.resolver import (
    CredentialResolver,
    get_config_store_handle,
    get_credential_resolver,
)
from app.credentials.service import CredentialService

__all__ = [
    "CredentialResolver",
    "CredentialService",
    "build_credential_service",
    "get_credential_resolver",
]


def build_credential_service(settings: Any) -> CredentialService:
    """Production composition — the route dependency and the daily job both
    use this, tests override the route dependency instead."""
    from noctusai_lib.api.auth.session import make_product_token_admin

    from app.credentials.prober import get_credential_prober

    admin_client = None
    if getattr(settings, "supabase_service_role_key", ""):
        from app.dependencies import get_admin_client

        admin_client = get_admin_client()
    return CredentialService(
        handle=get_config_store_handle(settings),
        settings=settings,
        token_admin=make_product_token_admin(admin_client),
        prober=get_credential_prober(),
    )
