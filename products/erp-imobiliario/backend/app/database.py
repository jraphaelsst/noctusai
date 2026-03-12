"""
Supabase database client setup.

All ERP tables live in the `erp` schema. The make_supabase_client call
passes schema="erp" so supabase-py sends `Accept-Profile: erp` /
`Content-Profile: erp` headers, routing .table() and .rpc() calls to
the correct schema.
"""
from typing import Optional
from supabase import Client
from noctusai_shared.database import make_supabase_client
from app.config import settings


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    """
    Create a Supabase client targeting the `erp` schema.

    Args:
        access_token: If provided, creates a client authenticated as this user.
                      If None, uses the service role key (admin access).
    """
    return make_supabase_client(
        url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
        service_role_key=settings.supabase_service_role_key,
        schema="erp",
        access_token=access_token,
    )


# Service role client singleton for backend operations
supabase_admin: Client = get_supabase_client() if settings.supabase_service_role_key else None
