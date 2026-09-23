"""The unified timeline (D9) + the card summary / badges (contract §3) —
social-wiring's half of them.

The MECHANICS (cursor codec, pager, the `nota` / `documento` / `checklist`
gatherers, the seed badges, the resumo skeleton) are the seed's
`noctusai_lib.domain.card_hub` — this module used to be their original and
they were lifted out of it as a MOVE (wave A, 2026-09-22). What stays here is
what is ABOUT social-wiring, plugged in through the config's named seams
(`app.modules.card_hub.config.CARD_HUB`):

- the `touch`, `movimento`, `visita` and `sistema` gatherers
  (`timeline_gatherers`);
- the `touches` + `temperatura` badges, spliced back into the badge row at
  the positions the API contract has always served them in
  (`badge_extensions`);
- the resumo's `atendimentos` key (`resumo_extensions`).

`get_timeline` / `compute_badges` / `get_card_resumo` survive as thin shims
with their historical `(client, org_id, cliente_id)` signatures.

`ocorrido_em` is the sort key and it is the event's OWN time, never
`created_at` of the row that records it (contract §3) — a backfilled
touch from March must sort in March. Every gatherer below sets
`ocorrido_em` from the domain event's own timestamp column, never from a
recording-row `created_at`, EXCEPT where the row IS the event (a movement
IS the moment it happened) — those coincide by construction, not by
mistake.

`movimento` reads `pipeline_movimentos` — written by
`app.modules.pipeline` (migration 034) — via a READ-ONLY join through
`atendimentos`/`processos_venda`. This module never imports from or
writes to `app.modules.pipeline` (ruling S1); it only queries tables that
module owns, exactly as the contract's §1 "already exists, do not
rebuild" table names it. `atendimentos.cliente_id` is nullable until
slice `054` (P1.4, parallel) finishes repointing every card — a `funil`
card whose `atendimentos.cliente_id` is still NULL simply has no
`movimento` entries yet; this is the expected, honest, and improving-
over-time state, not a bug in this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.domain.card_hub import SEED_GATHERERS, CardHubConfig
from noctusai_lib.domain.card_hub import badges as seed_badges
from noctusai_lib.domain.card_hub import timeline as seed_timeline
from noctusai_lib.domain.card_hub.badges import count_rows

from app.modules.card_hub import services as card_hub_services
from app.modules.card_hub.deps import card_hub_config
from app.modules.card_hub.services import (
    _actor,
    _in_batched_rows,
    _paged_rows,
    _resolve_actors,
)

_DEFAULT_LIMIT = seed_timeline.DEFAULT_LIMIT


# ─── social-wiring's gatherers (registered via `CARD_HUB.timeline_gatherers`) ─
#
# Seed gatherer signature: `(cfg, db, org_id, entity_id, entity)`. The
# parameters keep their historical names here (`client`, `cliente_id`,
# `cliente`) so every body below reads exactly as it did before the lift.


def _gather_touches(
    cfg: CardHubConfig, client: Any, org_id: UUID, cliente_id: UUID, cliente: dict
) -> list[dict]:
    # A prolific cliente's touch trail is exactly the "hundreds/thousands
    # accumulated over a lifetime" shape the 1 000-row cap has bitten in
    # this product before — paged, never a bare `.execute()`.
    rows = _paged_rows(client, "cliente_touches", org_id, eq_filters={"cliente_id": str(cliente_id)})
    return [
        {
            "id": r["id"],
            "kind": "touch",
            "ocorrido_em": r["ocorreu_em"],
            "ator": None,
            "payload": {
                "id": r["id"],
                "origem_tabela": r["origem_tabela"],
                "origem_id": r["origem_id"],
                "origem_rotulo": r.get("origem_label"),
                "resumo": r.get("nome"),
                "dados": {"chave_canonica": r.get("chave_canonica")},
            },
        }
        for r in rows
    ]


def _gather_movimentos(
    cfg: CardHubConfig, client: Any, org_id: UUID, cliente_id: UUID, cliente: dict
) -> list[dict]:
    atendimentos = _paged_rows(client, "atendimentos", org_id, eq_filters={"cliente_id": str(cliente_id)})
    atendimento_ids = [n["id"] for n in atendimentos]
    if not atendimento_ids:
        return []

    processos = _in_batched_rows(client, "processos_venda", org_id, "atendimento_id", atendimento_ids)
    processo_ids = [p["id"] for p in processos]

    funil_moves = _in_batched_rows(client, "pipeline_movimentos", org_id, "entidade_id", atendimento_ids)
    funil_moves = [m for m in funil_moves if m.get("pipeline") == "funil"]
    processo_moves = (
        _in_batched_rows(client, "pipeline_movimentos", org_id, "entidade_id", processo_ids)
        if processo_ids
        else []
    )
    processo_moves = [m for m in processo_moves if m.get("pipeline") == "processos_venda"]
    moves = funil_moves + processo_moves
    if not moves:
        return []

    stage_ids = {m["para_etapa_id"] for m in moves if m.get("para_etapa_id")} | {
        m["de_etapa_id"] for m in moves if m.get("de_etapa_id")
    }
    stages = _in_batched_rows(client, "pipeline_stages", org_id, "id", list(stage_ids)) if stage_ids else []
    # 🔴 `pipeline_stages` names its human-readable column `label` — there is no
    # `nome` column on that table at all. The original `s.get("nome", s["id"])`
    # therefore ALWAYS fell through to its default, so every movimento entry
    # rendered the stage's raw UUID: `Moveu de "b9e34f2d-2268-…" para
    # "4c3df1a7-68c7-…"`, on BOTH boards, for every card (found in prod
    # 2026-08-31 walking a card end-to-end).
    #
    # The default is the bug's camouflage: a missing key silently produced a
    # plausible-looking string instead of failing, which is exactly the
    # silent-fallback shape. `slug` is the honest intermediate fallback (still
    # human-readable) before the id is used as a genuine last resort.
    stage_names = {
        s["id"]: (s.get("label") or s.get("slug") or s["id"]) for s in stages
    }

    autor_ids = {m["responsavel_id"] for m in moves if m.get("responsavel_id")}
    resolved = _resolve_actors(autor_ids)

    return [
        {
            "id": m["id"],
            "kind": "movimento",
            "ocorrido_em": m["created_at"],
            "ator": _actor(resolved, m.get("responsavel_id")),
            "payload": {
                "id": m["id"],
                "de_etapa": stage_names.get(m.get("de_etapa_id")),
                "para_etapa": stage_names.get(m.get("para_etapa_id")),
                "autor": _actor(resolved, m.get("responsavel_id")),
            },
        }
        for m in moves
    ]


def _gather_sistema(
    cfg: CardHubConfig, client: Any, org_id: UUID, cliente_id: UUID, cliente: dict
) -> list[dict]:
    """Derived system events: created, archived, merged, and the undo of
    a merge. 🔴 "restored" (D4's manual un-archive) is DELIBERATELY
    ABSENT here: `clientes.arquivado_em` is NULLED (not stamped with a
    restoration timestamp) by `clientes_router.py::update_cliente_route`
    when `ativo` flips back to true, so there is no honestly-derivable
    timestamp for this event anywhere in the schema today. Fabricating
    one (e.g. "now") would misplace it in the sort order and lie about
    when it happened; surfaced in this slice's delivery note as a
    contract gap rather than silently invented here."""
    events: list[dict] = []
    if cliente.get("created_at"):
        events.append(
            {
                "id": f"sistema-criado-{cliente['id']}",
                "kind": "sistema",
                "ocorrido_em": cliente["created_at"],
                "ator": None,
                "payload": {"evento": "criado", "detalhe": None},
            }
        )
    if cliente.get("arquivado_em"):
        events.append(
            {
                "id": f"sistema-arquivado-{cliente['id']}",
                "kind": "sistema",
                "ocorrido_em": cliente["arquivado_em"],
                "ator": None,
                "payload": {"evento": "arquivado", "detalhe": None},
            }
        )

    merges = _paged_rows(
        client, "cliente_merges", org_id, eq_filters={"cliente_id_sobrevivente": str(cliente_id)}
    )
    for m in merges:
        events.append(
            {
                "id": f"sistema-merge-{m['id']}",
                "kind": "sistema",
                "ocorrido_em": m["created_at"],
                "ator": None,
                "payload": {"evento": "merged", "detalhe": m.get("nome_absorvido")},
            }
        )
        if m.get("desfeito_em"):
            events.append(
                {
                    "id": f"sistema-merge-undo-{m['id']}",
                    "kind": "sistema",
                    "ocorrido_em": m["desfeito_em"],
                    "ator": None,
                    "payload": {"evento": "merge_desfeito", "detalhe": m.get("nome_absorvido")},
                }
            )
    return events


def _gather_visitas(
    cfg: CardHubConfig, client: Any, org_id: UUID, cliente_id: UUID, cliente: dict
) -> list[dict]:
    """Routes planned and visits that resolved — DERIVED, like every other
    gatherer here (migration 082).

    🔴 This is the half of the roteiros feature that makes it a MEMORY rather
    than a counter. The user's requirement was explicit: in 2028, an agent
    handling this person must be able to see what happened in 2024 — which
    properties were walked, whether the visit happened, and what the corretor
    wrote down. `visitas.observacao` is that sentence, and this is where it
    becomes readable.

    Nothing is written anywhere: `timeline_service` has no insert path, and
    adding one for this would fork the module's whole design.

    A `pendente` visita produces NO entry. `feedback_em` is null until the
    outcome is recorded, and `_gather_sistema`'s ruling on "restored" applies
    unchanged — an event with no honestly derivable timestamp is omitted, never
    stamped with `now()`, which would misplace it in the sort order and lie
    about when it happened.
    """
    atendimentos = card_hub_services._atendimentos_do_cliente(client, org_id, cliente_id)
    if not atendimentos:
        return []
    roteiros = [
        r
        for r in _in_batched_rows(
            client, "roteiros", org_id, "atendimento_id", [str(a["id"]) for a in atendimentos]
        )
        if r.get("deleted_at") is None
    ]
    if not roteiros:
        return []

    events: list[dict] = []
    visitas = [
        v
        for v in _in_batched_rows(
            client, "visitas", org_id, "roteiro_id", [str(r["id"]) for r in roteiros]
        )
        if v.get("deleted_at") is None
    ]
    por_roteiro: dict[str, int] = {}
    for v in visitas:
        por_roteiro[str(v["roteiro_id"])] = por_roteiro.get(str(v["roteiro_id"]), 0) + 1

    for r in roteiros:
        if not r.get("created_at"):
            continue
        events.append(
            {
                "id": f"roteiro-{r['id']}",
                "kind": "visita",
                "ocorrido_em": r["created_at"],
                "ator": None,
                "payload": {
                    "evento": "roteiro_criado",
                    "roteiro_id": r["id"],
                    "titulo": r.get("titulo"),
                    "imoveis": por_roteiro.get(str(r["id"]), 0),
                },
            }
        )

    for v in visitas:
        if v.get("status") == "pendente" or not v.get("feedback_em"):
            continue
        events.append(
            {
                "id": f"visita-{v['id']}",
                "kind": "visita",
                "ocorrido_em": v["feedback_em"],
                "ator": None,
                "payload": {
                    "evento": (
                        "visita_realizada"
                        if v["status"] == "realizada"
                        else "visita_nao_realizada"
                    ),
                    "roteiro_id": v["roteiro_id"],
                    "codigo": v.get("codigo"),
                    "observacao": v.get("observacao"),
                },
            }
        )
    return events


#: The card's full kind registry — the seed's three plus ours, in the order
#: this module always gathered them (`sistema` last). The served order is the
#: sort, so this only decides tie-order between identical `(ocorrido_em, id)`
#: keys — kept anyway, so the lift changes nothing observable.
TIMELINE_GATHERERS = {
    "nota": SEED_GATHERERS["nota"],
    "touch": _gather_touches,
    "movimento": _gather_movimentos,
    "documento": SEED_GATHERERS["documento"],
    "checklist": SEED_GATHERERS["checklist"],
    "visita": _gather_visitas,
    "sistema": _gather_sistema,
}

# ─── Timeline ───────────────────────────────────────────────────────────


def get_timeline(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    kinds: Optional[set] = None,
    cursor: Optional[str] = None,
    limit: int = _DEFAULT_LIMIT,
) -> dict:
    return seed_timeline.get_timeline(
        card_hub_config(), client, org_id, cliente_id, kinds=kinds, cursor=cursor, limit=limit
    )


# ─── Card summary (the badge row) ────────────────────────────────────────


def badges_sw(
    cfg: CardHubConfig, client: Any, org_id: UUID, cliente_id: UUID, cliente: dict, badges: dict
) -> dict:
    """`CARD_HUB.badge_extensions` — adds `touches` + `temperatura` and
    REBUILDS the dict so the served key order is the contract's own
    (`touches` between `documentos` and `checklist_total`; `temperatura`
    last), not "seed keys, then ours".

    `touches` is a head-only count query like every other badge — never
    fetch-then-`len()` (contract §3: the board renders ~1200 cards; badges
    must be served, computed in SQL)."""
    touches_count = count_rows(cfg, client, "cliente_touches", org_id, cliente_id)
    return {
        "notas": badges["notas"],
        "documentos": badges["documentos"],
        "touches": touches_count,
        "checklist_total": badges["checklist_total"],
        "checklist_concluidos": badges["checklist_concluidos"],
        "tem_descricao": badges["tem_descricao"],
        "temperatura": _compute_temperatura(cliente),
    }


def _compute_temperatura(cliente: dict) -> Optional[dict]:
    """D8's provisional formula: recency of last touch + touch count.
    ALWAYS carries `provisoria: true` (contract §3) — D8 deferred the
    formula, not the component. `ultimo_contato_em`/`primeiro_contato_em`
    are maintained by the Phase 1 service layer on every touch write (see
    migration 048's header) — this function only reads them."""
    ultimo = cliente.get("ultimo_contato_em")
    if not ultimo:
        return None
    last_dt = datetime.fromisoformat(ultimo.replace("Z", "+00:00"))
    days_since = (datetime.now(timezone.utc) - last_dt).days
    if days_since <= 3:
        valor, rotulo = 90, "quente"
    elif days_since <= 14:
        valor, rotulo = 60, "morno"
    elif days_since <= 45:
        valor, rotulo = 30, "frio"
    else:
        valor, rotulo = 10, "gelado"
    return {"valor": valor, "rotulo": rotulo, "provisoria": True}


def resumo_sw(
    cfg: CardHubConfig, client: Any, org_id: UUID, cliente_id: UUID, cliente: dict, resumo: dict
) -> dict:
    """`CARD_HUB.resumo_extensions` — appends `atendimentos` (the last key
    the contract serves).

    The card shows the person's OWN data, and for a lead that data lives on
    the ORIGIN record (`leads` / `meta_ads_leads`) — `clientes` deliberately
    holds identity + card state, never contact fields. So each atendimento
    arrives with its origin embedded, under the SAME projection the boards
    use (`pipeline.configs.CARD_ORIGIN_SELECT`): one definition of "what a
    lead card projects", so the card and the board cannot end up showing
    different subsets of the same record."""
    # Local import: `pipeline.configs` imports nothing from card_hub, but
    # keeping this at call scope makes the one-way direction obvious and
    # avoids a module-level cycle if that ever changes.
    from app.modules.pipeline.configs import CARD_ORIGIN_SELECT

    atendimentos = _paged_rows(
        client,
        "atendimentos",
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        select=CARD_ORIGIN_SELECT,
    )
    return {**resumo, "atendimentos": atendimentos}


def compute_badges(client: Any, org_id: UUID, cliente_id: UUID, cliente: dict) -> dict:
    return seed_badges.compute_badges(card_hub_config(), client, org_id, cliente_id, cliente)


def get_card_resumo(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    return seed_badges.get_card_resumo(card_hub_config(), client, org_id, cliente_id)


__all__ = [
    "TIMELINE_GATHERERS",
    "badges_sw",
    "compute_badges",
    "get_card_resumo",
    "get_timeline",
    "resumo_sw",
]
