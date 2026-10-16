"""Lais "Perguntas essenciais" + the contato read route (lais-build-contract section 4, wave 2).

  GET /api/lais/perguntas                              member read    {data: {catalogo, limites}}
  PUT /api/lais/perguntas                              org admin      full replace -> same shape
  GET /api/lais/contatos/{connection_id}/{chat_id}     member read    {data: {contato, slots, interacao_atual}}

Errors (AppException envelope): 422 `limite_ativas` / `limite_qualificatorias` / `objetivo_obrigatorio` /
`chave_desconhecida` / `selecao_invalida`; 409 `usada_em_criterio` (`details.criterios`); 404 `contato_nao_encontrado`.
The org is always the caller's org from the auth tuple -- a contato of another org is a 404.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import lais_acesso, lais_contatos_service, lais_perguntas_service as svc

router = APIRouter(tags=["lais-perguntas"])


class PerguntaSelecionada(StrictHttpModel):
    chave: str = Field(min_length=2, max_length=64)
    qualificatoria: bool = False


class SelecaoUpdate(StrictHttpModel):
    selecao: list[PerguntaSelecionada] = Field(max_length=64)


def get_perguntas_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


@router.get("/api/lais/perguntas")
def get_perguntas(
    auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_perguntas_client),
) -> dict[str, Any]:
    return {"data": svc.montar_saida(client, coerce_org_uuid(auth[2]))}


@router.put("/api/lais/perguntas")
def put_perguntas(
    payload: SelecaoUpdate,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_perguntas_client),
    request: Request = None,
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "As perguntas da Julia")
    org_id = coerce_org_uuid(auth[2])
    return {"data": svc.substituir_selecao(client, org_id, [p.model_dump() for p in payload.selecao])}


@router.get("/api/lais/contatos/{connection_id}/{chat_id}")
def get_contato(
    connection_id: UUID,
    chat_id: str,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_perguntas_client),
) -> dict[str, Any]:
    org_id = coerce_org_uuid(auth[2])
    contato = lais_contatos_service.buscar_contato(client, org_id, connection_id, chat_id)
    if contato is None:
        raise AppException("contato_nao_encontrado", "Contato não encontrado.", status_code=404)
    lais_acesso.exigir_acesso(client, lais_acesso.contexto(auth, request), contato)  # A7: owner/admin only
    ativas = set(svc.selecao_org(client, org_id))
    interacao = lais_contatos_service.interacao_aberta(client, contato["id"])
    return {"data": {
        "contato": {k: contato.get(k) for k in (
            "id", "nome", "email", "operacao", "status_envio", "encerrado_at", "ultimo_inbound_at")},
        # values of a question the org later switched off are kept in the row but not shown
        "slots": {k: v for k, v in (contato.get("slots") or {}).items() if k in ativas},
        "interacao_atual": (
            {k: interacao.get(k) for k in ("id", "iniciada_at", "operacao", "tipo")} if interacao else None
        ),
    }}
