"""
Shared dependencies for FastAPI routers.
Handles JWT auth token extraction and Supabase client creation.
"""
from typing import Optional
from fastapi import Header, HTTPException
from noctusai_shared.auth import first_or_none  # noqa: F401
from app.database import get_supabase_client


async def get_current_user(authorization: Optional[str] = Header(None)):
    """Extract and validate JWT from Authorization header. Returns (user, token)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = authorization.replace("Bearer ", "")
    try:
        admin = get_supabase_client()
        user_response = admin.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


def get_org_id(user, *, required: bool = False) -> Optional[str]:
    """Extract org_id from user metadata.

    org_id is set in auth.users.raw_user_meta_data during signup (core)
    and user creation (ERP profiles router). Available on every request
    without extra DB queries.

    By default returns None if missing (backwards-compatible).
    Pass required=True in endpoints where org_id is strictly needed.
    """
    org_id = (user.user_metadata or {}).get("org_id")
    if not org_id and required:
        raise HTTPException(status_code=400, detail="Organização não encontrada no perfil do usuário")
    return org_id or None


def get_user_client(token: str):
    """Get a Supabase client authenticated as the user (respects RLS)."""
    return get_supabase_client(token)


def get_admin_client():
    """Get a Supabase client with service role (bypasses RLS)."""
    return get_supabase_client()


def log_action(user_id: str, tipo_acao: str, tipo_entidade: str,
               entidade_id: Optional[str] = None, descricao: str = "", detalhes: Optional[dict] = None):
    """Server-side action logging. Always runs with service role."""
    admin = get_admin_client()
    try:
        admin.table("user_actions_log").insert({
            "usuario_id": user_id,
            "tipo_acao": tipo_acao,
            "tipo_entidade": tipo_entidade,
            "entidade_id": entidade_id,
            "descricao": descricao,
            "detalhes": detalhes or {},
        }).execute()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to log action: {e}")
