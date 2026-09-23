"""The seed's timeline gatherers — one per event kind the seed itself owns.

A gatherer is `(cfg, db, org_id, entity_id, entity) -> list[entry]`, where an
entry is `{"id", "kind", "ocorrido_em", "ator", "payload"}`. The timeline
(`timeline.py`) flattens `payload` into the served item, so a gatherer owns
exactly the keys its kind renders — nothing else.

🔴 `ocorrido_em` IS THE EVENT'S OWN TIME, never the `created_at` of a row that
merely records it — a backfilled event from March must sort in March. The
seed's three kinds are all rows that ARE their event (a note is written at the
moment it's written; a document is uploaded when it's uploaded; a checklist
item's completion is stamped `concluido_em`), so for them the two coincide by
construction, not by mistake. A product gatherer over a recorded-later source
must read that source's own timestamp column.

A product ADDS kinds (`{**SEED_GATHERERS, "touch": gather_touches}`); it never
forks this file. Lifted verbatim from social-wiring's
`app/modules/card_hub/timeline_service.py` (`_gather_notas`,
`_gather_documentos`, `_gather_checklist_events`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Mapping

from noctusai_lib.integrations.persistence.table_reads import (
    actor,
    in_batched_rows,
    paged_rows,
)

if TYPE_CHECKING:  # pragma: no cover
    from .config import CardHubConfig

Gatherer = Callable[["CardHubConfig", Any, Any, Any, dict], list]


def gather_notas(cfg: "CardHubConfig", db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
    """Comments only. `tipo='descricao'` is card STATE (served in the resumo),
    not a timeline event — showing it in the thread would make every edit of
    the description look like a new comment."""
    rows = paged_rows(
        db,
        cfg.tables.notas,
        org_id,
        eq_filters={cfg.entity_fk: str(entity_id), "tipo": "comentario"},
    )
    autor_ids = {r["autor_id"] for r in rows if r.get("autor_id")}
    resolved = cfg.actor_resolver(autor_ids)
    return [
        {
            "id": r["id"],
            "kind": "nota",
            "ocorrido_em": r["created_at"],
            "ator": actor(resolved, r.get("autor_id")),
            "payload": {
                "id": r["id"],
                "corpo": r["corpo"],
                "autor": actor(resolved, r.get("autor_id")),
                "editado_em": r.get("editado_em"),
                "deleted_at": r.get("deleted_at"),
            },
        }
        for r in rows
    ]


def gather_documentos(cfg: "CardHubConfig", db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
    rows = paged_rows(
        db,
        cfg.tables.documentos,
        org_id,
        eq_filters={cfg.entity_fk: str(entity_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    return [
        {
            "id": r["id"],
            "kind": "documento",
            "ocorrido_em": r["created_at"],
            "ator": None,
            "payload": {
                "id": r["id"],
                "nome_original": r["nome_original"],
                "mime_type": r["mime_type"],
                "tamanho_bytes": r["tamanho_bytes"],
            },
        }
        for r in rows
    ]


def gather_audit(cfg: "CardHubConfig", db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
    """Default `"historico"` kind — the S2 audit-trail's
    (`noctusai_lib.api.audit`) `public.audit_logs` rows for mutating
    requests whose path carried THIS card's id, reshaped into timeline
    entries.

    Inert unless `cfg.audit_trail_enabled` AND `cfg.get_core_client`
    are both set (`CardHubConfig.__post_init__` only wires this into
    the default `timeline_gatherers` when both are true) — matching
    `settings.audit_trail_enabled`'s own default-off posture.

    Scoped by `org_id` (RLS-equivalent tenant boundary) AND a JSONB
    containment match on `details->path_params` for `cfg.id_param`
    (`AuditMiddleware` records `scope["path_params"]` verbatim under
    that key — see `noctusai_lib.api.audit.sink._to_row`). NOT also
    filtered by product/`resource_type`: `entity_id` is a UUID, so a
    cross-product collision on the SAME id is not a realistic risk,
    and `AuditMiddleware`'s `product` is the human-readable name
    (`create_product_app(name=...)`), which `CardHubConfig` has no
    access to — narrowing on it would need a new config field for
    marginal safety. Capped at the 200 most recent rows (no full
    pager — `noctusai_lib.integrations.persistence.table_reads
    .paged_rows` assumes flat `eq_filters`, not a JSONB containment
    filter); a card with a longer real history is a future
    enhancement, not a correctness gap for a default gatherer.
    """
    admin = cfg.get_core_client()
    rows = (
        admin.schema("public")
        .table("audit_logs")
        .select("*")
        .eq("org_id", str(org_id))
        .contains("details", {"path_params": {cfg.id_param: str(entity_id)}})
        .order("created_at", desc=True)
        .limit(200)
        .execute()
        .data
    )
    autor_ids = {r["user_id"] for r in rows if r.get("user_id")}
    resolved = cfg.actor_resolver(autor_ids)
    return [
        {
            "id": r["id"],
            "kind": "historico",
            "ocorrido_em": r["created_at"],
            "ator": actor(resolved, r.get("user_id")),
            "payload": {
                "method": r.get("action"),
                "route_template": (r.get("details") or {}).get("route_template"),
                "status": (r.get("details") or {}).get("status"),
                "actor_kind": (r.get("details") or {}).get("actor_kind"),
            },
        }
        for r in rows
    ]


def gather_checklist_events(cfg: "CardHubConfig", db: Any, org_id: Any, entity_id: Any, entity: dict) -> list[dict]:
    """One entry per COMPLETED checklist item — derived. A never-completed item
    has no event to show; the card tracks no separate "created" audit trail
    for items, so completion is the only derivable moment."""
    checklists = paged_rows(db, cfg.tables.checklists, org_id, eq_filters={cfg.entity_fk: str(entity_id)})
    if not checklists:
        return []
    titulo_by_id = {c["id"]: c["titulo"] for c in checklists}
    itens = in_batched_rows(
        db, cfg.tables.checklist_itens, org_id, "checklist_id", list(titulo_by_id.keys())
    )
    completed = [i for i in itens if i.get("concluido") and i.get("concluido_em")]
    autor_ids = {i["concluido_por"] for i in completed if i.get("concluido_por")}
    resolved = cfg.actor_resolver(autor_ids)
    return [
        {
            "id": i["id"],
            "kind": "checklist",
            "ocorrido_em": i["concluido_em"],
            "ator": actor(resolved, i.get("concluido_por")),
            "payload": {
                "checklist_id": i["checklist_id"],
                "titulo": titulo_by_id.get(i["checklist_id"]),
                "item_texto": i["texto"],
                "concluido": True,
            },
        }
        for i in completed
    ]


#: The kinds the seed owns. Insertion order is the gather order; the served
#: order is always the sort, so this only matters for readability.
SEED_GATHERERS: Mapping[str, Gatherer] = {
    "nota": gather_notas,
    "documento": gather_documentos,
    "checklist": gather_checklist_events,
}


__all__ = [
    "Gatherer",
    "SEED_GATHERERS",
    "gather_audit",
    "gather_checklist_events",
    "gather_documentos",
    "gather_notas",
]
