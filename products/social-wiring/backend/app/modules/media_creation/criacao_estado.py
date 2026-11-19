"""The criação sub-state machine -- DATA (criacao-pipeline-contract 1).

``cs_posts.criacao_estado`` is a projection written by migration 368's RPC in the same transaction as its event row.
The transition MATRIX lives here and only here (the database enforces the enum, the optimistic ``p_de`` check and the
atomicity -- not a second copy of the matrix).
"""
from __future__ import annotations

from typing import Optional

AGUARDANDO_APROVACAO = "aguardando_aprovacao"
REFINANDO = "refinando"
APROVADO = "aprovado"
NA_FILA = "na_fila"
GERANDO = "gerando"
AGUARDANDO_EDICAO = "aguardando_edicao"
AGUARDANDO_APROVACAO_MIDIA = "aguardando_aprovacao_midia"
MIDIA_APROVADA = "midia_aprovada"
MIDIA_REPROVADA = "midia_reprovada"
FALHOU = "falhou"
CANCELADO = "cancelado"

ESTADOS = (
    AGUARDANDO_APROVACAO, REFINANDO, APROVADO, NA_FILA, GERANDO, AGUARDANDO_EDICAO,
    AGUARDANDO_APROVACAO_MIDIA, MIDIA_APROVADA, MIDIA_REPROVADA, FALHOU, CANCELADO,
)

#: ``de`` (``None`` = a post that never had a sub-state) -> the states it may move to.
TRANSICOES: dict[Optional[str], frozenset[str]] = {
    None: frozenset({AGUARDANDO_APROVACAO, APROVADO}),
    AGUARDANDO_APROVACAO: frozenset({REFINANDO, APROVADO, CANCELADO}),
    REFINANDO: frozenset({AGUARDANDO_APROVACAO, APROVADO, CANCELADO}),
    APROVADO: frozenset({REFINANDO, NA_FILA, CANCELADO}),
    NA_FILA: frozenset({GERANDO, FALHOU, CANCELADO}),
    GERANDO: frozenset({AGUARDANDO_EDICAO, AGUARDANDO_APROVACAO_MIDIA, FALHOU, CANCELADO}),
    AGUARDANDO_EDICAO: frozenset({AGUARDANDO_APROVACAO_MIDIA, FALHOU, CANCELADO}),
    AGUARDANDO_APROVACAO_MIDIA: frozenset({MIDIA_APROVADA, MIDIA_REPROVADA, CANCELADO}),
    MIDIA_APROVADA: frozenset({CANCELADO}),
    MIDIA_REPROVADA: frozenset({NA_FILA, CANCELADO}),
    FALHOU: frozenset({NA_FILA, CANCELADO}),
    CANCELADO: frozenset({AGUARDANDO_APROVACAO, APROVADO}),
}

#: The event each state's entry records in ``cs_post_eventos`` (the intent-named vocabulary, migration 364).
EVENTO_POR_ESTADO: dict[str, str] = {
    NA_FILA: "criacao_enfileirada",
    AGUARDANDO_EDICAO: "criacao_concluida",
    AGUARDANDO_APROVACAO_MIDIA: "criacao_concluida",
    MIDIA_APROVADA: "midia_aprovada",
    MIDIA_REPROVADA: "midia_reprovada",
}

#: States whose record is written by ANOTHER writer in its own transaction -- a second event here would double-count:
#: ``gerando`` / ``falhou`` follow the step's event (``cs_criacao_passo_registrar``, 363), ``aprovado`` follows the
#: approvals organ's ``apr_events`` row, ``cancelado`` follows the ``pipeline_movimentos`` row of the move.
ESTADOS_COM_EVENTO_PROPRIO = frozenset({GERANDO, FALHOU, APROVADO, CANCELADO})


def transicao_valida(de: Optional[str], para: str) -> bool:
    return para in TRANSICOES.get(de, frozenset())


def evento_da_entrada(para: str, tipo: Optional[str] = None) -> Optional[str]:
    """The ``tipo`` to record on entering ``para``: the caller's explicit one wins (the roteiro loop passes
    ``contraparte_gerada`` / ``refinamento_pedido`` for the two approval states), else the state's own; ``None`` only for
    :data:`ESTADOS_COM_EVENTO_PROPRIO`. A state with no resolvable event is a programming error, never a silent skip."""
    if tipo:
        return tipo
    if para in EVENTO_POR_ESTADO:
        return EVENTO_POR_ESTADO[para]
    if para in ESTADOS_COM_EVENTO_PROPRIO:
        return None
    raise ValueError(f"o estado {para!r} exige o tipo do evento (contraparte_gerada / refinamento_pedido / ...)")


__all__ = [
    "ESTADOS", "ESTADOS_COM_EVENTO_PROPRIO", "EVENTO_POR_ESTADO", "TRANSICOES", "evento_da_entrada", "transicao_valida",
]
