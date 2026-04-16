"""
Supabase database client setup.

All therapy platform tables live in the `therapy` schema. Uses the seed
framework's DatabaseModule for standardized client creation.
"""
from noctusai_seed import create_database_module
from app.config import settings

db = create_database_module(settings, schema="therapy")
get_supabase_client = db.get_client
get_core_client = db.get_core_client
get_admin_client = db.get_admin_client
supabase_admin = db.get_admin_client() if settings.supabase_service_role_key else None
