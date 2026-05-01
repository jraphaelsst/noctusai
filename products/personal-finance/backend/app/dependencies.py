"""Dependencies for Personal Finance — delegates to framework + domain extensions."""
from typing import Optional
from fastapi import Header, HTTPException
from noctusai_seed import create_dependencies, create_database_module
from noctusai_lib.api.auth import first_or_none, resolve_sso_role  # noqa: F401
from app.config import settings

_db = create_database_module(settings, schema="personal-finance")
deps = create_dependencies(_db)

get_current_user = deps.get_current_user
get_user_role = deps.get_user_role
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client


async def get_current_user_org(authorization: Optional[str] = Header(None)):
    """Extract user + org_id from auth user_metadata.
    Returns (user, token, org_id) tuple. PF-specific convenience function.
    """
    user, token = await get_current_user(authorization)
    org_id = (user.user_metadata or {}).get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Usuario sem organizacao associada")
    return user, token, org_id
