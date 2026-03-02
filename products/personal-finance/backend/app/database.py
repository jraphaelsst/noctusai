"""
Supabase database client setup.

All personal-finance tables live in the "personal-finance" schema.
The ClientOptions(schema="personal-finance") tells supabase-py to send
Accept-Profile / Content-Profile headers so PostgREST routes queries
to the correct schema.
"""
from typing import Optional
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from app.config import settings

PF_OPTIONS = ClientOptions(schema="personal-finance")


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    """
    Create a Supabase client targeting the "personal-finance" schema.

    Args:
        access_token: If provided, creates a client authenticated as this user.
                      If None, uses the service role key (admin access).
    """
    if access_token:
        client = create_client(settings.supabase_url, settings.supabase_anon_key, options=PF_OPTIONS)
        client.auth.set_session(access_token, "")
        return client
    else:
        return create_client(settings.supabase_url, settings.supabase_service_role_key, options=PF_OPTIONS)


supabase_admin: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
    options=PF_OPTIONS
) if settings.supabase_service_role_key else None
