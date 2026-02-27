"""
Supabase database client setup.

All ERP tables live in the `erp` schema. The ClientOptions(schema="erp")
tells supabase-py to send `Accept-Profile: erp` / `Content-Profile: erp`
headers so PostgREST routes .table() and .rpc() calls to the correct schema.
"""
from typing import Optional
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from app.config import settings

ERP_OPTIONS = ClientOptions(schema="erp")


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    """
    Create a Supabase client targeting the `erp` schema.

    Args:
        access_token: If provided, creates a client authenticated as this user.
                      If None, uses the service role key (admin access).
    """
    if access_token:
        # Client authenticated as the user (respects RLS)
        client = create_client(settings.supabase_url, settings.supabase_anon_key, options=ERP_OPTIONS)
        client.auth.set_session(access_token, "")
        return client
    else:
        # Service role client (bypasses RLS — use for server-side operations)
        return create_client(settings.supabase_url, settings.supabase_service_role_key, options=ERP_OPTIONS)


# Service role client singleton for backend operations
supabase_admin: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
    options=ERP_OPTIONS
) if settings.supabase_service_role_key else None
