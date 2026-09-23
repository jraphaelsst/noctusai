"""Board mechanics BOTH igig pipelines share, on top of the seed pipeline.

The seed (`noctusai_lib.domain.pipeline`) owns stages, grouping, the move and
its history. What remains per board is small but identical for Comercial and
Esteira — so it lives once, here, parameterized by the `PipelineConfig`:

* where a dropped card lands (`posicao_para_indice` — fractional, ONE write),
* where a NEW card lands (`posicao_no_topo` — newest first, without a date sort
  that would take hand-arranged order away from the operator),
* the "entered the board" history row (`de_etapa_id` NULL),
* org-scoped id lookups that page past PostgREST's silent 1 000-row cap.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from noctusai_lib.domain.pipeline import PipelineConfig, position_for_index, position_of, position_on_top
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows, paged_rows
from noctusai_lib.primitives.exceptions import NotFoundError

__all__ = [
    "carregar",
    "coluna",
    "por_ids",
    "posicao_no_topo",
    "posicao_para_indice",
    "registrar_entrada",
]


def carregar(db: Any, tabela: str, org_id: str, registro_id: str, *, select: str = "*",
             rotulo: str | None = None) -> dict:
    """One org-scoped row, or the seed `NotFoundError` (→ 404)."""
    linhas = (
        db.table(tabela).select(select).eq("id", registro_id).eq("org_id", org_id).execute().data
        or []
    )
    if not linhas:
        raise NotFoundError((rotulo or tabela).capitalize(), registro_id)
    return linhas[0]


def por_ids(db: Any, tabela: str, org_id: str, ids: Iterable[Any], *, select: str) -> dict[str, dict]:
    """`id → row` for the given ids, batched (URL length) and paged (row cap)."""
    limpos = sorted({str(i) for i in ids if i})
    if not limpos:
        return {}
    return {
        str(r["id"]): r for r in in_batched_rows(db, tabela, org_id, "id", limpos, select=select)
    }


def coluna(db: Any, cfg: PipelineConfig, *, org_id: str, etapa_id: str) -> list[dict]:
    """Every card in one stage, in board order (position, then age)."""
    linhas = paged_rows(
        db, cfg.card_table, org_id, eq_filters={"etapa_id": etapa_id},
        select="id, kanban_pos, created_at",
    )
    linhas.sort(key=lambda r: (position_of(r), r.get("created_at") or ""))
    return linhas


# NOC-REMEDIATE[pipeline-column-position]: second copy of social-wiring's
# modules/pipeline/routers/boards.py::_posicao_para_indice (N=2 -> triage); the
# third consumer lifts it into noctusai_lib.domain.pipeline, cfg-parameterized. — 2026-09-23
def posicao_para_indice(
    db: Any, cfg: PipelineConfig, *, org_id: str, etapa_id: str, indice: int | None, card_id: str
) -> Decimal | None:
    """Fractional `kanban_pos` landing `card_id` at `indice` of its column.

    `None` when the client sent no index — a plain "move to this stage" must
    not disturb the position. The moved card is EXCLUDED from its neighbours:
    "drop at index 3" means three cards above it once it is gone.
    """
    if indice is None:
        return None
    vizinhos = [c for c in coluna(db, cfg, org_id=org_id, etapa_id=etapa_id) if c.get("id") != card_id]
    return position_for_index(vizinhos, indice)


def posicao_no_topo(db: Any, cfg: PipelineConfig, *, org_id: str, etapa_id: str) -> Decimal:
    return position_on_top(coluna(db, cfg, org_id=org_id, etapa_id=etapa_id))


def registrar_entrada(
    db: Any, cfg: PipelineConfig, *, org_id: str, card_id: str, etapa_id: str,
    user_id: Any, cliente_id: Any = None,
) -> None:
    """History row for a card ENTERING the board (`de_etapa_id` NULL).

    The seed's `move_card` records every transition; without this row the
    history of a card would start at its first move and "how long did it sit in
    the entry stage" would be unanswerable.
    """
    db.table(cfg.history_table).insert(
        {
            "org_id": org_id,
            "pipeline": cfg.pipeline,
            "entidade_id": card_id,
            "de_etapa_id": None,
            "para_etapa_id": etapa_id,
            "responsavel_id": str(user_id) if user_id else None,
            "cliente_id": cliente_id,
            "motivo": None,
        }
    ).execute()
