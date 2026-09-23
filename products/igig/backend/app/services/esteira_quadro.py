"""Esteira board — tarefa lifecycle on user-editable stages (roadmap R3).

Rules, keyed on stage ORDER and ROLE (never labels):

* FORWARD one step at a time (409 `etapa_invalida` otherwise) — skipping
  "Revisão interna" is exactly the shortcut the esteira exists to prevent;
* BACKWARD any distance, but only with a reason (422 `motivo_obrigatorio`),
  which the seed `move_card` writes to `pipeline_movimentos`;
* leaving the `aprovacao_cliente` stage backwards IS a refação — counted with
  the ATOMIC `igig.incrementar_refacoes()` (smoke finding 4: the old
  read-then-write lost increments);
* minting a client-approval link moves the tarefa INTO `aprovacao_cliente`, and
  the public portal may only decide while it is still there (smoke finding 4).

Card DTOs carry the cliente, pauta and responsável a card needs to be legible
on a phone (smoke finding 5: cards showed none of them).
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.domain.pipeline import get_stage, group_into_colunas, move_card
from noctusai_lib.integrations.persistence.table_reads import paged_rows

from app.pipelines import PAPEL_APROVACAO_CLIENTE, PIPELINE_ESTEIRA, etapas
from app.services import quadro_comum as qc
from app.services.regras import RegraViolada

logger = logging.getLogger(__name__)

__all__ = [
    "TAREFA_SELECT",
    "criar_tarefa",
    "decidir_aprovacao",
    "levar_para_aprovacao",
    "mover_tarefa",
    "quadro",
]

CFG = PIPELINE_ESTEIRA

TAREFA_SELECT = (
    "id, org_id, pauta_id, cliente_id, titulo, etapa_id, kanban_pos, responsavel_id, "
    "prazo, refacoes, observacao_cliente, created_at, updated_at"
)


def _indice(stages: list[dict], etapa_id: Any) -> int | None:
    for i, s in enumerate(stages):
        if str(s["id"]) == str(etapa_id):
            return i
    return None


# ── Read ─────────────────────────────────────────────────────────────
def quadro(
    db: Any, org_id: str, *, cliente_id: str | None = None, limite_por_etapa: int | None = None
) -> list[dict]:
    """Every active stage as a column, optionally filtered to one cliente (R9)."""
    stages = etapas(db, CFG, org_id)
    filtros = {"cliente_id": cliente_id} if cliente_id else None
    linhas = paged_rows(db, CFG.card_table, org_id, eq_filters=filtros, select=TAREFA_SELECT)
    pautas = qc.por_ids(
        db, "pauta", org_id, (r.get("pauta_id") for r in linhas),
        select="id, titulo, formato, data_publicacao",
    )
    clientes = qc.por_ids(db, "cliente", org_id, (r.get("cliente_id") for r in linhas),
                          select="id, nome")
    responsaveis = qc.por_ids(db, "profissional", org_id,
                              (r.get("responsavel_id") for r in linhas), select="id, nome")

    def dto(r: dict) -> dict:
        return {
            **r,
            "pauta": pautas.get(str(r.get("pauta_id"))),
            "cliente": clientes.get(str(r.get("cliente_id"))),
            "responsavel": responsaveis.get(str(r.get("responsavel_id"))),
        }

    return group_into_colunas(CFG, stages, linhas, row_to_dto=dto, limite_cards=limite_por_etapa)


# ── Create ───────────────────────────────────────────────────────────
def criar_tarefa(
    db: Any,
    org_id: str,
    *,
    pauta_id: str,
    titulo: str,
    responsavel_id: str | None = None,
    prazo: str | None = None,
    user_id: Any = None,
) -> dict:
    """A new tarefa at the esteira's first stage, on top of the column.

    `cliente_id` is derived from the pauta, never accepted from the caller —
    two sources for one fact is how they come to disagree.
    """
    pauta = qc.carregar(db, "pauta", org_id, pauta_id, select="id, cliente_id")
    if responsavel_id:
        qc.carregar(db, "profissional", org_id, responsavel_id, select="id", rotulo="profissional")
    stages = etapas(db, CFG, org_id)
    if not stages:
        raise RegraViolada(
            409, "esteira_sem_etapas",
            "A esteira não tem nenhuma etapa ativa. Configure as etapas primeiro.",
        )
    entrada = stages[0]
    criado = (
        db.table(CFG.card_table).insert(
            {
                "org_id": org_id,
                "pauta_id": pauta["id"],
                "cliente_id": pauta.get("cliente_id"),
                "titulo": titulo,
                "responsavel_id": responsavel_id,
                "prazo": prazo,
                "etapa_id": entrada["id"],
                "kanban_pos": str(qc.posicao_no_topo(db, CFG, org_id=org_id, etapa_id=entrada["id"])),
                "refacoes": 0,
            }
        ).execute().data or []
    )
    if not criado:
        raise RuntimeError("insert de tarefa não retornou a linha criada")
    tarefa = criado[0]
    qc.registrar_entrada(
        db, CFG, org_id=org_id, card_id=str(tarefa["id"]), etapa_id=entrada["id"],
        user_id=user_id, cliente_id=pauta.get("cliente_id"),
    )
    return tarefa


# ── Move ─────────────────────────────────────────────────────────────
def _incrementar_refacao(db: Any, org_id: str, tarefa_id: str) -> None:
    """Atomic `refacoes + 1` in the database — never read-modify-write here."""
    db.rpc("incrementar_refacoes", {"p_tarefa_id": tarefa_id, "p_org_id": org_id}).execute()


def mover_tarefa(
    db: Any,
    org_id: str,
    *,
    tarefa_id: str,
    para_etapa_id: str,
    user_id: Any,
    novo_indice: int | None = None,
    motivo: str | None = None,
) -> dict:
    """Drag a tarefa. See the module docstring for the rules."""
    tarefa = qc.carregar(db, CFG.card_table, org_id, tarefa_id, select=TAREFA_SELECT)
    destino = get_stage(db, CFG, para_etapa_id, org_id=org_id)
    stages = etapas(db, CFG, org_id)
    de, para = _indice(stages, tarefa.get("etapa_id")), _indice(stages, destino["id"])
    if para is None:
        raise RegraViolada(409, "etapa_invalida", "Esta etapa está desativada.")

    motivo = (motivo or "").strip() or None
    retrocesso = de is not None and para < de
    if de is not None and para - de > 1:
        raise RegraViolada(
            409, "etapa_invalida",
            "A tarefa só pode avançar uma etapa por vez.",
        )
    if retrocesso and not motivo:
        raise RegraViolada(
            422, "motivo_obrigatorio",
            "Informe o motivo para devolver a tarefa a uma etapa anterior.",
        )

    linha = move_card(
        db, CFG,
        card_id=tarefa_id,
        to_stage_id=destino["id"],
        user_id=user_id,
        nova_posicao=qc.posicao_para_indice(
            db, CFG, org_id=org_id, etapa_id=destino["id"], indice=novo_indice, card_id=tarefa_id
        ),
        motivo=motivo,
        org_id=org_id,
    )
    if retrocesso and stages[de].get("papel") == PAPEL_APROVACAO_CLIENTE:
        _incrementar_refacao(db, org_id, tarefa_id)
        logger.info("refação registrada (quadro) org=%s tarefa=%s", org_id, tarefa_id)
    return linha


def _etapa_de_aprovacao(stages: list[dict]) -> tuple[int, dict]:
    for i, s in enumerate(stages):
        if s.get("papel") == PAPEL_APROVACAO_CLIENTE:
            return i, s
    raise RegraViolada(
        409, "etapa_aprovacao_ausente",
        "Nenhuma etapa da esteira está marcada como 'Aprovação do cliente'.",
    )


def levar_para_aprovacao(db: Any, org_id: str, *, tarefa_id: str, user_id: Any) -> dict:
    """Move a tarefa INTO the approval stage — what minting a client link means.

    Refused (409 `etapa_invalida`) from a stage AFTER approval: re-opening an
    approved piece for the client is a backwards move, which needs a reason
    through the board, not a side effect of sending a link.
    """
    tarefa = qc.carregar(db, CFG.card_table, org_id, tarefa_id, select=TAREFA_SELECT)
    stages = etapas(db, CFG, org_id)
    i_aprov, aprovacao = _etapa_de_aprovacao(stages)
    atual = _indice(stages, tarefa.get("etapa_id"))
    if atual is not None and atual > i_aprov:
        raise RegraViolada(
            409, "etapa_invalida",
            "Esta tarefa já passou da aprovação do cliente.",
        )
    if str(tarefa.get("etapa_id")) == str(aprovacao["id"]):
        return tarefa
    return move_card(
        db, CFG,
        card_id=tarefa_id,
        to_stage_id=aprovacao["id"],
        user_id=user_id,
        motivo="Link de aprovação enviado ao cliente",
        org_id=org_id,
    )


def decidir_aprovacao(
    db: Any, org_id: str, *, tarefa_id: str, decisao: str, observacao: str = ""
) -> dict:
    """Apply the CLIENT's decision from the public portal.

    Only valid while the tarefa sits in the approval stage (409
    `fora_de_aprovacao` otherwise — the agency may have pulled it back).
    `aprovado` advances one stage; `ajuste` returns one stage, counts a
    refação atomically and stores the client's note. The history row has no
    responsável: the actor is the agency's client, who has no noc user.
    """
    tarefa = qc.carregar(db, CFG.card_table, org_id, tarefa_id, select=TAREFA_SELECT)
    stages = etapas(db, CFG, org_id)
    i_aprov, aprovacao = _etapa_de_aprovacao(stages)
    if str(tarefa.get("etapa_id")) != str(aprovacao["id"]):
        raise RegraViolada(
            409, "fora_de_aprovacao",
            "Este conteúdo não está mais aguardando a sua aprovação.",
        )

    if decisao == "aprovado":
        alvo = stages[i_aprov + 1] if i_aprov + 1 < len(stages) else None
        motivo = "Aprovado pelo cliente"
    else:
        alvo = stages[i_aprov - 1] if i_aprov > 0 else None
        motivo = (observacao or "").strip() or "Ajuste solicitado pelo cliente"

    linha = tarefa
    if alvo is not None:
        linha = move_card(
            db, CFG, card_id=tarefa_id, to_stage_id=alvo["id"], user_id=None,
            motivo=motivo, org_id=org_id,
        )
    if decisao == "ajuste":
        _incrementar_refacao(db, org_id, tarefa_id)
        db.table(CFG.card_table).update({"observacao_cliente": observacao}).eq(
            "id", tarefa_id
        ).eq("org_id", org_id).execute()
    return linha
