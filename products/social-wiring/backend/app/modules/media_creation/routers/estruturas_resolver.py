"""Free-text profile-name resolution endpoint (estruturas-contract.md sections 6.1 / 8.3, tier ``org``).

``GET /estruturas/resolver-perfil`` runs the SAME deterministic resolver the chat / forms use before the model
(:func:`resolver_perfis_no_texto`), so the FE chips and the tests see exactly what the AI would resolve. A pure
read of the platform-wide profile index; ``marca_id`` (optional) is only ownership-checked (404, never 403).

Included BEFORE the ``estruturas`` routers: its static path sits under ``/estruturas/`` and ``/{estrutura_id}``
would otherwise swallow it.

NOTE: no ``from __future__ import annotations`` -- keeps FastAPI resolving annotations in this module's globals.
"""
import logging
import uuid
from typing import Optional

from fastapi import Depends, Query

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.routers.estruturas import raise_http
from app.modules.media_creation.services.estruturas_retrieval import indice_de_perfis, resolver_perfis_no_texto
from app.modules.media_creation.services.estruturas_service import EstruturaError, EstruturasService

logger = logging.getLogger(__name__)

router = make_router(
    tier="org", guard=get_current_user_org, prefix="/api/media-creation/estruturas",
    tags=["Media Creation — Estruturas"],
)


def _resolver(org_id: str, user_id: str, texto: str, marca_id: Optional[str]) -> dict:
    db = get_admin_client()
    if marca_id:
        EstruturasService(db, org_id=org_id, user_id=user_id, is_admin=False).assert_marca(marca_id)
    return resolver_perfis_no_texto(texto, indice_de_perfis(db)).como_dict()


@router.get("/resolver-perfil")
async def resolver_perfil(
    texto: str = Query(min_length=1, max_length=300),
    marca_id: Optional[uuid.UUID] = None,
    auth=Depends(get_current_user_org),
):
    user_id = str(getattr(auth[0], "id", "") or "")
    try:
        data = await run_blocking(_resolver, str(auth[2]), user_id, texto, str(marca_id) if marca_id else None)
    except EstruturaError as exc:
        raise_http(exc)
    return success_response(data)
