"""
Standard FastAPI dependencies for NoctusAI products.

Every product needs the same auth pattern: extract JWT, validate user,
resolve role, get org_id, create authenticated clients. This module
provides factories that products call once at startup.

Usage::

    from noctusai_seed import create_dependencies

    deps = create_dependencies(db)

    # In routers:
    @router.get("/something")
    async def get_something(auth=Depends(deps.require_auth)):
        user, token = auth
        ...
"""
import logging
from typing import Optional
from fastapi import Header, HTTPException
from noctusai_lib.api.auth import resolve_sso_role

logger = logging.getLogger(__name__)


class ProductDependencies:
    """Encapsulates standard FastAPI dependencies for a product."""

    def __init__(self, db):
        self._db = db

    async def get_current_user(self, authorization: Optional[str] = Header(None)):
        """Extract and validate JWT from Authorization header. Returns (user, token)."""
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token ausente")
        token = authorization.replace("Bearer ", "")
        try:
            admin = self._db.get_client()
            user_response = admin.auth.get_user(token)
            if not user_response or not user_response.user:
                raise HTTPException(status_code=401, detail="Token invalido")
            return user_response.user, token
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Nao autenticado")

    @staticmethod
    def get_user_role(user) -> str:
        """Resolve user role. SSO admins get 'platform_admin', others get metadata role."""
        sso = resolve_sso_role(user)
        if sso:
            return sso
        return (user.user_metadata or {}).get("role", "user")

    @staticmethod
    def get_org_id(user) -> str:
        """Extract org_id from user metadata. Raises 403 if missing."""
        org_id = (user.user_metadata or {}).get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Usuario sem organizacao associada")
        return org_id

    def get_user_client(self, token: str):
        """Get a Supabase client authenticated as the user (respects RLS)."""
        return self._db.get_client(token)

    def get_admin_client(self):
        """Get a Supabase client with service role (bypasses RLS)."""
        return self._db.get_admin_client()

    def get_core_client(self):
        """Get a Supabase client targeting the public schema."""
        return self._db.get_core_client()


def create_dependencies(db) -> ProductDependencies:
    """Factory to create standard dependencies for a product.

    Args:
        db: DatabaseModule instance from create_database_module()
    """
    return ProductDependencies(db)
