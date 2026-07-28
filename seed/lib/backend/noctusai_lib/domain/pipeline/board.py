"""
Grouping cards into kanban columns, driven by the stage rows.

The board shape is unchanged from what the two ERP boards already returned
(`etapa`, `total`, `valorTotal`, `cards`), so the frontend contract survives the
move to DB-driven stages. What changes is where the column list comes FROM:
previously a hardcoded tuple in each product's service, now the stage rows.

Every configured stage is emitted even when empty — a column that vanishes when
its last card leaves is a board that reshapes itself under the user.
"""
from __future__ import annotations

from typing import Any, Callable

from .config import PipelineConfig


def stage_to_dto(stage: dict[str, Any]) -> dict[str, Any]:
    """Project a stage row to the shape the frontend renders columns from."""
    return {
        "id": stage.get("id"),
        "slug": stage.get("slug"),
        "label": stage.get("label"),
        "cor": stage.get("cor"),
        "posicao": stage.get("posicao"),
        "papel": stage.get("papel"),
        "ativo": stage.get("ativo", True),
    }


def group_into_colunas(
    cfg: PipelineConfig,
    stages: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    row_to_dto: Callable[[dict], dict] | None = None,
) -> list[dict[str, Any]]:
    """One column per configured stage, cards bucketed by `etapa_id`.

    Cards whose `etapa_id` matches no configured stage are NOT silently
    dropped — see `orphan_cards`. Dropping them is how a board quietly loses a
    deal after a stage is deleted out from under it.
    """
    by_stage: dict[str, list[dict]] = {s["id"]: [] for s in stages}
    for row in rows:
        bucket = by_stage.get(row.get("etapa_id"))
        if bucket is not None:
            bucket.append(row)

    colunas = []
    for stage in stages:
        cards = by_stage[stage["id"]]
        cards.sort(key=lambda r: (r.get("kanban_pos", 0), r.get("created_at") or ""))
        colunas.append(
            {
                # `etapa` carries the stage ID now. The frontend keys columns and
                # drop targets off it, and an ID is what survives a rename.
                "etapa": stage["id"],
                "stage": stage_to_dto(stage),
                "total": len(cards),
                "valorTotal": sum(float(c.get(cfg.value_field) or 0) for c in cards),
                "cards": [row_to_dto(c) for c in cards] if row_to_dto else cards,
            }
        )
    return colunas


def orphan_cards(
    stages: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cards pointing at a stage this pipeline no longer offers.

    Should always be empty: `delete_stage` reassigns cards before deleting, and
    the backfill in migration 042 refuses to complete while any card is
    unplaced. It is computed anyway so the condition is observable rather than
    presenting as "a deal disappeared from the board".
    """
    known = {s["id"] for s in stages}
    return [r for r in rows if r.get("etapa_id") not in known]
