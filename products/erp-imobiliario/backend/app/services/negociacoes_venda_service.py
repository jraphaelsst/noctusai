"""
Negociações de Venda Service — the Funil's card entity.

A *negociação de venda* is one deal in flight for one cliente. It exists
because a cliente can hold several concurrent deals at different stages,
which `erp.clientes.etapa_atual` (exactly one stage per cliente) cannot
represent. See `project-history/roadmaps/erp-processos-venda-2026-07.md`
Phase 1.5.

NOT to be confused with `erp.negociacoes` — that is the PERMUTA
(property-swap) table with its own router at `/api/negociacoes`. This is a
sibling entity, deliberately named for the same domain word; the roadmap
flags the readability hazard.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The Funil's stage vocabulary. Reused verbatim from `erp.etapa_funil` —
# negociações and clientes share one stage enum until the two boards'
# vocabularies genuinely diverge (roadmap Q5).
ETAPAS_FUNIL: Tuple[str, ...] = (
    "qualificacao",
    "visitas",
    "proposta",
    "negociacao",
    "fechado",
)

# Terminal-state vocabulary (`erp.status_negociacao_venda`).
STATUS_ABERTA = "aberta"
STATUS_ACEITA = "aceita"
STATUS_PERDIDA = "perdida"
STATUS_NEGOCIACAO = (STATUS_ABERTA, STATUS_ACEITA, STATUS_PERDIDA)

# NOTE: there is deliberately NO `AGENCY_PROFILE_ID` constant here.
#
# The "Agência" default corretor is PER-ORGANIZATION (migration 040), resolved
# by `erp.agency_profile_id()` from the caller's `erp.current_org_id()`. A
# module-level UUID would be a cross-tenant bug waiting to happen: it could only
# ever name ONE org's agency, and would silently attach another tenant's deals
# to it.
#
# To leave a deal unassigned, omit `corretor_id` on INSERT and let the column
# DEFAULT resolve it in the caller's own org context.

# The nested-join projection used by every read path. Kept in ONE place so a
# join rename can't drift between the list, board and detail queries.
NEGOCIACAO_SELECT = (
    "*,"
    "cliente:clientes!negociacoes_venda_cliente_id_fkey(id, nome, email, telefone, origem),"
    "corretor:profiles!negociacoes_venda_corretor_id_fkey(id, nome, email),"
    # The card's own stage, joined in. The card UI needs the stage's `papel` to
    # decide whether "Aceitar Proposta" applies, and joining beats having every
    # card component subscribe to a separate stages query.
    "etapa_rel:pipeline_stages!negociacoes_venda_etapa_id_fkey"
    "(id, slug, label, cor, papel, posicao)"
)

# Whitelist mirrors `frontend/src/types/negociacoes.ts → interface Negociacao`.
# Strips any column not listed (defense against silent schema drift + PII
# over-share), matching the `cliente_row_to_dto` precedent.
_NEGOCIACAO_DTO_FIELDS: Tuple[str, ...] = (
    "id",
    "cliente_id",
    "corretor_id",
    "titulo",
    "etapa",     # legacy enum column — retained for rollback, not authoritative
    "etapa_id",  # the stage row this card points at
    "status",
    "valor_estimado",
    "probabilidade",
    "kanban_pos",
    "arquivado",
    "closed_at",
    "created_at",
    "updated_at",
    "cliente",   # nested join object — projected by NEGOCIACAO_SELECT
    "corretor",  # nested join object — projected by NEGOCIACAO_SELECT
    "etapa_rel", # nested stage object — carries `papel` for role-keyed UI
)


def negociacao_row_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a raw DB row to the operational Negociação DTO contract."""
    if not row:
        return row
    return {k: row.get(k) for k in _NEGOCIACAO_DTO_FIELDS if k in row}


def negociacao_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of raw DB rows to Negociação DTO shape."""
    if not rows:
        return []
    return [negociacao_row_to_dto(r) for r in rows]


def search_negociacoes(rows: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Filter negociações by free text across the deal and its cliente.

    Searches the deal's own `titulo` plus the joined cliente's identifying
    fields — a user searching the Funil is looking for a PERSON at least as
    often as for a deal name.
    """
    q = query.lower()

    def matches(row: Dict[str, Any]) -> bool:
        cliente = row.get("cliente") or {}
        haystack = [
            row.get("titulo"),
            cliente.get("nome"),
            cliente.get("email"),
            cliente.get("telefone"),
        ]
        return any(q in str(v or "").lower() for v in haystack)

    return [r for r in rows if matches(r)]


def group_into_colunas(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group negociações into kanban columns, one per `etapa_funil` value.

    Every stage is emitted even when empty — a kanban with disappearing
    columns is unusable, and the frontend must not have to reconstruct the
    stage list to fill the gaps.
    """
    colunas = []
    for etapa in ETAPAS_FUNIL:
        cards = [r for r in rows if r.get("etapa") == etapa]
        cards.sort(key=lambda r: r.get("kanban_pos", 0))
        colunas.append({
            "etapa": etapa,
            "total": len(cards),
            "valorTotal": sum(float(c.get("valor_estimado", 0) or 0) for c in cards),
            "cards": negociacao_rows_to_dto(cards),
        })
    return colunas
