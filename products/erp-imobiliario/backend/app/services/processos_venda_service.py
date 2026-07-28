"""
Processos de Venda Service — the post-proposal execution pipeline.

Where the Funil answers "will this close?", this board answers "how far along
is the closing?". A processo is created by accepting a proposal on a
negociação (see `app/routers/negociacoes_venda.py::aceitar_proposta`), never
by hand — there is deliberately no bare create endpoint, because a processo
without the deal it came from has no provenance.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The 8 execution stages, in order. Mirrors `erp.etapa_processo` — a FIXED
# vocabulary from the user's own steps, not a configurable workflow (explicit
# roadmap anti-goal: don't build the abstraction on spec).
ETAPAS_PROCESSO: Tuple[str, ...] = (
    "elaboracao_contrato",
    "analise_partes",
    "revisao_contrato",
    "assinatura",
    "financiamento_escritura",
    "finalizacao",
    "entrega_chaves",
    "nota_fiscal",
)

# Where an accepted proposal lands.
ETAPA_PROCESSO_INICIAL = ETAPAS_PROCESSO[0]
# Terminal stage — nothing follows issuing the invoice. Consumers archive from
# here rather than inventing a ninth stage.
ETAPA_PROCESSO_FINAL = ETAPAS_PROCESSO[-1]

PROCESSO_SELECT = (
    "*,"
    "cliente:clientes!processos_venda_cliente_id_fkey(id, nome, email, telefone),"
    "corretor:profiles!processos_venda_corretor_id_fkey(id, nome, email),"
    "negociacao:negociacoes_venda!processos_venda_negociacao_venda_id_fkey"
    "(id, titulo, valor_estimado, closed_at)"
)

# Whitelist mirrors `frontend/src/types/processos.ts → interface ProcessoVenda`.
_PROCESSO_DTO_FIELDS: Tuple[str, ...] = (
    "id",
    "cliente_id",
    "negociacao_venda_id",
    "corretor_id",
    "etapa",
    "valor",
    "observacoes",
    "kanban_pos",
    "arquivado",
    "created_at",
    "updated_at",
    "cliente",
    "corretor",
    "negociacao",
)


def processo_row_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a raw DB row to the operational ProcessoVenda DTO contract."""
    if not row:
        return row
    return {k: row.get(k) for k in _PROCESSO_DTO_FIELDS if k in row}


def processo_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of raw DB rows to ProcessoVenda DTO shape."""
    if not rows:
        return []
    return [processo_row_to_dto(r) for r in rows]


def search_processos(rows: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Filter processos by free text across the cliente and the deal title."""
    q = query.lower()

    def matches(row: Dict[str, Any]) -> bool:
        cliente = row.get("cliente") or {}
        negociacao = row.get("negociacao") or {}
        haystack = [
            cliente.get("nome"),
            cliente.get("email"),
            cliente.get("telefone"),
            negociacao.get("titulo"),
            row.get("observacoes"),
        ]
        return any(q in str(v or "").lower() for v in haystack)

    return [r for r in rows if matches(r)]


def group_into_colunas(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group processos into one kanban column per execution stage.

    Every stage is emitted even when empty — same contract as the Funil board.
    """
    colunas = []
    for etapa in ETAPAS_PROCESSO:
        cards = [r for r in rows if r.get("etapa") == etapa]
        cards.sort(key=lambda r: r.get("kanban_pos", 0))
        colunas.append({
            "etapa": etapa,
            "total": len(cards),
            "valorTotal": sum(float(c.get("valor", 0) or 0) for c in cards),
            "cards": processo_rows_to_dto(cards),
        })
    return colunas
