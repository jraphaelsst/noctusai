"""Julia stage list for the Envio comparator ("stage >= estagio_minimo" compares `ordem`).

  GET /api/julia/qualificacao/estagios     org member -> {data: [{chave, rotulo, ordem, conclusivo}]}

A thin read-only proxy of agents' `GET /api/channels/agents/julia/qualificacao/estagios` through the org's
agents token: SW holds no copy of the stage list (the org's words live in agents' DB rows). Errors are typed
codes only: `agents_nao_configurado` 503, `agents_token_invalido` 502, `agents_indisponivel` 502 (never the
upstream detail).
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends

from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import AgentNotFound, AgentsClientError, AgentsTokenInvalid
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.routers.julia_agente_router import get_agents_client_factory
from app.services.julia_agente_service import DEFAULT_AGENT_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/qualificacao", tags=["julia-qualificacao"])


@router.get("/estagios")
async def get_estagios(
    auth: tuple = Depends(get_current_user_org),
    client_factory=Depends(get_agents_client_factory),
) -> dict[str, Any]:
    agents = client_factory(coerce_org_uuid(auth[2]))
    if agents is None:
        raise AppException("agents_nao_configurado", "O agente não está configurado.", status_code=503)
    try:
        estagios = await agents.estagios(DEFAULT_AGENT_KEY)
    except AgentsTokenInvalid as exc:
        raise AppException("agents_token_invalido", "O acesso ao agente é inválido.", status_code=502) from exc
    except (AgentNotFound, AgentsClientError) as exc:
        logger.warning("julia: stage list unavailable (%s)", type(exc).__name__)
        raise AppException("agents_indisponivel", "O agente está indisponível agora.", status_code=502) from exc
    return {"data": [
        {"chave": e.chave, "rotulo": e.rotulo, "ordem": e.ordem, "conclusivo": e.conclusivo} for e in estagios
    ]}


__all__ = ["router"]
