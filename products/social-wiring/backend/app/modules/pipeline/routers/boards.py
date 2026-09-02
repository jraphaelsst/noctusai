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

import logging

from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.services import table_reads
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

logger = logging.getLogger(__name__)


def _valores_negociados(client, org_id: str, rows: list[dict]) -> dict[str, float]:
    """`atendimento_id → valor_negociado`, for the cards on this board.

    One batched read for the whole board, not one per card. Returns only the
    atendimentos that HAVE a negociação with a value — a missing key is the
    caller's cue to fall back, and is the normal case for a card nobody has
    priced yet.
    """
    ids = [str(r["id"]) for r in rows if r.get("id")]
    if not ids:
        return {}
    linhas = table_reads.in_batched_rows(
        client, "atendimento_negociacao", coerce_org_uuid(org_id), "atendimento_id", ids,
        select="atendimento_id,valor_negociado",
        # This table is keyed on `atendimento_id` — it has no `id` column.
        order_col="atendimento_id",
    )
    out: dict[str, float] = {}
    for linha in linhas:
        bruto = linha.get("valor_negociado")
        if bruto is None:
            continue
        try:
            out[str(linha["atendimento_id"])] = float(bruto)
        except (TypeError, ValueError):
            # PostgREST hands `numeric` back as a JSON number, but a string is
            # what the API layer serialises. Neither should ever be garbage —
            # if it is, this card is worth 0 rather than taking the board down.
            logger.warning(
                "funil: valor_negociado ilegível para atendimento %s: %r",
                linha.get("atendimento_id"), bruto,
            )
    return out


def _valor_do_card(card: dict, valores: dict[str, float]) -> float:
    """What a funil card is worth.

    🔴 The negotiated value WINS over `valor_estimado`, and the order is the
    point. `valor_estimado` is a field the board has always offered and nobody
    has ever filled — every column read R$ 0,00 in production while holding a
    thousand leads. `valor_negociado` is typed by the person closing the deal,
    on the screen where the number matters. An estimate is what you have
    before you have the real figure; once the real figure exists it is not a
    tie-break, it is the answer.
    """
    negociado = valores.get(str(card.get("id")))
    if negociado is not None:
        return negociado
    return float(card.get("valor_estimado") or 0)


#: Cards returned per column by default. The counts and the column total are
#: always computed over EVERY card — this only bounds what crosses the wire.
#:
#: 🔴 Measured, not guessed: in production on 2026-08-25 the "Qualificação"
#: column held 1.070 cards, `/api/funil` took 3.248 ms, and a column that long
#: is not a board anyone triages — it is a list you scroll past. 50 is roughly
#: two screens, which is as far as a person reads before filtering instead.
LIMITE_CARDS_PADRAO = 50


def _intake_stage(stages: list[dict]) -> set[str]:
    """The stage new cards land on — its column sorts newest-first.

    `list_stages` returns stages already ordered by `posicao`, so the first
    element IS the leftmost column, and migration 034's trigger drops every
    new card there. That column answers "what just came in", so a hand-arranged
    `kanban_pos` order is the wrong thing for it — a lead that arrived a minute
    ago belongs on top, not wherever its position happens to fall.

    Derived from the stage list rather than hardcoded to a slug: the stages are
    per-org rows the user renames and reorders freely ("Qualificação" is only
    the default), so pinning a name here would silently stop matching the day
    somebody edits it. Empty list ⇒ empty set, never an IndexError.
    """
    return {stages[0]["id"]} if stages else set()


@funil_router.get("")
def obter_funil(
    busca: Optional[str] = Query(None),
    etapa_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    limite_por_etapa: int = Query(LIMITE_CARDS_PADRAO, ge=1, le=1000),
    auth: tuple = Depends(get_current_user_org_unified),
) -> dict:
    """Kanban columns of OPEN negociações, grouped by the org's configured
    stages — ONE card per person (P1.4): a row collapsed into a sibling
    (`substituida_por IS NOT NULL`) is excluded here, and the survivor's
    DTO carries the union of every folded row's origin data — see
    `configs.attach_colapsadas`.

    Each column carries `total` (every open card in that stage) and
    `exibidos` (how many this response actually contains). The board asks for
    one stage with a bigger `limite_por_etapa` when the user wants more.
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

    # 🔴 ORDER MATTERS, AND SEARCH IS WHY IT DIFFERS.
    #
    # `attach_colapsadas` fires a batched follow-up read per survivor and is
    # the expensive half of this endpoint. When nothing is being searched we
    # can bucket and truncate FIRST and enrich only the cards that will
    # actually be sent — 1.070 rows became ~300 in production.
    #
    # A search cannot do that: `search_atendimentos` matches on `lead` /
    # `campanha`, which only exist AFTER the merge. Truncating first would
    # hide matches that live past the cut, which is worse than being slow.
    if busca:
        rows = attach_colapsadas(ctx.db, ctx.org_id, rows)
        rows = search_atendimentos(rows, busca)
        enriquecer = None
    else:
        enriquecer = lambda visiveis: attach_colapsadas(ctx.db, ctx.org_id, visiveis)

    valores = _valores_negociados(ctx.db, ctx.org_id, rows)

    colunas = group_into_colunas(
        PIPELINE_FUNIL,
        stages,
        rows,
        # DTO conversion is deferred so the enrichment above can run on the
        # truncated set of raw rows first.
        row_to_dto=None,
        value_of=lambda card: _valor_do_card(card, valores),
        limite_cards=limite_por_etapa,
        # 🔴 Interacts with `limite_por_etapa` — which is why it is applied
        # server-side. The truncation runs AFTER this sort, so the intake
        # column's first 50 are the 50 NEWEST leads. Sorting in the browser
        # would only reorder whichever 50 the server had already picked by
        # `kanban_pos`, i.e. a column that claims "newest" and is not.
        recency_first_stages=_intake_stage(stages),
    )

    for coluna in colunas:
        visiveis = coluna["cards"]
        if enriquecer is not None and visiveis:
            visiveis = enriquecer(visiveis)
        coluna["cards"] = [atendimento_to_dto(c) for c in visiveis]

    return success_response(colunas)


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
        group_into_colunas(
            PIPELINE_PROCESSOS,
            stages,
            rows,
            row_to_dto=processo_to_dto,
            recency_first_stages=_intake_stage(stages),
        )
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
