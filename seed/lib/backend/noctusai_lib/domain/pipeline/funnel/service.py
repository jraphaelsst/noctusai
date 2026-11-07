"""The funnel organ's card logic — plain functions over a scoped client.

No FastAPI here (`domain/` must not import `api/` machinery beyond the shared
schema base). Every function takes the EFFECTIVE `org_id` — already resolved by
`scope()` — and refuses a falsy one: the whole reason this layer exists is that
`stages.list_stages(org_id=None)` silently reads every tenant.

Write discipline: every function validates BEFORE its first write, so a 4xx
leaves no partial state; history is written only by `move_card` and the entry
row of `create_card`, and is append-only.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from typing import Any, Callable, Mapping

from noctusai_lib.domain.pipeline.board import group_into_colunas, orphan_cards
from noctusai_lib.domain.pipeline.moves import move_card
from noctusai_lib.domain.pipeline.ordering import (
    position_for_drop,
    position_of,
    position_on_top,
)
from noctusai_lib.domain.pipeline.router import PipelineContext
from noctusai_lib.domain.pipeline.stages import get_stage, list_stages
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import actor as _actor
from noctusai_lib.primitives.accents import fold_accents_ascii
from noctusai_lib.primitives.exceptions import InternalError, NotFoundError

from .config import FunnelConfig, FunnelContext
from .errors import (
    FunnelError,
    acao_desconhecida,
    campo_nao_editavel,
    card_fechado,
    card_not_found,
    etapa_inativa,
    motivo_desconhecido,
    motivo_obrigatorio,
    stage_not_found,
)
from .gates import run_gate
from .schemas import CardDTO

logger = logging.getLogger(__name__)

#: Cards returned per column by default; counts and totals always cover ALL of them.
LIMITE_CARDS_PADRAO = 50
#: history `kind` column -> the `kind` served on a `/movimentos` item.
_EVENT_KINDS = {"mover": "movimento", "entrada": "movimento", "perdido": "perdido", "reaberto": "reaberto", "arquivado": "arquivado"}
_DTO_KEYS = frozenset(
    {"titulo", "subtitulo", "valor", "responsavel", "badges", "campos", "hub_entity_id", "status"}
)


# ───────────────────────────── tenancy ─────────────────────────────


def scope(cfg: FunnelConfig, ctx: PipelineContext) -> PipelineContext:
    """Resolve the EFFECTIVE tenant of a request — never "all tenants".

    org: the caller's org, or a 500 when the session resolved none.
    platform: the config's explicit `platform_org_id`, whatever the session says.
    """
    if cfg.tenancy == "platform":
        return PipelineContext(db=ctx.db, org_id=cfg.platform_org_id, user_id=ctx.user_id)
    if not ctx.org_id:
        raise InternalError("Organização do usuário não resolvida para o funil.")
    return PipelineContext(db=ctx.db, org_id=str(ctx.org_id), user_id=ctx.user_id)


def _require_org(org_id: Any) -> str:
    if not org_id:  # defence in depth: scope() already guarantees it
        raise InternalError("Funil sem organização efetiva.")
    return str(org_id)


# ───────────────────────────── reads ─────────────────────────────


def _card_query(db: Any, cfg: FunnelConfig, org_id: str, select: str = "*"):
    query = db.table(cfg.pipeline.card_table).select(select)
    if cfg.card_scoped_by_org:
        query = query.eq("org_id", _require_org(org_id))
    return query


def get_card_row(db: Any, cfg: FunnelConfig, org_id: str, card_id: str) -> dict:
    rows = _card_query(db, cfg, org_id).eq("id", card_id).execute().data or []
    if not rows:
        raise card_not_found(card_id)
    return rows[0]


def _paged_cards(db: Any, cfg: FunnelConfig, org_id: str, build: Callable[[Any], Any], *, select: str = "*", label: str) -> list[dict]:
    def fetch_page(start: int, end: int):
        return build(_card_query(db, cfg, org_id, select)).order("id").range(start, end).execute().data

    return list(iter_paged_rows(fetch_page, label=label))


def list_open_cards(
    db: Any, cfg: FunnelConfig, org_id: str, *, status: str = "aberto", responsavel_id: str | None = None
) -> list[dict]:
    def build(query):
        if status != "todos":
            query = query.eq(cfg.status_field, cfg.status_stored(status))
        if responsavel_id:
            query = query.eq(cfg.responsavel_field, responsavel_id)
        return query

    return _paged_cards(db, cfg, org_id, build, label=f"funnel {cfg.pipeline.pipeline} cards")


def column_cards(db: Any, cfg: FunnelConfig, org_id: str, etapa_id: str) -> list[dict]:
    """The OPEN cards of one stage — what a drop index is measured against."""
    return _paged_cards(
        db,
        cfg,
        org_id,
        lambda q: q.eq("etapa_id", etapa_id).eq(cfg.status_field, cfg.status_stored("aberto")),
        select="id, kanban_pos, created_at",
        label=f"funnel {cfg.pipeline.pipeline} column",
    )


# ───────────────────────────── DTO ─────────────────────────────


def card_dto(cfg: FunnelConfig, row: dict) -> CardDTO:
    """Project a card row to the wire DTO: column-derived defaults, then the
    product's `card_projection` merged over them (it wins; `campos` merges)."""
    owner_id = row.get(cfg.responsavel_field)
    if cfg.hub_entity_of is not None:
        hub_id = cfg.hub_entity_of(row)
    else:
        hub_id = row.get("id") if cfg.card_hub is not None else None
    dto: dict[str, Any] = {
        "id": str(row["id"]),
        "etapa_id": str(row["etapa_id"]) if row.get("etapa_id") else None,
        "kanban_pos": str(position_of(row)),
        "status": cfg.status_canonical(row.get(cfg.status_field)),
        "titulo": row.get(cfg.title_field) or "",
        "subtitulo": None,
        "valor": float(row.get(cfg.pipeline.value_field) or 0),
        "responsavel": {"id": str(owner_id), "nome": None} if owner_id else None,
        "badges": [],
        "motivo_perda_codigo": row.get("motivo_perda_codigo"),
        "motivo_perda": row.get("motivo_perda"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "hub_entity_id": str(hub_id) if hub_id else None,
        "campos": {key: row.get(column) for key, column in cfg.editable_fields.items()},
    }
    if cfg.card_projection is not None:
        projected = dict(cfg.card_projection(row))
        unknown = set(projected) - _DTO_KEYS
        if unknown:
            # A typo here would silently vanish from the card; refuse loudly.
            raise ValueError(
                f"card_projection returned keys outside the card DTO: {sorted(unknown)} "
                f"(allowed: {sorted(_DTO_KEYS)}; put extras in 'campos')"
            )
        campos = {**dto["campos"], **(projected.pop("campos", None) or {})}
        dto.update(projected)
        dto["campos"] = campos
        dto["valor"] = float(dto["valor"] or 0)
    return dto  # type: ignore[return-value]


def attach_owner_names(cfg: FunnelConfig, dtos: list[dict]) -> None:
    """Fill `responsavel.nome` for every DTO in ONE resolver call."""
    resolver = cfg.actor_resolver or (cfg.card_hub.actor_resolver if cfg.card_hub else None)
    if resolver is None:
        return
    pending = [d for d in dtos if d.get("responsavel") and not d["responsavel"].get("nome")]
    if not pending:
        return
    resolved = resolver({d["responsavel"]["id"] for d in pending})
    for dto in pending:
        found = _actor(resolved, dto["responsavel"]["id"])
        if found and found.get("nome"):
            dto["responsavel"] = {"id": dto["responsavel"]["id"], "nome": found["nome"]}


def _haystack(dto: Mapping[str, Any]) -> str:
    parts = [dto.get("titulo"), dto.get("subtitulo"), *(dto.get("campos") or {}).values()]
    return fold_accents_ascii(" ".join(str(p) for p in parts if p not in (None, ""))).lower()


# ───────────────────────────── board ─────────────────────────────


def board(
    db: Any,
    cfg: FunnelConfig,
    org_id: str,
    *,
    busca: str | None = None,
    limite_por_etapa: int = LIMITE_CARDS_PADRAO,
    responsavel_id: str | None = None,
    status: str = "aberto",
) -> list[dict]:
    """`PipelineColumn<Card>[]` — one column per ACTIVE stage, every column
    emitted even when empty; `total`/`valorTotal` cover the whole column and
    only the card list is cut to `limite_por_etapa`."""
    org_id = _require_org(org_id)
    stages = list_stages(db, cfg.pipeline, org_id=org_id)
    rows = list_open_cards(db, cfg, org_id, status=status, responsavel_id=responsavel_id)
    dtos = {str(r["id"]): card_dto(cfg, r) for r in rows}
    if busca and busca.strip():
        needle = fold_accents_ascii(busca.strip()).lower()
        rows = [r for r in rows if needle in _haystack(dtos[str(r["id"])])]
    colunas = group_into_colunas(
        cfg.pipeline,
        stages,
        rows,
        row_to_dto=lambda r: dtos[str(r["id"])],
        value_of=lambda r: dtos[str(r["id"])]["valor"],
        limite_cards=limite_por_etapa,
    )
    attach_owner_names(cfg, [c for col in colunas for c in col["cards"]])
    return colunas


def orphans(db: Any, cfg: FunnelConfig, org_id: str) -> list[dict]:
    """Open cards the board cannot place: no stage, or a deleted/inactive one."""
    org_id = _require_org(org_id)
    stages = list_stages(db, cfg.pipeline, org_id=org_id)
    rows = orphan_cards(stages, list_open_cards(db, cfg, org_id))
    dtos = [card_dto(cfg, r) for r in rows]
    attach_owner_names(cfg, dtos)
    return dtos


# ───────────────────────────── stage helpers ─────────────────────────────


def active_stage(db: Any, cfg: FunnelConfig, org_id: str, stage_id: str) -> dict:
    """The stage, scoped to the effective org — a foreign tenant's stage is a
    404 exactly like a missing one — and refused when inactive."""
    try:
        stage = get_stage(db, cfg.pipeline, stage_id, org_id=_require_org(org_id))
    except NotFoundError:
        raise stage_not_found(stage_id) from None
    if not stage.get("ativo", True):
        raise etapa_inativa(stage_id)
    return stage


def _first_stage(db: Any, cfg: FunnelConfig, org_id: str) -> dict:
    stages = list_stages(db, cfg.pipeline, org_id=_require_org(org_id))  # active only, in order
    if not stages:
        raise FunnelError("etapa_inativa", "O funil não tem nenhuma etapa ativa.", 409)
    return stages[0]


# ───────────────────────────── writes ─────────────────────────────


def _record_event(
    db: Any, cfg: FunnelConfig, org_id: str, row: dict, kind: str, user_id: Any, motivo: str | None = None
) -> None:
    """Append a status event (perdido / reaberto / arquivado) to the history.
    The card's current stage fills both stage columns."""
    stage_id = str(row["etapa_id"]) if row.get("etapa_id") else None
    event = {
        "org_id": org_id,
        "pipeline": cfg.pipeline.pipeline,
        "entidade_id": str(row["id"]),
        "de_etapa_id": stage_id,
        "para_etapa_id": stage_id,
        "kind": kind,
        "responsavel_id": str(user_id) if user_id else None,
        "motivo": motivo,
    }
    if cfg.pipeline.cliente_field:
        event["cliente_id"] = row.get(cfg.pipeline.cliente_field)
    db.table(cfg.pipeline.history_table).insert(event).execute()


def _record_entry(db: Any, cfg: FunnelConfig, org_id: str, row: dict, stage_id: str, user_id: Any) -> None:
    """History row for a card ENTERING the board (`de_etapa_id` NULL) — without
    it a card's history starts at its first move and "how long did it sit in
    the entry stage" is unanswerable."""
    entry = {
        "org_id": org_id,
        "pipeline": cfg.pipeline.pipeline,
        "entidade_id": str(row["id"]),
        "de_etapa_id": None,
        "para_etapa_id": stage_id,
        "kind": "entrada",
        "responsavel_id": str(user_id) if user_id else None,
        "motivo": None,
    }
    if cfg.pipeline.cliente_field:
        entry["cliente_id"] = row.get(cfg.pipeline.cliente_field)
    db.table(cfg.pipeline.history_table).insert(entry).execute()


def _map_campos(cfg: FunnelConfig, campos: Mapping[str, Any] | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in (campos or {}).items():
        column = cfg.editable_fields.get(key)
        if column is None:
            raise campo_nao_editavel(key)
        values[column] = value
    return values


def create_card(db: Any, cfg: FunnelConfig, ctx: PipelineContext, body: Mapping[str, Any]) -> dict:
    org_id = _require_org(ctx.org_id)
    extra_columns = _map_campos(cfg, body.get("campos"))  # validate before any write
    stage = (
        active_stage(db, cfg, org_id, body["etapa_id"]) if body.get("etapa_id") else _first_stage(db, cfg, org_id)
    )
    row: dict[str, Any] = {
        **extra_columns,
        cfg.title_field: body["titulo"],
        "etapa_id": stage["id"],
        "kanban_pos": str(position_on_top(column_cards(db, cfg, org_id, stage["id"]))),
        cfg.status_field: cfg.status_stored("aberto"),
    }
    if body.get("valor") is not None:
        row[cfg.pipeline.value_field] = body["valor"]
    if body.get("responsavel_id") is not None:
        row[cfg.responsavel_field] = body["responsavel_id"]
    if cfg.card_scoped_by_org:
        row["org_id"] = org_id
    if cfg.prepare_create is not None:
        row = cfg.prepare_create(db, FunnelContext(db=db, org_id=org_id, user_id=ctx.user_id), row)
    created = db.table(cfg.pipeline.card_table).insert(row).execute().data or []
    if not created:
        raise InternalError("O card não foi criado.")
    _record_entry(db, cfg, org_id, created[0], stage["id"], ctx.user_id)
    return created[0]


def _update_card(db: Any, cfg: FunnelConfig, org_id: str, card_id: str, values: dict[str, Any]) -> dict:
    query = db.table(cfg.pipeline.card_table).update(values).eq("id", card_id)
    if cfg.card_scoped_by_org:
        query = query.eq("org_id", _require_org(org_id))
    rows = query.execute().data or []
    if not rows:
        raise card_not_found(card_id)
    return rows[0]


def require_open(cfg: FunnelConfig, row: dict) -> None:
    status = cfg.status_canonical(row.get(cfg.status_field))
    if status != "aberto":
        raise card_fechado(status)


def update_card(db: Any, cfg: FunnelConfig, ctx: PipelineContext, card_id: str, body: Mapping[str, Any]) -> tuple[dict, list[str]]:
    """PATCH. Returns `(row, changed_keys)`; an empty patch writes nothing."""
    org_id = _require_org(ctx.org_id)
    current = get_card_row(db, cfg, org_id, card_id)
    values = _map_campos(cfg, body.get("campos"))
    if "titulo" in body:
        values[cfg.title_field] = body["titulo"]
    if "valor" in body and body["valor"] is not None:
        values[cfg.pipeline.value_field] = body["valor"]
    if "responsavel_id" in body:
        values[cfg.responsavel_field] = body["responsavel_id"]
    if not values:
        return current, []
    require_open(cfg, current)
    return _update_card(db, cfg, org_id, card_id, values), sorted(values)


def move(db: Any, cfg: FunnelConfig, ctx: PipelineContext, card_id: str, body: Mapping[str, Any]) -> tuple[dict, bool]:
    """Move a card; returns `(row, changed_stage)`.

    Order of refusals: card exists (404) -> card open (409) -> stage exists in
    THIS tenant (404) and active (409) -> gate (409), skipped on a within-column
    reorder -> write. A stage change without a drop index lands on TOP of the
    destination column (the newest arrival is read first); a same-stage call
    without an index changes nothing.
    """
    org_id = _require_org(ctx.org_id)
    current = get_card_row(db, cfg, org_id, card_id)
    require_open(cfg, current)
    stage = active_stage(db, cfg, org_id, body["para_etapa_id"])
    reordering = str(current.get("etapa_id")) == str(stage["id"])
    if not reordering:
        run_gate(
            cfg,
            FunnelContext(db=db, org_id=org_id, user_id=ctx.user_id, extra=body.get("extra") or {}, to_stage=stage),
            current,
            stage,
        )
    novo_indice = body.get("novo_indice")
    column = column_cards(db, cfg, org_id, stage["id"]) if (novo_indice is not None or not reordering) else []
    if novo_indice is not None:
        nova_posicao = position_for_drop(column, card_id, novo_indice)
    elif not reordering:
        nova_posicao = position_on_top(column)
    else:
        nova_posicao = None
    row = move_card(
        db,
        cfg.pipeline,
        card_id=card_id,
        to_stage_id=stage["id"],
        user_id=str(ctx.user_id) if ctx.user_id else None,  # type: ignore[arg-type]
        nova_posicao=nova_posicao,
        motivo=body.get("motivo"),
        org_id=org_id,
        card_scoped_by_org=cfg.card_scoped_by_org,
    )
    return row, not reordering


def lose_card(db: Any, cfg: FunnelConfig, ctx: PipelineContext, card_id: str, body: Mapping[str, Any]) -> dict:
    org_id = _require_org(ctx.org_id)
    current = get_card_row(db, cfg, org_id, card_id)
    require_open(cfg, current)
    codigo = (body.get("motivo_codigo") or "").strip()
    if not codigo:
        raise motivo_obrigatorio("motivo_codigo")
    reason = cfg.lost_reason(codigo)
    if reason is None:
        raise motivo_desconhecido(codigo)
    texto = (body.get("motivo_texto") or "").strip() or None
    if reason.exige_texto and texto is None:
        raise motivo_obrigatorio("motivo_texto")
    row = _update_card(
        db,
        cfg,
        org_id,
        card_id,
        {
            cfg.status_field: cfg.status_stored("perdido"),
            "motivo_perda_codigo": reason.codigo,
            "motivo_perda": texto,
        },
    )
    _record_event(db, cfg, org_id, current, "perdido", ctx.user_id, f"{reason.label}: {texto}" if texto else reason.label)
    return row


def reopen_card(db: Any, cfg: FunnelConfig, ctx: PipelineContext, card_id: str) -> tuple[dict, bool]:
    """Back to `aberto`, loss fields cleared. Reopening an open card is an
    idempotent no-op (`False` second element) — no write, no log."""
    org_id = _require_org(ctx.org_id)
    current = get_card_row(db, cfg, org_id, card_id)
    if cfg.status_canonical(current.get(cfg.status_field)) == "aberto":
        return current, False
    row = _update_card(
        db,
        cfg,
        org_id,
        card_id,
        {cfg.status_field: cfg.status_stored("aberto"), "motivo_perda_codigo": None, "motivo_perda": None},
    )
    _record_event(db, cfg, org_id, current, "reaberto", ctx.user_id)
    return row, True


def archive_card(db: Any, cfg: FunnelConfig, ctx: PipelineContext, card_id: str) -> dict:
    """Archive an open, won or lost card; archiving an archived one is `card_fechado`."""
    org_id = _require_org(ctx.org_id)
    current = get_card_row(db, cfg, org_id, card_id)
    if cfg.status_canonical(current.get(cfg.status_field)) == "arquivado":
        raise card_fechado("arquivado")
    row = _update_card(db, cfg, org_id, card_id, {cfg.status_field: cfg.status_stored("arquivado")})
    _record_event(db, cfg, org_id, current, "arquivado", ctx.user_id)
    return row


# ───────────────────────────── history ─────────────────────────────


def _encode_cursor(created_at: str, row_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([created_at, row_id]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        created_at, row_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return str(created_at), str(row_id)
    except (binascii.Error, ValueError, TypeError):
        raise FunnelError("cursor_invalido", "Cursor inválido.", 422) from None


def list_movimentos(
    db: Any, cfg: FunnelConfig, org_id: str, card_id: str, *, cursor: str | None = None, limit: int = 50
) -> dict:
    """Newest-first keyset page of a card's stage history (append-only rows)."""
    org_id = _require_org(org_id)
    get_card_row(db, cfg, org_id, card_id)  # 404 for a foreign/missing card
    history = cfg.pipeline.history_table

    def fetch_page(start: int, end: int):
        return (
            db.table(history)
            .select("*")
            .eq("org_id", org_id)
            .eq("pipeline", cfg.pipeline.pipeline)
            .eq("entidade_id", card_id)
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    rows = list(iter_paged_rows(fetch_page, label=f"funnel {cfg.pipeline.pipeline} movimentos"))
    rows.sort(key=lambda r: (str(r.get("created_at") or ""), str(r["id"])), reverse=True)
    total = len(rows)  # BEFORE the cursor cut, like the card-hub timeline
    if cursor:
        at, rid = _decode_cursor(cursor)
        rows = [r for r in rows if (str(r.get("created_at") or ""), str(r["id"])) < (at, rid)]
    page, rest = rows[:limit], rows[limit:]
    labels = {
        str(s["id"]): {"id": str(s["id"]), "label": s.get("label"), "slug": s.get("slug")}
        for s in list_stages(db, cfg.pipeline, incluir_inativas=True, org_id=org_id)
    }
    resolver = cfg.actor_resolver or (cfg.card_hub.actor_resolver if cfg.card_hub else None)
    resolved = resolver({r["responsavel_id"] for r in page if r.get("responsavel_id")}) if resolver else {}
    items = [
        {
            "id": str(r["id"]),
            "kind": _EVENT_KINDS.get(r.get("kind") or "mover", "movimento"),
            "ocorrido_em": r.get("created_at"),
            "de_etapa": labels.get(str(r["de_etapa_id"])) if r.get("de_etapa_id") else None,
            "para_etapa": labels.get(str(r.get("para_etapa_id"))),
            "motivo": r.get("motivo"),
            "ator": _actor(resolved, r.get("responsavel_id"))
            or ({"id": str(r["responsavel_id"]), "nome": None} if r.get("responsavel_id") else None),
            "created_at": r.get("created_at"),
        }
        for r in page
    ]
    next_cursor = _encode_cursor(str(page[-1].get("created_at") or ""), str(page[-1]["id"])) if rest else None
    return {"items": items, "total": total, "next_cursor": next_cursor}


# ───────────────────────────── meta ─────────────────────────────


def meta(cfg: FunnelConfig) -> dict:
    return {
        "pipeline": cfg.pipeline.pipeline,
        "papeis": list(cfg.pipeline.stage_roles),
        "lost_reasons": [
            {"codigo": r.codigo, "label": r.label, "exige_texto": r.exige_texto} for r in cfg.lost_reasons
        ],
        "gates": {
            papel: {"codigo": g.code, "inputs": list(g.inputs), "mensagem": g.mensagem}
            for papel, g in cfg.gates.items()
        },
        "acoes": [
            {"codigo": a.code, "label": a.label, "papeis": list(a.allowed_papeis)} for a in cfg.actions.values()
        ],
        "campos_editaveis": list(cfg.editable_fields),
    }


def run_action(
    db: Any, cfg: FunnelConfig, ctx: PipelineContext, card_id: str, codigo: str, payload: dict
) -> tuple[dict, dict]:
    """Run a product action on an open card; returns `(fresh_row, efeitos)`."""
    org_id = _require_org(ctx.org_id)
    action = cfg.actions.get(codigo)
    if action is None:
        raise acao_desconhecida(codigo)
    current = get_card_row(db, cfg, org_id, card_id)
    require_open(cfg, current)
    if action.allowed_papeis:
        stage = (
            get_stage(db, cfg.pipeline, str(current["etapa_id"]), org_id=org_id) if current.get("etapa_id") else {}
        )
        if stage.get("papel") not in action.allowed_papeis:
            raise acao_desconhecida(codigo)
    efeitos = action.handler(
        db, FunnelContext(db=db, org_id=org_id, user_id=ctx.user_id), current, dict(payload)
    )
    return get_card_row(db, cfg, org_id, card_id), dict(efeitos or {})


__all__ = [
    "LIMITE_CARDS_PADRAO",
    "active_stage",
    "archive_card",
    "attach_owner_names",
    "board",
    "card_dto",
    "column_cards",
    "create_card",
    "get_card_row",
    "lose_card",
    "list_movimentos",
    "meta",
    "move",
    "orphans",
    "reopen_card",
    "require_open",
    "run_action",
    "scope",
    "update_card",
]
