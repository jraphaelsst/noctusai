"""Timeline gatherer for the Esteira post card (esteira-contract.md 4 / 2.4).

Lives beside ``esteira_config`` (not in ``services/esteira_service.py``) because the config
binds it at import and the service imports the config: a gatherer in the service would be a
circular import. This closes the esteira-timeline-movimento remediation.

``movimento`` entries are the ``pipeline_movimentos`` rows the seed ``move_card`` writes with
``pipeline='esteira'`` and ``entidade_id=<post id>``. ``ocorrido_em`` is the row's own
``created_at``: a movement IS the moment it happened.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.persistence.table_reads import actor, in_batched_rows, paged_rows

PIPELINE = "esteira"


def gather_movimentos_esteira(cfg: Any, db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
    moves = paged_rows(
        db,
        "pipeline_movimentos",
        org_id,
        eq_filters={"pipeline": PIPELINE, "entidade_id": str(entity_id)},
    )
    if not moves:
        return []
    stage_ids = {m["para_etapa_id"] for m in moves if m.get("para_etapa_id")} | {
        m["de_etapa_id"] for m in moves if m.get("de_etapa_id")
    }
    stages = in_batched_rows(db, "pipeline_stages", org_id, "id", list(stage_ids)) if stage_ids else []
    # `pipeline_stages` names its human column `label` (no `nome`); slug, then id, are the fallbacks.
    names = {s["id"]: (s.get("label") or s.get("slug") or s["id"]) for s in stages}
    resolved = cfg.actor_resolver({m["responsavel_id"] for m in moves if m.get("responsavel_id")})
    return [
        {
            "id": m["id"],
            "kind": "movimento",
            "ocorrido_em": m["created_at"],
            "ator": actor(resolved, m.get("responsavel_id")),
            "payload": {
                "id": m["id"],
                "de_etapa": names.get(m.get("de_etapa_id")),
                "para_etapa": names.get(m.get("para_etapa_id")),
                "motivo": m.get("motivo"),
                "autor": actor(resolved, m.get("responsavel_id")),
            },
        }
        for m in moves
    ]
