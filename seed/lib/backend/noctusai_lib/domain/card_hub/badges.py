"""The card summary (`GET /{id}/card`) and its badge row.

Lifted from social-wiring's `timeline_service.compute_badges` /
`get_card_resumo`. The seed owns the badges its own tables can answer
(comments, documents, checklist progress, has-description); a product's own
badges (social-wiring: `touches`, `temperatura`) and resumo keys
(`atendimentos`) arrive through `CardHubConfig.badge_extensions` /
`resumo_extensions` — each receives the seed-built dict and returns the one
to serve, so the product owns both the extra keys AND their position.

🔴 Counts are SERVED, computed in SQL (`count="exact"` head queries) — never
fetch-then-`len()`. A board renders ~1 200 cards; badges must not drag every
row of every child table across the wire.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from noctusai_lib.integrations.persistence.table_reads import (
    in_batched_rows,
    paged_rows,
    table,
)

from .config import CardHubConfig
from .services import ensure_entity, get_descricao, get_entity_tags, get_membros


def count_rows(cfg: CardHubConfig, db: Any, table_name: str, org_id: UUID, entity_id: UUID, **extra_eq: Any) -> int:
    """A head-only count of `table_name` rows on this card."""
    query = (
        table(db, table_name)
        .select("id", count="exact")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
    )
    for key, value in extra_eq.items():
        query = query.eq(key, value)
    result = query.execute()
    return getattr(result, "count", None) or 0


def compute_badges(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, entity: dict) -> dict:
    # `notas` counts COMMENTS only — the description has its own
    # `tem_descricao` boolean (Trello's own comments/description split).
    notas_count = count_rows(cfg, db, cfg.tables.notas, org_id, entity_id, tipo="comentario")
    descricao = get_descricao(cfg, db, org_id, entity_id)
    documentos_count = count_rows(cfg, db, cfg.tables.documentos, org_id, entity_id)

    checklists = paged_rows(db, cfg.tables.checklists, org_id, eq_filters={cfg.entity_fk: str(entity_id)})
    checklist_ids = [c["id"] for c in checklists]
    if checklist_ids:
        itens = in_batched_rows(db, cfg.tables.checklist_itens, org_id, "checklist_id", checklist_ids)
        checklist_total = len(itens)
        checklist_concluidos = sum(1 for i in itens if i.get("concluido"))
    else:
        checklist_total = 0
        checklist_concluidos = 0

    badges = {
        "notas": notas_count,
        "documentos": documentos_count,
        "checklist_total": checklist_total,
        "checklist_concluidos": checklist_concluidos,
        "tem_descricao": descricao is not None,
    }
    for extend in cfg.badge_extensions:
        badges = extend(cfg, db, org_id, entity_id, entity, badges)
    return badges


def _datas(entity: dict) -> dict:
    return {
        "data_inicio": entity.get("data_inicio"),
        "data_entrega": entity.get("data_entrega"),
        "entrega_concluida": entity.get("entrega_concluida", False),
        "lembrete_minutos_antes": entity.get("lembrete_minutos_antes"),
        "recorrencia": entity.get("recorrencia"),
    }


def get_card_resumo(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> dict:
    """`{<entity_kind>, tags, membros, descricao, [datas], badges, ...ext}`."""
    entity = ensure_entity(cfg, db, org_id, entity_id)

    # Reuses the services' own paged tag/membro reads — one bug surface.
    resumo: dict = {
        cfg.entity_kind: entity,
        "tags": get_entity_tags(cfg, db, org_id, entity_id)["items"],
        "membros": get_membros(cfg, db, org_id, entity_id)["items"],
        # The single Descrição is card STATE, served here — never in the
        # timeline (see `gatherers.gather_notas`).
        "descricao": get_descricao(cfg, db, org_id, entity_id),
    }
    if cfg.entity_datas:
        resumo["datas"] = _datas(entity)
    resumo["badges"] = compute_badges(cfg, db, org_id, entity_id, entity)
    for extend in cfg.resumo_extensions:
        resumo = extend(cfg, db, org_id, entity_id, entity, resumo)
    return resumo


__all__ = ["compute_badges", "count_rows", "get_card_resumo"]
