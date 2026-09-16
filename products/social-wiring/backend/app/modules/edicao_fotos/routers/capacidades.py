"""`GET /api/edicao-fotos/capacidades` — contract §2.

Server-computed by the engine (`compute_capabilities`); never derived from SSO
metadata. Open to every Edição de Fotos actor: org members, platform admins
and photo curators (who hold a grant but may have no batch access)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from noctusai_lib.domain.permissions import PermissionGrantRepository
from noctusai_lib.domain.photo_editing import Actor, PhotoEditingPorts, compute_capabilities
from noctusai_lib.domain.photo_editing.types import PHOTO_CURATOR_PERMISSION

from app.modules.edicao_fotos.deps import (
    get_actor,
    get_edicao_ports,
    get_grant_repository,
    is_member,
)
from app.modules.edicao_fotos.errors import api_error

router = APIRouter(prefix="/api/edicao-fotos", tags=["edicao-fotos"])


@router.get("/capacidades")
async def capacidades_route(
    actor: Actor = Depends(get_actor),
    grants: PermissionGrantRepository = Depends(get_grant_repository),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    if not is_member(actor) and not await grants.has_permission(
        user_id=actor.user_id, permission=PHOTO_CURATOR_PERMISSION
    ):
        raise api_error(
            403, "sem_acesso_edicao_fotos", "Seu papel na organização não dá acesso à Edição de Fotos."
        )
    settings = await ports.repo.get_org_settings(actor.org_id)
    return await compute_capabilities(
        actor=actor, settings=settings, grants=grants, capabilities=ports.capabilities
    )
