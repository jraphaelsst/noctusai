"""
NoctusAI Core — Supabase database client (framework-delegated).

Thin wrapper over `noctusai_seed.create_database_module` that preserves
the historical public surface every core router imports from this module:
`get_supabase_client`, `get_admin_client`, `supabase_admin`.

Refactored by `projects/core-seed-wiring-v2/` Phase 1 (2026-04-23) from a
custom 35-LOC implementation → 12-LOC framework delegation. Behavior is
byte-identical: same Supabase client, same service-role fallback, same
per-schema targeting (`public`).
"""
from typing import Optional

from supabase import Client

from noctusai_seed import create_database_module
from app.config import settings

_db = create_database_module(settings, schema="public")


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    """Return a Supabase client targeting the public schema.

    With ``access_token``: user-authenticated (respects RLS).
    Without: service-role client (bypasses RLS).
    """
    return _db.get_client(access_token)


def get_admin_client() -> Client:
    """Cached service-role client (bypasses RLS)."""
    return _db.get_admin_client()


# Service-role singleton — some core services import this directly.
supabase_admin: Optional[Client] = (
    _db.get_admin_client() if settings.supabase_service_role_key else None
)
