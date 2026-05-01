"""
Supabase database client factory for all NoctusAI backends.

Provides a parameterized factory function that each product backend
calls with its own schema and settings. The factory handles both
user-authenticated clients (RLS) and service-role clients (admin).
"""
from __future__ import annotations

from typing import Optional
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions


def make_supabase_client(
    url: str,
    anon_key: str,
    service_role_key: str,
    schema: Optional[str] = None,
    access_token: Optional[str] = None,
) -> Client:
    """
    Create a Supabase client with the given configuration.

    Args:
        url: Supabase project URL
        anon_key: Supabase anon/public key
        service_role_key: Supabase service role key (admin access)
        schema: PostgreSQL schema to target (e.g., "erp", "personal-finance").
                None uses the default "public" schema.
        access_token: If provided, creates a client authenticated as this user
                      (respects RLS). If None, uses the service role key.

    Returns:
        Configured Supabase Client instance
    """
    options = ClientOptions(schema=schema) if schema else ClientOptions()

    if access_token:
        # Client authenticated as the user (respects RLS)
        client = create_client(url, anon_key, options=options)
        client.auth.set_session(access_token, "")
        return client
    else:
        # Service role client (bypasses RLS — use for server-side operations)
        return create_client(url, service_role_key, options=options)
