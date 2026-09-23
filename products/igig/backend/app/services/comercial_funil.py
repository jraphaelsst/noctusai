"""Comercial funnel — the negócio card's lifecycle (roadmap R2/R4).

    open   `abrir_negocio`  a lead enters the funnel at the entry stage
    move   `mover_negocio`  drag between stages (seed `move_card`)
    close  moving INTO the `fechado`-role stage — REQUIRES an orçamento of this
           negócio: accepts it (siblings → substituido), marks the negócio
           ganho and creates the Cliente from the lead (idempotent)
    lose   `perder_negocio` archive with a required reason (loss statistics)

Every rule keys on the stage ROLE (`papel`), never its label or position, so
the owner may rename/reorder "Fechado" without opening a bypass.

Writes are ordered so that a retry after a mid-way failure converges instead
of duplicating: every read-and-validate happens BEFORE the first write, the
Cliente is found-or-created by `lead_id` (backed by the unique index
`idx_igig_cliente_lead`), and an orçamento already `aceito` for this negócio is
accepted again as a no-op.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from noctusai_lib.domain.pipeline import get_stage, group_into_colunas, move_card
from noctusai_lib.integrations.persistence.table_reads import paged_rows

from app.pipelines import PAPEL_FECHADO, PIPELINE_COMERCIAL, etapas
from app.services import quadro_comum as qc
from app.services.regras import RegraViolada

logger = logging.getLogger(__name__)

__all__ = [
    "NEGOCIO_SELECT",
    "abrir_negocio",
    "mover_negocio",
    "perder_negocio",
    "quadro",
    "listar_negocios",
    "buscar_negocio",
]

CFG = PIPELINE_COMERCIAL

NEGOCIO_SELECT = (
    "id, org_id, lead_id, titulo, valor_estimado, etapa_id, kanban_pos, responsavel_id, "
    "status, stage_entered_at, ganho_em, perdido_em, motivo_perda, perdido_stage_id, "
    "orcamento_aceito_id, cliente_id, data_inicio, data_entrega, entrega_concluida, "
    "created_at, updated_at"
)
_LEAD_CARD = "id, nome, empresa, email, telefone, instagram, origem, status"

#: Statuses an orçamento must NOT be in to be accepted at close.
_ORCAMENTO_ENCERRADO = {"recusado", "expirado", "substituido"}
#: Sibling statuses a close supersedes ("only one acceptable version").
_ORCAMENTO_EM_ABERTO = ("rascunho", "enviado")


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dwell_dias(row: dict) -> float | None:
    """Days spent in the stage a `perdido` negócio was archived from.

    `None` for anything else, or when a timestamp is missing (a row from
    before either column existed) — an approximate number would be worse
    than none."""
    if row.get("status") != "perdido":
        return None
    entrada, saida = row.get("stage_entered_at"), row.get("perdido_em")
    if not entrada or not saida:
        return None
    inicio = datetime.fromisoformat(str(entrada))
    fim = datetime.fromisoformat(str(saida))
    if inicio.tzinfo is None:
        inicio = inicio.replace(tzinfo=timezone.utc)
    if fim.tzinfo is None:
        fim = fim.replace(tzinfo=timezone.utc)
    return round((fim - inicio).total_seconds() / 86400, 1)


# ── Read ─────────────────────────────────────────────────────────────
def _card_dto(
    row: dict, leads: dict[str, dict], responsaveis: dict[str, dict],
    etapas_por_id: dict[str, dict] | None = None,
) -> dict:
    lead = leads.get(str(row.get("lead_id")))
    resp = responsaveis.get(str(row.get("responsavel_id")))
    estagio = (etapas_por_id or {}).get(str(row.get("perdido_stage_id")))
    return {
        **row,
        "lead": lead,
        "responsavel": {"id": resp["id"], "nome": resp.get("nome")} if resp else None,
        "perdido_stage": {"id": estagio["id"], "label": estagio.get("label")} if estagio else None,
        "dwell_dias": _dwell_dias(row),
    }


def quadro(db: Any, org_id: str, *, limite_por_etapa: int | None = None) -> list[dict]:
    """Columns of OPEN + WON negócios, one per active stage (empty ones too).

    Lost negócios are an archive, not a column (roadmap decision 2026-09-22):
    they would otherwise sit in the funnel math as if still in play.
    """
    stages = etapas(db, CFG, org_id)
    linhas = paged_rows(
        db, CFG.card_table, org_id,
        refine=lambda q: q.in_("status", ["aberto", "ganho"]),
        select=NEGOCIO_SELECT,
    )
    leads = qc.por_ids(db, "lead", org_id, (r.get("lead_id") for r in linhas), select=_LEAD_CARD)
    responsaveis = qc.por_ids(
        db, "profissional", org_id, (r.get("responsavel_id") for r in linhas), select="id, nome"
    )
    return group_into_colunas(
        CFG, stages, linhas,
        row_to_dto=lambda r: _card_dto(r, leads, responsaveis),
        limite_cards=limite_por_etapa,
    )


def listar_negocios(
    db: Any, org_id: str, *, status: str | None = None, q: str | None = None,
) -> list[dict]:
    """Every negócio for the org, ANY status — the board (`quadro`) only ever
    holds `aberto`/`ganho` ones, so this is how a `perdido` archive (or a
    deep-linked lookup) is listed. `q` searches the card's título.
    """
    def _refine(query: Any) -> Any:
        if status:
            query = query.eq("status", status)
        if q:
            query = query.ilike("titulo", f"%{q}%")
        return query

    linhas = paged_rows(db, CFG.card_table, org_id, refine=_refine, select=NEGOCIO_SELECT)
    leads = qc.por_ids(db, "lead", org_id, (r.get("lead_id") for r in linhas), select=_LEAD_CARD)
    responsaveis = qc.por_ids(
        db, "profissional", org_id, (r.get("responsavel_id") for r in linhas), select="id, nome"
    )
    estagios = qc.por_ids(
        db, "pipeline_stages", org_id, (r.get("perdido_stage_id") for r in linhas), select="id, label"
    )
    return [_card_dto(r, leads, responsaveis, estagios) for r in linhas]


def buscar_negocio(db: Any, org_id: str, negocio_id: str) -> dict:
    """One negócio card, ANY status — the same shape `quadro` puts on the
    board, so the FE can open a card regardless of where it links from
    (perdido archive, an orçamento, a search result)."""
    row = qc.carregar(db, CFG.card_table, org_id, negocio_id, select=NEGOCIO_SELECT, rotulo="negócio")
    leads = qc.por_ids(db, "lead", org_id, [row.get("lead_id")], select=_LEAD_CARD)
    responsaveis = qc.por_ids(db, "profissional", org_id, [row.get("responsavel_id")], select="id, nome")
    estagios = qc.por_ids(
        db, "pipeline_stages", org_id, [row.get("perdido_stage_id")], select="id, label"
    )
    return _card_dto(row, leads, responsaveis, estagios)


# ── Open ─────────────────────────────────────────────────────────────
def abrir_negocio(
    db: Any,
    org_id: str,
    *,
    lead_id: str,
    titulo: str | None = None,
    valor_estimado: float | None = None,
    responsavel_id: str | None = None,
    user_id: Any = None,
) -> dict:
    """Put a lead on the funnel: a new negócio at the entry stage, on top.

    The entry stage is the FIRST active stage by position — whatever the
    owner named or moved there.
    """
    lead = qc.carregar(db, "lead", org_id, lead_id, select="id, nome, empresa")
    if responsavel_id:
        qc.carregar(db, "profissional", org_id, responsavel_id, select="id", rotulo="profissional")
    stages = etapas(db, CFG, org_id)
    if not stages:
        raise RegraViolada(
            409, "funil_sem_etapas",
            "O funil comercial não tem nenhuma etapa ativa. Configure as etapas primeiro.",
        )
    entrada = stages[0]
    posicao = qc.posicao_no_topo(db, CFG, org_id=org_id, etapa_id=entrada["id"])
    criado = (
        db.table(CFG.card_table)
        .insert(
            {
                "org_id": org_id,
                "lead_id": lead["id"],
                "titulo": (titulo or lead.get("empresa") or lead.get("nome") or "Negócio").strip(),
                "valor_estimado": valor_estimado,
                "responsavel_id": responsavel_id,
                "etapa_id": entrada["id"],
                "kanban_pos": str(posicao),
                "status": "aberto",
                "stage_entered_at": _agora(),
            }
        )
        .execute()
        .data
        or []
    )
    if not criado:
        raise RuntimeError("insert de negocio não retornou a linha criada")
    negocio = criado[0]
    qc.registrar_entrada(
        db, CFG, org_id=org_id, card_id=str(negocio["id"]), etapa_id=entrada["id"], user_id=user_id
    )
    logger.info("negocio aberto org=%s negocio=%s lead=%s", org_id, negocio["id"], lead["id"])
    return negocio


# ── Move / close ─────────────────────────────────────────────────────
def mover_negocio(
    db: Any,
    org_id: str,
    *,
    negocio_id: str,
    para_etapa_id: str,
    user_id: Any,
    novo_indice: int | None = None,
    motivo: str | None = None,
    orcamento_id: str | None = None,
) -> dict:
    """Move a negócio card. Entering the `fechado` stage closes the deal.

    Raises :class:`RegraViolada`:
      409 `negocio_perdido`       — a lost deal is archived, not on the board
      409 `negocio_ganho`         — a won deal cannot leave Fechado
      409 `orcamento_obrigatorio` — closing without naming the accepted orçamento
      409 `orcamento_invalido`    — not this negócio's, or recusado/expirado/substituido
      409 `orcamento_expirado`    — its `validade` is past
      409 `orcamento_ja_aceito`   — ANOTHER orçamento of this negócio is aceito
    """
    negocio = qc.carregar(db, CFG.card_table, org_id, negocio_id, select=NEGOCIO_SELECT,
                          rotulo="negócio")
    destino = get_stage(db, CFG, para_etapa_id, org_id=org_id)
    mudou = str(negocio.get("etapa_id")) != str(destino["id"])

    if negocio.get("status") == "perdido":
        raise RegraViolada(409, "negocio_perdido", "Este negócio foi marcado como perdido.")
    if negocio.get("status") == "ganho" and mudou:
        raise RegraViolada(
            409, "negocio_ganho",
            "Um negócio fechado não sai da etapa de fechamento.",
        )

    extra: dict[str, Any] = {}
    if mudou:
        extra["stage_entered_at"] = _agora()
    if mudou and destino.get("papel") == PAPEL_FECHADO:
        extra.update(_fechar(db, org_id, negocio, orcamento_id))

    return move_card(
        db, CFG,
        card_id=negocio_id,
        to_stage_id=destino["id"],
        user_id=user_id,
        nova_posicao=qc.posicao_para_indice(
            db, CFG, org_id=org_id, etapa_id=destino["id"], indice=novo_indice, card_id=negocio_id
        ),
        motivo=motivo,
        extra_updates=extra,
        org_id=org_id,
    )


def _validar_orcamento(db: Any, org_id: str, negocio_id: str, orcamento_id: str | None) -> dict:
    if not orcamento_id:
        raise RegraViolada(
            409, "orcamento_obrigatorio",
            "Para fechar o negócio, informe qual orçamento foi aceito.",
        )
    linhas = (
        db.table("orcamento").select("id, negocio_id, status, validade")
        .eq("id", orcamento_id).eq("org_id", org_id).execute().data or []
    )
    if not linhas or str(linhas[0].get("negocio_id")) != str(negocio_id):
        raise RegraViolada(409, "orcamento_invalido", "Este orçamento não pertence a este negócio.")
    orcamento = linhas[0]
    if orcamento.get("status") in _ORCAMENTO_ENCERRADO:
        raise RegraViolada(
            409, "orcamento_invalido",
            f"Este orçamento está {orcamento['status']} e não pode ser aceito.",
        )
    validade = orcamento.get("validade")
    if orcamento.get("status") != "aceito" and validade and str(validade)[:10] < date.today().isoformat():
        raise RegraViolada(409, "orcamento_expirado", "A validade deste orçamento já passou.")

    outro_aceito = (
        db.table("orcamento").select("id")
        .eq("org_id", org_id).eq("negocio_id", negocio_id).eq("status", "aceito")
        .neq("id", orcamento_id).execute().data or []
    )
    if outro_aceito:
        raise RegraViolada(
            409, "orcamento_ja_aceito",
            "Outro orçamento deste negócio já foi aceito — feche com ele.",
        )
    return orcamento


def _garantir_cliente(db: Any, org_id: str, negocio: dict) -> str:
    """The Cliente this deal becomes — found or created, never duplicated."""
    if negocio.get("cliente_id"):
        return str(negocio["cliente_id"])
    lead = qc.carregar(
        db, "lead", org_id, str(negocio["lead_id"]),
        select="id, nome, empresa, email, telefone, origem, cliente_id",
    )
    cliente_id = lead.get("cliente_id")
    if not cliente_id:
        existentes = (
            db.table("cliente").select("id")
            .eq("org_id", org_id).eq("lead_id", lead["id"]).execute().data or []
        )
        cliente_id = existentes[0]["id"] if existentes else None
    if not cliente_id:
        criado = (
            db.table("cliente").insert(
                {
                    "org_id": org_id,
                    "nome": lead.get("empresa") or lead.get("nome"),
                    "email": lead.get("email"),
                    "telefone": lead.get("telefone"),
                    "origem": lead.get("origem"),
                    "lead_id": lead["id"],
                    "negocio_id": negocio["id"],
                    "status": "prospect",
                }
            ).execute().data or []
        )
        if not criado:
            raise RuntimeError("insert de cliente não retornou a linha criada")
        cliente_id = criado[0]["id"]
        logger.info("cliente criado a partir do lead org=%s lead=%s cliente=%s",
                    org_id, lead["id"], cliente_id)
    db.table("lead").update({"status": "convertido", "cliente_id": cliente_id}).eq(
        "id", lead["id"]
    ).eq("org_id", org_id).execute()
    return str(cliente_id)


def _fechar(db: Any, org_id: str, negocio: dict, orcamento_id: str | None) -> dict:
    """Validate, accept the orçamento, ensure the Cliente; return the card updates."""
    negocio_id = str(negocio["id"])
    orcamento = _validar_orcamento(db, org_id, negocio_id, orcamento_id)
    cliente_id = _garantir_cliente(db, org_id, negocio)
    agora = _agora()

    # Siblings first: the partial unique index allows ONE `aceito` per negócio,
    # and superseding the open versions before accepting keeps every
    # intermediate state valid.
    db.table("orcamento").update({"status": "substituido"}).eq("org_id", org_id).eq(
        "negocio_id", negocio_id
    ).in_("status", list(_ORCAMENTO_EM_ABERTO)).neq("id", orcamento["id"]).execute()

    aceite: dict[str, Any] = {"cliente_id": cliente_id}
    if orcamento.get("status") != "aceito":
        aceite.update({"status": "aceito", "aceito_em": agora})
    db.table("orcamento").update(aceite).eq("id", orcamento["id"]).eq("org_id", org_id).execute()

    logger.info("negocio fechado org=%s negocio=%s orcamento=%s cliente=%s",
                org_id, negocio_id, orcamento["id"], cliente_id)
    return {
        "status": "ganho",
        "ganho_em": agora,
        "orcamento_aceito_id": orcamento["id"],
        "cliente_id": cliente_id,
    }


# ── Lose ─────────────────────────────────────────────────────────────
def perder_negocio(db: Any, org_id: str, *, negocio_id: str, motivo: str) -> dict:
    """Archive an open deal with its reason, the stage it died in and when.

    Recorded rather than deleted: loss rate by stage and by reason is what the
    owner asked this data for.
    """
    negocio = qc.carregar(db, CFG.card_table, org_id, negocio_id, select=NEGOCIO_SELECT,
                          rotulo="negócio")
    if negocio.get("status") != "aberto":
        raise RegraViolada(
            409, "negocio_encerrado",
            f"Só um negócio em aberto pode ser marcado como perdido (status: {negocio.get('status')}).",
        )
    if not (motivo or "").strip():
        raise RegraViolada(422, "motivo_obrigatorio", "Informe o motivo da perda.")
    linhas = (
        db.table(CFG.card_table).update(
            {
                "status": "perdido",
                "perdido_em": _agora(),
                "motivo_perda": motivo.strip(),
                "perdido_stage_id": negocio.get("etapa_id"),
            }
        ).eq("id", negocio_id).eq("org_id", org_id).execute().data or []
    )
    if not linhas:
        raise RuntimeError("update de negocio não retornou a linha")
    return linhas[0]
