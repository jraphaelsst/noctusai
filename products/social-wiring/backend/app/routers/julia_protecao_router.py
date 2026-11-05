"""Julia > Proteção (owner 2026-10-21: "set limits and rate limitings ... so we protect our operation"; GUARDRAILS B5).

  GET   /api/julia/protecao/config                  admin  {data:{...limits, padrao, faixas, defaults}}  (every limit, visible)
  PUT   /api/julia/protecao/config                  admin  {any limit key | prompt_documento_lead}        {data: config}
  GET   /api/julia/protecao/bloqueios?historico     admin  {data:{items}}                                 (active; `historico=true` = lifted too)
  POST  /api/julia/protecao/bloqueios {numero,motivo,duracao_min?}  admin  (manual block; permanent unless `duracao_min`)
  POST  /api/julia/protecao/bloqueios/{id}/desbloquear  admin
  GET   /api/julia/protecao/permitidos              admin  {data:{ativo, items:[{id,numero,rotulo,criado_em}]}}   (the allowlist)
  POST  /api/julia/protecao/permitidos {numero,rotulo?}  admin  201 {data:item}
  DELETE /api/julia/protecao/permitidos/{id}        admin  {data:{ok:true}}
  (the allowlist switch is `permitidos_ativo` on PUT/GET /config)

All org-admin actions. The limits and the blocklist are data per org (migration 298); the webhook reads them on every inbound.
ALLOWLIST (migration 323, owner 2026-11-05: "so she only replies to me at first. The list, when empty, answers all numbers"):
`permitidos_ativo` ON + a non-empty list => a sender not on it is not Julia's (the webhook keeps today's behaviour, motivo
`fora_da_lista_de_permitidos`); OFF or an empty list => nobody is filtered; an unreadable list with the switch ON fails CLOSED.
A listed number bypasses the 11.1 snapshot / previous-chat rules (explicit opt-in); staff, the blocklist and opt-out still win.
The number is stored as canonical BR digits (`+55` and the mobile 9th digit optional on input and on the inbound side).
Typed errors: 422 `numero_invalido` (allowlist too) / `rotulo_invalido`, 409 `numero_ja_permitido`, 404 `permitido_nao_encontrado`, 422 `valor_invalido` / `prompt_invalido` / `motivo_obrigatorio` / `numero_invalido`, 409 `numero_da_equipe` /
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

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_platform_admin_check, get_scoped_admin_client
from app.services import julia_protecao_service as prot
from app.services.julia_edicao import exigir_admin_da_plataforma

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
    permitidos_ativo: Optional[bool] = None
    prompt_documento_lead: Optional[str] = Field(default=None, max_length=prot.PROMPT_MAX + 1000)


class BloqueioIn(StrictHttpModel):
    numero: str = Field(min_length=1, max_length=40)
    motivo: str = Field(min_length=1, max_length=prot.MOTIVO_MAX)
    duracao_min: Optional[int] = Field(default=None, ge=1, le=525600)


class PermitidoIn(StrictHttpModel):
    numero: str = Field(min_length=1, max_length=40)
    rotulo: Optional[str] = Field(default=None, max_length=prot.ROTULO_MAX * 2)


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
    e_admin_da_plataforma=Depends(get_platform_admin_check),
) -> dict[str, Any]:
    campos = corpo.model_dump(exclude_unset=True)
    if "prompt_documento_lead" in campos:
        # The document-reading prompt is Julia's content: NoctusAI writes it (owner 2026-11-04). The numeric limits stay org-admin.
        exigir_admin_da_plataforma(e_admin_da_plataforma, auth, "prompt_documento_lead")
    else:
        _admin(auth, request, core, "Os limites de proteção da Julia")
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


@router.get("/permitidos")
def listar_permitidos(
    request: Request = None, auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_protecao_client),
    core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "A lista de números permitidos")
    org = _org(auth)
    return {"data": {"ativo": bool(prot.obter_config(client, org).get("permitidos_ativo")), "items": prot.listar_permitidos(client, org)}}


@router.post("/permitidos", status_code=201)
def permitir(
    corpo: PermitidoIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_protecao_client), core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "A lista de números permitidos")
    return {"data": prot.adicionar_permitido(client, _org(auth), str(auth[0].id), numero=corpo.numero, rotulo=corpo.rotulo)}


@router.delete("/permitidos/{permitido_id}")
def remover_permitido(
    permitido_id: UUID, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_protecao_client), core: Any = Depends(get_protecao_core),
) -> dict[str, Any]:
    _admin(auth, request, core, "A lista de números permitidos")
    return {"data": prot.remover_permitido(client, _org(auth), permitido_id)}
