"""Julia wave 1 -- Conhecimento (lais-build-contract section 3).

  GET /api/julia/conhecimento             org member   {secoes, preview_md, hash}
  PUT /api/julia/conhecimento/{secao}     org admin    {dados, versao} -> optimistic lock (409 versao_conflito)
  GET /api/julia/conhecimento/preview     org member   {markdown, hash}  ("Ver o que a Julia sabe")

Success envelope `{"data": ...}`; errors are `AppException` (`{"error": {...}}`): 422 `secao_invalida` /
`invalid_field`, 409 `versao_conflito`, 403 non-admin. The body is validated per section by the
service (pydantic `extra="forbid"`).
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client, get_settings
from app.services import julia_agente_service as agente
from app.services import julia_conhecimento_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/conhecimento", tags=["julia-conhecimento"])


class SecaoUpdate(StrictHttpModel):
    dados: Any
    versao: int = Field(ge=0)  # the `versao` the caller read (0 = never saved)


def get_conhecimento_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


async def get_nome_agente(auth: tuple = Depends(get_current_user_org), cfg: Any = Depends(get_settings)) -> Optional[str]:
    """DI seam: the agent's status name (the per-org persona); None -> the default persona (tests override)."""
    org_id = coerce_org_uuid(auth[2])
    return await agente.nome_do_agente(agente.resolve_agents_client(org_id, cfg=cfg))


@router.get("")
def get_conhecimento(
    auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_conhecimento_client),
    nome_agente: Optional[str] = Depends(get_nome_agente),
) -> dict[str, Any]:
    org_id = coerce_org_uuid(auth[2])
    secoes = svc.ler_secoes(client, org_id, nome_agente)
    md = svc.render_md_secoes(secoes, svc._hoje(None))
    return {"data": {"secoes": secoes, "preview_md": md, "hash": svc.hash_md(md)}}


@router.get("/preview")
def get_preview(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_conhecimento_client)) -> dict[str, Any]:
    org_id = coerce_org_uuid(auth[2])
    md = svc.render_md(client, org_id)
    return {"data": {"markdown": md, "hash": svc.hash_md(md)}}


@router.put("/{secao}")
def put_secao(
    secao: str,
    payload: SecaoUpdate,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conhecimento_client),
    nome_agente: Optional[str] = Depends(get_nome_agente),
    request: Request = None,
) -> dict[str, Any]:
    user, _token, raw_org = auth
    require_org_admin_for(get_core_client(), auth, request, "O conhecimento da Julia")
    org_id = coerce_org_uuid(raw_org)
    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return {"data": svc.salvar_secao(client, org_id, secao, payload.dados, payload.versao, user_id, nome_agente)}
