"""
Database clients for Social Wiring.

Thin wrapper around the seed framework's DatabaseModule.
Kept for backward compatibility with tests and any imports.
"""
from noctusai_seed import create_database_module
from app.config import settings
from app.sqlite_client import SQLiteClient

_sqlite_client = SQLiteClient(settings.sqlite_path)
_db = None
_use_sqlite = settings.database_backend.lower() == "sqlite"
if not _use_sqlite:
    _db = create_database_module(settings, schema="social_wiring")

def get_supabase_client(token: str | None = None):
    if _use_sqlite:
        return _sqlite_client
    return _db.get_client(token)


def get_core_client():
    if _use_sqlite:
        return _sqlite_client
    return _db.get_core_client()


def get_admin_client():
    if _use_sqlite:
        return _sqlite_client
    return _db.get_admin_client()


supabase_admin = (
    _sqlite_client
    if _use_sqlite
    else (_db.get_admin_client() if settings.supabase_service_role_key else None)
)
