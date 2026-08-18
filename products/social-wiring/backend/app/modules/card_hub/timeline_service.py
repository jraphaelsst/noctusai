"""The unified timeline (D9) + the card summary / badges (contract §3).

`ocorrido_em` is the sort key and it is the event's OWN time, never
`created_at` of the row that records it (contract §3) — a backfilled
touch from March must sort in March. Every source function below sets
`ocorrido_em` from the domain event's own timestamp column, never from a
recording-row `created_at`, EXCEPT where the row IS the event (a note is
created at the moment it's written; a movement IS the moment it happened)
— those two coincide by construction, not by mistake.

`movimento` reads `pipeline_movimentos` — written by
`app.modules.pipeline` (migration 034) — via a READ-ONLY join through
`negociacoes_venda`/`processos_venda`. This module never imports from or
writes to `app.modules.pipeline` (ruling S1); it only queries tables that
module owns, exactly as the contract's §1 "already exists, do not
rebuild" table names it. `negociacoes_venda.cliente_id` is nullable until
slice `054` (P1.4, parallel) finishes repointing every card — a `funil`
card whose `negociacoes_venda.cliente_id` is still NULL simply has no
`movimento` entries yet; this is the expected, honest, and improving-
over-time state, not a bug in this module.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.modules.card_hub import services as card_hub_services
from app.modules.card_hub.services import (
    _actor,
    _in_batched_rows,
    _paged_rows,
    _resolve_actors,
    _t,
    ensure_cliente,
)

_ALL_KINDS = {"nota", "touch", "movimento", "documento", "checklist", "sistema"}
_DEFAULT_LIMIT = 50


# ─── cursor codec ───────────────────────────────────────────────────────


def _encode_cursor(ocorrido_em: str, entry_id: str) -> str:
    raw = f"{ocorrido_em}|{entry_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ocorrido_em, entry_id = raw.split("|", 1)
        return ocorrido_em, entry_id
    except Exception as exc:  # noqa: BLE001 — any decode failure is "bad cursor"
        from noctusai_lib.primitives.exceptions import ValidationError_

        raise ValidationError_(f"cursor inválido: {cursor!r}") from exc


def _sort_key(entry: dict) -> tuple[str, str]:
    return (entry["ocorrido_em"], entry["id"])


# ─── per-kind gatherers ─────────────────────────────────────────────────


def _gather_notas(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    # Contract correction: `tipo='descricao'` is card STATE (surfaced via
    # `CardResumo.descricao`), not a timeline event — showing it in the
    # thread would make every edit of the description look like a new
    # comment. Only `tipo='comentario'` rows are gathered here.
    rows = _paged_rows(
        client,
        "cliente_notas",
        org_id,
        eq_filters={"cliente_id": str(cliente_id), "tipo": "comentario"},
    )
    autor_ids = {r["autor_id"] for r in rows if r.get("autor_id")}
    resolved = _resolve_actors(autor_ids)
    return [
        {
            "id": r["id"],
            "kind": "nota",
            "ocorrido_em": r["created_at"],
            "ator": _actor(resolved, r.get("autor_id")),
            "payload": {
                "id": r["id"],
                "corpo": r["corpo"],
                "autor": _actor(resolved, r.get("autor_id")),
                "editado_em": r.get("editado_em"),
                "deleted_at": r.get("deleted_at"),
            },
        }
        for r in rows
    ]


def _gather_touches(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
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


def _gather_movimentos(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    negociacoes = _paged_rows(client, "negociacoes_venda", org_id, eq_filters={"cliente_id": str(cliente_id)})
    negociacao_ids = [n["id"] for n in negociacoes]
    if not negociacao_ids:
        return []

    processos = _in_batched_rows(client, "processos_venda", org_id, "negociacao_venda_id", negociacao_ids)
    processo_ids = [p["id"] for p in processos]

    funil_moves = _in_batched_rows(client, "pipeline_movimentos", org_id, "entidade_id", negociacao_ids)
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
    stage_names = {s["id"]: s.get("nome", s["id"]) for s in stages}

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


def _gather_documentos(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    rows = _paged_rows(
        client,
        "cliente_documentos",
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
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


def _gather_checklist_events(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """One timeline entry per COMPLETED checklist item — derived, per
    contract §3. A never-completed item has no event to show; this
    product does not track a separate "created" audit trail for
    checklist items, so completion is the only derivable moment."""
    checklists = _paged_rows(client, "cliente_checklists", org_id, eq_filters={"cliente_id": str(cliente_id)})
    if not checklists:
        return []
    titulo_by_id = {c["id"]: c["titulo"] for c in checklists}
    itens = _in_batched_rows(
        client, "cliente_checklist_itens", org_id, "checklist_id", list(titulo_by_id.keys())
    )
    completed = [i for i in itens if i.get("concluido") and i.get("concluido_em")]
    autor_ids = {i["concluido_por"] for i in completed if i.get("concluido_por")}
    resolved = _resolve_actors(autor_ids)
    return [
        {
            "id": i["id"],
            "kind": "checklist",
            "ocorrido_em": i["concluido_em"],
            "ator": _actor(resolved, i.get("concluido_por")),
            "payload": {
                "checklist_id": i["checklist_id"],
                "titulo": titulo_by_id.get(i["checklist_id"]),
                "item_texto": i["texto"],
                "concluido": True,
            },
        }
        for i in completed
    ]


def _gather_sistema(client: Any, org_id: UUID, cliente_id: UUID, cliente: dict) -> list[dict]:
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


_GATHERERS = {
    "nota": _gather_notas,
    "touch": _gather_touches,
    "movimento": _gather_movimentos,
    "documento": _gather_documentos,
    "checklist": _gather_checklist_events,
}


def get_timeline(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    kinds: Optional[set] = None,
    cursor: Optional[str] = None,
    limit: int = _DEFAULT_LIMIT,
) -> dict:
    cliente = ensure_cliente(client, org_id, cliente_id)
    requested = kinds & _ALL_KINDS if kinds else set(_ALL_KINDS)

    entries: list[dict] = []
    for kind, gather in _GATHERERS.items():
        if kind in requested:
            entries.extend(gather(client, org_id, cliente_id))
    if "sistema" in requested:
        entries.extend(_gather_sistema(client, org_id, cliente_id, cliente))

    entries.sort(key=_sort_key, reverse=True)
    total = len(entries)

    if cursor:
        cursor_ocorrido_em, cursor_id = _decode_cursor(cursor)
        entries = [
            e
            for e in entries
            if (e["ocorrido_em"], e["id"]) < (cursor_ocorrido_em, cursor_id)
        ]

    page = entries[:limit]
    next_cursor = None
    if len(entries) > limit:
        last = page[-1]
        next_cursor = _encode_cursor(last["ocorrido_em"], last["id"])

    items = [
        {
            "id": e["id"],
            "kind": e["kind"],
            "ocorrido_em": e["ocorrido_em"],
            "ator": e["ator"],
            **e["payload"],
        }
        for e in page
    ]
    return {"items": items, "total": total, "next_cursor": next_cursor}


# ─── Card summary (the badge row) ────────────────────────────────────────


def _count(client: Any, table: str, org_id: UUID, cliente_id: UUID, **extra_eq) -> int:
    """A head-only count query — never fetch-then-`len()` (contract §3:
    the board renders ~1200 cards; badges must be served, computed in
    SQL)."""
    query = (
        _t(client, table)
        .select("id", count="exact")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
    )
    for key, value in extra_eq.items():
        query = query.eq(key, value)
    result = query.execute()
    return getattr(result, "count", None) or 0


def compute_badges(client: Any, org_id: UUID, cliente_id: UUID, cliente: dict) -> dict:
    # Contract correction: `notas` counts COMMENTS only (`tipo='comentario'`)
    # — the description has its own `tem_descricao` boolean, mirroring
    # Trello's own split between the `comments` and `description` badges.
    notas_count = _count(client, "cliente_notas", org_id, cliente_id, tipo="comentario")
    descricao = card_hub_services.get_descricao(client, org_id, cliente_id)
    documentos_count = _count(client, "cliente_documentos", org_id, cliente_id)
    touches_count = _count(client, "cliente_touches", org_id, cliente_id)

    checklists = _paged_rows(client, "cliente_checklists", org_id, eq_filters={"cliente_id": str(cliente_id)})
    checklist_ids = [c["id"] for c in checklists]
    if checklist_ids:
        itens = _in_batched_rows(client, "cliente_checklist_itens", org_id, "checklist_id", checklist_ids)
        checklist_total = len(itens)
        checklist_concluidos = sum(1 for i in itens if i.get("concluido"))
    else:
        checklist_total = 0
        checklist_concluidos = 0

    temperatura = _compute_temperatura(cliente)

    return {
        "notas": notas_count,
        "documentos": documentos_count,
        "touches": touches_count,
        "checklist_total": checklist_total,
        "checklist_concluidos": checklist_concluidos,
        "tem_descricao": descricao is not None,
        "temperatura": temperatura,
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


def get_card_resumo(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    cliente = ensure_cliente(client, org_id, cliente_id)

    # Reuses `services.py`'s own paginated tag/membro reads rather than a
    # second copy of the same join — one bug surface, not two.
    tags_out = card_hub_services.get_cliente_tags(client, org_id, cliente_id)["items"]
    membros_out = card_hub_services.get_membros(client, org_id, cliente_id)["items"]

    negociacoes = _paged_rows(client, "negociacoes_venda", org_id, eq_filters={"cliente_id": str(cliente_id)})

    return {
        "cliente": cliente,
        "tags": tags_out,
        "membros": membros_out,
        # Contract correction: the card's single Descrição is card STATE,
        # surfaced here (never in the timeline — see `_gather_notas`).
        "descricao": card_hub_services.get_descricao(client, org_id, cliente_id),
        "datas": {
            "data_inicio": cliente.get("data_inicio"),
            "data_entrega": cliente.get("data_entrega"),
            "entrega_concluida": cliente.get("entrega_concluida", False),
            "lembrete_minutos_antes": cliente.get("lembrete_minutos_antes"),
            "recorrencia": cliente.get("recorrencia"),
        },
        "badges": compute_badges(client, org_id, cliente_id, cliente),
        "negociacoes": negociacoes,
    }


__all__ = ["compute_badges", "get_card_resumo", "get_timeline"]
