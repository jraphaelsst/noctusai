"""
Supabase database client setup.

All seed product tables live in the "{{SCHEMA_NAME}}" schema.
The make_supabase_client call passes schema="{{SCHEMA_NAME}}" so supabase-py sends
Accept-Profile / Content-Profile headers, routing queries to the correct schema.
"""
from typing import Optional
from supabase import Client
from noctusai_shared.database import make_supabase_client
from app.config import settings


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    """
    Create a Supabase client targeting the "{{SCHEMA_NAME}}" schema.

    Args:
        access_token: If provided, creates a client authenticated as this user.
                      If None, uses the service role key (admin access).
    """
    return make_supabase_client(
        url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
        service_role_key=settings.supabase_service_role_key,
        schema="{{SCHEMA_NAME}}",
        access_token=access_token,
    )


def get_core_client() -> Client:
    """Create a Supabase client targeting the `public` schema.

    Used for platform-level tables (notifications, etc.) that live in the
    core schema, not in the product-specific schema.
    """
    return make_supabase_client(
        url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
        service_role_key=settings.supabase_service_role_key,
        schema="public",
    )


supabase_admin: Client = get_supabase_client() if settings.supabase_service_role_key else None
