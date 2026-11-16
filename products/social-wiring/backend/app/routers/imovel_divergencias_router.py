"""Imóveis > Vista sync switches, approvals and history -- the API (`vista_divergencias`, owner 2026-11-04).

  GET  /api/imoveis/divergencias/config                         org admin  {data: {ativa, vista_escrita_ativa, destino_user_id, vista_escrita_disponivel}}
  PUT  /api/imoveis/divergencias/config                         org admin  {ativa?, vista_escrita_ativa?, destino_user_id?} -> same shape
  (`destino_user_id` = who gets the WhatsApp digest of opened approvals, kept 2026-11-15; null clears it; omitted = untouched)
  GET  /api/imoveis/{codigo}/divergencias                       org member {items: [Divergencia]} (pending first, then decided)
  POST /api/imoveis/{codigo}/divergencias/{id}/resolver         org admin  {escolha: aprovar|recusar, valor?} -> the Divergencia
  GET  /api/imoveis/{codigo}/historico?cursor=&limit=           org member {data: {items: [{id, kind, ocorrido_em, ator, payload, ...payload}], next_cursor}}

`vista_escrita_disponivel` = the cached, non-mutating probe of the key's `PUT /imoveis/detalhes` grant: true permitted, false denied,
null unknown (no credential / timeout). Never the key. The history is built with the SEED card_hub timeline engine (kinds `vista`,
`aprovacao`, `vista_envio`, `alteracao`, `preco`, `nota`); each item is the engine's flattened shape plus a `payload` copy.
`payload` of a field change = `{campo, rotulo, de, para, acao, conversa?, status?, divergencia_id?, detalhe?}`.

Divergencia = {id, campo, status: pendente|resolvido, valor_vista, vista_em, valor_nosso, nosso_em, nosso_por: {id,nome}|null,
origem: {tipo: captacao|cadastro|julia, contato_id?, thread_id?, trecho?}|null, resolucao?: {escolha, valor?, por, em}} (no `data`
envelope -- the FE contract). Strict 401 without a session, 403 for a non-admin (reads are open to any org member), 404 unknown divergence,
409 already decided / the owned layer refused, 422 invalid choice/value. `aprovar` pushes our value to Vista when the switch is on and the
PUT is permitted, else records "atualizar manualmente no Vista"; `recusar` keeps Vista. (`vista|nosso|manual` still resolve rows the first
version opened.) The platform AuditMiddleware records each write with the acting admin; every decision also writes `imovel_historico`.

NOC-REMEDIATE[transicao-vista-divergencias]: removable with the mechanism (vista.md § 6c) -- 2026-11-04
"""
# No `from __future__ import annotations`: FastAPI body models are resolved from the signature.
from typing import Any, Callable, Literal, Optional, Union

import anyio
from anyio import from_thread
from fastapi import APIRouter, Depends, Query, Request

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org
from app.modules.imovel_hub.deps import get_imovel_hub_client
from app.services import imovel_historico_service, vista_credenciais, vista_divergencias as div

router = APIRouter(prefix="/api/imoveis", tags=["imoveis-divergencias"])


def get_divergencias_core() -> Any:
    """DI seam: the core client (admin check) -- tests override."""
    return get_core_client()


def get_vista_adapter_provider() -> Callable[[Any], Any]:
    """DI seam: `org_id -> the Vista adapter of that org` (raises `VistaConfigError` when it has no credential) -- tests override."""
    return vista_credenciais.adapter_da_org


class ResolverIn(StrictHttpModel):
    escolha: Literal["aprovar", "recusar", "vista", "nosso", "manual"]
    valor: Optional[Union[float, int, str]] = None


class ConfigIn(StrictHttpModel):
    ativa: Optional[bool] = None
    vista_escrita_ativa: Optional[bool] = None
    destino_user_id: Optional[str] = None


def _admin(auth: tuple, request: Optional[Request], core: Any) -> tuple[Any, Optional[str]]:
    require_org_admin_for(core, auth, request, "As divergências com o Vista")
    user = auth[0]
    uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return coerce_org_uuid(auth[2]), (str(uid) if uid else None)


def _estado(db: Any, org_id: Any, provider: Callable[[Any], Any]) -> dict[str, Any]:
    """The config + the cached write-permission verdict (a sync handler: the probe runs on the worker thread's event loop bridge)."""
    cfg = div.config(db, org_id)
    disponivel = from_thread.run(div.escrita_disponivel, org_id, lambda: provider(org_id))
    return {**cfg, "vista_escrita_disponivel": disponivel}


@router.get("/divergencias/config")
def ler_config(request: Request = None, auth: tuple = Depends(get_current_user_org), core: Any = Depends(get_divergencias_core),
               db: Any = Depends(get_imovel_hub_client), provider: Callable = Depends(get_vista_adapter_provider)) -> dict[str, Any]:
    org_id, _ = _admin(auth, request, core)
    return {"data": _estado(db, org_id, provider)}


@router.put("/divergencias/config")
def salvar_config(corpo: ConfigIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
                  core: Any = Depends(get_divergencias_core), db: Any = Depends(get_imovel_hub_client),
                  provider: Callable = Depends(get_vista_adapter_provider)) -> dict[str, Any]:
    org_id, uid = _admin(auth, request, core)
    div.salvar_config(
        db, org_id, ativa=corpo.ativa, vista_escrita_ativa=corpo.vista_escrita_ativa, user_id=uid,
        destino_user_id=corpo.destino_user_id, mudar_destino="destino_user_id" in corpo.model_fields_set,
    )
    return {"data": _estado(db, org_id, provider)}


@router.get("/{codigo}/divergencias")
def listar(codigo: str, auth: tuple = Depends(get_current_user_org),
           core: Any = Depends(get_divergencias_core), db: Any = Depends(get_imovel_hub_client)) -> dict[str, Any]:
    return div.listar_do_imovel(db, core, coerce_org_uuid(auth[2]), codigo)


@router.post("/{codigo}/divergencias/{conflito_id}/resolver")
def resolver(codigo: str, conflito_id: str, corpo: ResolverIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
             core: Any = Depends(get_divergencias_core), db: Any = Depends(get_imovel_hub_client),
             provider: Callable = Depends(get_vista_adapter_provider)) -> dict[str, Any]:
    org_id, uid = _admin(auth, request, core)

    def empurrar(cod: str, campo: str, valor: Any, conversa: Optional[dict]) -> tuple[Optional[str], Optional[str]]:
        """Send our value to Vista (with its note) iff the switch is on and the PUT is permitted; else `(reason, None)`."""
        if not div.config(db, org_id)["vista_escrita_ativa"]:
            return "escrita_desligada", None
        if campo not in div.CAMPO_VISTA:
            return "campo_nao_enviavel", None
        permitida = from_thread.run(div.escrita_disponivel, org_id, lambda: provider(org_id))
        if permitida is not True:
            return ("sem_permissao" if permitida is False else "permissao_desconhecida"), None
        try:
            adapter = provider(org_id)
        except Exception as exc:
            return type(exc).__name__, None
        return from_thread.run(lambda: div.enviar_ao_vista(
            adapter, cod, campo, valor, conversa=conversa, canal="aprovação no NoctusAI", fonte="Proprietário",
            motivo="aprovação de um usuário: o proprietário confirmou o valor e o Vista estava diferente"))

    try:
        return div.resolver(db, core, org_id, codigo, conflito_id, corpo.escolha, corpo.valor, uid, empurrar=empurrar)
    except LookupError as exc:
        raise AppException("divergencia_nao_encontrada", str(exc), status_code=404) from exc
    except div.ResolucaoInvalida as exc:
        raise AppException("valor_invalido", str(exc), status_code=422) from exc
    except div.ResolucaoImpossivel as exc:
        raise AppException("divergencia_nao_resolvida", str(exc), status_code=409) from exc


@router.get("/{codigo}/historico")
def historico(codigo: str, cursor: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=100), auth: tuple = Depends(get_current_user_org),
              db: Any = Depends(get_imovel_hub_client)) -> dict[str, Any]:
    """The imóvel's history: Vista changes, approvals, sends to Vista, price changes and notes -- one thread, newest first."""
    return {"data": imovel_historico_service.linha_do_tempo(db, coerce_org_uuid(auth[2]), codigo, cursor=cursor, limit=limit)}


__all__ = ["router"]
