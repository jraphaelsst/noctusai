"""
Funil de Vendas + Processos de Venda — `/api/funil`, `/api/atendimentos-venda`,
`/api/processos-venda`.

Every stage-move goes through `noctusai_lib.domain.pipeline.move_card`, which
writes the transition to `social_wiring.pipeline_movimentos`. That is not a
convention here — it is literally the same function erp calls, so this board
cannot ship without an audit trail the way erp's Processos board once did.

Cards are NOT created here. A card exists because a lead arrived, and the
trigger installed by migration 034 spawns it — for leads from the router, from
the workbook importer, and from the Meta Lead-Ads sync alike. There is
deliberately no `POST /api/atendimentos-venda`.
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
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_current_user_org_unified
from app.modules.pipeline import stage_gate
from app.modules.pipeline.configs import (
    ATENDIMENTO_SELECT,
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    PROCESSO_SELECT,
    attach_colapsadas,
    atendimento_to_dto,
    processo_to_dto,
    search_atendimentos,
    search_processos,
)
from app.modules.pipeline.deps import pipeline_context

funil_router = APIRouter(prefix="/api/funil", tags=["funil"])
atendimentos_router = APIRouter(prefix="/api/atendimentos-venda", tags=["atendimentos-venda"])
processos_router = APIRouter(prefix="/api/processos-venda", tags=["processos-venda"])

STATUS_ABERTA = "aberta"


def _fetch_all(build_query, *, label: str) -> list[dict]:
    """Walk an offset-paged PostgREST read to completion.

    Every board read here used to be a bare `.select().execute()`, which
    PostgREST silently caps at `db-max-rows` (1000 on Supabase) with no
    error and no truncation signal. That is the single bug class this
    product has shipped to production most often — a summary reporting
    `total=1000` against 12 177 real rows (2026-07-22), and 365 of 1 365
    negociações silently skipped (`98377d26`). The board was under the cap
    only by the luck of its per-org + `status='aberta'` filtering, which is
    not a property anyone maintains on purpose.

    `build_query` returns a FRESH query per page on purpose: a PostgREST
    builder accumulates state, so reusing one would compound `.range()`
    across pages. Termination is the pager's problem, not ours
    (`noctusai_lib.integrations.persistence.iter_paged_rows`) — an
    offset loop that trusts the backend to honour `range()` hangs forever
    against one that does not.
    """

    def fetch_page(start: int, end: int):
        return build_query().order("id").range(start, end).execute().data

    return list(iter_paged_rows(fetch_page, label=label))


class MoverEtapaRequest(StrictHttpModel):
    # A stage ID, never a name — stages are user-editable rows.
    para_etapa_id: str
    motivo: Optional[str] = None
    novo_indice: Optional[int] = None


class AtendimentoUpdate(StrictHttpModel):
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
    """Kanban columns of OPEN negociações, grouped by the org's configured
    stages — ONE card per person (P1.4): a row collapsed into a sibling
    (`substituida_por IS NOT NULL`) is excluded here, and the survivor's
    DTO carries the union of every folded row's origin data — see
    `configs.attach_colapsadas`.
    """
    ctx = pipeline_context(auth)
    stages = list_stages(ctx.db, PIPELINE_FUNIL, org_id=ctx.org_id)

    def build_query():
        query = (
            ctx.db.table("atendimentos")
            .select(ATENDIMENTO_SELECT)
            .eq("org_id", ctx.org_id)
            .eq("status", STATUS_ABERTA)
            .is_("substituida_por", "null")
        )
        if not incluir_arquivados:
            query = query.eq("arquivado", False)
        if etapa_id:
            query = query.eq("etapa_id", etapa_id)
        return query

    rows = _fetch_all(build_query, label="funil negociações")
    rows = attach_colapsadas(ctx.db, ctx.org_id, rows)
    if busca:
        rows = search_atendimentos(rows, busca)

    return success_response(
        group_into_colunas(PIPELINE_FUNIL, stages, rows, row_to_dto=atendimento_to_dto)
    )


@atendimentos_router.get("")
def listar_atendimentos(
    status: Optional[str] = Query(None),
    lead_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    """Flat list — the board uses `/api/funil` instead. Same P1.4 exclusion
    as `obter_funil` (a collapsed row is never a valid list entry), without
    the origin-merge — this endpoint has no frontend consumer today (see
    the delivery note) and keeping it a plain projection avoids paying the
    sibling-fetch cost for a path nothing reads."""
    ctx = pipeline_context(auth)
    def build_query():
        query = (
            ctx.db.table("atendimentos")
            .select(ATENDIMENTO_SELECT)
            .eq("org_id", ctx.org_id)
            .is_("substituida_por", "null")
        )
        if status:
            query = query.eq("status", status)
        if lead_id:
            query = query.eq("lead_id", lead_id)
        if not incluir_arquivados:
            query = query.eq("arquivado", False)
        return query

    rows = _fetch_all(build_query, label="negociações")
    return success_response([atendimento_to_dto(r) for r in rows])


@atendimentos_router.patch("/{atendimento_id}")
def atualizar_atendimento(
    atendimento_id: str,
    body: AtendimentoUpdate,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)
    data = body.model_dump(exclude_none=True)
    if not data:
        raise ValidationError_("Nenhum campo para atualizar.")
    rows = (
        ctx.db.table("atendimentos")
        .update(data)
        .eq("id", atendimento_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not rows:
        raise NotFoundError("Atendimento", atendimento_id)
    return success_response(atendimento_to_dto(rows[0]))


@atendimentos_router.post("/{atendimento_id}/mover-etapa")
def mover_atendimento(
    atendimento_id: str,
    body: MoverEtapaRequest,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)

    current = (
        ctx.db.table("atendimentos")
        .select("id, status, cliente_id")
        .eq("id", atendimento_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not current:
        raise NotFoundError("Atendimento", atendimento_id)
    # A closed deal is off the board; moving it would resurrect it into a stage
    # while its status still says closed.
    if current[0]["status"] != STATUS_ABERTA:
        raise ValidationError_(
            f"Atendimento não está aberta (status: {current[0]['status']})."
        )

    # 🔴 ORDER MATTERS: the target stage is validated BEFORE the data gate.
    #
    # `move_card` validates the stage itself, so this look-up is redundant for
    # the happy path — but without it the completeness gate below runs first
    # and answers a bad/foreign `para_etapa_id` with a 400 about missing client
    # data instead of the 404 the stage deserves. That trades a precise error
    # for a misleading one, and tells the caller about OUR record when their
    # request never named a valid destination. Same reason `mover_processo`
    # resolves its stage up front.
    get_stage(ctx.db, PIPELINE_FUNIL, body.para_etapa_id, org_id=ctx.org_id)

    # The card cannot advance while nobody knows who this is or how to reach
    # them — see `stage_gate` for why the rule is asked of the checklist rather
    # than re-derived from columns here.
    pendentes = stage_gate.pendencias(ctx.db, ctx.org_id, current[0].get("cliente_id"))
    if pendentes:
        raise ValidationError_(stage_gate.mensagem(pendentes))

    row = move_card(
        ctx.db,
        PIPELINE_FUNIL,
        card_id=atendimento_id,
        to_stage_id=body.para_etapa_id,
        user_id=ctx.user_id,
        novo_indice=body.novo_indice,
        motivo=body.motivo,
        org_id=ctx.org_id,
    )
    return success_response(atendimento_to_dto(row))


@atendimentos_router.post("/{atendimento_id}/aceitar-proposta")
def aceitar_proposta(
    atendimento_id: str,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    """Accept the proposal: close the negociação and open its processo.

    The seam between the two boards. Gated on the stage's ROLE, never its name,
    so renaming or reordering "Proposta" cannot break it.

    IDEMPOTENT: `processos_venda.atendimento_id` is UNIQUE, so a second
    processo is impossible. A repeat click short-circuits on the pre-check; a
    genuinely concurrent one loses the insert race and is caught below.
    """
    ctx = pipeline_context(auth)

    current = (
        ctx.db.table("atendimentos")
        .select("id, etapa_id, status, valor_estimado")
        .eq("id", atendimento_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not current:
        raise NotFoundError("Atendimento", atendimento_id)
    atendimento = current[0]

    existing = (
        ctx.db.table("processos_venda")
        .select(PROCESSO_SELECT)
        .eq("atendimento_id", atendimento_id)
        .execute()
        .data
        or []
    )
    if existing:
        return success_response({
            "atendimento": atendimento_to_dto(atendimento),
            "processo": processo_to_dto(existing[0]),
            "already_accepted": True,
        })

    if atendimento["status"] != STATUS_ABERTA:
        raise ValidationError_(
            f"Atendimento não está aberta (status: {atendimento['status']})."
        )

    stage_aceite = stage_by_role(ctx.db, PIPELINE_FUNIL, STAGE_ROLE_ACCEPT, org_id=ctx.org_id)
    if not stage_aceite:
        raise ValidationError_(
            "Nenhuma etapa do funil está marcada como etapa de aceite de proposta. "
            "Defina o papel 'proposta_aceite' em uma etapa nas configurações do funil."
        )
    if atendimento.get("etapa_id") != stage_aceite["id"]:
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
                "atendimento_id": atendimento_id,
                "etapa_id": etapa_inicial["id"],
                "valor": atendimento.get("valor_estimado") or 0,
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
            .eq("atendimento_id", atendimento_id)
            .execute()
            .data
            or []
        )
        if not existing:
            raise
        return success_response({
            "atendimento": atendimento_to_dto(atendimento),
            "processo": processo_to_dto(existing[0]),
            "already_accepted": True,
        })

    # The deal leaves the Funil entirely. `closed_at` is what makes cycle-time
    # measurable — the CHECK in 034 refuses a closed status without it.
    fechada = (
        ctx.db.table("atendimentos")
        .update({"status": "aceita", "closed_at": "now()"})
        .eq("id", atendimento_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )

    return success_response({
        "atendimento": atendimento_to_dto(fechada[0] if fechada else atendimento),
        "processo": processo_to_dto(created[0]),
        "already_accepted": False,
    })


@atendimentos_router.post("/{atendimento_id}/perder")
def perder_atendimento(
    atendimento_id: str,
    body: PerderRequest,
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    ctx = pipeline_context(auth)
    rows = (
        ctx.db.table("atendimentos")
        .update({"status": "perdida", "closed_at": "now()"})
        .eq("id", atendimento_id)
        .eq("org_id", ctx.org_id)
        .execute()
        .data
        or []
    )
    if not rows:
        raise NotFoundError("Atendimento", atendimento_id)
    return success_response(atendimento_to_dto(rows[0]))


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

    def build_query():
        query = ctx.db.table("processos_venda").select(PROCESSO_SELECT).eq("org_id", ctx.org_id)
        if not incluir_arquivados:
            query = query.eq("arquivado", False)
        if etapa_id:
            query = query.eq("etapa_id", etapa_id)
        return query

    rows = _fetch_all(build_query, label="processos de venda")
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
