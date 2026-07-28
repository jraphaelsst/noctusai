"""
Funil de Vendas + Processos de Venda — `/api/funil`, `/api/negociacoes-venda`,
`/api/processos-venda`.

Every stage-move goes through `noctusai_lib.domain.pipeline.move_card`, which
writes the transition to `social_wiring.pipeline_movimentos`. That is not a
convention here — it is literally the same function erp calls, so this board
cannot ship without an audit trail the way erp's Processos board once did.

Cards are NOT created here. A card exists because a lead arrived, and the
trigger installed by migration 034 spawns it — for leads from the router, from
the workbook importer, and from the Meta Lead-Ads sync alike. There is
deliberately no `POST /api/negociacoes-venda`.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.domain.pipeline import (
    STAGE_ROLE_ACCEPT,
    get_stage,
    group_into_colunas,
    list_stages,
    move_card,
    resolve_initial_stage,
    stage_by_role,
)
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_current_user_org_unified
from app.modules.pipeline.configs import (
    NEGOCIACAO_SELECT,
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    PROCESSO_SELECT,
    negociacao_to_dto,
    processo_to_dto,
    search_negociacoes,
    search_processos,
)
from app.modules.pipeline.deps import pipeline_context

funil_router = APIRouter(prefix="/api/funil", tags=["funil"])
negociacoes_router = APIRouter(prefix="/api/negociacoes-venda", tags=["negociacoes-venda"])
processos_router = APIRouter(prefix="/api/processos-venda", tags=["processos-venda"])

STATUS_ABERTA = "aberta"


class MoverEtapaRequest(StrictHttpModel):
    # A stage ID, never a name — stages are user-editable rows.
    para_etapa_id: str
    motivo: Optional[str] = None
    novo_indice: Optional[int] = None


class NegociacaoUpdate(StrictHttpModel):
    titulo: Optional[str] = Field(default=None, max_length=255)
    valor_estimado: Optional[float] = Field(default=None, ge=0)
    arquivado: Optional[bool] = None


class ProcessoUpdate(StrictHttpModel):
    valor: Optional[float] = Field(default=None, ge=0)
    observacoes: Optional[str] = None
    arquivado: Optional[bool] = None


class PerderRequest(StrictHttpModel):
    motivo: Optional[str] = None


# ─────────────────────────────── Funil board ────────────────────────────────

@funil_router.get("")
def obter_funil(
    busca: Optional[str] = Query(None),
    etapa_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    """Kanban columns of OPEN negociações, grouped by the org's configured stages."""
    ctx = pipeline_context(auth)
    stages = list_stages(ctx.db, PIPELINE_FUNIL, org_id=ctx.org_id)

    query = (
        ctx.db.table("negociacoes_venda")
        .select(NEGOCIACAO_SELECT)
        .eq("org_id", ctx.org_id)
        .eq("status", STATUS_ABERTA)
    )
    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa_id:
        query = query.eq("etapa_id", etapa_id)

    rows = query.execute().data or []
    if busca:
        rows = search_negociacoes(rows, busca)

    return success_response(
        group_into_colunas(PIPELINE_FUNIL, stages, rows, row_to_dto=negociacao_to_dto)
    )


@negociacoes_router.get("")
def listar_negociacoes(
    status: Optional[str] = Query(None),
    lead_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    """Flat list — the board uses `/api/funil` instead."""
    ctx = pipeline_context(auth)
    query = ctx.db.table("negociacoes_venda").select(NEGOCIACAO_SELECT).eq("org_id", ctx.org_id)
    if status:
        query = query.eq("status", status)
    if lead_id:
        query = query.eq("lead_id", lead_id)
    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    rows = query.execute().data or []
    return success_response([negociacao_to_dto(r) for r in rows])


@negociacoes_router.patch("/{negociacao_id}")
def atualizar_negociacao(
    negociacao_id: str,
    body: NegociacaoUpdate,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)
    data = body.model_dump(exclude_none=True)
    if not data:
        raise ValidationError_("Nenhum campo para atualizar.")
    rows = (
        ctx.db.table("negociacoes_venda")
        .update(data)
        .eq("id", negociacao_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not rows:
        raise NotFoundError("Negociação", negociacao_id)
    return success_response(negociacao_to_dto(rows[0]))


@negociacoes_router.post("/{negociacao_id}/mover-etapa")
def mover_negociacao(
    negociacao_id: str,
    body: MoverEtapaRequest,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)

    current = (
        ctx.db.table("negociacoes_venda")
        .select("id, status")
        .eq("id", negociacao_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not current:
        raise NotFoundError("Negociação", negociacao_id)
    # A closed deal is off the board; moving it would resurrect it into a stage
    # while its status still says closed.
    if current[0]["status"] != STATUS_ABERTA:
        raise ValidationError_(
            f"Negociação não está aberta (status: {current[0]['status']})."
        )

    row = move_card(
        ctx.db,
        PIPELINE_FUNIL,
        card_id=negociacao_id,
        to_stage_id=body.para_etapa_id,
        user_id=ctx.user_id,
        novo_indice=body.novo_indice,
        motivo=body.motivo,
        org_id=ctx.org_id,
    )
    return success_response(negociacao_to_dto(row))


@negociacoes_router.post("/{negociacao_id}/aceitar-proposta")
def aceitar_proposta(
    negociacao_id: str,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    """Accept the proposal: close the negociação and open its processo.

    The seam between the two boards. Gated on the stage's ROLE, never its name,
    so renaming or reordering "Proposta" cannot break it.

    IDEMPOTENT: `processos_venda.negociacao_venda_id` is UNIQUE, so a second
    processo is impossible. A repeat click short-circuits on the pre-check; a
    genuinely concurrent one loses the insert race and is caught below.
    """
    ctx = pipeline_context(auth)

    current = (
        ctx.db.table("negociacoes_venda")
        .select("id, etapa_id, status, valor_estimado")
        .eq("id", negociacao_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not current:
        raise NotFoundError("Negociação", negociacao_id)
    negociacao = current[0]

    existing = (
        ctx.db.table("processos_venda")
        .select(PROCESSO_SELECT)
        .eq("negociacao_venda_id", negociacao_id)
        .execute()
        .data
        or []
    )
    if existing:
        return success_response({
            "negociacao": negociacao_to_dto(negociacao),
            "processo": processo_to_dto(existing[0]),
            "already_accepted": True,
        })

    if negociacao["status"] != STATUS_ABERTA:
        raise ValidationError_(
            f"Negociação não está aberta (status: {negociacao['status']})."
        )

    stage_aceite = stage_by_role(ctx.db, PIPELINE_FUNIL, STAGE_ROLE_ACCEPT, org_id=ctx.org_id)
    if not stage_aceite:
        raise ValidationError_(
            "Nenhuma etapa do funil está marcada como etapa de aceite de proposta. "
            "Defina o papel 'proposta_aceite' em uma etapa nas configurações do funil."
        )
    if negociacao.get("etapa_id") != stage_aceite["id"]:
        raise ValidationError_(
            f"Só é possível aceitar a proposta de uma negociação na etapa "
            f"'{stage_aceite['label']}'."
        )

    etapa_inicial = resolve_initial_stage(ctx.db, PIPELINE_PROCESSOS, org_id=ctx.org_id)

    try:
        created = (
            ctx.db.table("processos_venda")
            .insert({
                "org_id": ctx.org_id,
                "negociacao_venda_id": negociacao_id,
                "etapa_id": etapa_inicial["id"],
                "valor": negociacao.get("valor_estimado") or 0,
            })
            .execute()
            .data
            or []
        )
    except Exception:
        # Lost the race against a concurrent accept — the UNIQUE constraint is
        # the real guarantee; re-read and return the winner's row rather than
        # surfacing a 500 for a request whose intent was already satisfied.
        existing = (
            ctx.db.table("processos_venda")
            .select(PROCESSO_SELECT)
            .eq("negociacao_venda_id", negociacao_id)
            .execute()
            .data
            or []
        )
        if not existing:
            raise
        return success_response({
            "negociacao": negociacao_to_dto(negociacao),
            "processo": processo_to_dto(existing[0]),
            "already_accepted": True,
        })

    # The deal leaves the Funil entirely. `closed_at` is what makes cycle-time
    # measurable — the CHECK in 034 refuses a closed status without it.
    fechada = (
        ctx.db.table("negociacoes_venda")
        .update({"status": "aceita", "closed_at": "now()"})
        .eq("id", negociacao_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )

    return success_response({
        "negociacao": negociacao_to_dto(fechada[0] if fechada else negociacao),
        "processo": processo_to_dto(created[0]),
        "already_accepted": False,
    })


@negociacoes_router.post("/{negociacao_id}/perder")
def perder_negociacao(
    negociacao_id: str,
    body: PerderRequest,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)
    rows = (
        ctx.db.table("negociacoes_venda")
        .update({"status": "perdida", "closed_at": "now()"})
        .eq("id", negociacao_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not rows:
        raise NotFoundError("Negociação", negociacao_id)
    return success_response(negociacao_to_dto(rows[0]))


# ───────────────────────── Processos de Venda board ─────────────────────────

@processos_router.get("")
def obter_processos(
    busca: Optional[str] = Query(None),
    etapa_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)
    stages = list_stages(ctx.db, PIPELINE_PROCESSOS, org_id=ctx.org_id)

    query = ctx.db.table("processos_venda").select(PROCESSO_SELECT).eq("org_id", ctx.org_id)
    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa_id:
        query = query.eq("etapa_id", etapa_id)

    rows = query.execute().data or []
    if busca:
        rows = search_processos(rows, busca)

    return success_response(
        group_into_colunas(PIPELINE_PROCESSOS, stages, rows, row_to_dto=processo_to_dto)
    )


@processos_router.patch("/{processo_id}")
def atualizar_processo(
    processo_id: str,
    body: ProcessoUpdate,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)
    data = body.model_dump(exclude_none=True)
    if not data:
        raise ValidationError_("Nenhum campo para atualizar.")
    rows = (
        ctx.db.table("processos_venda")
        .update(data)
        .eq("id", processo_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not rows:
        raise NotFoundError("Processo", processo_id)
    return success_response(processo_to_dto(rows[0]))


@processos_router.post("/{processo_id}/mover-etapa")
def mover_processo(
    processo_id: str,
    body: MoverEtapaRequest,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)
    get_stage(ctx.db, PIPELINE_PROCESSOS, body.para_etapa_id, org_id=ctx.org_id)
    row = move_card(
        ctx.db,
        PIPELINE_PROCESSOS,
        card_id=processo_id,
        to_stage_id=body.para_etapa_id,
        user_id=ctx.user_id,
        novo_indice=body.novo_indice,
        org_id=ctx.org_id,
    )
    return success_response(processo_to_dto(row))


@processos_router.post("/{processo_id}/arquivar")
def arquivar_processo(
    processo_id: str,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    """Toggle archive — how a finished processo leaves the terminal column."""
    ctx = pipeline_context(auth)
    current = (
        ctx.db.table("processos_venda")
        .select("id, arquivado")
        .eq("id", processo_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not current:
        raise NotFoundError("Processo", processo_id)
    rows = (
        ctx.db.table("processos_venda")
        .update({"arquivado": not current[0]["arquivado"]})
        .eq("id", processo_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    return success_response(processo_to_dto(rows[0] if rows else current[0]))
