"""
NoctusAI Core — Supabase database client.

Core uses the default "public" schema (no schema override needed).
"""
from typing import Optional
from supabase import Client
from noctusai_lib.database import make_supabase_client
from app.config import settings


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    """
    Create a Supabase client targeting the default public schema.

    Args:
        access_token: If provided, creates a client authenticated as this user.
                      If None, uses the service role key (admin access).
    """
    return make_supabase_client(
        url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
        service_role_key=settings.supabase_service_role_key,
        schema=None,
        access_token=access_token,
    )


def get_admin_client() -> Client:
    """Get a Supabase client with service role (bypasses RLS)."""
    return get_supabase_client()


# Service role client singleton for backend operations (e.g. SSO session generation)
supabase_admin: Client = get_supabase_client() if settings.supabase_service_role_key else None
