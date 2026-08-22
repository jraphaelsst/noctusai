"""The permanent document checklist — DERIVED completeness, human override.

WHAT IS CANONICAL, WHAT IS DERIVED, AND WHAT IS DATA
----------------------------------------------------
:data:`ITENS` is the checklist. It is identical for every client by definition
("always gonna be needed from leads when they become clients"), so it lives
here, once, and every card renders the same list.

A tick is **derived**, not stored: an item is done when the thing it asks for
is actually present — the cliente column is filled in, or a document of that
type has been uploaded. The database stores only a human OVERRIDE
(`concluido_manual`, migration 068), for the cases where a person knows
something the record cannot show.

🔴 WHY DERIVED RATHER THAN RECOMPUTED ON WRITE
----------------------------------------------
The alternative is a hook that recomputes and stores the six ticks whenever a
cliente or a document changes. It loses for a structural reason: leads enter
this product from Meta leadgen, OLX, ImovelWeb, Vista, the XLSX importer, the
manual lead form, and the merge/undo path in `clientes_service`. Every one of
those is a separate write site that has to remember to call the hook, and the
one that forgets fails *silently* — a stale checklist looks exactly like a
client who has not sent their documents yet.

Derivation has no such interval. There is no moment at which a tick is allowed
to disagree with the data, so no write path can desynchronise it, including
paths written after this file. It is the same reasoning migration 067 used to
keep the checklist DEFINITION in code, carried one column further.

It also makes a whole class of state unrepresentable: a stored `true` sitting
next to an empty column — "done" for a field nobody ever filled in.

`key` is the stable identity and `label` is presentation. Renaming a label is
free; changing a key orphans its overrides, so keys are append-only in practice.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from app.modules.card_hub.services import _now, _t, ensure_cliente

TABLE = "cliente_documento_checklist"
CLIENTES_TABLE = "clientes"
DOCUMENTOS_TABLE = "cliente_documentos"

#: The six the user named, in the order they asked for them — the sequence you
#: actually ask a person for their details in, not alphabetical.
#:
#: Each item declares HOW it is satisfied, which is what makes the derivation a
#: property of the definition rather than a parallel lookup table someone has
#: to keep in step:
#:
#: - ``campo``     — done when that `clientes` column is non-empty.
#: - ``documento`` — done when a non-deleted `cliente_documentos` row of that
#:                   `tipo_documento` exists.
ITENS: tuple[dict[str, str], ...] = (
    {"key": "nome_completo", "label": "Nome Completo", "campo": "nome_completo"},
    {"key": "email", "label": "Email", "campo": "email"},
    {"key": "data_nascimento", "label": "Data de Nascimento", "campo": "data_nascimento"},
    {"key": "genero", "label": "Gênero", "campo": "genero"},
    {"key": "rg", "label": "RG", "documento": "rg"},
    {"key": "cpf", "label": "CPF", "documento": "cpf"},
)

ITEM_KEYS = tuple(item["key"] for item in ITENS)

#: Columns the derivation reads. Selected explicitly rather than `*` so adding
#: a column to `clientes` cannot silently widen what this module pulls.
_CLIENTE_COLUNAS = tuple(i["campo"] for i in ITENS if "campo" in i)


def _preenchido(value: Any) -> bool:
    """Is this column value present for checklist purposes?

    Whitespace-only is empty. A name of `"   "` satisfies a NOT NULL check and
    satisfies nobody else, and treating it as done would tick an item for a
    value no human would accept.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def derivar(
    cliente: Optional[dict],
    tipos_documento_presentes: frozenset[str],
) -> dict[str, bool]:
    """The rule, as a pure function: item key → is it satisfied?

    Pure and dependency-free on purpose. This is the part that decides whether
    a card claims a client's paperwork is complete, so it is testable without a
    database, an org, or an HTTP request.
    """
    cliente = cliente or {}
    out: dict[str, bool] = {}
    for item in ITENS:
        if "campo" in item:
            out[item["key"]] = _preenchido(cliente.get(item["campo"]))
        else:
            out[item["key"]] = item["documento"] in tipos_documento_presentes
    return out


def _out(item: dict[str, str], derivado: bool, override: Optional[dict]) -> dict:
    """One checklist line: the canonical definition + derivation + override.

    `concluido` stays the single boolean the UI reads, so the response shape is
    unchanged for existing consumers. `origem` is additive and says WHY, which
    is what lets the card explain a tick the user did not make — and, just as
    importantly, a tick that is stuck on because someone forced it.
    """
    manual = override.get("concluido_manual") if override else None
    concluido = derivado if manual is None else bool(manual)
    return {
        "key": item["key"],
        "label": item["label"],
        "concluido": concluido,
        "origem": "derivado" if manual is None else "manual",
        "derivado": derivado,
        "concluido_em": override.get("concluido_em") if override else None,
        "concluido_por": override.get("concluido_por") if override else None,
    }


def _tipos_presentes(client: Any, org_id: UUID, cliente_id: UUID) -> frozenset[str]:
    """Document types this client has actually uploaded.

    Soft-deleted rows are excluded: a document the client asked us to delete
    cannot go on satisfying a requirement it no longer backs.
    """
    res = (
        _t(client, DOCUMENTOS_TABLE)
        .select("tipo_documento,deleted_at")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    )
    return frozenset(
        r["tipo_documento"]
        for r in (res.data or [])
        if r.get("deleted_at") is None
    )


def _cliente_row(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[dict]:
    res = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(_CLIENTE_COLUNAS))
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Every canonical item, derived, with any human override applied.

    Always returns all six, in `ITENS` order, whether or not any override row
    exists — the list is the contract, the rows are just opinions about it.
    """
    ensure_cliente(client, org_id, cliente_id)

    cliente = _cliente_row(client, org_id, cliente_id)
    tipos = _tipos_presentes(client, org_id, cliente_id)
    derivado = derivar(cliente, tipos)

    res = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    )
    by_key = {r["item_key"]: r for r in (res.data or [])}

    itens = [_out(item, derivado[item["key"]], by_key.get(item["key"])) for item in ITENS]
    return {
        "items": itens,
        "total": len(itens),
        "concluidos": sum(1 for i in itens if i["concluido"]),
    }


def marcar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    item_key: str,
    *,
    concluido: Optional[bool],
    user_id: Optional[UUID] = None,
) -> dict:
    """Set or clear the human override on one item. Upsert on `(cliente, item)`.

    `concluido=None` CLEARS the override and hands the item back to the
    derivation. Without that, the first person to touch an item would pin it
    forever — including pinning a `false` onto a client who later supplies the
    very data the item asks for, which is the stale-checklist failure this
    module exists to prevent, reintroduced by hand.

    Raises `KeyError` for a key outside :data:`ITENS` — the caller turns that
    into a 422. Accepting an arbitrary key would let a typo write a row that
    nothing ever reads: a silent no-op wearing a 200.
    """
    if item_key not in ITEM_KEYS:
        raise KeyError(item_key)

    ensure_cliente(client, org_id, cliente_id)
    now = _now()
    existing = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("item_key", item_key)
        .execute()
    )
    rows = existing.data or []

    updates = {
        "concluido_manual": concluido,
        # Cleared unless this is an affirmative tick: a `concluido_em` left
        # behind on an untick or a cleared override reads as "done, at some
        # point", which is the opposite of what just happened.
        "concluido_em": now if concluido else None,
        "concluido_por": str(user_id) if (concluido and user_id) else None,
        "updated_at": now,
    }

    if rows:
        _t(client, TABLE).update(updates).eq("id", rows[0]["id"]).execute()
        merged = {**rows[0], **updates}
    else:
        merged = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "item_key": item_key,
            "created_at": now,
            **updates,
        }
        _t(client, TABLE).insert(merged).execute()

    item = next(i for i in ITENS if i["key"] == item_key)
    derivado = derivar(
        _cliente_row(client, org_id, cliente_id),
        _tipos_presentes(client, org_id, cliente_id),
    )
    return _out(item, derivado[item["key"]], merged)


__all__ = [
    "ITENS",
    "ITEM_KEYS",
    "TABLE",
    "derivar",
    "listar",
    "marcar",
]
