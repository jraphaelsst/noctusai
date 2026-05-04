"""Dependencies for dev-team product — delegates to framework.

Mirrors mailing/erp-imobiliario shape exactly. The seed factory provides
the auth + DB primitives; we re-export so router files can do
`from app.dependencies import get_current_user, get_org_id, get_admin_client`.
"""
from noctusai_seed import create_dependencies, create_database_module
from app.config import settings

_db = create_database_module(settings, schema="dev_team")
deps = create_dependencies(_db)

get_current_user = deps.get_current_user
get_user_role = deps.get_user_role
get_org_id = deps.get_org_id
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client
