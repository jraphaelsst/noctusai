"""
Dependencies for Seed Product.

Thin wrapper around the seed framework's ProductDependencies.
Kept for backward compatibility with tests and any imports.
"""
from noctusai_seed import create_dependencies, create_database_module
from noctusai_shared.auth import first_or_none, resolve_sso_role  # noqa: F401
from app.config import settings

_db = create_database_module(settings, schema="seed")
_deps = create_dependencies(_db)

get_current_user = _deps.get_current_user
get_user_role = _deps.get_user_role
get_org_id = _deps.get_org_id
get_user_client = _deps.get_user_client
get_admin_client = _deps.get_admin_client
