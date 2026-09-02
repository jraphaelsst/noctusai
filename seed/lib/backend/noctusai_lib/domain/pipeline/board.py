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

import logging
from typing import Any, Callable, Collection

from .config import PipelineConfig

logger = logging.getLogger(__name__)


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
    value_of: Callable[[dict], float] | None = None,
    limite_cards: int | None = None,
    recency_first_stages: Collection[str] | None = None,
) -> list[dict[str, Any]]:
    """One column per configured stage, cards bucketed by `etapa_id`.

    Cards whose `etapa_id` matches no configured stage are NOT silently
    dropped — see `orphan_cards`. Dropping them is how a board quietly loses a
    deal after a stage is deleted out from under it.

    `value_of` overrides where a card's money comes from. The default reads
    `cfg.value_field`, which is a single column name — fine while the value
    lives on the card's own row, useless once it lives somewhere else. The
    funil's does: `atendimentos.valor_estimado` is a field nobody fills, while
    `atendimento_negociacao.valor_negociado` is the number the person closing
    the deal actually types. A callable lets the caller answer "what is this
    card worth" without this function learning about either table.

    `limite_cards` truncates the CARDS in each column while leaving `total`
    and `valorTotal` computed over ALL of them. 🔴 That split is the whole
    point: a board showing 50 of 1.070 must still say 1.070 and still total
    the money for 1.070. Truncating the counts too would turn a display limit
    into a silent under-report of the pipeline.

    `recency_first_stages` names the stages that sort NEWEST-FIRST by
    `created_at` instead of by `kanban_pos` — the intake column, where what
    matters is "what just arrived", not an order somebody arranged by hand.
    Opt-in and empty by default: every other column, and every board that does
    not pass it, keeps the hand-arranged `kanban_pos` order untouched.

    🔴 It interacts with `limite_cards`, and that is the reason this belongs
    HERE and not in the frontend. The truncation happens after this sort, so a
    recency stage's "first 50" are the 50 NEWEST cards. Sorting client-side
    would reorder only whichever 50 the server already chose by `kanban_pos` —
    a column that claims to show the newest while showing an arbitrary window.

    A recency stage is not hand-orderable, by construction — `kanban_pos` is
    ignored there. That costs nothing today: `PipelineBoard.onMove` already
    early-returns on a same-column drop (`fromStage === toStage`), so a
    within-column reorder persists nothing on ANY column and resets on the
    next fetch. `kanban_pos` only ever changes on a CROSS-stage move, which
    this seam does not touch. Should a caller ever make within-column
    reordering persistent, it must exclude these stages or the drag will lie.
    """
    by_stage: dict[str, list[dict]] = {s["id"]: [] for s in stages}
    for row in rows:
        bucket = by_stage.get(row.get("etapa_id"))
        if bucket is not None:
            bucket.append(row)

    # `orphan_cards` documented itself as making this condition "observable
    # rather than presenting as 'a deal disappeared from the board'" — but it
    # was exported, unit-tested, and called by NOTHING in production, so the
    # condition was in fact silent. A net nobody wired is not a net.
    #
    # A WARNING, not an exception: the cards that DID resolve must still
    # render. Failing the whole board because one card is misplaced turns a
    # partial display problem into a total outage.
    stranded = orphan_cards(stages, rows)
    if stranded:
        logger.warning(
            "pipeline.%s: %d %s card(s) point at a stage this board does not "
            "offer (deleted or deactivated) and are not rendered: %s",
            cfg.pipeline,
            len(stranded),
            cfg.entity_label,
            [r.get("id") for r in stranded[:20]],
        )

    def _valor(card: dict) -> float:
        if value_of is not None:
            return value_of(card)
        return float(card.get(cfg.value_field) or 0)

    recency = set(recency_first_stages or ())

    colunas = []
    for stage in stages:
        cards = by_stage[stage["id"]]
        if stage["id"] in recency:
            # Newest first. `created_at` is an ISO-8601 UTC string, so a plain
            # reverse string sort IS chronological — no parsing needed. A row
            # with no `created_at` sorts last rather than crashing the board.
            cards.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        else:
            cards.sort(key=lambda r: (r.get("kanban_pos", 0), r.get("created_at") or ""))
        # Counts and money over the WHOLE column; only the card list is cut.
        total = len(cards)
        valor_total = sum(_valor(c) for c in cards)
        visiveis = cards if limite_cards is None else cards[:limite_cards]
        colunas.append(
            {
                # `etapa` carries the stage ID now. The frontend keys columns and
                # drop targets off it, and an ID is what survives a rename.
                "etapa": stage["id"],
                "stage": stage_to_dto(stage),
                "total": total,
                "valorTotal": valor_total,
                # How many of `total` this response actually carries. The board
                # needs it to decide whether to offer "load more" — inferring
                # it from `len(cards) < total` would break the moment a column
                # is exactly `limite_cards` long.
                "exibidos": len(visiveis),
                "cards": [row_to_dto(c) for c in visiveis] if row_to_dto else visiveis,
            }
        )
    return colunas


def orphan_cards(
    stages: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Cards pointing at a stage this pipeline no longer offers.

    Should always be empty: `delete_stage` reassigns cards before deleting,
    `_guard_deactivation` refuses to retire a stage that still holds any, and
    the backfill in migration 042 refuses to complete while a card is unplaced.

    Called by `group_into_colunas` on every board render so the condition is
    observable rather than presenting as "a deal disappeared from the board".
    It previously was NOT — it was exported and unit-tested but wired to
    nothing, which made this docstring's promise false in production.
    """
    known = {s["id"] for s in stages}
    return [r for r in rows if r.get("etapa_id") not in known]
