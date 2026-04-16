"""Database clients for Daily Life — delegates to framework."""
from noctusai_seed import create_database_module
from app.config import settings

db = create_database_module(settings, schema="daily_life")

get_supabase_client = db.get_client
get_core_client = db.get_core_client
get_admin_client = db.get_admin_client
supabase_admin = db.get_admin_client() if settings.supabase_service_role_key else None
