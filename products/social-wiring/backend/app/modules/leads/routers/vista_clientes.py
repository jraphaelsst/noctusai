"""Vista clientes -> our lead people (fill-empty-only) — /api/leads/vista-clientes/* (CONTRACT ad-lead-intake § 8).

  POST /sync                    org admin  · ONE bounded batch (`limite`, resumable `cursor`); dry_run=true by default (reads Vista, writes nothing)
  GET  /resumo                  org member · links, pending notices, settings, the last run
  GET  /avisos                  org member · divergence / ambiguous-match notices (?status=pendente&tipo=campo_divergente|match_ambiguo)
  POST /avisos/{id}/resolver    org admin  · {acao: resolvida | ignorada}
  GET  /config  ·  PUT /config  member / org admin · the org's Vista request budget + the LGPD identity flag (CPF/RG, default OFF)

Mounted under `/api/leads` BEFORE `leads.router`'s catch-all `/{lead_id}` (see `app/modules/leads/__init__.py`).
"""
from __future__ import annotations

from typing import Any, Callable, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException, NotFoundError
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.leads.services import vista_clientes_sync as svc

router = APIRouter(prefix="/api/leads/vista-clientes", tags=["leads-vista-clientes"])


class ResolverIn(StrictHttpModel):
    acao: Literal["resolvida", "ignorada"]
    nota: Optional[str] = None


class ConfigIn(StrictHttpModel):
    vista_rps: Optional[float] = None
    importar_identidade: bool = False


def get_vista_clientes_core() -> Any:
    """DI seam: the core client (org roles live in `public.noctus_users`)."""
    return get_core_client()


def get_vista_adapter_factory() -> Callable[..., Any]:
    """DI seam: builds the org's paced Vista adapter (503 when the org has no credentials). Tests override this network edge."""
    from app.services import vista_credenciais

    return vista_credenciais.adapter_ou_503


def _admin(core: Any, auth: tuple, request: Request, contexto: str) -> None:
    require_org_admin_for(core, auth, request, contexto)


@router.post("/sync", status_code=200)
def sincronizar(
    request: Request,
    dry_run: bool = Query(default=True),
    limite: int = Query(default=svc.LIMITE_PADRAO, ge=1, le=svc.LIMITE_MAX),
    cursor: Optional[str] = Query(default=None, pattern=r"^\d{1,9}$"),
    modo: Literal["novos", "refazer"] = Query(default="novos"),
    pausa_s: float = Query(default=0.0, ge=0, le=10),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    core: Any = Depends(get_vista_clientes_core),
    fabrica_vista: Callable[..., Any] = Depends(get_vista_adapter_factory),
) -> dict:
    """Runs now, one batch (plain `def`: threadpool). Calls Vista, paced by the org's budget. A full pass is the CALLER looping on `proximo_cursor`."""
    _admin(core, auth, request, "A sincronização dos clientes do Vista")
    org_id = coerce_org_uuid(auth[2])
    estado = svc.estado_da_org(client, org_id)
    adapter = fabrica_vista(org_id, rate_per_sec=estado["vista_rps"])
    return success_response(svc.sincronizar_sync(client, adapter, org_id, dry_run=dry_run, limite=limite, cursor=cursor, modo=modo, pausa_s=pausa_s))


@router.get("/resumo")
def resumo(auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client)) -> dict:
    return success_response(svc.resumo(client, coerce_org_uuid(auth[2])))


@router.get("/avisos")
def listar_avisos(
    status: Optional[Literal["pendente", "resolvida", "ignorada"]] = Query(default="pendente"),
    tipo: Optional[Literal["campo_divergente", "match_ambiguo"]] = Query(default=None),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    rows = svc.listar_avisos(client, coerce_org_uuid(auth[2]), status, tipo)
    return success_response({"items": rows, "total": len(rows)})


@router.post("/avisos/{aviso_id}/resolver")
def resolver_aviso(
    aviso_id: UUID, body: ResolverIn, request: Request,
    auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
    core: Any = Depends(get_vista_clientes_core),
) -> dict:
    _admin(core, auth, request, "O aviso de cliente do Vista")
    try:
        return success_response(svc.resolver_aviso(client, coerce_org_uuid(auth[2]), aviso_id, body.acao, getattr(auth[0], "id", None), body.nota))
    except LookupError as exc:
        raise NotFoundError("vista_cliente_aviso", str(aviso_id)) from exc


@router.get("/config")
def get_config(auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client)) -> dict:
    e = svc.estado_da_org(client, coerce_org_uuid(auth[2]))
    return success_response({"vista_rps": e["vista_rps"], "importar_identidade": e["importar_identidade"]})


@router.put("/config")
def put_config(
    body: ConfigIn, request: Request, auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
    core: Any = Depends(get_vista_clientes_core),
) -> dict:
    _admin(core, auth, request, "A configuração da sincronização de clientes do Vista")
    try:
        e = svc.salvar_config(client, coerce_org_uuid(auth[2]), vista_rps=body.vista_rps, importar_identidade=body.importar_identidade, user_id=getattr(auth[0], "id", None))
    except ValueError as exc:
        raise AppException("vista_rps_invalido", str(exc), status_code=422) from exc
    return success_response({"vista_rps": e["vista_rps"], "importar_identidade": e["importar_identidade"]})


__all__ = ["router"]
