"""`GET|POST|DELETE /api/edicao-fotos/curadores` — contract §8.

Photo-curator grants (`photo_curator`) through the seed permissions organ
(`noctusai_lib.domain.permissions`, Core 046 `public.user_permission_grants`).
Platform admin only — curators manage the platform-scope reference pool and
guides, so granting one is a platform decision."""
from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import APIRouter, Depends

from noctusai_lib.domain.permissions import PermissionGrant, PermissionGrantRepository
from noctusai_lib.domain.photo_editing import Actor
from noctusai_lib.domain.photo_editing.types import PHOTO_CURATOR_PERMISSION

from app.modules.edicao_fotos.deps import get_grant_repository, require_platform_admin
from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.schemas import CuradorCreateBody

router = APIRouter(prefix="/api/edicao-fotos/curadores", tags=["edicao-fotos"])

#: `ids -> {id: {"nome", "email"}}` for the ids that exist.
UserDirectory = Callable[[list[str]], dict[str, dict]]

_MAX_DIRECTORY_IDS = 500


def _noctus_users(ids: list[str]) -> dict[str, dict]:
    from app.dependencies import get_core_client

    if not ids:
        return {}
    if len(ids) > _MAX_DIRECTORY_IDS:
        raise RuntimeError(f"user directory lookup of {len(ids)} ids exceeds {_MAX_DIRECTORY_IDS}")
    rows = (
        get_core_client()
        .table("noctus_users")
        .select("id, nome, email")
        .in_("id", ids)
        .limit(len(ids))
        .execute()
        .data
        or []
    )
    return {str(r["id"]): {"nome": r.get("nome"), "email": r.get("email")} for r in rows}


def get_user_directory() -> UserDirectory:
    """Seam: trusted `public.noctus_users` lookup."""
    return _noctus_users


def _grant_out(grant: PermissionGrant, users: dict[str, dict]) -> dict:
    info = users.get(grant.user_id, {})
    return {
        "user_id": grant.user_id,
        "nome": info.get("nome"),
        "email": info.get("email"),
        "concedido_por": grant.granted_by,
        "created_at": grant.created_at.isoformat() if grant.created_at else None,
    }


@router.get("")
async def list_curadores_route(
    _actor: Actor = Depends(require_platform_admin),
    grants: PermissionGrantRepository = Depends(get_grant_repository),
    directory: UserDirectory = Depends(get_user_directory),
) -> dict:
    listed = await grants.list_grants(permission=PHOTO_CURATOR_PERMISSION)
    users = directory([g.user_id for g in listed])
    items = [_grant_out(g, users) for g in listed]
    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
async def add_curador_route(
    body: CuradorCreateBody,
    actor: Actor = Depends(require_platform_admin),
    grants: PermissionGrantRepository = Depends(get_grant_repository),
    directory: UserDirectory = Depends(get_user_directory),
) -> dict:
    user_id = str(body.user_id)
    users = directory([user_id])
    if user_id not in users:
        raise api_error(404, "usuario_nao_encontrado", "Usuário não encontrado.")
    grant = await grants.add_grant(
        user_id=user_id, permission=PHOTO_CURATOR_PERMISSION, granted_by=actor.user_id
    )
    return _grant_out(grant, users)


@router.delete("/{user_id}", status_code=204)
async def remove_curador_route(
    user_id: UUID,
    _actor: Actor = Depends(require_platform_admin),
    grants: PermissionGrantRepository = Depends(get_grant_repository),
) -> None:
    removed = await grants.remove_grant(user_id=str(user_id), permission=PHOTO_CURATOR_PERMISSION)
    if not removed:
        raise api_error(404, "curador_nao_encontrado", "Este usuário não é curador.")
