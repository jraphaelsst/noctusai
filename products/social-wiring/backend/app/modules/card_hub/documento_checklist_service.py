"""The permanent document checklist — the six things every new client owes us.

WHAT IS CANONICAL AND WHAT IS DATA
----------------------------------
:data:`ITENS` is the checklist. It is identical for every client by definition
("always gonna be needed from leads when they become clients"), so it lives
here, once, and every card renders the same list. The database stores only
which items a given client has ticked (`067_documento_checklist.sql`).

That split is the whole design. Materialising six rows per client would make
the DEFINITION per-client data, and then adding a seventh field would need a
backfill across every existing client — with cards created before and after
showing different checklists until it finished.

`key` is the stable identity and `label` is presentation. Renaming a label is
free; changing a key orphans its ticks, so keys are append-only in practice.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from app.modules.card_hub.services import _now, _t, ensure_cliente

TABLE = "cliente_documento_checklist"

#: The six the user named, in the order they asked for them. Order is the
#: collection order, not alphabetical — it is the sequence you actually ask a
#: person for their details in.
ITENS: tuple[dict[str, str], ...] = (
    {"key": "nome_completo", "label": "Nome Completo"},
    {"key": "email", "label": "Email"},
    {"key": "data_nascimento", "label": "Data de Nascimento"},
    {"key": "genero", "label": "Gênero"},
    {"key": "rg", "label": "RG"},
    {"key": "cpf", "label": "CPF"},
)

ITEM_KEYS = tuple(item["key"] for item in ITENS)


def _out(item: dict[str, str], row: Optional[dict]) -> dict:
    """One checklist line: the canonical definition + this client's tick.

    A missing row is not an error and not "unknown" — it means not done. That
    is why the definition drives the output and the row only decorates it.
    """
    return {
        "key": item["key"],
        "label": item["label"],
        "concluido": bool(row["concluido"]) if row else False,
        "concluido_em": row.get("concluido_em") if row else None,
        "concluido_por": row.get("concluido_por") if row else None,
    }


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Every canonical item, with this client's ticks applied.

    Always returns all six, in `ITENS` order, whether or not any row exists —
    the list is the contract, the rows are just state.
    """
    ensure_cliente(client, org_id, cliente_id)
    res = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    )
    by_key = {r["item_key"]: r for r in (res.data or [])}
    itens = [_out(item, by_key.get(item["key"])) for item in ITENS]
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
    concluido: bool,
    user_id: Optional[UUID] = None,
) -> dict:
    """Tick or untick one item. Upsert on `(cliente_id, item_key)`.

    Raises `KeyError` for a key outside :data:`ITENS` — the caller turns that
    into a 422. Accepting an arbitrary key would let a typo write a row that
    nothing ever reads, which is a silent no-op wearing a 200.
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
        "concluido": concluido,
        # Cleared on untick: a `concluido_em` left behind on an unticked item
        # reads as "done, at some point", which is the opposite of what the
        # untick just said.
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
    return _out(item, merged)


__all__ = ["ITENS", "ITEM_KEYS", "TABLE", "listar", "marcar"]
