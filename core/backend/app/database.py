"""
NoctusAI Core — Supabase database client.
"""
from typing import Optional
from supabase import create_client, Client
from app.config import settings


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    if access_token:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        client.auth.set_session(access_token, "")
        return client
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_admin_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# Service role client singleton for backend operations (e.g. SSO session generation)
supabase_admin: Client = create_client(
    settings.supabase_url, settings.supabase_service_role_key
) if settings.supabase_service_role_key else None
