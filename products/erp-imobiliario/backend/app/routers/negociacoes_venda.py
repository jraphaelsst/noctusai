"""
Negociações de Venda Router — the Funil's deal entity + the accept-proposal seam.

NOT `/api/negociacoes` — that is the PERMUTA (property-swap) router. This is a
sibling resource at `/api/negociacoes-venda`. See
`app/services/negociacoes_venda_service.py` for why the names collide.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from app.dependencies import get_current_user, get_user_client, log_action, first_or_none
from app.responses import success_response
from app.services.negociacoes_venda_service import (
    NEGOCIACAO_SELECT,
    STATUS_ABERTA,
    STATUS_ACEITA,
    STATUS_PERDIDA,
    group_into_colunas,
    negociacao_row_to_dto,
    negociacao_rows_to_dto,
    search_negociacoes,
)
from app.services.processos_venda_service import processo_row_to_dto
from app.services.pipelines import (
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    legacy_etapa_update,
)
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.domain.pipeline import (
    STAGE_ROLE_ACCEPT,
    get_stage,
    move_card,
    resolve_initial_stage,
    stage_by_role,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/negociacoes-venda", tags=["Negociações de Venda"])


class NegociacaoCreate(StrictHttpModel):
    cliente_id: str
    titulo: Optional[str] = Field(default=None, max_length=255)
    # Omitted → the DB DEFAULT (`erp.agency_profile_id()`) applies. The corretor
    # is swappable by design; `erp.clientes.usuario_id` was already the corretor,
    # what was missing was reassignment + a default for unassigned deals.
    corretor_id: Optional[str] = None
    etapa_id: Optional[str] = None
    valor_estimado: Optional[float] = Field(default=None, ge=0)
    probabilidade: Optional[int] = Field(default=None, ge=0, le=100)


class NegociacaoUpdate(StrictHttpModel):
    titulo: Optional[str] = Field(default=None, max_length=255)
    corretor_id: Optional[str] = None
    etapa_id: Optional[str] = None
    valor_estimado: Optional[float] = Field(default=None, ge=0)
    probabilidade: Optional[int] = Field(default=None, ge=0, le=100)
    arquivado: Optional[bool] = None


class MoverEtapaRequest(StrictHttpModel):
    # A stage ID, not a name. Stages are user-editable rows since migration
    # 042, so the destination must be identified by something a rename cannot
    # change.
    para_etapa_id: str
    motivo: Optional[str] = None
    novo_indice: Optional[int] = None


class PerderNegociacaoRequest(StrictHttpModel):
    motivo: Optional[str] = None


def _resolve_etapa_id(db, etapa_id: str) -> dict:
    """Validate a stage ID against THIS pipeline's configured stages.

    Replaces a membership test against the `erp.etapa_funil` enum: since
    migration 042 the stage vocabulary is per-organization rows, so the enum is
    no longer the authority on what is a legal stage.
    """
    return get_stage(db, PIPELINE_FUNIL, etapa_id)


@router.get("")
async def listar_negociacoes(
    busca: Optional[str] = Query(None),
    corretor_id: Optional[str] = Query(None),
    etapa_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    cliente_id: Optional[str] = Query(None),
    incluir_arquivados: bool = Query(False),
    auth=Depends(get_current_user),
):
    """Flat list of negociações. The kanban board uses `/api/funil` instead."""
    _user, token = auth
    db = get_user_client(token)

    query = db.table("negociacoes_venda").select(NEGOCIACAO_SELECT).order(
        "kanban_pos", desc=False
    )
    if not incluir_arquivados:
        query = query.eq("arquivado", False)
    if etapa_id:
        query = query.eq("etapa_id", etapa_id)
    if status:
        query = query.eq("status", status)
    if cliente_id:
        query = query.eq("cliente_id", cliente_id)
    if corretor_id and corretor_id != "todos":
        query = query.eq("corretor_id", corretor_id)

    rows = query.execute().data or []
    if busca:
        rows = search_negociacoes(rows, busca)

    return success_response(negociacao_rows_to_dto(rows))


@router.post("")
async def criar_negociacao(body: NegociacaoCreate, auth=Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    # A deal with no explicit stage enters at the FIRST configured stage —
    # derived from the user's own order, not a hardcoded 'qualificacao'.
    etapa_id = data.pop("etapa_id", None)
    stage = _resolve_etapa_id(db, etapa_id) if etapa_id else resolve_initial_stage(db, PIPELINE_FUNIL)
    data["etapa_id"] = stage["id"]
    data.update(legacy_etapa_update(PIPELINE_FUNIL, stage))

    # Corretor resolution — same rule as clientes, deliberately. Explicit
    # assignment wins (including an explicit `AGENCY_PROFILE_ID`, which is how
    # a deal is left unassigned); otherwise the CREATOR owns it.
    #
    # NOT defaulted to the agency: this table's SELECT policy is
    # `has_role(admin) OR auth.uid() = corretor_id`, so an agency-owned deal is
    # invisible to the corretor who created it. The agency is the DB-level
    # DEFAULT (satisfying NOT NULL for service-role/import paths with no real
    # corretor) and the explicit unassign target — not the default for a
    # request made by an identifiable user.
    data.setdefault("corretor_id", user.id)

    row = first_or_none(db.table("negociacoes_venda").insert(data).execute())
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao criar negociação")

    log_action(
        user.id, "criar", "negociacao_venda", row["id"],
        f"Criou negociação para cliente {body.cliente_id}",
    )
    return success_response(negociacao_row_to_dto(row))


@router.get("/{negociacao_id}")
async def obter_negociacao(negociacao_id: str, auth=Depends(get_current_user)):
    _user, token = auth
    db = get_user_client(token)

    result = db.table("negociacoes_venda").select(NEGOCIACAO_SELECT).eq(
        "id", negociacao_id
    ).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Negociação não encontrada")
    return success_response(negociacao_row_to_dto(result.data))


@router.patch("/{negociacao_id}")
async def atualizar_negociacao(
    negociacao_id: str, body: NegociacaoUpdate, auth=Depends(get_current_user)
):
    user, token = auth
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    if "etapa_id" in data:
        stage = _resolve_etapa_id(db, data["etapa_id"])
        data.update(legacy_etapa_update(PIPELINE_FUNIL, stage))

    row = first_or_none(
        db.table("negociacoes_venda").update(data).eq("id", negociacao_id).execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Negociação não encontrada")

    log_action(user.id, "editar", "negociacao_venda", negociacao_id,
               f"Editou negociação {negociacao_id}")
    return success_response(negociacao_row_to_dto(row))


@router.post("/{negociacao_id}/mover-etapa")
async def mover_etapa(
    negociacao_id: str, body: MoverEtapaRequest, auth=Depends(get_current_user)
):
    """Move a negociação across Funil stages, writing the transition to history.

    The move mechanic (validate → update → record → log) now lives in
    `noctusai_lib.domain.pipeline.move_card`, shared with Processos de Venda.
    It used to be duplicated here, and the duplicate had already lost the
    history write on the other board.
    """
    user, token = auth
    db = get_user_client(token)

    current = db.table("negociacoes_venda").select(
        "id, status"
    ).eq("id", negociacao_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Negociação não encontrada")

    # A closed deal is off the board; moving it would resurrect it into a stage
    # while its status still says closed — an inconsistency the board cannot
    # render honestly.
    if current.data["status"] != STATUS_ABERTA:
        raise HTTPException(
            status_code=409,
            detail=f"Negociação não está aberta (status: {current.data['status']})",
        )

    destino = get_stage(db, PIPELINE_FUNIL, body.para_etapa_id)

    row = move_card(
        db,
        PIPELINE_FUNIL,
        card_id=negociacao_id,
        to_stage_id=body.para_etapa_id,
        user_id=user.id,
        novo_indice=body.novo_indice,
        motivo=body.motivo,
        log_action=log_action,
        extra_updates=legacy_etapa_update(PIPELINE_FUNIL, destino),
    )
    return success_response(negociacao_row_to_dto(row))


@router.post("/{negociacao_id}/aceitar-proposta")
async def aceitar_proposta(negociacao_id: str, auth=Depends(get_current_user)):
    """Accept the proposal: close the negociação and open its processo de venda.

    The seam between the two boards (roadmap P2.3). Only valid from the
    `proposta` stage — accepting is what ENDS the negotiation, so it cannot be
    triggered from a stage where no proposal is on the table.

    IDEMPOTENT: `processos_venda.negociacao_venda_id` is UNIQUE, so a second
    processo is impossible rather than merely unlikely. A repeat click short-
    circuits on the pre-check; a genuinely CONCURRENT one loses the insert race
    and is caught below, re-reading the winner's row. Either way the caller gets
    200 and the existing processo — the deal is in execution, which is what was
    asked for.
    """
    user, token = auth
    db = get_user_client(token)

    current = db.table("negociacoes_venda").select(
        "id, cliente_id, corretor_id, etapa, etapa_id, status, valor_estimado"
    ).eq("id", negociacao_id).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Negociação não encontrada")

    negociacao = current.data

    existing = db.table("processos_venda").select("*").eq(
        "negociacao_venda_id", negociacao_id
    ).execute()
    existing_row = first_or_none(existing)
    if existing_row:
        return success_response({
            "negociacao": negociacao_row_to_dto(negociacao),
            "processo": processo_row_to_dto(existing_row),
            "already_accepted": True,
        })

    if negociacao["status"] != STATUS_ABERTA:
        raise HTTPException(
            status_code=409,
            detail=f"Negociação não está aberta (status: {negociacao['status']})",
        )

    # Resolve the gate stage by ROLE, never by name. Stages are user-editable
    # since migration 042: renaming "Proposta" to "Em Proposta", recolouring it
    # or moving it to the front of the board must not break this seam, and
    # comparing against the literal slug 'proposta' would break all three.
    stage_aceite = stage_by_role(db, PIPELINE_FUNIL, STAGE_ROLE_ACCEPT)
    if not stage_aceite:
        raise HTTPException(
            status_code=409,
            detail=(
                "Nenhuma etapa do funil está marcada como etapa de aceite de "
                "proposta. Defina o papel 'proposta_aceite' em uma etapa nas "
                "configurações do funil."
            ),
        )
    if negociacao.get("etapa_id") != stage_aceite["id"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Só é possível aceitar a proposta de uma negociação na etapa "
                f"'{stage_aceite['label']}'"
            ),
        )

    etapa_inicial = resolve_initial_stage(db, PIPELINE_PROCESSOS)

    try:
        processo = first_or_none(db.table("processos_venda").insert({
            "cliente_id": negociacao["cliente_id"],
            "negociacao_venda_id": negociacao_id,
            "corretor_id": negociacao["corretor_id"],
            "etapa_id": etapa_inicial["id"],
            "valor": negociacao.get("valor_estimado") or 0,
            **legacy_etapa_update(PIPELINE_PROCESSOS, etapa_inicial),
        }).execute())
    except Exception as exc:
        # The select-then-insert above is not atomic. Two concurrent clicks can
        # both pass the `existing_row` check, and the second insert then
        # violates the UNIQUE constraint on `negociacao_venda_id`.
        #
        # That constraint is the real idempotency guarantee — it makes a second
        # processo impossible rather than merely unlikely — but the loser of the
        # race previously surfaced as a 500. Re-reading and returning the
        # winner's row honours what the caller actually asked for: this deal is
        # in execution.
        existing_row = first_or_none(
            db.table("processos_venda").select("*").eq(
                "negociacao_venda_id", negociacao_id
            ).execute()
        )
        if not existing_row:
            raise
        logger.info(
            "aceitar_proposta: concurrent accept for negociacao=%s resolved to "
            "the existing processo (%s)", negociacao_id, exc,
        )
        return success_response({
            "negociacao": negociacao_row_to_dto(negociacao),
            "processo": processo_row_to_dto(existing_row),
            "already_accepted": True,
        })

    if not processo:
        raise HTTPException(status_code=500, detail="Erro ao criar processo de venda")

    # The deal leaves the Funil entirely (user decision, roadmap 2026-07-16).
    # `closed_at` is what makes negotiation cycle-time measurable — the CHECK
    # constraint in migration 040 refuses a closed status without it.
    negociacao_fechada = first_or_none(
        db.table("negociacoes_venda").update({
            "status": STATUS_ACEITA,
            "closed_at": "now()",
        }).eq("id", negociacao_id).execute()
    )

    log_action(
        user.id, "editar", "negociacao_venda", negociacao_id,
        "Aceitou proposta — negociação movida para Processos de Venda",
        {"processo_id": processo["id"]},
    )
    return success_response({
        "negociacao": negociacao_row_to_dto(negociacao_fechada or negociacao),
        "processo": processo_row_to_dto(processo),
        "already_accepted": False,
    })


@router.post("/{negociacao_id}/perder")
async def perder_negociacao(
    negociacao_id: str, body: PerderNegociacaoRequest, auth=Depends(get_current_user)
):
    """Mark a deal lost — the other way off the board.

    Without this, 'perdida' would be an enum value nothing can ever produce,
    and conversion statistics would have no denominator.
    """
    user, token = auth
    db = get_user_client(token)

    current = db.table("negociacoes_venda").select("id, status").eq(
        "id", negociacao_id
    ).single().execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Negociação não encontrada")
    if current.data["status"] != STATUS_ABERTA:
        raise HTTPException(
            status_code=409,
            detail=f"Negociação não está aberta (status: {current.data['status']})",
        )

    row = first_or_none(
        db.table("negociacoes_venda").update({
            "status": STATUS_PERDIDA,
            "closed_at": "now()",
        }).eq("id", negociacao_id).execute()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Negociação não encontrada")

    log_action(user.id, "editar", "negociacao_venda", negociacao_id,
               "Marcou negociação como perdida", {"motivo": body.motivo})
    return success_response(negociacao_row_to_dto(row))


@router.delete("/{negociacao_id}")
async def excluir_negociacao(negociacao_id: str, auth=Depends(get_current_user)):
    user, token = auth
    db = get_user_client(token)

    existing = db.table("negociacoes_venda").select("id").eq(
        "id", negociacao_id
    ).execute()
    if not first_or_none(existing):
        raise HTTPException(status_code=404, detail="Negociação não encontrada")

    db.table("negociacoes_venda").delete().eq("id", negociacao_id).execute()
    log_action(user.id, "excluir", "negociacao_venda", negociacao_id,
               f"Excluiu negociação {negociacao_id}")
    return success_response({"id": negociacao_id})
