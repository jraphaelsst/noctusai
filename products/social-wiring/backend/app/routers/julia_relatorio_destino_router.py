"""Julia v3 report destination + the lead card's report feed (CONTRACT julia-v2 section 12.5).

  GET /api/julia/relatorio-destino                   org admin   {data: {modo, usuario_id, usuario_nome, telefone_resolvido|null, atualizado_em}}
  PUT /api/julia/relatorio-destino {modo, usuario_id?}   org admin   same shape (full replace; audited; the old destination is told)
  GET /api/julia/contatos/{id}/relatorios            lead access  {data: [{id, tipo, texto, dados, destino_e164, envio_status, envio_erro, created_at, ...}]}
                                                                    newest first (A7: the contato's owner or an org owner/admin; another org -> 404)

`modo` is `usuario` (reports go to that member of the org -- `usuario_id` -- on the WhatsApp they set in noc; "my number is set in
noc") or `responsavel` (the lead's assigned responsavel, `usuario_id` as the fallback). No phone on the user: the report is still saved on
the lead card, the send is skipped and they are told in-app. Errors (AppException envelope): 422 `modo_invalido` / `usuario_obrigatorio` / `usuario_fora_da_org`.

NB: registered BEFORE `julia_perguntas_router`, whose `GET /api/julia/contatos/{connection_id}/{chat_id}` would otherwise swallow
`GET /api/julia/contatos/{id}/relatorios`.
"""
# No `from __future__ import annotations`: FastAPI body models are resolved from the signature.
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client, get_settings
from app.services import julia_acesso, julia_relatorio_service as svc

router = APIRouter(prefix="/api/julia", tags=["julia-relatorio-destino"])


def get_relatorio_destino_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


def get_servicos_internos(cfg=Depends(get_settings)) -> svc.ServicosInternos:
    """DI seam: the staff-send collaborators (the code to the new number, the warning to the old one). Tests override."""
    from noctusai_lib.integrations.redis import make_redis_client
    from noctusai_lib.integrations.whatsapp import get_whatsapp_client

    from app.dependencies import get_admin_client
    from app.services.whatsapp_connection_store import build_whatsapp_connection_store

    def lookup(connection_id: UUID):
        return build_whatsapp_connection_store(get_admin_client(), encryption_key=cfg.encryption_key).get_by_id(connection_id, decrypt=True)

    return svc.ServicosInternos(
        scoped=get_scoped_admin_client("social_wiring"), core_client=get_core_client(), waha_factory=get_whatsapp_client,
        connection_lookup=lookup, redis=make_redis_client(cfg.redis_url, decode_responses=True), cfg=cfg,
    )


class DestinoIn(StrictHttpModel):
    modo: Literal["usuario", "responsavel"]
    usuario_id: Optional[UUID] = None


def _resposta(dados: dict[str, Any]) -> dict[str, Any]:
    return {"data": dados}


@router.get("/relatorio-destino")
def get_destino(
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_relatorio_destino_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "O destino dos relatórios da Julia")
    return _resposta(svc.obter_destino(client, get_core_client(), coerce_org_uuid(auth[2])))


@router.put("/relatorio-destino")
async def put_destino(
    payload: DestinoIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    servicos: svc.ServicosInternos = Depends(get_servicos_internos),
    client: Any = Depends(get_relatorio_destino_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "O destino dos relatórios da Julia")
    servicos.scoped = client
    return _resposta(await svc.alterar_destino(
        servicos, coerce_org_uuid(auth[2]), modo=payload.modo, usuario_id=payload.usuario_id, user_id=getattr(auth[0], "id", None)))


@router.get("/contatos/{contato_id}/relatorios")
def listar_relatorios(
    contato_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_relatorio_destino_client),
) -> dict[str, Any]:
    contato = julia_acesso.exigir_contato(client, julia_acesso.contexto(auth, request), contato_id)
    return {"data": svc.listar_relatorios(client, coerce_org_uuid(auth[2]), contato["id"])}
