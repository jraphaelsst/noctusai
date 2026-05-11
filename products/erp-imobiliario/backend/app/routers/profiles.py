"""
Profiles Router — User management with SECURE admin operations.
Admin operations (delete user) use the service role key on the backend,
never exposed to the client.
"""
import logging
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import Field
from app.dependencies import get_current_user, get_user_client, get_admin_client, get_org_id, log_action, first_or_none
from app.responses import success_response, ok_response
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profiles", tags=["Profiles"])


class ProfileCreate(StrictHttpModel):
    nome: str
    email: str
    telefone: Optional[str] = None
    password: str


class ProfileUpdate(StrictHttpModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    cargo: Optional[str] = None
    # Live DB column is `avatar` (verified 2026-05-03). The Pydantic field name
    # accepts the live name; frontend may submit either via the alias.
    avatar: Optional[str] = Field(default=None, alias="avatar_url")
    tema: Optional[Literal["light", "dark"]] = None

    model_config = {"populate_by_name": True}


@router.get("")
async def listar_profiles(auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    result = db.table("profiles").select("*").order("created_at", desc=True).execute()
    return success_response(result.data or [], total=len(result.data or []))


@router.post("")
async def criar_profile(body: ProfileCreate, auth = Depends(get_current_user)):
    """Create a new user. Uses service role to create auth user."""
    user, token = auth
    admin = get_admin_client()

    # Get caller's org_id to assign to new user
    org_id = get_org_id(user)

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
                "org_id": org_id,
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

    return success_response({"id": new_user_id, "email": body.email, "nome": nome_formatado})


@router.patch("/{profile_id}")
async def atualizar_profile(profile_id: str, body: ProfileUpdate, auth = Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("profiles").update(data).eq("id", profile_id).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    log_action(user.id, "editar", "usuario", profile_id, f"Editou perfil {profile_id}")
    return success_response(row)


@router.delete("/{profile_id}")
async def excluir_profile(profile_id: str, auth = Depends(get_current_user)):
    """
    Delete user SECURELY using service role key.
    This is the critical fix — admin.deleteUser only runs on the server.
    """
    user, token = auth
    admin = get_admin_client()

    # Prevent self-deletion
    if profile_id == user.id:
        raise HTTPException(status_code=400, detail="Não é possível excluir a si mesmo")

    # Verify target user belongs to same org. The check fails CLOSED:
    # before migration 024 (2026-05-03) `profiles.org_id` did not exist,
    # so `target_profile.data.get("org_id")` always returned None and the
    # cross-org guard was silently bypassed. The column now exists and
    # is backfilled, but a profile with NULL org_id (legacy / un-migrated
    # row) still raises 403 — the safer side of the boundary.
    caller_org = get_org_id(user)
    target_profile = admin.table("profiles").select("nome, org_id").eq("id", profile_id).single().execute()
    if not target_profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    target_org = target_profile.data.get("org_id")
    if not target_org:
        raise HTTPException(
            status_code=403,
            detail="Perfil sem organização escopada — exclusão bloqueada",
        )
    if caller_org != target_org:
        raise HTTPException(status_code=403, detail="Acesso negado")

    nome = target_profile.data.get("nome", "Unknown")

    # Delete profile first (cascade deletes user_roles)
    admin.table("profiles").delete().eq("id", profile_id).execute()

    # Delete from auth (service role — secure, server-side only)
    try:
        admin.auth.admin.delete_user(profile_id)
    except Exception as e:
        logger.warning(f"Failed to delete auth user {profile_id}: {e}")

    log_action(user.id, "excluir", "usuario", profile_id, f"Excluiu usuário {nome}")
    return ok_response(f"Usuário {nome} excluído com sucesso")
