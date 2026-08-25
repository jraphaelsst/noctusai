"""Business logic for the `card_hub` module — everything in contract §2/§3
EXCEPT documents (see `documentos_service.py` — LGPD-complete storage is
its own file, ruling S2).

`client` is always the `social_wiring`-scoped admin client from
`app.modules.card_hub.deps.get_card_hub_client` — every function here
accepts it as a parameter rather than resolving its own, so a single
request (and a single test) sees one consistent view of the mock/real
backend (see that dependency's docstring for why a second independently-
derived `.schema()` call would NOT see the same data).

Pagination: every unbounded read composes
`noctusai_lib.integrations.persistence.iter_paged_rows` — see that
module's docstring for the two hazards it closes (PostgREST's 1 000-row
cap, and a pager that never terminates if the backend disregards
`range()`). `.in_()` filters over `_IN_FILTER_BATCH` are chunked first —
PostgREST rides `in_()` values in the URL query string, and an unbatched
~1 000-item list is a bare 400.

Those read helpers no longer live here. This module used to keep its own
copy of `_batched` (a fork of `clientes_service`'s, and it said so); a
third consumer arrived and they moved to `app.services.table_reads`. The
`_t` / `_batched` / `_paged_rows` / `_resolve_actors` / `_actor` names
below are aliases over the canonical definitions, so every call site in
this file reads unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
)

from app.dependencies import get_core_client
from app.services import clientes_service as clientes_svc
from app.services import table_reads

_PAGE_SIZE = table_reads.PAGE_SIZE
_IN_FILTER_BATCH = table_reads.IN_FILTER_BATCH


# ─── shared helpers ─────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── PostgREST read helpers — canonical definitions in `table_reads` ────
#
# These were defined here, and `_batched` was already a copy of
# `clientes_service`'s. `imovel_hub` made a third consumer, so they moved to
# `app.services.table_reads` (see that module's header for why THESE
# helpers in particular are worth one home: each one's real body is a
# defence against a limit that is invisible at the call site).
#
# The private names survive as aliases so every existing call site in this
# module reads exactly as it did.

_t = table_reads.table
_batched = table_reads.batched
_paged_rows = table_reads.paged_rows
_in_batched_rows = table_reads.in_batched_rows
_resolve_actors = table_reads.resolve_actors
_actor = table_reads.actor


def ensure_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    cliente = clientes_svc.get_cliente(client, org_id, cliente_id)
    if cliente is None:
        raise NotFoundError("clientes", str(cliente_id))
    return cliente


# ─── Notas ──────────────────────────────────────────────────────────────


# ─── Which atendimento does this belong to? ─────────────────────────────────
#
# Lives HERE rather than in the module that first needed it. It arrived with
# agendamentos, and compradores (migration 073) is the second caller asking the
# identical question — "this card is a person, but the thing I am attaching
# belongs to a DEAL; which one?". Two copies of that answer would disagree
# about archived and collapsed rows, which is the subtle half.
#
# `AmbiguousAtendimento` moves with it: the resolver's refusal is part of the
# resolver, and a caller that imports one without the other cannot handle what
# it raises. `agendamentos_service` re-exports both, so its existing importers
# and tests are untouched.


class AmbiguousAtendimento(AppException):
    """The person has more than one open atendimento, so "the" one is a guess.

    Raised rather than picking the newest: an appointment filed against the
    wrong deal renders identically on the card and is wrong in the one place
    D17 says matters — the history.

    An `AppException`, NOT a bare exception the router converts: the seed's
    handler renders `details` into the error envelope, so the candidate ids
    survive to the client. A `raise HTTPException(detail={...})` does NOT —
    the seed's HTTPException handler stringifies the detail into `message`,
    which is how the first version of this shipped a 409 the UI could not read.
    """

    def __init__(self, candidates: list[str]):
        self.candidates = candidates
        super().__init__(
            code="AMBIGUOUS_ATENDIMENTO",
            message=(
                "Este cliente tem mais de um atendimento aberto — escolha a qual "
                "o agendamento pertence."
                if candidates
                else "Este cliente não tem atendimento aberto — informe atendimento_id."
            ),
            status_code=409,
            details={"atendimentos": candidates},
        )


def _atendimentos_do_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    return _paged_rows(client, "atendimentos", org_id, eq_filters={"cliente_id": str(cliente_id)})


def resolve_atendimento_id(
    client: Any, org_id: UUID, cliente_id: UUID, explicit: Optional[UUID] = None
) -> str:
    """Which atendimento a new appointment belongs to.

    `explicit` wins and is validated against this cliente — accepting an
    unvalidated id would let a caller file an appointment onto someone else's
    deal. Otherwise: the single open atendimento, or `AmbiguousAtendimento`.
    """
    rows = _atendimentos_do_cliente(client, org_id, cliente_id)
    if explicit is not None:
        if not any(str(r["id"]) == str(explicit) for r in rows):
            raise NotFoundError("atendimentos", str(explicit))
        return str(explicit)

    abertos = [
        r for r in rows
        if r.get("substituida_por") is None and not r.get("arquivado", False)
    ]
    if len(abertos) == 1:
        return str(abertos[0]["id"])
    if not abertos:
        # Every atendimento is closed/archived. Refuse rather than resurrect
        # one — "which closed deal is this visit for?" is the user's call.
        raise AmbiguousAtendimento([])
    raise AmbiguousAtendimento([str(r["id"]) for r in abertos])


def _nota_out(row: dict, resolved_actors: dict[str, dict]) -> dict:
    return {
        "id": row["id"],
        "tipo": row.get("tipo", "comentario"),
        "corpo": row["corpo"],
        "autor": _actor(resolved_actors, row.get("autor_id")),
        "editado_em": row.get("editado_em"),
        "deleted_at": row.get("deleted_at"),
    }


def create_nota(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    corpo: str,
    autor_id: Optional[UUID],
    tipo: str = "comentario",
) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    if tipo == "descricao":
        # Application-level check ahead of the DB's partial unique index
        # (migration 056) — a second `descricao` must return a typed
        # 409, never a raw 500 from the constraint (contract correction).
        existing_descricao = (
            _t(client, "cliente_notas")
            .select("id")
            .eq("org_id", str(org_id))
            .eq("cliente_id", str(cliente_id))
            .eq("tipo", "descricao")
            .is_("deleted_at", "null")
            .execute()
        ).data or []
        if existing_descricao:
            raise ConflictError(
                "Este cliente já possui uma descrição — edite a existente em vez de criar outra.",
                resource="cliente_notas",
            )
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "cliente_id": str(cliente_id),
        "autor_id": str(autor_id) if autor_id else None,
        "tipo": tipo,
        "corpo": corpo,
        "editado_em": None,
        "deleted_at": None,
        "created_at": _now(),
    }
    _t(client, "cliente_notas").insert(row).execute()
    resolved = _resolve_actors({row["autor_id"]} if row["autor_id"] else set())
    return _nota_out(row, resolved)


def update_nota(client: Any, org_id: UUID, cliente_id: UUID, nota_id: UUID, *, corpo: str) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    existing = (
        _t(client, "cliente_notas")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(nota_id))
        .execute()
    ).data or []
    if not existing or existing[0].get("deleted_at"):
        raise NotFoundError("cliente_notas", str(nota_id))
    updates = {"corpo": corpo, "editado_em": _now()}
    _t(client, "cliente_notas").update(updates).eq("id", str(nota_id)).execute()
    merged = {**existing[0], **updates}
    resolved = _resolve_actors({merged["autor_id"]} if merged.get("autor_id") else set())
    return _nota_out(merged, resolved)


def get_descricao(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[dict]:
    """The card's single `tipo='descricao'` note (contract correction) —
    `{id, corpo, editado_em}` or `None`. Never the `autor`/`deleted_at`
    shape `_nota_out` returns for comentários; the description is card
    state, not a timeline-shaped resource."""
    rows = (
        _t(client, "cliente_notas")
        .select("id,corpo,editado_em")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("tipo", "descricao")
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    return {"id": row["id"], "corpo": row["corpo"], "editado_em": row.get("editado_em")}


def delete_nota(client: Any, org_id: UUID, cliente_id: UUID, nota_id: UUID) -> None:
    ensure_cliente(client, org_id, cliente_id)
    existing = (
        _t(client, "cliente_notas")
        .select("id,deleted_at")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(nota_id))
        .execute()
    ).data or []
    if not existing or existing[0].get("deleted_at"):
        raise NotFoundError("cliente_notas", str(nota_id))
    _t(client, "cliente_notas").update({"deleted_at": _now()}).eq("id", str(nota_id)).execute()


# ─── Tags ───────────────────────────────────────────────────────────────


def _tag_out(row: dict) -> dict:
    return {"id": row["id"], "nome": row["nome"], "cor": row["cor"]}


def list_tags(client: Any, org_id: UUID) -> dict:
    rows = _paged_rows(client, "cliente_tags", org_id, order_col="nome")
    items = [_tag_out(r) for r in rows]
    return {"items": items, "total": len(items)}


def create_tag(client: Any, org_id: UUID, *, nome: str, cor: str) -> dict:
    existing = (
        _t(client, "cliente_tags")
        .select("id")
        .eq("org_id", str(org_id))
        .ilike("nome", nome)
        .execute()
    ).data or []
    if existing:
        raise ConflictError(f"Tag '{nome}' já existe", resource="cliente_tags")
    row = {"id": str(uuid4()), "org_id": str(org_id), "nome": nome, "cor": cor, "created_at": _now()}
    _t(client, "cliente_tags").insert(row).execute()
    return _tag_out(row)


def update_tag(client: Any, org_id: UUID, tag_id: UUID, *, nome: Optional[str], cor: Optional[str]) -> dict:
    existing = (
        _t(client, "cliente_tags").select("*").eq("org_id", str(org_id)).eq("id", str(tag_id)).execute()
    ).data or []
    if not existing:
        raise NotFoundError("cliente_tags", str(tag_id))
    updates: dict = {}
    if nome is not None:
        dupes = (
            _t(client, "cliente_tags")
            .select("id")
            .eq("org_id", str(org_id))
            .ilike("nome", nome)
            .execute()
        ).data or []
        if any(d["id"] != str(tag_id) for d in dupes):
            raise ConflictError(f"Tag '{nome}' já existe", resource="cliente_tags")
        updates["nome"] = nome
    if cor is not None:
        updates["cor"] = cor
    if updates:
        _t(client, "cliente_tags").update(updates).eq("id", str(tag_id)).execute()
    return _tag_out({**existing[0], **updates})


def delete_tag(client: Any, org_id: UUID, tag_id: UUID) -> None:
    existing = (
        _t(client, "cliente_tags").select("id").eq("org_id", str(org_id)).eq("id", str(tag_id)).execute()
    ).data or []
    if not existing:
        raise NotFoundError("cliente_tags", str(tag_id))
    # Refuse-then-unlink, never a silent orphan (contract §3): the DELETE
    # itself also removes every link, but a caller relying on "delete
    # refuses if in use" would be surprised by a silent cascade — this
    # product's convention (see `clientes_router.py`'s own
    # `manter_separados`/merge shapes) is to act, not warn, so the
    # cascade below IS the intended behaviour, not a shortcut around it.
    _t(client, "cliente_tag_links").delete().eq("org_id", str(org_id)).eq("tag_id", str(tag_id)).execute()
    _t(client, "cliente_tags").delete().eq("id", str(tag_id)).execute()


def set_cliente_tags(client: Any, org_id: UUID, cliente_id: UUID, *, tag_ids: list[UUID], criado_por: Optional[UUID]) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    valid_tags = _in_batched_rows(client, "cliente_tags", org_id, "id", [str(t) for t in tag_ids])
    valid_ids = {row["id"] for row in valid_tags}
    unknown = {str(t) for t in tag_ids} - valid_ids
    if unknown:
        raise NotFoundError("cliente_tags", ",".join(sorted(unknown)))

    _t(client, "cliente_tag_links").delete().eq("org_id", str(org_id)).eq("cliente_id", str(cliente_id)).execute()
    for tag_id in valid_ids:
        _t(client, "cliente_tag_links").insert(
            {
                "cliente_id": str(cliente_id),
                "tag_id": tag_id,
                "org_id": str(org_id),
                "criado_por": str(criado_por) if criado_por else None,
                "created_at": _now(),
            }
        ).execute()
    return get_cliente_tags(client, org_id, cliente_id)


def get_cliente_tags(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    # `cliente_tag_links` has NO `id` column — its PK is the composite
    # `(cliente_id, tag_id)` (migration 056). `tag_id` is the pager's
    # dedup/order key here since `cliente_id` is already pinned by the
    # `eq_filters` below, making `tag_id` unique within this result set.
    links = _paged_rows(
        client,
        "cliente_tag_links",
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        order_col="tag_id",
        id_key="tag_id",
    )
    tag_ids = [link["tag_id"] for link in links]
    tags = _in_batched_rows(client, "cliente_tags", org_id, "id", tag_ids)
    items = [_tag_out(t) for t in tags]
    items.sort(key=lambda t: t["nome"])
    return {"items": items, "total": len(items)}


# ─── Membros ────────────────────────────────────────────────────────────


def _membro_out(row: dict) -> dict:
    return {"id": row["id"], "nome": row["nome"], "cor": row.get("cor")}


def get_membros(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    # `cliente_membros` has NO `id` column either — see `get_cliente_tags`'s
    # identical note; `lead_corretor_id` is the pager's key here.
    links = _paged_rows(
        client,
        "cliente_membros",
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        order_col="lead_corretor_id",
        id_key="lead_corretor_id",
    )
    corretor_ids = [link["lead_corretor_id"] for link in links]
    corretores = _in_batched_rows(client, "lead_corretores", org_id, "id", corretor_ids)
    items = [_membro_out(c) for c in corretores]
    items.sort(key=lambda m: m["nome"])
    return {"items": items, "total": len(items)}


def set_membros(client: Any, org_id: UUID, cliente_id: UUID, *, lead_corretor_ids: list[UUID]) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    valid_corretores = _in_batched_rows(
        client, "lead_corretores", org_id, "id", [str(c) for c in lead_corretor_ids]
    )
    valid_ids = {row["id"] for row in valid_corretores}
    unknown = {str(c) for c in lead_corretor_ids} - valid_ids
    if unknown:
        raise NotFoundError("lead_corretores", ",".join(sorted(unknown)))

    _t(client, "cliente_membros").delete().eq("org_id", str(org_id)).eq("cliente_id", str(cliente_id)).execute()
    for corretor_id in valid_ids:
        _t(client, "cliente_membros").insert(
            {
                "cliente_id": str(cliente_id),
                "lead_corretor_id": corretor_id,
                "org_id": str(org_id),
                "created_at": _now(),
            }
        ).execute()
    return get_membros(client, org_id, cliente_id)


# ─── Datas + lembretes ──────────────────────────────────────────────────


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


def _checklist_item_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "texto": row["texto"],
        "concluido": row["concluido"],
        "concluido_em": row.get("concluido_em"),
        "concluido_por": row.get("concluido_por"),
        "posicao": row["posicao"],
    }


def list_checklists(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    checklists = _paged_rows(
        client, "cliente_checklists", org_id, eq_filters={"cliente_id": str(cliente_id)}, order_col="posicao"
    )
    checklist_ids = [c["id"] for c in checklists]
    itens = _in_batched_rows(client, "cliente_checklist_itens", org_id, "checklist_id", checklist_ids)
    itens_by_checklist: dict[str, list[dict]] = {}
    for item in itens:
        itens_by_checklist.setdefault(item["checklist_id"], []).append(item)
    out = [_checklist_out(c, itens_by_checklist.get(c["id"], [])) for c in checklists]
    return {"items": out, "total": len(out)}


def create_checklist(client: Any, org_id: UUID, cliente_id: UUID, *, titulo: str) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    existing = (
        _t(client, "cliente_checklists")
        .select("posicao")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []
    next_pos = (max((c["posicao"] for c in existing), default=-1)) + 1
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "cliente_id": str(cliente_id),
        "titulo": titulo,
        "posicao": next_pos,
        "origem": "ad_hoc",
        "etapa_id": None,
        "created_at": _now(),
    }
    _t(client, "cliente_checklists").insert(row).execute()
    return _checklist_out(row, [])


def update_checklist(
    client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID, *, titulo: Optional[str], posicao: Optional[int]
) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    existing = _require_checklist(client, org_id, cliente_id, checklist_id)
    updates: dict = {}
    if titulo is not None:
        updates["titulo"] = titulo
    if posicao is not None:
        updates["posicao"] = posicao
    if updates:
        _t(client, "cliente_checklists").update(updates).eq("id", str(checklist_id)).execute()
    merged = {**existing, **updates}
    itens = (
        _t(client, "cliente_checklist_itens").select("*").eq("org_id", str(org_id)).eq("checklist_id", str(checklist_id)).execute()
    ).data or []
    return _checklist_out(merged, itens)


def delete_checklist(client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID) -> None:
    ensure_cliente(client, org_id, cliente_id)
    _require_checklist(client, org_id, cliente_id, checklist_id)
    _t(client, "cliente_checklist_itens").delete().eq("org_id", str(org_id)).eq("checklist_id", str(checklist_id)).execute()
    _t(client, "cliente_checklists").delete().eq("id", str(checklist_id)).execute()


def _require_checklist(client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID) -> dict:
    rows = (
        _t(client, "cliente_checklists")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(checklist_id))
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("cliente_checklists", str(checklist_id))
    return rows[0]


def create_checklist_item(
    client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID, *, texto: str
) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    _require_checklist(client, org_id, cliente_id, checklist_id)
    existing = (
        _t(client, "cliente_checklist_itens")
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
        "created_at": _now(),
    }
    _t(client, "cliente_checklist_itens").insert(row).execute()
    return _checklist_item_out(row)


def update_checklist_item(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    checklist_id: UUID,
    item_id: UUID,
    *,
    texto: Optional[str],
    concluido: Optional[bool],
    posicao: Optional[int],
    concluido_por: Optional[UUID],
) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    _require_checklist(client, org_id, cliente_id, checklist_id)
    existing = (
        _t(client, "cliente_checklist_itens")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("checklist_id", str(checklist_id))
        .eq("id", str(item_id))
        .execute()
    ).data or []
    if not existing:
        raise NotFoundError("cliente_checklist_itens", str(item_id))

    updates: dict = {}
    if texto is not None:
        updates["texto"] = texto
    if posicao is not None:
        updates["posicao"] = posicao
    if concluido is not None:
        updates["concluido"] = concluido
        updates["concluido_em"] = _now() if concluido else None
        updates["concluido_por"] = str(concluido_por) if (concluido and concluido_por) else None
    if updates:
        _t(client, "cliente_checklist_itens").update(updates).eq("id", str(item_id)).execute()
    return _checklist_item_out({**existing[0], **updates})


def delete_checklist_item(
    client: Any, org_id: UUID, cliente_id: UUID, checklist_id: UUID, item_id: UUID
) -> None:
    ensure_cliente(client, org_id, cliente_id)
    _require_checklist(client, org_id, cliente_id, checklist_id)
    existing = (
        _t(client, "cliente_checklist_itens")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("checklist_id", str(checklist_id))
        .eq("id", str(item_id))
        .execute()
    ).data or []
    if not existing:
        raise NotFoundError("cliente_checklist_itens", str(item_id))
    _t(client, "cliente_checklist_itens").delete().eq("id", str(item_id)).execute()


__all__ = [
    "create_checklist",
    "create_checklist_item",
    "create_nota",
    "create_tag",
    "delete_checklist",
    "delete_checklist_item",
    "delete_nota",
    "delete_tag",
    "ensure_cliente",
    "get_cliente_tags",
    "get_descricao",
    "get_membros",
    "list_checklists",
    "list_tags",
    "set_cliente_tags",
    "set_membros",
    "update_checklist",
    "update_checklist_item",
    "update_nota",
    "update_tag",
]
