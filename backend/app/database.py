"""
Supabase database client setup.
"""
from supabase import create_client, Client
from app.config import settings


def get_supabase_client(access_token: str | None = None) -> Client:
    """
    Create a Supabase client.

    Args:
        access_token: If provided, creates a client authenticated as this user.
                      If None, uses the service role key (admin access).
    """
    if access_token:
        # Client authenticated as the user (respects RLS)
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        client.auth.set_session(access_token, "")
        return client
    else:
        # Service role client (bypasses RLS — use for server-side operations)
        return create_client(settings.supabase_url, settings.supabase_service_role_key)


# Service role client singleton for backend operations
supabase_admin: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key
) if settings.supabase_service_role_key else None
