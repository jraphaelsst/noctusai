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

from noctusai_lib.domain.pipeline import (
    get_stage,
    group_into_colunas,
    move_card,
    stage_by_role,
    update_stage,
)
from noctusai_lib.integrations.persistence.table_reads import paged_rows

from app.pipelines import PAPEL_AGENDADO, PAPEL_APROVACAO_CLIENTE, PIPELINE_ESTEIRA, etapas
from app.services import quadro_comum as qc
from app.services.regras import RegraViolada, mensagem_horas_perdidas

logger = logging.getLogger(__name__)

__all__ = [
    "TAREFA_SELECT",
    "buscar_tarefa",
    "criar_tarefa",
    "decidir_aprovacao",
    "excluir_tarefa",
    "levar_para_aprovacao",
    "mover_tarefa",
    "quadro",
    "reatribuir_papel",
]

CFG = PIPELINE_ESTEIRA

#: pt-BR label per system role — the wording `reatribuir_papel`'s refusal
#: message names, so it reads like the "Papéis das etapas" panel rather than
#: the raw machine code.
_ROTULO_PAPEL = {
    PAPEL_APROVACAO_CLIENTE: "Aprovação do cliente",
    PAPEL_AGENDADO: "Agendado",
}

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
        # `marca_id` rides along so the tarefa detail sheet's Repertório da
        # marca sidebar can default to the pauta's OWN brand instead of an
        # arbitrary one when the cliente carries several (achado 2).
        select="id, titulo, formato, data_publicacao, marca_id",
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


def buscar_tarefa(db: Any, org_id: str, tarefa_id: str) -> dict:
    """One tarefa, in the SAME rich shape `quadro()` puts on a card (pauta,
    cliente, responsável joined) — so a deep link (a decision or automation
    notification's `?tarefa=<id>`) can open the sheet regardless of which
    `?cliente=` filter is active on the board, instead of reading as "não
    encontrada" for a tarefa that exists but belongs to a filtered-out
    cliente. `qc.carregar` 404s (seed `NotFoundError`) for an unknown or
    another org's tarefa — same as `board.py`'s own per-row lookups."""
    row = qc.carregar(db, CFG.card_table, org_id, tarefa_id, select=TAREFA_SELECT, rotulo="tarefa")
    pautas = qc.por_ids(
        db, "pauta", org_id, [row.get("pauta_id")],
        select="id, titulo, formato, data_publicacao, marca_id",
    )
    clientes = qc.por_ids(db, "cliente", org_id, [row.get("cliente_id")], select="id, nome")
    responsaveis = qc.por_ids(
        db, "profissional", org_id, [row.get("responsavel_id")], select="id, nome"
    )
    return {
        **row,
        "pauta": pautas.get(str(row.get("pauta_id"))),
        "cliente": clientes.get(str(row.get("cliente_id"))),
        "responsavel": responsaveis.get(str(row.get("responsavel_id"))),
    }


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


# ── Delete ───────────────────────────────────────────────────────────
def _apontamentos_da_tarefa(db: Any, org_id: str, tarefa_id: str) -> list[dict]:
    return (
        db.table("apontamento").select("minutos").eq("tarefa_id", tarefa_id)
        .eq("org_id", org_id).execute().data or []
    )


def excluir_tarefa(
    db: Any, org_id: str, *, tarefa_id: str, user_id: Any = None,
    confirmar_perda_horas: bool = False,
) -> None:
    """Remove a tarefa from the board (smoke finding 5: there was no delete).

    Org-scoped lookup first so another org's id is a 404, never a silent no-op.
    Apontamentos and approval links go with it (`ON DELETE CASCADE`, migrations
    006/007); the `pipeline_movimentos` history is kept on purpose — it is the
    audit trail of what happened to the card, and a delete is part of it.

    Refuses (409 `horas_serao_perdidas`) when the tarefa carries logged hours
    and the caller has not explicitly confirmed the loss — deleting used to
    silently erase every apontamento (and the custo real / DRE input they
    feed) with no warning at all.
    """
    qc.carregar(db, CFG.card_table, org_id, tarefa_id, select="id")
    apontamentos = _apontamentos_da_tarefa(db, org_id, tarefa_id)
    if apontamentos and not confirmar_perda_horas:
        minutos = sum(int(a.get("minutos") or 0) for a in apontamentos)
        raise RegraViolada(
            409, "horas_serao_perdidas",
            mensagem_horas_perdidas(minutos, len(apontamentos)),
        )
    db.table(CFG.card_table).delete().eq("id", tarefa_id).eq("org_id", org_id).execute()
    logger.info("tarefa excluída org=%s tarefa=%s por=%s", org_id, tarefa_id, user_id)


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
    else:
        # A later approval must not leave a STALE "Cliente pediu: …" note on
        # screen (achado 9) — an earlier round's ajuste observation has
        # nothing to do with what the client just approved.
        db.table(CFG.card_table).update({"observacao_cliente": None}).eq(
            "id", tarefa_id
        ).eq("org_id", org_id).execute()
    return linha


# ── Stage roles ──────────────────────────────────────────────────────
def reatribuir_papel(db: Any, org_id: str, *, etapa_id: str, papel: str | None) -> dict:
    """Atomically move a system role (`aprovacao_cliente`/`agendado`) onto —
    or off of — one stage.

    The seed's generic stage PATCH (`noctusai_lib.domain.pipeline.
    update_stage`) refuses to set a role that another stage already holds
    (by design — at most one stage per role), so "reassign" is really two
    writes: clear the old holder, then set the new one. Doing that from the
    frontend as two separate PATCH calls leaves a window with NO stage
    carrying the role, and offers no way to refuse "clear the only
    `aprovacao_cliente` holder and assign nothing else" (achado 11 — the
    seed's own `DeleteStageDialog` copy told users to "atribua o papel a
    outra etapa primeiro" with no UI action that did it).

    Refuses (409 `papel_obrigatorio`) a bare CLEAR (`papel=None` or any OTHER
    role) of a stage that currently holds a DIFFERENT system role — every
    role here is unique-per-stage by construction, so taking `etapa_id`'s own
    role away always leaves that role with ZERO holders fleet-wide, the exact
    same "stranded feature" `update_stage`'s deactivation guard already
    refuses for a `DELETE`/`ativo=false`. Before this, only `aprovacao_cliente`
    carried this guard (achado 11): assigning `aprovacao_cliente` to the
    stage that already held `agendado` silently dropped `agendado` — a system
    role a card-hub reminder or a future feature could come to rely on, gone
    with no warning and no code path pointing at it (2026-09 audit follow-up).
    Reassigning to a DIFFERENT stage stays a single call: pass the new
    holder's `etapa_id` with the target `papel`; this function clears the
    previous holder of THAT role itself — the caller only ever moves ONE
    role at a time.
    """
    atual = get_stage(db, CFG, etapa_id, org_id=org_id)
    papel_atual = atual.get("papel")
    if papel_atual == papel:
        return atual
    if papel_atual and papel_atual != papel:
        rotulo = _ROTULO_PAPEL.get(papel_atual, papel_atual)
        raise RegraViolada(
            409, "papel_obrigatorio",
            f"Esta é a única etapa marcada como '{rotulo}'. "
            "Atribua esse papel a outra etapa antes de trocá-lo ou removê-lo desta.",
        )
    if papel:
        titular = stage_by_role(db, CFG, papel, org_id=org_id)
        if titular is not None and str(titular["id"]) != str(etapa_id):
            update_stage(db, CFG, str(titular["id"]), {"papel": None}, org_id=org_id)
    return update_stage(db, CFG, etapa_id, {"papel": papel}, org_id=org_id)
