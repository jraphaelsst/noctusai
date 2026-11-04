"""Imóveis router — /api/imoveis.

Endpoints:
    GET  /api/imoveis                  → paginated rows: Vista mirror ∪ manual (imoveis_catalogo)
    GET  /api/imoveis/busca            → typeahead over the REGISTRY ∪ mirror
    GET  /api/imoveis/filtros          → distinct filter values (derived)
    GET  /api/imoveis/duplicatas       → possible manual-vs-Vista duplicate pairs (§8.6)
    GET  /api/imoveis/caracteristicas  → amenity slug → count, usage-ordered
    GET  /api/imoveis/{codigo}         → one imóvel (Vista mirror, or manual captação)
    POST /api/imoveis/sync?modo=…      → queue a Vista refresh (org admin; 202, poll /sync/ultimo)
    GET  /api/imoveis/sync/ultimo      → the last refresh run (path, counts, when)

Auth: ``Depends(get_current_user_org)`` on every route, no exceptions. Reads
go through the admin client with an explicit `org_id` filter — defense in
depth on top of RLS.

Reads hit `social_wiring.imoveis`, never Vista. Only `/sync` talks to the
CRM, and it is the write path.
"""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Literal, Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
)
from app.modules.imovel_hub import busca_service as busca_svc
from app.modules.imovel_hub import captacao_service as captacao_svc
from app.modules.imovel_hub import dados_service as dados_svc
from app.modules.imovel_hub import duplicatas_service as duplicatas_svc
from app.modules.imovel_hub import vinculo_service as vinculo_svc
from app.modules.imovel_hub.deps import get_imovel_hub_client
from app.services import vista_credenciais
from app.services import imoveis_atualizacao_service as atualizacao_svc
from app.services.imoveis_service import build_imoveis_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imoveis", tags=["imoveis"])


# ─── Schemas ──────────────────────────────────────────────────────────────


class ImovelPageOut(BaseModel):
    """`items` is deliberately `list[dict]`, not a per-field imóvel schema.

    The service already selects `*` and returns rows straight through, now
    including the 29 fields + the two presentation-only derived values
    (`orientacao_solar`, `dias_desde_atualizacao`) from CONTRACT §1/§3
    (`imoveis-vista-field-surface`). A hand-maintained field allowlist here
    would have to grow in lockstep with every future Vista column and would
    silently drop one the moment it didn't — the exact "hand-maintained
    list drifts" failure mode CLAUDE.md §1 calls out. Nothing narrows the
    row between the service and the client.
    """

    items: list[dict] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    pages: int = 1


class FiltrosOut(BaseModel):
    status: list[str] = Field(default_factory=list)
    categoria: list[str] = Field(default_factory=list)
    cidade: list[str] = Field(default_factory=list)
    bairro: list[str] = Field(default_factory=list)


# ─── Routes ───────────────────────────────────────────────────────────────


@router.get("", response_model=ImovelPageOut)
async def list_imoveis(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    status_: Optional[str] = Query(None, alias="status"),
    categoria: Optional[str] = None,
    cidade: Optional[str] = None,
    bairro: Optional[str] = None,
    search: Optional[str] = None,
    caracteristicas: Optional[list[str]] = Query(None),
    possivel_duplicado: Optional[bool] = Query(
        None, description="true = only imóveis with a pending possible-duplicate pair."
    ),
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> ImovelPageOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    result = build_imoveis_service(db).list(
        org_id,
        page=page,
        page_size=page_size,
        status=status_,
        categoria=categoria,
        cidade=cidade,
        bairro=bairro,
        search=search,
        caracteristicas=caracteristicas,
        possivel_duplicado=possivel_duplicado,
    )
    return ImovelPageOut(**result)


@router.get("/busca")
def buscar_imoveis(
    q: str = Query(..., min_length=busca_svc.TERMO_MINIMO),
    limit: int = Query(
        busca_svc.LIMITE_PADRAO, ge=1, le=busca_svc.LIMITE_MAXIMO
    ),
    auth=Depends(get_current_user_org),
    db=Depends(get_imovel_hub_client),
) -> dict:
    """Typeahead over the REGISTRY ∪ the mirror — every imóvel we have ever
    seen, not only the ones Vista lists today.

    🔴 SEPARATE FROM `GET /api/imoveis?search=`, and not a replacement for it.
    That route is the catalog browser: paginated, filterable, mirror-only, and
    correct for what it does — a person browsing what is FOR SALE does not want
    sold properties in the grid. This one answers "which imóvel do you mean?"
    for a picker whose every downstream FK points at `imovel_registry`, where
    35% of rows (prod, 2026-08-25) are absent from the mirror precisely because
    they SOLD. Collapsing the two would break one of them.

    Response is `{"items": [...], "total": n}` per the house envelope, where
    `total` is the length of `items` — see `busca_service.buscar` for why this
    endpoint deliberately does not report a catalog count.

    Declared BEFORE `/{codigo}`: `busca` is a perfectly valid código and
    FastAPI matches in declaration order. `test_static_routes_are_declared_
    before_the_catch_all` holds this shut.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return busca_svc.buscar(db, org_id, termo=q, limite=limit)


@router.get("/busca/duplicatas")
def buscar_possiveis_duplicatas(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=busca_svc.LIMITE_MAXIMO),
    auth=Depends(get_current_user_org),
    db=Depends(get_imovel_hub_client),
) -> dict:
    """"Did you mean one of these?" for `ImovelCodigoPicker`'s "cadastrar
    como imóvel novo" step (migration 159) — see `busca_service.
    sugestoes_para_cadastro`. Called only when `/busca` for the same term
    already came back empty; never a hard block.

    Declared BEFORE `/{codigo}` for the same reason `/busca` is: FastAPI
    matches path segments in declaration order and `busca` (a literal
    prefix segment here, not a `codigo` value) would otherwise be shadowed.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return busca_svc.sugestoes_para_cadastro(db, org_id, termo=q, limite=limit)


# 🔴 ROUTE ORDER — lives HERE and not in the `imovel_hub` router: this router is
# mounted FIRST and its `GET /{codigo}` would read a one-segment `/duplicatas`
# as an imóvel whose código is "DUPLICATAS" (the same trap `/conflitos` documents
# in `imovel_hub/router.py`). The mutating routes (`/duplicatas/{id}/descartar`,
# `/duplicatas/{id}/vincular`, `/{codigo}/desvincular`) are POSTs on 2-3 segments
# and live in `imovel_hub/router.py`. A test pins both.
@router.get("/duplicatas")
def list_duplicatas(
    status_: str = Query("pendente", alias="status"),
    auth=Depends(get_current_user_org),
    hub=Depends(get_imovel_hub_client),
) -> list[dict]:
    """Possible manual-vs-Vista duplicate pairs (CONTRACT §8.6), highest score
    first: `[{id, score, sinais, status, detectado_em, resolvido_por,
    resolvido_em, manual: ImovelResumo, vista: ImovelResumo}]`. Bare JSON."""
    _user, _token, raw_org = auth
    return duplicatas_svc.listar(hub, coerce_org_uuid(raw_org), status=status_)


@router.get("/filtros", response_model=FiltrosOut)
def get_filtros(
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> FiltrosOut:
    """Filter dropdown values, derived from stored rows — never hardcoded."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return FiltrosOut(**build_imoveis_service(db).filter_options(org_id))


@router.get("/caracteristicas")
def get_caracteristicas(
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
) -> dict[str, int]:
    """Amenity slug → imóvel count, usage-ordered.

    The UI orders filters by this and drops the zeroes — the census found 28
    of the 76 tenant keys are never `Sim`, and showing them would be 28
    filters that always return nothing.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return build_imoveis_service(db).caracteristica_counts(org_id)


#: Strong references to in-flight refresh tasks (the loop only holds a weak one).
_TAREFAS: set = set()


class SyncIniciadoOut(BaseModel):
    """`POST /sync` queues the run and returns at once: a full refresh takes minutes. Poll `GET /sync/ultimo`."""

    execucao_id: str
    status: str
    ja_em_andamento: bool = False


def get_core_for_sync() -> Any:
    """DI seam: the core client (the admin notice) — tests override."""
    from app.dependencies import get_core_client

    return get_core_client()


def get_sync_service_factory() -> Any:
    """DI seam: `None` = the real `build_sync_service` — tests inject a double."""
    return None


def _admin_ou_403(core: Any, auth: tuple, request: Optional[Request]) -> None:
    from noctusai_lib.api.auth.session import require_org_admin_for

    require_org_admin_for(core, auth, request, "A atualização de imóveis do Vista")


@router.post("/sync", response_model=SyncIniciadoOut, status_code=status.HTTP_202_ACCEPTED)
async def sync_imoveis(
    modo: Literal["auto", "listar", "detalhes"] = Query(
        "auto",
        description=(
            "auto: try Vista's listar, fall back to the per-code refresh when listar is silent; "
            "listar: only listar; detalhes: only the per-code refresh."
        ),
    ),
    escopo: Literal["vitrine", "resto", "todos"] = Query(
        "vitrine", description="Per-code refresh scope (ignored when listar answers).",
    ),
    request: Request = None,
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
    core=Depends(get_core_for_sync),
    sync_factory=Depends(get_sync_service_factory),
) -> SyncIniciadoOut:
    """Queue a Vista refresh of THIS org's catalog (org admin). Idempotent — upserts by (org_id, codigo); a click
    while a run is going returns the running one (single flight)."""
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    await anyio.to_thread.run_sync(lambda: _admin_ou_403(core, auth, request))

    # THIS org's own credential (encrypted store); an org with none is a 503, never an env fallback.
    adapter = await anyio.to_thread.run_sync(lambda: vista_credenciais.adapter_ou_503(org_id))

    user_id = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    linha, nova = await anyio.to_thread.run_sync(
        lambda: atualizacao_svc.iniciar(db, org_id, origem="manual", modo=modo, escopo=escopo, user_id=user_id)
    )
    if nova:
        tarefa = asyncio.get_running_loop().create_task(
            atualizacao_svc.executar(
                db, adapter, org_id, modo=modo, escopo=escopo, origem="manual", user_id=user_id,
                execucao_id=linha["id"], core=core, sync_factory=sync_factory,
            )
        )
        _TAREFAS.add(tarefa)
        tarefa.add_done_callback(_TAREFAS.discard)
    return SyncIniciadoOut(execucao_id=str(linha["id"]), status=linha.get("status", "em_andamento"), ja_em_andamento=not nova)


class UltimaAtualizacaoOut(BaseModel):
    """What the list page shows under "Última atualização do Vista"."""

    execucao_id: Optional[str] = None
    em_andamento: bool = False
    status: Optional[str] = None
    caminho: Optional[str] = None
    origem: Optional[str] = None
    iniciado_em: Optional[str] = None
    finalizado_em: Optional[str] = None
    novos: int = 0
    atualizados: int = 0
    inalterados: int = 0
    removidos: int = 0
    falhas: int = 0
    chamadas: dict = Field(default_factory=dict)
    sincronizado_em: Optional[str] = None


@router.get("/sync/ultimo", response_model=UltimaAtualizacaoOut)
def ultima_atualizacao(auth=Depends(get_current_user_org), db=Depends(get_admin_client)) -> UltimaAtualizacaoOut:
    """The last refresh run of this org (any org member may read it) + the newest `sincronizado_em` of the mirror."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    linha = atualizacao_svc.ultima_execucao(db, org_id)
    mirror = (
        db.schema("social_wiring").table("imoveis").select("sincronizado_em").eq("org_id", str(org_id))
        .order("sincronizado_em", desc=True).limit(1).execute().data or []
    )
    base = {"sincronizado_em": mirror[0].get("sincronizado_em") if mirror else None}
    if linha is None:
        return UltimaAtualizacaoOut(**base)
    rel = linha.get("relatorio") or {}
    return UltimaAtualizacaoOut(
        execucao_id=str(linha["id"]), em_andamento=linha.get("status") == "em_andamento", status=linha.get("status"),
        caminho=linha.get("caminho"), origem=linha.get("origem"), iniciado_em=linha.get("iniciado_em"),
        finalizado_em=linha.get("finalizado_em"), novos=int(rel.get("novos") or 0), atualizados=int(rel.get("atualizados") or 0),
        inalterados=int(rel.get("inalterados") or 0), removidos=int(rel.get("removidos") or 0), falhas=int(rel.get("falhas") or 0),
        chamadas=rel.get("chamadas") or {}, **base,
    )


# Declared LAST: `/{codigo}` would otherwise shadow `/filtros`,
# `/caracteristicas` and `/sync`, since FastAPI matches in declaration order
# and a bare path segment is a valid `codigo`.
#
# `-> dict`, no `response_model`, DELIBERATELY — same reasoning as
# `ImovelPageOut.items` above: `ImoveisService.get` already returns every
# column plus the derived `orientacao_solar`/`dias_desde_atualizacao`
# (CONTRACT §3), and a typed schema here would just be a second field list
# to keep in sync with the first.
#
# The Vista row is READ-ONLY (Vista rejects writes on this key — CONTRACT
# §"Scope"); the editable surfaces are `PATCH /manuais/{codigo}` and
# `PATCH /{codigo}/referencias`, both on the `imovel_hub` router (CONTRACT
# §8.3). A MANUAL código (migration 226) has no mirror row: it is built from
# `imovel_captacao` + `imovel_dados` into the SAME shape, `fonte: "manual"`.
# Every imóvel carries `fonte` and `referencias`.
@router.get("/{codigo}")
async def get_imovel(
    codigo: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_admin_client),
    hub=Depends(get_imovel_hub_client),
) -> dict:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    canonico = codigo.strip().upper()
    imoveis = build_imoveis_service(db)
    row = imoveis.get(org_id, canonico)
    if row is not None:
        dados = (await anyio.to_thread.run_sync(lambda: dados_svc.linha(hub, org_id, canonico)))
        row["fonte"] = "vista"
        row["referencias"] = dados_svc.referencias_da_linha(dados)
        # `empreendimento` is already the mirror's column; the condomínio
        # answer is ours (imovel_dados, migration 300) — on the shape for EVERY
        # imóvel so the edit modal needs no second query.
        row.update(captacao_svc.condominio_campos(dados))
        row["condominio"] = (await anyio.to_thread.run_sync(lambda: dados_svc.condominio_resumo(hub, org_id, (dados or {}).get("condominio_id"))))
        return _com_vinculo(hub, org_id, canonico, row)
    manual = captacao_svc.obter_manual(hub, org_id, canonico)
    if manual is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Imóvel {codigo} não encontrado.",
        )
    vinculo = (await anyio.to_thread.run_sync(lambda: vinculo_svc.resolver_vinculo(hub, org_id, canonico)))
    if vinculo is not None and vinculo.manual_codigo == canonico:
        # LINKED (§8.7): the Vista listing's catalog data, the manual record's
        # own código / address / referências / condomínio.
        listagem = imoveis.get(org_id, vinculo.vista_codigo)
        if listagem is not None:
            manual = captacao_svc.sobrepor_listagem_vista(manual, listagem)
    return _com_vinculo(hub, org_id, canonico, manual)


def _com_vinculo(hub, org_id, canonico: str, imovel: dict) -> dict:
    """`vinculo` + `duplicatas_pendentes` on the Imovel shape (every imóvel)."""
    vinculo = vinculo_svc.resolver_vinculo(hub, org_id, canonico)
    imovel["vinculo"] = vinculo.as_dict() if vinculo else None
    imovel["duplicatas_pendentes"] = duplicatas_svc.pendentes_do_imovel(hub, org_id, canonico)
    return imovel
