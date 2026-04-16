"""
Database client factories for NoctusAI products.

Every product needs:
  - A client targeting its own schema (for product tables)
  - A client targeting the public schema (for core platform tables)
  - An admin client (service role, bypasses RLS)

Usage::

    from noctusai_seed import create_database_module

    db = create_database_module(settings, schema="mailing")

    # In routers/services:
    client = db.get_client(token)       # user-authenticated
    admin = db.get_admin_client()        # service role
    core = db.get_core_client()          # public schema
"""
from typing import Optional
from supabase import Client
from noctusai_shared.database import make_supabase_client


class DatabaseModule:
    """Encapsulates database client factories for a product schema."""

    def __init__(self, settings, schema: str):
        self._settings = settings
        self._schema = schema
        self._admin: Optional[Client] = None

    def get_client(self, access_token: Optional[str] = None) -> Client:
        """Create a Supabase client targeting the product schema.

        Args:
            access_token: If provided, authenticates as this user (respects RLS).
                          If None, uses service role (admin access).
        """
        return make_supabase_client(
            url=self._settings.supabase_url,
            anon_key=self._settings.supabase_anon_key,
            service_role_key=self._settings.supabase_service_role_key,
            schema=self._schema,
            access_token=access_token,
        )

    def get_core_client(self) -> Client:
        """Create a Supabase client targeting the public schema.

        Used for platform-level tables (notifications, noctus_users, etc.).
        """
        return make_supabase_client(
            url=self._settings.supabase_url,
            anon_key=self._settings.supabase_anon_key,
            service_role_key=self._settings.supabase_service_role_key,
            schema="public",
        )

    def get_admin_client(self) -> Client:
        """Get a cached admin client (service role, bypasses RLS)."""
        if self._admin is None:
            self._admin = self.get_client()
        return self._admin


def create_database_module(settings, schema: str) -> DatabaseModule:
    """Factory to create database module for a product.

    Args:
        settings: Product settings instance (must have supabase_url, etc.)
        schema: Database schema name (e.g. "mailing", "erp", "therapy")
    """
    return DatabaseModule(settings, schema)
