"""Platform kill switch API (Julia v3 contract §12.1; migration 056).

``GET|PUT /api/studio/plataforma/agentes/{key}/controle`` — ``{desligado, motivo, alterado_em, alterado_por}``.
Platform admin only (``require_platform_admin``: 401 unauthenticated, 403 ``platform_admin_required`` for anyone
else — a platform-issued content token is NOT enough: switching an agent off for every org is a human act).
``desligado=true`` stops the agent for EVERY org (turn status ``agente_desligado_plataforma``, no model call).
The change is audited with the actor (``plataforma_desligada`` / ``plataforma_religada``). Seam:
``get_plataforma_controle_store_dep``.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.dependencies import require_platform_admin
from app.routers.channel_threads_router import get_plataforma_controle_store_dep
from app.routers.studio_agents_router import actor_id, http_error
from app.stores.errors import NotFound
from app.stores.plataforma_controles import MOTIVO_MAX
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(tags=["plataforma-controle"])

_CHAVE = r"^[a-z0-9]+([-_][a-z0-9]+)*$"


class PlataformaControleOut(BaseModel):
    agent_key: str
    desligado: bool
    motivo: str | None = None
    alterado_em: datetime | None = None
    alterado_por: UUID | None = None


class PlataformaControlePut(StrictHttpModel):
    desligado: bool
    motivo: str | None = Field(default=None, max_length=MOTIVO_MAX)


def _out(rec) -> PlataformaControleOut:
    return PlataformaControleOut(
        agent_key=rec.agent_key, desligado=rec.desligado, motivo=rec.motivo,
        alterado_em=rec.alterado_em, alterado_por=rec.alterado_por,
    )


@router.get("/api/studio/plataforma/agentes/{agent_key}/controle", response_model=PlataformaControleOut)
def get_plataforma_controle(
    agent_key: str,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_plataforma_controle_store_dep),
) -> PlataformaControleOut:
    return _out(store.get(agent_key))


@router.put("/api/studio/plataforma/agentes/{agent_key}/controle", response_model=PlataformaControleOut)
def put_plataforma_controle(
    agent_key: str,
    payload: PlataformaControlePut,
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_plataforma_controle_store_dep),
) -> PlataformaControleOut:
    """Switch the agent off (``desligado=true``) or back on for every org. 404 ``agent_not_found`` when no platform
    definition has that key."""
    try:
        rec = store.set(agent_key, desligado=payload.desligado, motivo=payload.motivo, actor=actor_id(ctx))
    except NotFound as exc:
        raise http_error(404, "agent_not_found", "Agente não encontrado.") from exc
    return _out(rec)
