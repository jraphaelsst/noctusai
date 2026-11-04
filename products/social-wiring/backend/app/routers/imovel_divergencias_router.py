"""Imóveis > Divergências com o Vista -- the review API (TRANSITIONAL; `vista_divergencias`, owner 2026-11-04).

  GET  /api/imoveis/{codigo}/divergencias                       org member  {items: [Divergencia]} (pending first, then decided)
  POST /api/imoveis/{codigo}/divergencias/{id}/resolver         org admin   {escolha: vista|nosso|manual, valor?} -> the Divergencia
  GET  /api/imoveis/divergencias/config                         org admin  {data: {ativa, destino_user_id}}
  PUT  /api/imoveis/divergencias/config                         org admin  {ativa?, destino_user_id?}

Divergencia = {id, campo, status: pendente|resolvido, valor_vista, vista_em, valor_nosso, nosso_em, nosso_por: {id,nome}|null,
origem: {tipo: captacao|cadastro|julia, contato_id?, thread_id?, trecho?}|null, resolucao?: {escolha, valor?, por, em}} (no `data`
envelope -- the FE contract). Strict 401 without a session, 403 for a non-admin (reads are open to any org member), 404 unknown divergence, 409 already decided / the owned layer refused,
422 invalid choice/value. 'vista' writes Vista's value into OUR overlay (or clears our override); 'nosso' keeps ours and records
the decision so the same pair never alerts again; 'manual' types a third value. The platform AuditMiddleware records each write
with the acting admin and the row keeps `decidido_por` / `decidido_em` / `motivo_resolucao`.

NOC-REMEDIATE[transicao-vista-divergencias]: removable with the mechanism (vista.md § 6c) -- 2026-11-04
"""
# No `from __future__ import annotations`: FastAPI body models are resolved from the signature.
from typing import Any, Literal, Optional, Union

import anyio
from fastapi import APIRouter, Depends, Request

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org
from app.modules.imovel_hub.deps import get_imovel_hub_client
from app.services import vista_divergencias as div

router = APIRouter(prefix="/api/imoveis", tags=["imoveis-divergencias"])


def get_divergencias_core() -> Any:
    """DI seam: the core client (admin check) -- tests override."""
    return get_core_client()


class ResolverIn(StrictHttpModel):
    escolha: Literal["vista", "nosso", "manual"]
    valor: Optional[Union[float, int, str]] = None


class ConfigIn(StrictHttpModel):
    ativa: Optional[bool] = None
    destino_user_id: Optional[str] = None


def _admin(auth: tuple, request: Optional[Request], core: Any) -> tuple[Any, Optional[str]]:
    require_org_admin_for(core, auth, request, "As divergências com o Vista")
    user = auth[0]
    uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return coerce_org_uuid(auth[2]), (str(uid) if uid else None)


@router.get("/divergencias/config")
def ler_config(request: Request = None, auth: tuple = Depends(get_current_user_org), core: Any = Depends(get_divergencias_core),
               db: Any = Depends(get_imovel_hub_client)) -> dict[str, Any]:
    org_id, _ = _admin(auth, request, core)
    return {"data": div.config(db, org_id)}


@router.put("/divergencias/config")
def salvar_config(corpo: ConfigIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
                  core: Any = Depends(get_divergencias_core), db: Any = Depends(get_imovel_hub_client)) -> dict[str, Any]:
    org_id, uid = _admin(auth, request, core)
    return {"data": div.salvar_config(
        db, org_id, ativa=corpo.ativa, destino_user_id=corpo.destino_user_id, user_id=uid,
        mudar_destino="destino_user_id" in corpo.model_fields_set,
    )}


@router.get("/{codigo}/divergencias")
def listar(codigo: str, auth: tuple = Depends(get_current_user_org),
           core: Any = Depends(get_divergencias_core), db: Any = Depends(get_imovel_hub_client)) -> dict[str, Any]:
    return div.listar_do_imovel(db, core, coerce_org_uuid(auth[2]), codigo)


@router.post("/{codigo}/divergencias/{conflito_id}/resolver")
def resolver(codigo: str, conflito_id: str, corpo: ResolverIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
             core: Any = Depends(get_divergencias_core), db: Any = Depends(get_imovel_hub_client)) -> dict[str, Any]:
    org_id, uid = _admin(auth, request, core)
    try:
        return div.resolver(db, core, org_id, codigo, conflito_id, corpo.escolha, corpo.valor, uid)
    except LookupError as exc:
        raise AppException("divergencia_nao_encontrada", str(exc), status_code=404) from exc
    except div.ResolucaoInvalida as exc:
        raise AppException("valor_invalido", str(exc), status_code=422) from exc
    except div.ResolucaoImpossivel as exc:
        raise AppException("divergencia_nao_resolvida", str(exc), status_code=409) from exc


__all__ = ["router"]
