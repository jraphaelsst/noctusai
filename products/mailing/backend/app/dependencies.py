"""Dependencies for Mailing Product — delegates to framework."""
from noctusai_seed import create_dependencies, create_database_module
from app.config import settings

_db = create_database_module(settings, schema="mailing")
deps = create_dependencies(_db)

get_current_user = deps.get_current_user
get_user_role = deps.get_user_role
get_org_id = deps.get_org_id
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client
