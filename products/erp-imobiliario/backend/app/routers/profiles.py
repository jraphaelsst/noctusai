"""
Profiles Router — User management with SECURE admin operations.
Admin operations (delete user) use the service role key on the backend,
never exposed to the client.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profiles", tags=["Profiles"])


class ProfileCreate(BaseModel):
    nome: str
    email: str
    telefone: Optional[str] = None
    password: str


class ProfileUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    cargo: Optional[str] = None
    avatar_url: Optional[str] = None


@router.get("")
async def listar_profiles(authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("profiles").select("*").order("created_at", desc=True).execute()
    return {"data": result.data or [], "total": len(result.data or [])}


@router.post("")
async def criar_profile(body: ProfileCreate, authorization: Optional[str] = Header(None)):
    """Create a new user. Uses service role to create auth user."""
    user, token = await get_current_user(authorization)
    admin = get_admin_client()

    # Format name
    nome_formatado = " ".join(
        word.capitalize() for word in body.nome.strip().split()
    )

    # Create auth user with service role (secure, server-side)
    try:
        auth_result = admin.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
            "user_metadata": {
                "nome": nome_formatado,
                "telefone": body.telefone or "",
            },
        })
    except Exception as e:
        error_msg = str(e).lower()
        if "already" in error_msg or "duplicate" in error_msg:
            raise HTTPException(status_code=409, detail="Este email já está cadastrado")
        raise HTTPException(status_code=400, detail="Erro ao criar usuário")

    new_user_id = auth_result.user.id if auth_result.user else None

    log_action(user.id, "criar", "usuario", new_user_id,
               f"Criou usuário {nome_formatado}",
               {"email": body.email})

    return {"data": {"id": new_user_id, "email": body.email, "nome": nome_formatado}}


@router.patch("/{profile_id}")
async def atualizar_profile(profile_id: str, body: ProfileUpdate, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("profiles").update(data).eq("id", profile_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    log_action(user.id, "editar", "usuario", profile_id, f"Editou perfil {profile_id}")
    return {"data": result.data}


@router.delete("/{profile_id}")
async def excluir_profile(profile_id: str, authorization: Optional[str] = Header(None)):
    """
    Delete user SECURELY using service role key.
    This is the critical fix — admin.deleteUser only runs on the server.
    """
    user, token = await get_current_user(authorization)
    admin = get_admin_client()

    # Get profile name before delete
    profile = admin.table("profiles").select("nome").eq("id", profile_id).single().execute()
    nome = profile.data.get("nome", "Unknown") if profile.data else "Unknown"

    # Delete profile first (cascade deletes user_roles)
    admin.table("profiles").delete().eq("id", profile_id).execute()

    # Delete from auth (service role — secure, server-side only)
    try:
        admin.auth.admin.delete_user(profile_id)
    except Exception as e:
        logger.warning(f"Failed to delete auth user {profile_id}: {e}")

    log_action(user.id, "excluir", "usuario", profile_id, f"Excluiu usuário {nome}")
    return {"ok": True}
