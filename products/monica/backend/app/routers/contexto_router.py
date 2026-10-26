"""`/api/contexto` -- Monica's own context (who she is, her approach, tone of voice, ...), the org-owned
"specs" of her future lead agent. The values live in the AGENTS product (`agents.agent_org_specs`); this is a
thin proxy over the seed `AgentsOrgSpecsClient` that forwards the LOGGED-IN USER's bearer unchanged, so agents'
own `require_admin` decides who may read or write (never a service token: a non-admin would edit the context).

Errors: agents' 422 is re-emitted `{detail, code, **fields}` (the form pins it on the field), a refused token is
403, no agents link configured is 503, the agent not yet created for the org is 404, anything else upstream is 502.
Recipe: KB § INTEGRATIONS/agents-org-specs.md.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.integrations.agents import (
    AgentNotFound,
    AgentsBadRequest,
    AgentsClientError,
    AgentsNotConfigured,
    AgentsTokenInvalid,
    make_agents_org_specs_client,
)

from app.config import settings
from app.dependencies import get_current_user_org

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Contexto"])


class ContextoIn(StrictHttpModel):
    valores: dict[str, str] = Field(default_factory=dict)


def _agents_base_url() -> str:
    if settings.agents_url:
        return settings.agents_url.rstrip("/")
    try:
        return resolve_product_url("agents")
    except ValueError:
        return ""


def _http_error(exc: AgentsClientError) -> HTTPException:
    if isinstance(exc, AgentsNotConfigured):
        return HTTPException(503, detail="A integração com o agente ainda não está configurada.")
    if isinstance(exc, AgentsTokenInvalid):
        return HTTPException(403, detail="Apenas administradores podem ver e editar o contexto.")
    if isinstance(exc, AgentNotFound):
        return HTTPException(404, detail="O contexto ainda não foi liberado para esta conta.")
    if isinstance(exc, AgentsBadRequest):
        return HTTPException(422, detail={"detail": str(exc), "code": exc.code, **exc.fields})
    logger.warning("contexto: agents call failed (%s)", type(exc).__name__)
    return HTTPException(502, detail="Não foi possível falar com o serviço de agentes. Tente de novo.")


def get_agents_client():
    """FastAPI dependency (the test seam: `dependency_overrides[get_agents_client]`)."""
    try:
        return make_agents_org_specs_client(base_url=_agents_base_url(), allow_fake=settings.agents_allow_fake)
    except AgentsNotConfigured as exc:
        raise _http_error(exc) from exc


@router.get("/api/contexto")
async def get_contexto(
    auth: tuple = Depends(get_current_user_org), agents=Depends(get_agents_client),
) -> dict[str, Any]:
    _user, token, _org = auth
    try:
        out = await agents.get_org_specs(settings.monica_agent_key, token=token)
    except AgentsClientError as exc:
        raise _http_error(exc) from exc
    return out.as_dict()


@router.put("/api/contexto")
async def put_contexto(
    body: ContextoIn, auth: tuple = Depends(get_current_user_org), agents=Depends(get_agents_client),
) -> dict[str, Any]:
    _user, token, _org = auth
    try:
        out = await agents.put_org_specs(settings.monica_agent_key, body.valores, token=token)
    except AgentsClientError as exc:
        raise _http_error(exc) from exc
    return out.as_dict()
