"""Database clients for Mailing Product — delegates to framework."""
from noctusai_seed import create_database_module
from app.config import settings

db = create_database_module(settings, schema="mailing")

get_supabase_client = db.get_client
get_core_client = db.get_core_client
get_admin_client = db.get_admin_client
