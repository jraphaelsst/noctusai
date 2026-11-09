"""Ad-lead intake — /api/leads/ad-intake/* (CONTRACT products/social-wiring/projects/ad-lead-intake-CONTRACT.md).

  POST /backfill                       org admin · batch of the intake over existing Meta leads (dry_run=true by default)
  GET  /resumo                         org member · intake outcomes by status + pending corretor divergences
  GET  /lead/{lead_id}                 org member · one lead's intake + its links (the post-deploy check reads this)
  POST /lead/{lead_id}/retry           org admin  · re-run the intake of ONE lead (Vista is called)
  GET  /imovel/{codigo}/leads          org member · "Leads interessados": leads linked to the property
  GET  /corretor-divergencias          org member · lead corretor x property corretor warnings (?status=pendente&tipo=…)
  POST /corretor-divergencias/{id}/resolver   org admin · a human checked it: resolvida | ignorada
  POST /corretores/sync                org admin  · refine the in-house brokers from Vista's roster now (dry_run=true by default)
  GET  /corretor-avisos                org member · brokers missing / Inativo in Vista (corretor_sumiu_no_vista)
  POST /corretor-avisos/{id}/resolver  org admin  · {acao: resolvida | ignorada}
  GET  /config  ·  PUT /config         member / org admin · the intake settings (the fallback MAIN broker's Vista Codigo)
  GET  /ref-avisos                     org member · ref-divergence notices (?tipo=ref_sumiu_no_vista|ref_nova_no_vista&status=)
  POST /ref-avisos/{id}/restaurar      org admin  · a ref that vanished from Vista: unpause + clear (one click)
  POST /ref-avisos/{id}/resolver       org admin  · {acao: confirmar_sumiu (stays paused) | ciente (a new ref)}

Mounted under `/api/leads` BEFORE `leads.router`'s catch-all `/{lead_id}` (see `app/modules/leads/__init__.py`).
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException, NotFoundError
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org_unified
from app.modules.imovel_hub import busca_service
from app.modules.leads.deps import get_leads_client
from app.modules.leads.services import ad_lead_intake_backfill, ad_lead_intake_service as intake, corretores_vista_sync
from app.services import imovel_ref_avisos, table_reads

router = APIRouter(prefix="/api/leads/ad-intake", tags=["leads-ad-intake"])


class ResolverAvisoIn(StrictHttpModel):
    acao: Literal["confirmar_sumiu", "ciente"]
    nota: Optional[str] = None


class RestaurarAvisoIn(StrictHttpModel):
    nota: Optional[str] = None


class ResolverDivergenciaIn(StrictHttpModel):
    status: Literal["resolvida", "ignorada"]
    nota: Optional[str] = None


def get_ad_intake_core() -> Any:
    """Core client as a FastAPI dependency, so tests override the IDENTITY source and the real admin guard runs."""
    return get_core_client()


def _admin(core: Any, auth: tuple, request: Request, contexto: str) -> None:
    require_org_admin_for(core, auth, request, contexto)


@router.post("/backfill", status_code=200)
def backfill(
    request: Request,
    dry_run: bool = Query(default=True),
    limite: int = Query(default=ad_lead_intake_backfill.LIMITE_PADRAO, ge=1, le=ad_lead_intake_backfill.LIMITE_MAX),
    cursor: Optional[str] = Query(default=None),
    modo: Literal["novos", "pendentes", "refazer"] = Query(default="novos"),
    pausa_s: float = Query(default=0.0, ge=0, le=10),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
core: Any = Depends(get_ad_intake_core)) -> dict:
    _admin(core, auth, request, "O backfill do intake de leads de anúncio")
    org_id = coerce_org_uuid(auth[2])
    return success_response(
        ad_lead_intake_backfill.backfill_intake(client, org_id, dry_run=dry_run, limite=limite, cursor=cursor, modo=modo, pausa_s=pausa_s)
    )


@router.get("/resumo")
def resumo(auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client)) -> dict:
    return success_response(ad_lead_intake_backfill.resumo(client, coerce_org_uuid(auth[2])))


def _um(client: Any, tabela: str, org_id: UUID, **eq: Any) -> list[dict]:
    q = client.table(tabela).select("*").eq("org_id", str(org_id))
    for k, v in eq.items():
        q = q.eq(k, str(v))
    return list(q.execute().data or [])


@router.get("/lead/{lead_id}")
def get_intake_do_lead(lead_id: UUID, auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client)) -> dict:
    org_id = coerce_org_uuid(auth[2])
    leads = _um(client, "leads", org_id, id=lead_id)
    if not leads:
        raise NotFoundError("lead", str(lead_id))
    lead = leads[0]
    registro = next(iter(_um(client, "imovel_registry", org_id, id=lead["imovel_ref_id"])), None) if lead.get("imovel_ref_id") else None
    codigo = (registro or {}).get("codigo_canonical") or (lead.get("codigo_imovel") or "").strip().upper() or None
    return success_response(
        {
            "lead": {k: lead.get(k) for k in ("id", "meta_lead_id", "codigo_imovel", "imovel_ref_id", "corretor_id", "qualificacao_form")},
            "intake": next(iter(_um(client, intake.T_INTAKES, org_id, lead_id=lead_id)), None),
            "imovel": next(iter(_um(client, "imoveis", org_id, codigo_norm=codigo)), None) if codigo else None,
            "interesses": _um(client, "cliente_imovel_interesses", org_id, lead_id=lead_id),
            "corretores_do_imovel": _um(client, intake.T_CORRETORES, org_id, codigo_canonical=codigo) if codigo else [],
            "divergencia_corretor": next(iter(_um(client, intake.T_DIVERGENCIAS, org_id, lead_id=lead_id)), None),
        }
    )


@router.post("/lead/{lead_id}/retry")
def retry_intake(
    lead_id: UUID, request: Request, auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client), 
core: Any = Depends(get_ad_intake_core)) -> dict:
    _admin(core, auth, request, "O intake de leads de anúncio")
    org_id = coerce_org_uuid(auth[2])
    try:
        res = intake.intake_imovel_do_lead(client, org_id, lead_id)  # plain `def`: runs in the threadpool, no loop to block
    except LookupError as exc:
        raise NotFoundError("lead", str(lead_id)) from exc
    return success_response(res)


@router.get("/imovel/{codigo}/leads")
def leads_do_imovel(
    codigo: str,
    limite: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    """Leads linked to the property: `leads.imovel_ref_id` (the registry row) ∪ `cliente_imovel_interesses.lead_id`."""
    org_id = coerce_org_uuid(auth[2])
    canonico = busca_service.canonical(codigo)
    reg = next(iter(_um(client, "imovel_registry", org_id, codigo_canonical=canonico)), None)
    if reg is None:
        raise NotFoundError("imovel", canonico)
    ids = {str(r["id"]) for r in _um(client, "leads", org_id, imovel_ref_id=reg["id"])}
    ids |= {
        str(r["lead_id"])
        for r in table_reads.paged_rows(client, "cliente_imovel_interesses", org_id, eq_filters={"codigo": canonico}, refine=lambda q: q.is_("deleted_at", "null"))
        if r.get("lead_id")
    }
    leads = table_reads.in_batched_rows(
        client, "leads", org_id, "id", sorted(ids),
        select="id,cliente_nome,contato,data_entrada,origem_raw,corretor_id,created_at,meta_lead_id",
    )
    leads.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return success_response({"items": leads[offset: offset + limite], "total": len(leads), "codigo": canonico})


@router.get("/corretor-divergencias")
def listar_divergencias(
    status: Optional[Literal["pendente", "resolvida", "ignorada"]] = Query(default="pendente"),
    tipo: Optional[Literal["fora_dos_corretores", "nao_e_principal", "lead_sem_corretor"]] = Query(default=None),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    org_id = coerce_org_uuid(auth[2])
    rows = table_reads.paged_rows(client, intake.T_DIVERGENCIAS, org_id, eq_filters={k: v for k, v in (("status", status), ("tipo", tipo)) if v} or None)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return success_response({"items": rows, "total": len(rows)})


@router.post("/corretor-divergencias/{divergencia_id}/resolver")
def resolver_divergencia(
    divergencia_id: UUID,
    body: ResolverDivergenciaIn,
    request: Request,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
core: Any = Depends(get_ad_intake_core)) -> dict:
    _admin(core, auth, request, "A divergência de corretor")
    org_id = coerce_org_uuid(auth[2])
    linhas = _um(client, intake.T_DIVERGENCIAS, org_id, id=divergencia_id)
    if not linhas:
        raise NotFoundError("lead_corretor_divergencia", str(divergencia_id))
    patch = {"status": body.status, "nota": body.nota, "resolvido_em": intake._agora(), "resolvido_por": str(getattr(auth[0], "id", "") or "") or None}
    client.table(intake.T_DIVERGENCIAS).update(patch).eq("org_id", str(org_id)).eq("id", str(divergencia_id)).execute()
    return success_response({**linhas[0], **patch})


@router.get("/ref-avisos")
def listar_ref_avisos(
    tipo: Optional[Literal["ref_sumiu_no_vista", "ref_nova_no_vista"]] = Query(default=None),
    status: Optional[Literal["pendente", "restaurada", "confirmada_sumiu", "ciente"]] = Query(default="pendente"),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    rows = imovel_ref_avisos.listar(client, coerce_org_uuid(auth[2]), tipo=tipo, status=status)
    return success_response({"items": rows, "total": len(rows)})


def _resolver_aviso(aviso_id: UUID, acao: str, nota: Optional[str], auth: tuple, client: Any) -> dict:
    try:
        row = imovel_ref_avisos.resolver(client, coerce_org_uuid(auth[2]), aviso_id, acao, getattr(auth[0], "id", None), nota)
    except LookupError as exc:
        raise NotFoundError("imovel_ref_aviso", str(aviso_id)) from exc
    except imovel_ref_avisos.AcaoInvalida as exc:
        raise AppException("acao_invalida", str(exc), status_code=422) from exc
    return success_response(row)


@router.post("/ref-avisos/{aviso_id}/restaurar")
def restaurar_ref_aviso(
    aviso_id: UUID, request: Request, body: Optional[RestaurarAvisoIn] = None,
    auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
core: Any = Depends(get_ad_intake_core)) -> dict:
    _admin(core, auth, request, "Restaurar um imóvel que sumiu do Vista")
    return _resolver_aviso(aviso_id, "restaurar", body.nota if body else None, auth, client)


@router.post("/ref-avisos/{aviso_id}/resolver")
def resolver_ref_aviso(
    aviso_id: UUID, body: ResolverAvisoIn, request: Request,
    auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
core: Any = Depends(get_ad_intake_core)) -> dict:
    _admin(core, auth, request, "A divergência de ref com o Vista")
    return _resolver_aviso(aviso_id, body.acao, body.nota, auth, client)


class ConfigIn(StrictHttpModel):
    corretor_principal_fallback_vista_codigo: Optional[str] = None


class ResolverCorretorAvisoIn(StrictHttpModel):
    acao: Literal["resolvida", "ignorada"]
    nota: Optional[str] = None


@router.post("/corretores/sync")
def sincronizar_corretores(
    request: Request, dry_run: bool = Query(default=True),
    auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
core: Any = Depends(get_ad_intake_core)) -> dict:
    """Runs now (not queued): one roster read is a handful of calls. DRY-RUN by default: classifies, writes nothing."""
    from app.services import vista_credenciais

    _admin(core, auth, request, "A sincronização dos corretores com o Vista")
    org_id = coerce_org_uuid(auth[2])
    adapter = vista_credenciais.adapter_ou_503(org_id)
    return success_response(corretores_vista_sync.sincronizar_sync(client, adapter, org_id, dry_run=dry_run))


@router.get("/corretor-avisos")
def listar_corretor_avisos(
    status: Optional[Literal["pendente", "resolvida", "ignorada"]] = Query(default="pendente"),
    auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
) -> dict:
    rows = corretores_vista_sync.listar_avisos(client, coerce_org_uuid(auth[2]), status)
    return success_response({"items": rows, "total": len(rows)})


@router.post("/corretor-avisos/{aviso_id}/resolver")
def resolver_corretor_aviso(
    aviso_id: UUID, body: ResolverCorretorAvisoIn, request: Request,
    auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
core: Any = Depends(get_ad_intake_core)) -> dict:
    _admin(core, auth, request, "O aviso de corretor do Vista")
    try:
        return success_response(corretores_vista_sync.resolver_aviso(client, coerce_org_uuid(auth[2]), aviso_id, body.acao, getattr(auth[0], "id", None), body.nota))
    except LookupError as exc:
        raise NotFoundError("corretor_aviso", str(aviso_id)) from exc


@router.get("/config")
def get_config(auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client)) -> dict:
    return success_response(intake.config_do_org(client, coerce_org_uuid(auth[2])))


@router.put("/config")
def put_config(
    body: ConfigIn, request: Request, auth: tuple = Depends(get_current_user_org_unified), client: Any = Depends(get_leads_client),
core: Any = Depends(get_ad_intake_core)) -> dict:
    _admin(core, auth, request, "A configuração do intake de leads de anúncio")
    org_id = coerce_org_uuid(auth[2])
    codigo = (body.corretor_principal_fallback_vista_codigo or "").strip() or None
    patch = {"corretor_principal_fallback_vista_codigo": codigo, "updated_at": intake._agora(), "updated_by": str(getattr(auth[0], "id", "") or "") or None}
    if intake._um(client, intake.T_CONFIG, org_id, "org_id", org_id):
        client.table(intake.T_CONFIG).update(patch).eq("org_id", str(org_id)).execute()
    else:
        client.table(intake.T_CONFIG).insert({"org_id": str(org_id), **patch}).execute()
    return success_response(intake.config_do_org(client, org_id))


__all__ = ["router"]
