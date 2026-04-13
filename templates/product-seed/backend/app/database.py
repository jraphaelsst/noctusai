"""
{{PRODUCT_NAME}} — Supabase client targeting the '{{SCHEMA_NAME}}' schema.
"""
from noctusai_shared.database import make_supabase_client
from app.config import settings

SCHEMA = "{{SCHEMA_NAME}}"


def get_supabase_client(access_token: str | None = None):
    """Get a Supabase client targeting the product schema.

    - With access_token: authenticates as user (respects RLS)
    - Without: uses service role key (admin access, bypasses RLS)
    """
    return make_supabase_client(
        url=settings.supabase_url,
        key=settings.supabase_service_role_key if not access_token else settings.supabase_anon_key,
        schema=SCHEMA,
        access_token=access_token,
    )


def get_admin_client():
    """Service role client — bypasses RLS. Use for admin operations."""
    return get_supabase_client()


def get_user_client(token: str):
    """User-authenticated client — respects RLS."""
    return get_supabase_client(access_token=token)


def get_core_client():
    """Client targeting the 'public' schema for platform-level tables (notifications, etc.)."""
    return make_supabase_client(
        url=settings.supabase_url,
        key=settings.supabase_service_role_key,
        schema="public",
    )
