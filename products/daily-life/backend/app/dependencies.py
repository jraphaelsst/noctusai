"""Dependencies for Daily Life — delegates to framework."""
from noctusai_seed import create_dependencies, create_database_module
from noctusai_shared.auth import first_or_none, resolve_sso_role  # noqa: F401
from app.config import settings

_db = create_database_module(settings, schema="daily_life")
deps = create_dependencies(_db)

get_current_user = deps.get_current_user
get_user_role = deps.get_user_role
get_org_id = deps.get_org_id
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client
