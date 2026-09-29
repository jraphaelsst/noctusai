"""Notas, tags, membros, checklists — the card's non-document state.

Lifted from social-wiring's `app/modules/card_hub/services.py` (lines
271-641 at the time of the move) as a MOVE, not a rewrite: every function body
is the original, with the literal table / FK names replaced by the
`CardHubConfig` fields they were always instances of. Response shapes and
status codes are unchanged; error MESSAGES are NOT — a `NotFoundError` names
a pt-BR resource label ("Nota", "Etiqueta", "Membro", "Checklist", "Item do
checklist", or `cfg.entity_kind` capitalized — never a raw table like
`cliente_notas`, which the user never typed or chose and which social-wiring
and igig both originally raised with verbatim).

`db` is always the product's schema-scoped PostgREST client, passed in —
never resolved here — so one request (and one test) sees one consistent view
of the backend.

Pagination: every unbounded read composes
`noctusai_lib.integrations.persistence.table_reads` (PostgREST's 1 000-row
cap + the `in_()` URL-length limit — see that module).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence.table_reads import (
    actor,
    in_batched_rows,
    paged_rows,
    table,
)
from noctusai_lib.primitives.exceptions import ConflictError, NotFoundError

from .config import CardHubConfig


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entity_label(cfg: CardHubConfig) -> str:
    """The entity's pt-BR display label for a 404 — `cfg.entity_label` when
    set (a machine `entity_kind` like "negocio" isn't the word a person
    reads: "Negócio"), else `cfg.entity_kind`
    capitalized ("cliente" -> "Cliente", "negocio" -> "Negocio", "lead" ->
    "Lead"), or the generic "Registro" when a product leaves `entity_kind`
    blank. Never the raw `entity_table` — a product whose table name isn't
    also its user-facing word (social-wiring: `entity_table="clientes"`,
    plural) must not leak that spelling into a message the user reads."""
    if cfg.entity_label and cfg.entity_label.strip():
        return cfg.entity_label.strip()
    kind = (cfg.entity_kind or "").strip()
    return kind[:1].upper() + kind[1:] if kind else "Registro"


# ─── the entity ──────────────────────────────────────────────────────────


def _default_get_entity(cfg: CardHubConfig, db: Any, org_id: Any, entity_id: Any) -> Optional[dict]:
    rows = (
        table(db, cfg.entity_table)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(entity_id))
        .execute()
    ).data or []
    return rows[0] if rows else None


def ensure_entity(cfg: CardHubConfig, db: Any, org_id: Any, entity_id: Any) -> dict:
    """The entity row, or `NotFoundError(<entity label>, id)` — the 404 every
    per-entity route answers for an id that is not this org's. The label is
    `cfg.entity_kind` (a pt-BR word), never `entity_table` (a DB identifier a
    user never typed or chose — see `_entity_label`)."""
    if cfg.ensure_entity is not None:
        entity = cfg.ensure_entity(db, org_id, entity_id)
    else:
        entity = _default_get_entity(cfg, db, org_id, entity_id)
    if entity is None:
        raise NotFoundError(_entity_label(cfg), str(entity_id))
    return entity


# ─── Notas ───────────────────────────────────────────────────────────────


def _nota_out(row: dict, resolved_actors: dict[str, dict]) -> dict:
    return {
        "id": row["id"],
        "tipo": row.get("tipo", "comentario"),
        "corpo": row["corpo"],
        "autor": actor(resolved_actors, row.get("autor_id")),
        "editado_em": row.get("editado_em"),
        "deleted_at": row.get("deleted_at"),
    }


def create_nota(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    *,
    corpo: str,
    autor_id: Optional[UUID],
    tipo: str = "comentario",
) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    if tipo == "descricao":
        # Application-level check ahead of the DB's partial unique index — a
        # second `descricao` must return a typed 409, never a raw 500 from
        # the constraint.
        existing_descricao = (
            table(db, cfg.tables.notas)
            .select("id")
            .eq("org_id", str(org_id))
            .eq(cfg.entity_fk, str(entity_id))
            .eq("tipo", "descricao")
            .is_("deleted_at", "null")
            .execute()
        ).data or []
        if existing_descricao:
            raise ConflictError(
                f"Este {cfg.entity_kind} já possui uma descrição — edite a existente em vez de criar outra.",
                resource=cfg.tables.notas,
            )
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        cfg.entity_fk: str(entity_id),
        "autor_id": str(autor_id) if autor_id else None,
        "tipo": tipo,
        "corpo": corpo,
        "editado_em": None,
        "deleted_at": None,
        "created_at": now_iso(),
    }
    table(db, cfg.tables.notas).insert(row).execute()
    resolved = cfg.actor_resolver({row["autor_id"]} if row["autor_id"] else set())
    return _nota_out(row, resolved)


def update_nota(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, nota_id: UUID, *, corpo: str) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    existing = (
        table(db, cfg.tables.notas)
        .select("*")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("id", str(nota_id))
        .execute()
    ).data or []
    if not existing or existing[0].get("deleted_at"):
        raise NotFoundError("Nota", str(nota_id))
    updates = {"corpo": corpo, "editado_em": now_iso()}
    table(db, cfg.tables.notas).update(updates).eq("id", str(nota_id)).execute()
    merged = {**existing[0], **updates}
    resolved = cfg.actor_resolver({merged["autor_id"]} if merged.get("autor_id") else set())
    return _nota_out(merged, resolved)


def get_descricao(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> Optional[dict]:
    """The card's single `tipo='descricao'` note — `{id, corpo, editado_em}` or
    `None`. Never the `autor`/`deleted_at` shape comentários carry; the
    description is card state, not a timeline-shaped resource."""
    rows = (
        table(db, cfg.tables.notas)
        .select("id,corpo,editado_em")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("tipo", "descricao")
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    return {"id": row["id"], "corpo": row["corpo"], "editado_em": row.get("editado_em")}


def delete_nota(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, nota_id: UUID) -> None:
    """Soft delete — a deleted note leaves a tombstone, never rewrites history."""
    ensure_entity(cfg, db, org_id, entity_id)
    existing = (
        table(db, cfg.tables.notas)
        .select("id,deleted_at")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("id", str(nota_id))
        .execute()
    ).data or []
    if not existing or existing[0].get("deleted_at"):
        raise NotFoundError("Nota", str(nota_id))
    table(db, cfg.tables.notas).update({"deleted_at": now_iso()}).eq("id", str(nota_id)).execute()


# ─── Tags (org catalogue + per-entity links) ──────────────────────────────


def _tag_out(row: dict) -> dict:
    return {"id": row["id"], "nome": row["nome"], "cor": row["cor"]}


def list_tags(cfg: CardHubConfig, db: Any, org_id: UUID) -> dict:
    rows = paged_rows(db, cfg.tables.tags, org_id, order_col="nome")
    items = [_tag_out(r) for r in rows]
    return {"items": items, "total": len(items)}


def create_tag(cfg: CardHubConfig, db: Any, org_id: UUID, *, nome: str, cor: str) -> dict:
    existing = (
        table(db, cfg.tables.tags)
        .select("id")
        .eq("org_id", str(org_id))
        .ilike("nome", nome)
        .execute()
    ).data or []
    if existing:
        raise ConflictError(f"Tag '{nome}' já existe", resource=cfg.tables.tags)
    row = {"id": str(uuid4()), "org_id": str(org_id), "nome": nome, "cor": cor, "created_at": now_iso()}
    table(db, cfg.tables.tags).insert(row).execute()
    return _tag_out(row)


def update_tag(cfg: CardHubConfig, db: Any, org_id: UUID, tag_id: UUID, *, nome: Optional[str], cor: Optional[str]) -> dict:
    existing = (
        table(db, cfg.tables.tags).select("*").eq("org_id", str(org_id)).eq("id", str(tag_id)).execute()
    ).data or []
    if not existing:
        raise NotFoundError("Etiqueta", str(tag_id))
    updates: dict = {}
    if nome is not None:
        dupes = (
            table(db, cfg.tables.tags)
            .select("id")
            .eq("org_id", str(org_id))
            .ilike("nome", nome)
            .execute()
        ).data or []
        if any(d["id"] != str(tag_id) for d in dupes):
            raise ConflictError(f"Tag '{nome}' já existe", resource=cfg.tables.tags)
        updates["nome"] = nome
    if cor is not None:
        updates["cor"] = cor
    if updates:
        table(db, cfg.tables.tags).update(updates).eq("id", str(tag_id)).execute()
    return _tag_out({**existing[0], **updates})


def delete_tag(cfg: CardHubConfig, db: Any, org_id: UUID, tag_id: UUID) -> None:
    """Deleting a catalogue tag unlinks it from every card, explicitly — the
    act-not-warn convention; the DB's ON DELETE CASCADE is the backstop."""
    existing = (
        table(db, cfg.tables.tags).select("id").eq("org_id", str(org_id)).eq("id", str(tag_id)).execute()
    ).data or []
    if not existing:
        raise NotFoundError("Etiqueta", str(tag_id))
    table(db, cfg.tables.tag_links).delete().eq("org_id", str(org_id)).eq("tag_id", str(tag_id)).execute()
    table(db, cfg.tables.tags).delete().eq("id", str(tag_id)).execute()


def set_entity_tags(
    cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, *, tag_ids: list[UUID], criado_por: Optional[UUID]
) -> dict:
    """Full replace — the PUT body IS the card's tag set."""
    ensure_entity(cfg, db, org_id, entity_id)
    valid_tags = in_batched_rows(db, cfg.tables.tags, org_id, "id", [str(t) for t in tag_ids])
    valid_ids = {row["id"] for row in valid_tags}
    unknown = {str(t) for t in tag_ids} - valid_ids
    if unknown:
        raise NotFoundError("Etiqueta", ",".join(sorted(unknown)))

    table(db, cfg.tables.tag_links).delete().eq("org_id", str(org_id)).eq(cfg.entity_fk, str(entity_id)).execute()
    for tag_id in valid_ids:
        table(db, cfg.tables.tag_links).insert(
            {
                cfg.entity_fk: str(entity_id),
                "tag_id": tag_id,
                "org_id": str(org_id),
                "criado_por": str(criado_por) if criado_por else None,
                "created_at": now_iso(),
            }
        ).execute()
    return get_entity_tags(cfg, db, org_id, entity_id)


def get_entity_tags(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> dict:
    # The link table has NO `id` column — its PK is the composite
    # `(<entity_fk>, tag_id)`. `tag_id` is the pager's dedup/order key since
    # the entity is already pinned by `eq_filters`.
    links = paged_rows(
        db,
        cfg.tables.tag_links,
        org_id,
        eq_filters={cfg.entity_fk: str(entity_id)},
        order_col="tag_id",
        id_key="tag_id",
    )
    tag_ids = [link["tag_id"] for link in links]
    tags = in_batched_rows(db, cfg.tables.tags, org_id, "id", tag_ids)
    items = [_tag_out(t) for t in tags]
    items.sort(key=lambda t: t["nome"])
    return {"items": items, "total": len(items)}


# ─── Membros ─────────────────────────────────────────────────────────────


def _membro_out(cfg: CardHubConfig, row: dict) -> dict:
    src = cfg.member_source
    return {"id": row["id"], "nome": row[src.label], "cor": row.get(src.cor) if src.cor else None}


def get_membros(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    src = cfg.member_source
    # The link table has NO `id` column either — the member FK is the key.
    links = paged_rows(
        db,
        cfg.tables.membros,
        org_id,
        eq_filters={cfg.entity_fk: str(entity_id)},
        order_col=src.fk,
        id_key=src.fk,
    )
    member_ids = [link[src.fk] for link in links]
    members = in_batched_rows(db, src.table, org_id, "id", member_ids)
    items = [_membro_out(cfg, m) for m in members]
    items.sort(key=lambda m: m["nome"])
    return {"items": items, "total": len(items)}


def set_membros(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, *, member_ids: list[UUID]) -> dict:
    """Full replace. An unknown member id is a 404 naming "Membro" — never a
    silently-dropped assignment, and never the raw member table."""
    ensure_entity(cfg, db, org_id, entity_id)
    src = cfg.member_source
    valid_members = in_batched_rows(db, src.table, org_id, "id", [str(c) for c in member_ids])
    valid_ids = {row["id"] for row in valid_members}
    unknown = {str(c) for c in member_ids} - valid_ids
    if unknown:
        raise NotFoundError("Membro", ",".join(sorted(unknown)))

    table(db, cfg.tables.membros).delete().eq("org_id", str(org_id)).eq(cfg.entity_fk, str(entity_id)).execute()
    for member_id in valid_ids:
        table(db, cfg.tables.membros).insert(
            {
                cfg.entity_fk: str(entity_id),
                src.fk: member_id,
                "org_id": str(org_id),
                "created_at": now_iso(),
            }
        ).execute()
    return get_membros(cfg, db, org_id, entity_id)


# ─── Lembretes (ad-hoc, `lembretes_crud` opt-in) ────────────────────────

#: Brazil abolished DST in 2019 — América/São Paulo is a fixed UTC-3 offset
#: going forward, so a NAIVE `dispara_em` (no offset in the request) can be
#: anchored without a tz database lookup.
_SAO_PAULO = timezone(timedelta(hours=-3))


def _normalize_dispara_em(value: datetime) -> str:
    """UTC ISO, always — a naive `dispara_em` is assumed to already be
    América/São Paulo wall-clock (the "Lembretes" subpage's picker, never the
    server's own locale); an offset-aware one is trusted as given. Storing
    one consistent representation is what makes both the scheduler's
    `dispara_em <= now` drain and this module's own chronological `list`
    correct string comparisons, not just correct TIMESTAMPTZ comparisons."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=_SAO_PAULO)
    return aware.astimezone(timezone.utc).isoformat()


def _lembrete_out(row: dict, responsaveis: dict[str, dict]) -> dict:
    responsavel_id = row.get("responsavel_id")
    return {
        "id": row["id"],
        "titulo": row.get("titulo") or "",
        "dispara_em": row["dispara_em"],
        "responsavel": responsaveis.get(responsavel_id) if responsavel_id else None,
        # `concluido` mirrors `enviado_em`: set either by the scheduler's
        # delivery drain OR directly by a user "mark done" action — from the
        # card's point of view both mean "this reminder no longer needs
        # attention", and the scheduler's own pending query
        # (`enviado_em IS NULL`) already treats a user-completed row as done.
        "concluido": row.get("enviado_em") is not None,
        "concluido_em": row.get("enviado_em"),
        "created_at": row.get("created_at"),
    }


def _resolve_responsaveis(cfg: CardHubConfig, db: Any, org_id: UUID, rows: list[dict]) -> dict[str, dict]:
    ids = sorted({r["responsavel_id"] for r in rows if r.get("responsavel_id")})
    if not ids:
        return {}
    src = cfg.member_source
    found = in_batched_rows(db, src.table, org_id, "id", ids)
    return {m["id"]: _membro_out(cfg, m) for m in found}


def _require_lembrete(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, lembrete_id: UUID) -> dict:
    rows = (
        table(db, cfg.tables.lembretes)
        .select("*")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("id", str(lembrete_id))
        .execute()
    ).data or []
    if not rows:
        # "Lembrete" — a pt-BR user-facing label, not `cfg.tables.lembretes`
        # (`cliente_lembretes`/`negocio_lembretes`): the raw table name in a
        # 404 detail is an internal leak the user never typed or chose.
        raise NotFoundError("Lembrete", str(lembrete_id))
    return rows[0]


def _require_responsavel(cfg: CardHubConfig, db: Any, org_id: UUID, responsavel_id: UUID) -> None:
    src = cfg.member_source
    found = in_batched_rows(db, src.table, org_id, "id", [str(responsavel_id)])
    if not found:
        raise NotFoundError("Membro", str(responsavel_id))


def list_lembretes(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> dict:
    """Every ad-hoc reminder on the card, pending and done, oldest fire
    first. A CANCELLED row (the generic scope-cancel mechanic
    `lembretes.cancelar_lembretes` uses for the Datas-driven single fire) is
    superseded and never shown here — this CRUD never produces one itself."""
    ensure_entity(cfg, db, org_id, entity_id)
    rows = paged_rows(
        db, cfg.tables.lembretes, org_id, eq_filters={cfg.entity_fk: str(entity_id)}, order_col="dispara_em"
    )
    # `dispara_em` is stored UTC-normalized (`_normalize_dispara_em`), so a
    # plain string sort IS a chronological sort — sorted explicitly rather
    # than trusting `.order()`, which a fake / a read-replica lag could both
    # leave unsorted.
    rows = sorted((r for r in rows if not r.get("cancelado_em")), key=lambda r: r["dispara_em"])
    responsaveis = _resolve_responsaveis(cfg, db, org_id, rows)
    items = [_lembrete_out(r, responsaveis) for r in rows]
    return {"items": items, "total": len(items)}


def create_lembrete(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    *,
    titulo: str,
    dispara_em: datetime,
    responsavel_id: Optional[UUID] = None,
) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    if responsavel_id is not None:
        _require_responsavel(cfg, db, org_id, responsavel_id)
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        cfg.entity_fk: str(entity_id),
        "titulo": titulo,
        "dispara_em": _normalize_dispara_em(dispara_em),
        "enviado_em": None,
        "cancelado_em": None,
        "responsavel_id": str(responsavel_id) if responsavel_id else None,
        "destinatarios": [],
        "created_at": now_iso(),
    }
    table(db, cfg.tables.lembretes).insert(row).execute()
    return _lembrete_out(row, _resolve_responsaveis(cfg, db, org_id, [row]))


def update_lembrete(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    lembrete_id: UUID,
    *,
    titulo: Any = ...,
    dispara_em: Any = ...,
    responsavel_id: Any = ...,
    concluido: Any = ...,
) -> dict:
    """`...` (not sent) on any kwarg means "leave alone" — the route passes
    only the fields `model_fields_set` actually carried, so
    `responsavel_id=None` (sent explicitly) clears the assignment while an
    absent `responsavel_id` leaves it untouched."""
    ensure_entity(cfg, db, org_id, entity_id)
    existing = _require_lembrete(cfg, db, org_id, entity_id, lembrete_id)
    updates: dict = {}
    if titulo is not ...:
        updates["titulo"] = titulo
    if dispara_em is not ...:
        updates["dispara_em"] = _normalize_dispara_em(dispara_em)
    if responsavel_id is not ...:
        if responsavel_id is not None:
            _require_responsavel(cfg, db, org_id, responsavel_id)
            updates["responsavel_id"] = str(responsavel_id)
        else:
            updates["responsavel_id"] = None
    if concluido is not ...:
        updates["enviado_em"] = now_iso() if concluido else None
    if updates:
        table(db, cfg.tables.lembretes).update(updates).eq("id", str(lembrete_id)).execute()
    merged = {**existing, **updates}
    return _lembrete_out(merged, _resolve_responsaveis(cfg, db, org_id, [merged]))


def delete_lembrete(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, lembrete_id: UUID) -> None:
    ensure_entity(cfg, db, org_id, entity_id)
    _require_lembrete(cfg, db, org_id, entity_id, lembrete_id)
    table(db, cfg.tables.lembretes).delete().eq("id", str(lembrete_id)).execute()


# ─── Checklists ──────────────────────────────────────────────────────────


def _checklist_item_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "texto": row["texto"],
        "concluido": row["concluido"],
        "concluido_em": row.get("concluido_em"),
        "concluido_por": row.get("concluido_por"),
        "posicao": row["posicao"],
    }


def _checklist_out(row: dict, itens: list[dict]) -> dict:
    total = len(itens)
    concluidos = sum(1 for i in itens if i.get("concluido"))
    return {
        "id": row["id"],
        "titulo": row["titulo"],
        "posicao": row["posicao"],
        "origem": row["origem"],
        "etapa_id": row.get("etapa_id"),
        "itens": [_checklist_item_out(i) for i in sorted(itens, key=lambda x: x["posicao"])],
        "total_itens": total,
        "concluidos": concluidos,
    }


def list_checklists(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> dict:
    """Every checklist on the card, with its items and SERVED progress — the
    browser never counts."""
    ensure_entity(cfg, db, org_id, entity_id)
    checklists = paged_rows(
        db, cfg.tables.checklists, org_id, eq_filters={cfg.entity_fk: str(entity_id)}, order_col="posicao"
    )
    checklist_ids = [c["id"] for c in checklists]
    itens = in_batched_rows(db, cfg.tables.checklist_itens, org_id, "checklist_id", checklist_ids)
    itens_by_checklist: dict[str, list[dict]] = {}
    for item in itens:
        itens_by_checklist.setdefault(item["checklist_id"], []).append(item)
    out = [_checklist_out(c, itens_by_checklist.get(c["id"], [])) for c in checklists]
    return {"items": out, "total": len(out)}


def create_checklist(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, *, titulo: str) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    existing = (
        table(db, cfg.tables.checklists)
        .select("posicao")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .execute()
    ).data or []
    next_pos = (max((c["posicao"] for c in existing), default=-1)) + 1
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        cfg.entity_fk: str(entity_id),
        "titulo": titulo,
        "posicao": next_pos,
        "origem": "ad_hoc",
        "etapa_id": None,
        "created_at": now_iso(),
    }
    table(db, cfg.tables.checklists).insert(row).execute()
    return _checklist_out(row, [])


def _require_checklist(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, checklist_id: UUID) -> dict:
    rows = (
        table(db, cfg.tables.checklists)
        .select("*")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("id", str(checklist_id))
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("Checklist", str(checklist_id))
    return rows[0]


def update_checklist(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    checklist_id: UUID,
    *,
    titulo: Optional[str],
    posicao: Optional[int],
) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    existing = _require_checklist(cfg, db, org_id, entity_id, checklist_id)
    updates: dict = {}
    if titulo is not None:
        updates["titulo"] = titulo
    if posicao is not None:
        updates["posicao"] = posicao
    if updates:
        table(db, cfg.tables.checklists).update(updates).eq("id", str(checklist_id)).execute()
    merged = {**existing, **updates}
    itens = (
        table(db, cfg.tables.checklist_itens)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("checklist_id", str(checklist_id))
        .execute()
    ).data or []
    return _checklist_out(merged, itens)


def delete_checklist(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, checklist_id: UUID) -> None:
    ensure_entity(cfg, db, org_id, entity_id)
    _require_checklist(cfg, db, org_id, entity_id, checklist_id)
    table(db, cfg.tables.checklist_itens).delete().eq("org_id", str(org_id)).eq("checklist_id", str(checklist_id)).execute()
    table(db, cfg.tables.checklists).delete().eq("id", str(checklist_id)).execute()


def create_checklist_item(
    cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, checklist_id: UUID, *, texto: str
) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    _require_checklist(cfg, db, org_id, entity_id, checklist_id)
    existing = (
        table(db, cfg.tables.checklist_itens)
        .select("posicao")
        .eq("org_id", str(org_id))
        .eq("checklist_id", str(checklist_id))
        .execute()
    ).data or []
    next_pos = (max((i["posicao"] for i in existing), default=-1)) + 1
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "checklist_id": str(checklist_id),
        "texto": texto,
        "concluido": False,
        "concluido_em": None,
        "concluido_por": None,
        "posicao": next_pos,
        "created_at": now_iso(),
    }
    table(db, cfg.tables.checklist_itens).insert(row).execute()
    return _checklist_item_out(row)


def update_checklist_item(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    checklist_id: UUID,
    item_id: UUID,
    *,
    texto: Optional[str],
    concluido: Optional[bool],
    posicao: Optional[int],
    concluido_por: Optional[UUID],
) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    _require_checklist(cfg, db, org_id, entity_id, checklist_id)
    existing = (
        table(db, cfg.tables.checklist_itens)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("checklist_id", str(checklist_id))
        .eq("id", str(item_id))
        .execute()
    ).data or []
    if not existing:
        raise NotFoundError("Item do checklist", str(item_id))

    updates: dict = {}
    if texto is not None:
        updates["texto"] = texto
    if posicao is not None:
        updates["posicao"] = posicao
    if concluido is not None:
        updates["concluido"] = concluido
        updates["concluido_em"] = now_iso() if concluido else None
        updates["concluido_por"] = str(concluido_por) if (concluido and concluido_por) else None
    if updates:
        table(db, cfg.tables.checklist_itens).update(updates).eq("id", str(item_id)).execute()
    return _checklist_item_out({**existing[0], **updates})


def delete_checklist_item(
    cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, checklist_id: UUID, item_id: UUID
) -> None:
    ensure_entity(cfg, db, org_id, entity_id)
    _require_checklist(cfg, db, org_id, entity_id, checklist_id)
    existing = (
        table(db, cfg.tables.checklist_itens)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("checklist_id", str(checklist_id))
        .eq("id", str(item_id))
        .execute()
    ).data or []
    if not existing:
        raise NotFoundError("Item do checklist", str(item_id))
    table(db, cfg.tables.checklist_itens).delete().eq("id", str(item_id)).execute()


__all__ = [
    "create_checklist",
    "create_checklist_item",
    "create_nota",
    "create_tag",
    "delete_checklist",
    "delete_checklist_item",
    "delete_nota",
    "delete_tag",
    "ensure_entity",
    "get_descricao",
    "get_entity_tags",
    "get_membros",
    "list_checklists",
    "list_tags",
    "now_iso",
    "set_entity_tags",
    "set_membros",
    "update_checklist",
    "update_checklist_item",
    "update_nota",
    "update_tag",
]
