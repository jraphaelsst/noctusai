"""
Supabase database client setup — seed framework.

All ERP tables live in the `erp` schema. The seed framework's DatabaseModule
handles schema routing automatically.
"""
from noctusai_seed import create_database_module
from app.config import settings

db = create_database_module(settings, schema="erp")

get_supabase_client = db.get_client
get_core_client = db.get_core_client
get_admin_client = db.get_admin_client

# Service role client singleton for backend operations
supabase_admin = db.get_admin_client() if settings.supabase_service_role_key else None
