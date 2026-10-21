"""Julia > Proteção (owner 2026-10-21: "set limits and rate limitings ... so we protect our operation"; GUARDRAILS B5).

  GET   /api/julia/protecao/config                  admin  {data:{...limits, padrao, faixas, defaults}}  (every limit, visible)
  PUT   /api/julia/protecao/config                  admin  {any limit key | prompt_documento_lead}        {data: config}
  GET   /api/julia/protecao/bloqueios?historico     admin  {data:{items}}                                 (active; `historico=true` = lifted too)
  POST  /api/julia/protecao/bloqueios {numero,motivo,duracao_min?}  admin  (manual block; permanent unless `duracao_min`)
  POST  /api/julia/protecao/bloqueios/{id}/desbloquear  admin

All org-admin actions. The limits and the blocklist are data per org (migration 298); the webhook reads them on every inbound.
Typed errors: 422 `valor_invalido` / `prompt_invalido` / `motivo_obrigatorio` / `numero_invalido`, 409 `numero_da_equipe` /
`numero_ja_bloqueado` / `bloqueio_ja_desfeito`, 404 `bloqueio_nao_encontrado`.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import julia_protecao_service as prot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/protecao", tags=["julia-protecao"])


def get_protecao_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


def get_protecao_core() -> Any:
    """DI seam: the core client (admin check)."""
    return get_core_client()


class ConfigIn(StrictHttpModel):
    entrada_limite: Optional[int] = None
    entrada_janela_s: Optional[int] = None
    midia_limite_chat_dia: Optional[int] = None
    midia_limite_conexao_dia: Optional[int] = None
    bloqueio_auto_ativo: Optional[bool] = None
    bloqueio_auto_limiar: Optional[int] = None
    bloqueio_auto_janela_min: Optional[int] = None
    bloqueio_auto_duracao_min: Optional[int] = None
    prompt_documento_lead: Optional[str] = Field(default=None, max_length=prot.PROMPT_MAX + 1000)


class BloqueioIn(StrictHttpModel):
    numero: str = Field(min_length=1, max_length=40)
    motivo: str = Field(min_length=1, max_length=prot.MOTIVO_MAX)
    duracao_min: Optional[int] = Field(default=None, ge=1, le=525600)


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _admin(auth: tuple, request: Optional[Request], core: Any, what: str) -> None:
    require_org_admin_for(core, auth, request, what)


def _config_payload(config: dict[str, Any]) -> dict[str, Any]:
    from app.services.media_service import PROMPT_DOCUMENTO_LEAD_PADRAO

    return {**config, "faixas": {k: list(v) for k, v in prot.FAIXAS.items()}, "padroes": dict(prot.PADRAO),
            "prompt_documento_padrao": PROMPT_DOCUMENTO_LEAD_PADRAO}


@router.get("/config")
def ler_config(
    request: Request = None, auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_protecao_client),
    core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "Os limites de proteção da Julia")
    return {"data": _config_payload(prot.obter_config(client, _org(auth)))}


@router.put("/config")
def salvar_config(
    corpo: ConfigIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_protecao_client), core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "Os limites de proteção da Julia")
    campos = corpo.model_dump(exclude_unset=True)
    return {"data": _config_payload(prot.salvar_config(client, _org(auth), str(auth[0].id), campos))}


@router.get("/bloqueios")
def listar_bloqueios(
    historico: bool = Query(False), request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_protecao_client), core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "A lista de números bloqueados")
    return {"data": {"items": prot.listar_bloqueios(client, _org(auth), somente_ativos=not historico)}}


@router.post("/bloqueios", status_code=201)
def bloquear(
    corpo: BloqueioIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_protecao_client), core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "O bloqueio de números")
    expira = datetime.now(timezone.utc) + timedelta(minutes=corpo.duracao_min) if corpo.duracao_min else None
    return {"data": prot.bloquear(client, _org(auth), str(auth[0].id), numero=corpo.numero, motivo=corpo.motivo, expira_em=expira)}


@router.post("/bloqueios/{bloqueio_id}/desbloquear")
def desbloquear(
    bloqueio_id: UUID, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_protecao_client), core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "O desbloqueio de números")
    return {"data": prot.desbloquear(client, _org(auth), str(auth[0].id), bloqueio_id)}
