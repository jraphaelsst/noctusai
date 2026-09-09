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
    _atendimentos_do_cliente,
    _now,
    _t,
    ensure_cliente,
    resolve_atendimento_id,
)

TABLE = "atendimento_partes"
CLIENTES_TABLE = "clientes"
ATENDIMENTOS_TABLE = "atendimentos"

#: The one `papel` that is not merely a label. Every other role describes what
#: a person does on this deal; `conjuge` asserts a fact about two people that
#: outlives it — and CC art. 1.647 makes it decide who has to sign. Named
#: rather than spelled inline so the link rule below and the vocabularies above
#: cannot drift apart on a typo.
PAPEL_CONJUGE = "conjuge"

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


def atualizar_papel(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    parte_id: UUID,
    *,
    papel: str,
) -> dict:
    """Change what a party IS to their side — and, for a spouse, WHO to.

    🔴 WHY THIS EXISTS AT ALL, WHEN `adicionar` ALREADY TAKES A `papel`
    -------------------------------------------------------------------
    Because nothing ever sent one. `AdicionarCompradorDialog` asks for the two
    fields `pipeline.stage_gate.CAMPOS_OBRIGATORIOS` requires and nothing else,
    on purpose — the moment a party is added is the moment the operator knows
    LEAST about them. So the side's default was applied and could never be
    corrected: every buyer-side party was a `comprador` and every seller-side
    one a `proprietario`, forever, through an API that had listed five roles
    per side since migration 098.

    That is not a cosmetic gap. A married seller's spouse must consent to the
    sale (CC art. 1.647, and migration 097's header states the consequence): a
    contract cannot ask who has to sign if no row can say `conjuge`.

    🔴 THE SIDE IS READ OFF THE ROW, NEVER TAKEN FROM THE CALLER
    -------------------------------------------------------------
    `PAPEIS_POR_LADO` is the whole validation, so whoever names the `lado`
    names the vocabulary. A caller allowed to claim "this is the buyer side"
    could call a vendedor a `fiador` and this function would agree with them.
    The row already knows which side it is on; that is the answer used.

    🔴 SETTING `conjuge` ALSO LINKS THE SPOUSE — see `_principal_do_conjuge`
    ------------------------------------------------------------------------
    A `papel` of `conjuge` says "married to the principal" and the principal is
    usually derivable, so deriving it is what turns a label into an answerable
    question. When it is NOT derivable the label still lands and the link does
    not — ambiguity is not an error, but guessing which of two co-buyers a
    spouse belongs to would put the wrong name on a contract.

    Moving a party OFF `conjuge` deliberately does NOT unlink: the marriage is
    a fact about two people, not about how this deal labels one of them, and a
    mis-click on a dropdown must not silently erase it. Clearing a wrong spouse
    is `PATCH /api/clientes/{id}` on the person's own record — the same place it
    is set by hand.
    """
    row = dict(_parte_do_cliente(client, org_id, cliente_id, parte_id))

    lado_alvo = normalizar_lado(row.get("lado"))
    papeis = PAPEIS_POR_LADO[lado_alvo]
    if papel not in papeis:
        # Same refusal `adicionar` already gives an unknown role, from the same
        # tuple — one vocabulary, checked the same way at both doors.
        raise ValidationError_(
            f"Papel inválido para o lado {lado_alvo}: {papel}. "
            f"Esperado um de {', '.join(papeis)}."
        )

    parte_cliente_id = str(row["cliente_id"])
    principal_id: Optional[str] = None
    if papel == PAPEL_CONJUGE:
        principal_id = _principal_do_conjuge(client, org_id, row, lado_alvo)
        if principal_id is not None:
            # Checked BEFORE the papel is written, so a refusal leaves nothing
            # half-applied. A 409 whose party had already been relabelled would
            # be a lie about what the request did.
            _recusar_conjuge_ocupado(client, org_id, parte_cliente_id, principal_id)

    _t(client, TABLE).update({"papel": papel}).eq("id", str(parte_id)).eq(
        "org_id", str(org_id)
    ).execute()
    row["papel"] = papel

    if principal_id is not None:
        _casar(client, org_id, parte_cliente_id, principal_id)

    clientes = _clientes_por_id(client, org_id, [parte_cliente_id])
    out = _out(row, clientes.get(parte_cliente_id))
    #: Not part of `_FIELDS` — it belongs to the two PEOPLE, not to the edge
    #: row. Returned anyway so the caller can tell the ambiguous case (papel
    #: set, `null` here) from the linked one without a second round-trip.
    out["conjuge_cliente_id"] = principal_id
    return out


def _principal_do_conjuge(
    client: Any, org_id: UUID, parte: dict, lado: str
) -> Optional[str]:
    """Whose spouse is this? — or `None` when only a guess could answer.

    🔴 THE TWO SIDES ASK IT DIFFERENTLY, AND THE ASYMMETRY IS REAL
    ---------------------------------------------------------------
    On the SELLER side the principal is a row in this table: the
    `proprietario` (migration 098 — the seller does not arrive as a lead, so
    every seller-side party lives here, the first one being the owner).

    On the BUYER side the principal is `atendimentos.cliente_id`, the titular,
    who is deliberately NOT a row here (migration 073: a second row asserting
    what the atendimento already says is a second truth, and the two disagree
    the first time either moves).

    🔴 A SECOND CO-BUYER MAKES THE QUESTION AMBIGUOUS, NOT HARDER
    --------------------------------------------------------------
    So other buyer-side `comprador` parties count as candidates alongside the
    titular. Luciano and his brother both buying, plus a spouse: "whose?" has
    two defensible answers, and picking the titular because they are easiest to
    find would put a name on a signature line for no reason at all. Zero
    candidates and two candidates get the same treatment — no link — because in
    both cases nothing here knows the answer.
    """
    atendimento_id = str(parte["atendimento_id"])
    eu = str(parte["cliente_id"])
    partes = (
        _t(client, TABLE)
        .select("cliente_id,papel,lado")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", atendimento_id)
        .eq("lado", lado)
        .execute()
    ).data or []
    candidatos = [
        str(r["cliente_id"])
        for r in partes
        if r.get("papel") == PAPEL_PADRAO_POR_LADO[lado]
        and str(r["cliente_id"]) != eu
    ]
    if lado == "comprador":
        atd = (
            _t(client, ATENDIMENTOS_TABLE)
            .select("id,cliente_id")
            .eq("org_id", str(org_id))
            .eq("id", atendimento_id)
            .execute()
        ).data or []
        titular = str(atd[0]["cliente_id"]) if atd and atd[0].get("cliente_id") else None
        if titular and titular != eu:
            candidatos.append(titular)
    unicos = sorted(set(candidatos))
    return unicos[0] if len(unicos) == 1 else None


def _conjuge_atual(client: Any, org_id: UUID, cliente_id: str) -> Optional[str]:
    rows = (
        _t(client, CLIENTES_TABLE)
        .select("id,conjuge_cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .execute()
    ).data or []
    valor = rows[0].get("conjuge_cliente_id") if rows else None
    return str(valor) if valor else None


def _recusar_conjuge_ocupado(
    client: Any, org_id: UUID, a_id: str, b_id: str
) -> None:
    """Refuse rather than clobber a spouse who is already named.

    A `conjuge_cliente_id` pointing at somebody else is not stale data to be
    corrected in passing — it is either an earlier deal's correct answer or a
    mistake somebody has to look at. Overwriting it from a dropdown would move
    a signature requirement onto a different person with no trace, which is
    precisely the silent-error shape. Idempotent when the two already name each
    other, so re-picking `conjuge` on a linked party is a no-op, not a 409.
    """
    for um, outro in ((a_id, b_id), (b_id, a_id)):
        atual = _conjuge_atual(client, org_id, um)
        if atual is not None and atual != str(outro):
            raise ConflictError(
                "Esta pessoa já tem outro cônjuge vinculado — corrija o "
                "cadastro dela antes de marcar este vínculo."
            )


def _casar(client: Any, org_id: UUID, a_id: str, b_id: str) -> None:
    """Write the link in BOTH directions — a marriage is symmetric.

    One-directional would make "who must sign with this owner?" answerable from
    the spouse's card and unanswerable from the owner's, which is the card the
    question is actually asked from.
    """
    for um, outro in ((a_id, b_id), (b_id, a_id)):
        _t(client, CLIENTES_TABLE).update(
            {"conjuge_cliente_id": str(outro)}
        ).eq("id", str(um)).eq("org_id", str(org_id)).execute()


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


def _parte_do_cliente(
    client: Any, org_id: UUID, cliente_id: UUID, parte_id: UUID
) -> dict:
    """The parte row, proven to hang off an atendimento of THIS cliente.

    🔴 THE OWNERSHIP CHECK IS THE AUTHORISATION. `ensure_cliente` proves the
    cliente exists in the org; it says nothing about whether this PARTE belongs
    to them. Scoping the lookup by `org_id + parte_id` alone — which `remover`
    did, and which `atualizar_papel` copied — means any parte in the org is
    reachable through any cliente's URL: `DELETE /clientes/<A>/compradores/
    <parte-of-B>` succeeded and detached B's spouse from B's deal.

    Org is still the tenancy boundary, so this was never a cross-tenant leak.
    Within an org it is an authorisation hole all the same, and the correct
    shape already exists next door: `roteiros_service._obter` refuses a route
    reached through someone else's id, for the reason it states — "an id alone
    must never be enough to read or edit someone else's route."

    `listar` and `adicionar` were already correct (both go through
    `resolve_atendimento_id` and filter on `atendimento_id`). This is the same
    guarantee for the two verbs that lacked it.
    """
    ensure_cliente(client, org_id, cliente_id)
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(parte_id))
        .execute()
    ).data or []
    row = rows[0] if rows else None
    if row is None:
        raise NotFoundError(TABLE, str(parte_id))
    permitidos = {
        str(r["id"]) for r in _atendimentos_do_cliente(client, org_id, cliente_id)
    }
    if str(row.get("atendimento_id")) not in permitidos:
        # Indistinguishable from "does not exist", deliberately: telling a
        # caller that a parte exists but belongs to someone else is itself a
        # disclosure.
        raise NotFoundError(TABLE, str(parte_id))
    return row


def remover(client: Any, org_id: UUID, cliente_id: UUID, parte_id: UUID) -> None:
    """Detach a party. The PERSON is not deleted.

    Removing someone from a deal is not the same as erasing them, and their
    documents belong to them rather than to this atendimento. Cascading to the
    `clientes` row would destroy uploads the org may be legally required to
    retain (`cliente_documento_tipos.retencao_dias`), on a click that reads as
    "they're not part of this purchase after all".
    """
    _parte_do_cliente(client, org_id, cliente_id, parte_id)
    _t(client, TABLE).delete().eq("id", str(parte_id)).eq(
        "org_id", str(org_id)
    ).execute()


__all__ = [
    "PAPEIS",
    "PAPEIS_POR_LADO",
    "PAPEL_CONJUGE",
    "PAPEL_PADRAO",
    "TABLE",
    "adicionar",
    "atualizar_papel",
    "listar",
    "remover",
]
