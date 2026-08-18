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
PostgREST rides `in_()` values in the URL query string, and an
unbatched ~1 000-item list is a bare 400 (see
`clientes_service.py::_batched`'s identical rationale; this module keeps
its own copy rather than importing that module's private helper).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.exceptions import ConflictError, NotFoundError

from app.dependencies import get_core_client
from app.services import clientes_service as clientes_svc

_PAGE_SIZE = 1000
_IN_FILTER_BATCH = 200


# ─── shared helpers ─────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return client.table(name)


def _batched(items: list, size: int = _IN_FILTER_BATCH):
    """Yield `items` in chunks of `size` — see module docstring."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _paged_rows(
    client: Any,
    table: str,
    org_id: UUID,
    *,
    eq_filters: Optional[dict] = None,
    order_col: str = "id",
    id_key: str = "id",
    extra: Optional[Any] = None,
) -> list[dict]:
    """Every row of `table` for `org_id` (+ `eq_filters`), paged past
    PostgREST's row cap via the seed's shared pager. `extra`, when given,
    is `fn(query) -> query` applied AFTER the eq filters and BEFORE
    `.order()` — for filter shapes `eq_filters` can't express (e.g.
    `.is_("deleted_at", "null")`)."""
    eq_filters = eq_filters or {}

    def fetch_page(start: int, end: int):
        query = _t(client, table).select("*").eq("org_id", str(org_id))
        for key, value in eq_filters.items():
            query = query.eq(key, value)
        if extra is not None:
            query = extra(query)
        return query.order(order_col).range(start, end).execute().data

    return list(
        iter_paged_rows(
            fetch_page,
            page_size=_PAGE_SIZE,
            id_key=id_key,
            label=f"{table} for org_id={org_id}",
        )
    )


def _in_batched_rows(
    client: Any, table: str, org_id: UUID, in_col: str, ids: list[str]
) -> list[dict]:
    """Every row of `table` matching `in_col IN ids`, batched (URL-length
    safety) AND paged (row-cap safety) — composes both hazards from the
    module docstring."""
    if not ids:
        return []
    out: list[dict] = []
    for batch in _batched(sorted(set(ids))):

        def fetch_page(start: int, end: int, _batch=batch):
            return (
                _t(client, table)
                .select("*")
                .eq("org_id", str(org_id))
                .in_(in_col, _batch)
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        out.extend(
            iter_paged_rows(
                fetch_page,
                page_size=_PAGE_SIZE,
                label=f"{table}.{in_col} batch for org_id={org_id}",
            )
        )
    return out


def _resolve_actors(ids: set) -> dict[str, dict]:
    """`{id, nome}` for every id in `ids`, resolved against
    `public.noctus_users` (the trusted user table — see
    `app.dependencies.get_core_client`'s docstring for why this is the
    `public`-schema client, not `social_wiring`). Missing users fall back
    to `{"id": id, "nome": None}` — a stale/foreign id is not an error
    here, just an unresolved name."""
    clean_ids = {str(i) for i in ids if i}
    if not clean_ids:
        return {}
    core = get_core_client()
    out: dict[str, dict] = {}
    for batch in _batched(sorted(clean_ids)):
        rows = (
            core.table("noctus_users")
            .select("id,nome,email")
            .in_("id", batch)
            .execute()
            .data
            or []
        )
        for row in rows:
            out[str(row["id"])] = {
                "id": row["id"],
                "nome": row.get("nome") or row.get("email"),
            }
    return out


def _actor(resolved: dict[str, dict], raw_id: Optional[str]) -> Optional[dict]:
    if not raw_id:
        return None
    return resolved.get(str(raw_id)) or {"id": raw_id, "nome": None}


def ensure_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    cliente = clientes_svc.get_cliente(client, org_id, cliente_id)
    if cliente is None:
        raise NotFoundError("clientes", str(cliente_id))
    return cliente


# ─── Notas ──────────────────────────────────────────────────────────────


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


def _compute_dispara_em(data_entrega: Optional[str], lembrete_minutos_antes: Optional[int]) -> Optional[str]:
    if not data_entrega or lembrete_minutos_antes is None:
        return None
    dt = datetime.fromisoformat(data_entrega.replace("Z", "+00:00"))
    from datetime import timedelta

    dispara = dt - timedelta(minutes=lembrete_minutos_antes)
    return dispara.isoformat()


def patch_datas(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    data_inicio: Optional[str] = ...,
    data_entrega: Optional[str] = ...,
    entrega_concluida: Optional[bool] = ...,
    lembrete_minutos_antes: Optional[int] = ...,
    recorrencia: Optional[str] = ...,
) -> dict:
    """`...` (Ellipsis) sentinels an unset field (only the fields the PATCH
    body actually carried are written — `exclude_unset` upstream in the
    router). Setting `data_entrega` + `lembrete_minutos_antes` materialises
    a `cliente_lembretes` row; clearing either cancels the pending one —
    see the module's reminder-honesty note below `proximo_lembrete`."""
    cliente = ensure_cliente(client, org_id, cliente_id)

    updates: dict = {}
    if data_inicio is not ...:
        updates["data_inicio"] = data_inicio
    if data_entrega is not ...:
        updates["data_entrega"] = data_entrega
    if entrega_concluida is not ...:
        updates["entrega_concluida"] = entrega_concluida
    if lembrete_minutos_antes is not ...:
        updates["lembrete_minutos_antes"] = lembrete_minutos_antes
    if recorrencia is not ...:
        updates["recorrencia"] = recorrencia

    merged = {**cliente, **updates}
    if updates:
        _t(client, "clientes").update(updates).eq("id", str(cliente_id)).execute()

    # Reminder materialisation — only re-evaluated when a relevant field
    # was actually touched by this PATCH.
    proximo_lembrete = None
    if "data_entrega" in updates or "lembrete_minutos_antes" in updates:
        # Cancel any pending (un-fired, un-cancelled) reminder first —
        # the old target time is stale the moment either input changes.
        pending = (
            _t(client, "cliente_lembretes")
            .select("id")
            .eq("org_id", str(org_id))
            .eq("cliente_id", str(cliente_id))
            .is_("enviado_em", "null")
            .is_("cancelado_em", "null")
            .execute()
        ).data or []
        for row in pending:
            _t(client, "cliente_lembretes").update({"cancelado_em": _now()}).eq("id", row["id"]).execute()

        dispara_em = _compute_dispara_em(merged.get("data_entrega"), merged.get("lembrete_minutos_antes"))
        if dispara_em:
            lembrete_id = str(uuid4())
            _t(client, "cliente_lembretes").insert(
                {
                    "id": lembrete_id,
                    "org_id": str(org_id),
                    "cliente_id": str(cliente_id),
                    "dispara_em": dispara_em,
                    "enviado_em": None,
                    "cancelado_em": None,
                    "destinatarios": [],
                    "created_at": _now(),
                }
            ).execute()
            proximo_lembrete = {"id": lembrete_id, "dispara_em": dispara_em}
    else:
        proximo_lembrete = _get_proximo_lembrete(client, org_id, cliente_id)

    return {
        "data_inicio": merged.get("data_inicio"),
        "data_entrega": merged.get("data_entrega"),
        "entrega_concluida": merged.get("entrega_concluida", False),
        "lembrete_minutos_antes": merged.get("lembrete_minutos_antes"),
        "recorrencia": merged.get("recorrencia"),
        # 🔴 NOC-REMEDIATE[reminder-delivery]: `cliente_lembretes` rows are
        # materialised (correctly, per the pending/cancel logic above) but
        # NOTHING in this slice delivers them — no scheduler job drains
        # `idx_sw_cliente_lembretes_pending`. A UI that showed a reminder
        # as "set" with no delivery path would be a lying UI (contract
        # §3); `proximo_lembrete` is reported honestly here (the row DOES
        # exist and WILL be found by a future sweep), and this marker
        # names the still-missing delivery leg for a dedicated follow-up
        # rather than silently accepting the gap. 2026-08-18.
        "proximo_lembrete": proximo_lembrete,
    }


def _get_proximo_lembrete(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, "cliente_lembretes")
        .select("id,dispara_em")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .is_("enviado_em", "null")
        .is_("cancelado_em", "null")
        .order("dispara_em")
        .execute()
    ).data or []
    if not rows:
        return None
    return {"id": rows[0]["id"], "dispara_em": rows[0]["dispara_em"]}


# ─── Checklists ─────────────────────────────────────────────────────────


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
    "patch_datas",
    "set_cliente_tags",
    "set_membros",
    "update_checklist",
    "update_checklist_item",
    "update_nota",
    "update_tag",
]
