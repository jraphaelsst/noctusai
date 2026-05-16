"""
Database clients for Social Wiring.

Thin wrapper around the seed framework's DatabaseModule.
Kept for backward compatibility with tests and any imports.
"""
from noctusai_seed import create_database_module
from app.config import settings

_db = create_database_module(settings, schema="social_wiring")

get_supabase_client = _db.get_client
get_core_client = _db.get_core_client
get_admin_client = _db.get_admin_client
supabase_admin = _db.get_admin_client() if settings.supabase_service_role_key else None
