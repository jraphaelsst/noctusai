"""The other people party to an atendimento (migration 073).

WHY THIS MODULE IS SO SMALL
---------------------------
Because a comprador is a `clientes` row, and everything a comprador needs
already works on a `cliente_id`.

Luciano buys a flat; Luciano is married; the agency's contract needs his wife's
identity data and her documents to exactly the same standard as his. She is not
a lesser kind of record — she needs the same eight checklist items, the same
RG/CPF uploads, the same extraction, the same access log and the same LGPD
retention. So she IS a cliente, and this module only records the EDGE: which
people are party to which atendimento, and in what role.

That is the whole design, and it is what keeps this file under 200 lines
instead of forking `documento_checklist_service`, `documentos_service` and
`identidade_extracao_service` for person #2.

THE TITULAR IS NOT IN HERE
--------------------------
`atendimentos.cliente_id` already names them. A second row asserting the same
thing is a second truth, and the two disagree the first time either moves. So
this table holds the ADDITIONAL parties and the card renders the titular first
from the atendimento itself — see the migration's header for the full argument.

LINKING VS CREATING
-------------------
Both are supported, and the distinction matters. A spouse who is already a lead
in this org must be LINKED, not copied — copying her would give the org two
records for one person, each accumulating half of her documents. `adicionar`
therefore takes either an existing `cliente_id` or the fields to create one,
never both.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    _now,
    _t,
    ensure_cliente,
    resolve_atendimento_id,
)

TABLE = "atendimento_partes"
CLIENTES_TABLE = "clientes"

#: The roles a party can hold, as code rather than a schema CHECK — same
#: reasoning as `documento_checklist_service.ITENS`. The business learns new
#: words (procurador, fiador, anuente) faster than a migration cycle, and the
#: constraint is enforced here regardless.
#:
#: `comprador` is the default and, today, effectively the only one the UI
#: offers: the user's framing is that the titular IS a comprador and adding a
#: party adds ANOTHER comprador — a spouse who is equally a buyer, not a
#: subordinate attached to one.
#:
#: 🔴 ROLES ARE NOW PER SIDE (migration 098), and the two tuples below are not
#: the same list twice. `conjuge` and `procurador` appear in both because they
#: are the same relationship to a DIFFERENT principal — which is precisely why
#: `lado` is its own column rather than a prefix on these strings; 098's header
#: makes the full argument.
#:
#: What differs is the head of each list. The buyer side leads with
#: `comprador`; the seller side leads with `proprietario`, because the person a
#: deal is made with IS the owner — that is "the vendedor is the property
#: owner" stated as data. `inventariante` exists only on the seller side (an
#: estate sells, it never buys) and `fiador` only on the buyer's, for the
#: mirror reason.
LADOS: tuple[str, ...] = ("comprador", "vendedor")
LADO_PADRAO = "comprador"

PAPEIS_POR_LADO: dict[str, tuple[str, ...]] = {
    "comprador": ("comprador", "conjuge", "fiador", "procurador", "outro"),
    "vendedor": ("proprietario", "conjuge", "procurador", "inventariante", "outro"),
}

PAPEL_PADRAO_POR_LADO: dict[str, str] = {
    "comprador": "comprador",
    "vendedor": "proprietario",
}

#: How `clientes.vinculo_origem` records who introduced this person. Migration
#: 074 left that column TEXT rather than a CHECK precisely so a new
#: relationship path would need no migration; the seller side is that path
#: arriving.
VINCULO_ORIGEM_POR_LADO: dict[str, str] = {
    "comprador": "comprador_atendimento",
    "vendedor": "vendedor_atendimento",
}

#: Kept under its original name for callers that predate `lado`. It is the
#: buyer side's tuple, so an unmigrated call behaves exactly as it always did.
PAPEIS: tuple[str, ...] = PAPEIS_POR_LADO["comprador"]

PAPEL_PADRAO = "comprador"


def normalizar_lado(lado: Optional[str]) -> str:
    """Validate a side, defaulting to the buyer's.

    Defaulting rather than requiring, for the same reason migration 098's
    column defaults: every caller written before the seller side existed means
    the buyer side, and every row written before it is one.
    """
    valor = (lado or LADO_PADRAO).strip().lower()
    if valor not in LADOS:
        raise ValidationError_(
            f"Lado inválido: {lado}. Esperado um de {', '.join(LADOS)}."
        )
    return valor


_FIELDS = (
    "id", "atendimento_id", "cliente_id", "lado", "papel", "ordem",
    "observacao", "created_at",
)

#: Columns of the joined person the card needs to render a party row without a
#: second round-trip. Explicit rather than `*` so widening `clientes` cannot
#: silently widen what this endpoint returns — it is personal data.
_CLIENTE_RESUMO = ("id", "nome", "nome_completo", "celular", "email")


def _out(row: dict, cliente: Optional[dict] = None) -> dict:
    out = {k: row.get(k) for k in _FIELDS}
    out["cliente"] = (
        {k: cliente.get(k) for k in _CLIENTE_RESUMO} if cliente else None
    )
    return out


def _clientes_por_id(client: Any, org_id: UUID, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    res = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(_CLIENTE_RESUMO))
        .eq("org_id", str(org_id))
        .in_("id", ids)
        .execute()
    )
    return {str(r["id"]): r for r in (res.data or [])}


def listar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID] = None,
    lado: Optional[str] = None,
) -> dict:
    """Every additional party on this card's atendimento, in display order.

    `lado` selects the side — one call per panel, so the Comprador and
    Vendedor tabs are the same code reading different rows rather than two
    implementations that drift.

    Returns an EMPTY list — never an error — when the person has no atendimento
    the resolver can name. The card asks this on every open, and a 409 for "no
    open deal" would break a panel that has nothing to show anyway. Creating is
    where ambiguity has to be resolved, because that is where a wrong guess
    writes something.
    """
    lado_alvo = normalizar_lado(lado)
    ensure_cliente(client, org_id, cliente_id)
    try:
        alvo = resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)
    except AmbiguousAtendimento:
        # Caught NARROWLY, and only here. "No open atendimento" and "more than
        # one" both mean this read has no single deal to report on, and the
        # panel has nothing to show either way. A bare `except Exception` would
        # also swallow a NotFoundError for an explicit `atendimento_id` that
        # belongs to someone else — turning an authorization-shaped refusal
        # into an empty list, which is the silent-fallback shape.
        return {"items": [], "total": 0, "atendimento_id": None, "lado": lado_alvo}

    res = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", alvo)
        .eq("lado", lado_alvo)
        .execute()
    )
    rows = sorted(
        res.data or [],
        key=lambda r: (r.get("ordem") or 0, str(r.get("created_at") or "")),
    )
    clientes = _clientes_por_id(client, org_id, [str(r["cliente_id"]) for r in rows])
    itens = [_out(r, clientes.get(str(r["cliente_id"]))) for r in rows]
    return {
        "items": itens,
        "total": len(itens),
        "atendimento_id": alvo,
        "lado": lado_alvo,
    }


def adicionar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    parte_cliente_id: Optional[UUID] = None,
    nome: Optional[str] = None,
    celular: Optional[str] = None,
    papel: Optional[str] = None,
    observacao: Optional[str] = None,
    atendimento_id: Optional[UUID] = None,
    lado: Optional[str] = None,
    user_id: Optional[UUID] = None,
) -> dict:
    """Attach another person to this card's atendimento.

    Either `parte_cliente_id` (link someone who already exists) or `nome`
    (create them) — never both, and never neither. Accepting both would make
    the caller's intent unknowable when they disagree; accepting neither would
    write a party with nobody in it.
    """
    lado_alvo = normalizar_lado(lado)
    papeis = PAPEIS_POR_LADO[lado_alvo]
    papel = papel or PAPEL_PADRAO_POR_LADO[lado_alvo]
    if papel not in papeis:
        raise ValidationError_(
            f"Papel inválido para o lado {lado_alvo}: {papel}. "
            f"Esperado um de {', '.join(papeis)}."
        )
    if (parte_cliente_id is None) == (nome is None):
        raise ValidationError_(
            "Informe cliente_id (para vincular alguém que já existe) OU nome "
            "(para cadastrar), nunca ambos."
        )

    ensure_cliente(client, org_id, cliente_id)
    alvo = resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)

    if parte_cliente_id is not None:
        # Validated against THIS org — an unvalidated id would attach a
        # stranger's record to this deal.
        ensure_cliente(client, org_id, parte_cliente_id)
        novo_cliente_id = str(parte_cliente_id)
        # 🔴 BUYER-SIDE ONLY. The titular is named by `atendimentos.cliente_id`
        # and is a buyer by construction, so re-adding them there is a
        # duplicate. On the SELLER side there is no titular column at all
        # (migration 098's header explains the asymmetry) — but the same
        # person still cannot be on both sides of one deal, and that is what
        # `uq_sw_atendimento_partes_pessoa` enforces at the database rather
        # than here.
        if lado_alvo == "comprador" and novo_cliente_id == str(cliente_id):
            raise ValidationError_(
                "O titular já é parte deste atendimento — adicione outra pessoa."
            )
        # A linked person gets the relationship recorded too, not just a
        # created one — "any link to another cliente" is the ask, and a spouse
        # who happened to already be a lead is no less related for it.
        _vincular(client, org_id, novo_cliente_id, cliente_id, lado_alvo)
    else:
        novo_cliente_id = _criar_cliente(
            client,
            org_id,
            nome=nome,
            celular=celular,
            vinculado_a=cliente_id,
            lado=lado_alvo,
        )

    ja = (
        _t(client, TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", alvo)
        .eq("cliente_id", novo_cliente_id)
        .execute()
    )
    if ja.data:
        # A double-click, not an intent. Reported rather than silently ignored:
        # a 201 for a row that was not created teaches the UI to trust a
        # response that is not true.
        raise ConflictError("Esta pessoa já é parte deste atendimento.")

    # Ordem is per SIDE: each panel numbers its own people from zero, so the
    # first vendedor is ordem 0 (the proprietário) rather than continuing the
    # buyer list's count.
    atual = (
        _t(client, TABLE)
        .select("ordem")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", alvo)
        .eq("lado", lado_alvo)
        .execute()
    )
    proxima_ordem = max(
        [int(r.get("ordem") or 0) for r in (atual.data or [])], default=-1
    ) + 1

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": alvo,
        "cliente_id": novo_cliente_id,
        "lado": lado_alvo,
        "papel": papel,
        "ordem": proxima_ordem,
        "observacao": observacao,
        "created_at": _now(),
        "created_by": str(user_id) if user_id else None,
    }
    _t(client, TABLE).insert(row).execute()
    clientes = _clientes_por_id(client, org_id, [novo_cliente_id])
    return _out(row, clientes.get(novo_cliente_id))


def _vincular(
    client: Any,
    org_id: UUID,
    cliente_id: str,
    titular_id: UUID,
    lado: str = LADO_PADRAO,
) -> None:
    """Record who introduced this person — FIRST-WRITER-WINS (migration 074).

    Only written when the column is empty, so someone who was already a lead in
    their own right, or who is a party to an earlier deal, keeps their original
    introducer. Overwriting would make the field mean "the most recent deal
    they appeared in", which is what `atendimento_partes` already says and says
    better.
    """
    if str(cliente_id) == str(titular_id):
        return
    rows = (
        _t(client, CLIENTES_TABLE)
        .select("id,vinculado_a_cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("vinculado_a_cliente_id"):
        return
    _t(client, CLIENTES_TABLE).update({
        "vinculado_a_cliente_id": str(titular_id),
        "vinculo_origem": VINCULO_ORIGEM_POR_LADO[lado],
        "vinculado_em": _now(),
    }).eq("id", str(cliente_id)).eq("org_id", str(org_id)).execute()


def _criar_cliente(
    client: Any,
    org_id: UUID,
    *,
    nome: Optional[str],
    celular: Optional[str],
    vinculado_a: Optional[UUID] = None,
    lado: str = LADO_PADRAO,
) -> str:
    """A minimal cliente for a party who is not yet in the system.

    `nome_completo` is set, not just `nome`. The name typed into "Adicionar
    Comprador" is an operator deliberately entering someone's name for a
    contract — that is exactly what `nome_completo` means, and writing it to
    `nome` alone would leave the person's own checklist showing "Nome Completo"
    unticked the moment they were created.

    No `chave_canonica`: this person has not contacted us through any channel,
    so they have no canonical key, and inventing one from the phone would enter
    them into the dedup space as if they had.

    🔴 `vinculado_a_cliente_id` is set at CREATION (migration 074), not left
    for a later pass. Without it this row is indistinguishable from a lead who
    walked in off the street — no channel, no key, no touches, no campaign — and
    `atendimento_partes` only explains her for as long as the atendimento
    exists, because it cascades on its delete.
    """
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "nome": nome,
        "nome_completo": nome,
        "celular": celular,
        "chave_canonica": None,
        "chave_tipo": None,
        "identidade_incerta": False,
        "ativo": True,
        "vinculado_a_cliente_id": str(vinculado_a) if vinculado_a else None,
        "vinculo_origem": VINCULO_ORIGEM_POR_LADO[lado] if vinculado_a else None,
        "vinculado_em": _now() if vinculado_a else None,
        "created_at": _now(),
    }
    _t(client, CLIENTES_TABLE).insert(row).execute()
    return row["id"]


def remover(client: Any, org_id: UUID, cliente_id: UUID, parte_id: UUID) -> None:
    """Detach a party. The PERSON is not deleted.

    Removing someone from a deal is not the same as erasing them, and their
    documents belong to them rather than to this atendimento. Cascading to the
    `clientes` row would destroy uploads the org may be legally required to
    retain (`cliente_documento_tipos.retencao_dias`), on a click that reads as
    "they're not part of this purchase after all".
    """
    ensure_cliente(client, org_id, cliente_id)
    rows = (
        _t(client, TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("id", str(parte_id))
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(TABLE, str(parte_id))
    _t(client, TABLE).delete().eq("id", str(parte_id)).eq(
        "org_id", str(org_id)
    ).execute()


__all__ = [
    "PAPEIS",
    "PAPEL_PADRAO",
    "TABLE",
    "adicionar",
    "listar",
    "remover",
]
