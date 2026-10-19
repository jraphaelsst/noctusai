"""`/api/atendimento-blocos` (maya-blocks CONTRACT §4.1 / §4.2).

  GET  /api/atendimento-blocos    any member of the org   {data: {blocos[6], etapas_sem_bloco, agentes_por_bloco, supervisao_ativa}}
  PUT  /api/atendimento-blocos    owner/admin             body {blocos: [{bloco, agent_key, ativo, etapas}]} -> same as GET

No session -> strict 401; the org is the session's selected org, never a parameter. Errors (`{error: {code,
message, details}}`): 403 not owner/admin; 422 VALIDATION_ERROR (unknown field / unknown or duplicate `bloco` /
duplicate stage), `etapa_desconhecida`, `etapa_em_dois_blocos`, `sdr_sem_etapas`, `agente_indisponivel`;
409 `conflito_concorrente` (the DB trigger refused a concurrent save).
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field, field_validator

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.modules.atendimento_blocos import handoffs
from app.modules.atendimento_blocos import service as svc

router = APIRouter(prefix="/api/atendimento-blocos", tags=["atendimento-blocos"])

handoffs.registrar()  # binds the `novo_lead` -> sdr handoff sink (T1) on the Julia event bus

NomeBloco = Literal["sdr", "atendimento", "negociacao", "juridico", "financeiro", "contador"]


def get_blocos_client() -> Any:
    """DI seam: the `social_wiring`-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class BlocoIn(StrictHttpModel):
    bloco: NomeBloco
    agent_key: Optional[str] = Field(..., max_length=40)
    ativo: bool
    etapas: list[str] = Field(..., max_length=100)

    @field_validator("etapas")
    @classmethod
    def _sem_repeticao(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("etapa repetida no bloco")
        return v


class BlocosIn(StrictHttpModel):
    blocos: list[BlocoIn] = Field(..., min_length=1, max_length=6)

    @field_validator("blocos")
    @classmethod
    def _bloco_unico(cls, v: list[BlocoIn]) -> list[BlocoIn]:
        nomes = [b.bloco for b in v]
        if len(set(nomes)) != len(nomes):
            raise ValueError("bloco repetido no corpo")
        return v


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


@router.get("")
def obter(
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_blocos_client),
) -> dict[str, Any]:
    return {"data": svc.ler(client, _org(auth))}


@router.put("")
def salvar(
    corpo: BlocosIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_blocos_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "A configuração dos blocos do atendimento")
    user_id = getattr(auth[0], "id", None)
    itens = [b.model_dump(mode="json") for b in corpo.blocos]
    return {"data": svc.salvar(client, _org(auth), itens, updated_by=str(user_id) if user_id else None)}
