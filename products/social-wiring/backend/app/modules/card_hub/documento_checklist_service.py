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
The alternative is a hook that recomputes and stores every tick whenever a
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

from noctusai_lib.integrations.documents import looks_like_a_name

from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.services import _now, _t, ensure_cliente

TABLE = "cliente_documento_checklist"
CLIENTES_TABLE = "clientes"
DOCUMENTOS_TABLE = "cliente_documentos"

#: The fields the user named, in the order they asked for them — the sequence
#: you actually ask a person for their details in, not alphabetical. The order
#: is presentation AND meaning: it is the order the operator collects them in,
#: so a card read top-to-bottom shows the next thing to ask for.
#:
#: Each item declares HOW it is satisfied, which is what makes the derivation a
#: property of the definition rather than a parallel lookup table someone has
#: to keep in step:
#:
#: - ``campos``    — done when ANY of those `clientes` columns is non-empty,
#:                   listed most-canonical first.
#: - ``fontes``    — named readers in `_FONTES`, for facts whose location
#:                   depends on another column. Consulted AFTER `campos`.
#: - ``documento`` — done when a non-deleted `cliente_documentos` row of that
#:                   `tipo_documento` exists.
#:
#: - ``exige``     — an extra predicate the value must satisfy to count.
#:
#: 🔴 WHY ``nome_completo`` READS TWO COLUMNS THROUGH A PREDICATE
#: --------------------------------------------------------------
#: This item shipped reading `clientes.nome_completo` alone. That column
#: arrived with migration 068 and is written by nothing except an operator
#: filling it in, so it was empty for **all 10.255 clients** while 10.150 of
#: them had a `nome` from their registration. The item could therefore never
#: tick for anyone — a permanently-red gate, and those get ignored, which makes
#: the whole checklist untrustworthy.
#:
#: The obvious fix — also read `nome` — is WRONG on its own, and there is a
#: test asserting so: `nome` is a WhatsApp push name, a Meta `full_name`, or an
#: OLX handle. It is "Ana" for 4.417 of the 10.255 rows. Accepting it would
#: auto-tick "Nome Completo" for essentially every lead, which is the same
#: untrustworthy checklist arrived at from the other direction.
#:
#: So the item asks what it actually means: do we hold something that IS a full
#: name? `documents.looks_like_a_name` is that question, already written and
#: already tested — two substantive words, no digits, not an institutional
#: phrase. On today's data it ticks the 5.733 rows that carry a real name and
#: leaves the 4.417 push names alone.
#:
#: Note `nome_oficial` is deliberately absent. It is the name read off an
#: identity document, held for COMPARISON against the registration (migration
#: 071); letting it satisfy "do we know their name?" would collapse the two
#: facts the comparison exists to keep apart.
#: 🔴 WHY `celular` AND `email` NEED A ``fontes`` AND NOT JUST A ``campos``
#: ------------------------------------------------------------------------
#: Both facts can live in one of two places, and which one is authoritative
#: depends on a THIRD column. `clientes.chave_canonica` holds either a phone or
#: an email, and `chave_tipo` says which — so "the client's phone number" is
#: `chave_canonica` for a phone-keyed cliente and is emphatically NOT
#: `chave_canonica` for an email-keyed one, where reading it would tick
#: "Celular" with an email address.
#:
#: A plain `campos` entry cannot express that: it asks only whether a column is
#: non-empty. So a source is a NAMED READER (`_FONTES`) that gets the whole
#: row and returns a value or None, and an item may list several. `campos` is
#: kept for the ordinary case rather than folded into `fontes`, because most
#: items really are just "is this column filled in?" and spelling that as a
#: lambda would make the common case the hard one to read.
#:
#: Precedence is list order, most-explicit first: an operator-typed `celular`
#: outranks the registration key, exactly as `nome_completo` outranks `nome`.
ITENS: tuple[dict[str, Any], ...] = (
    {"key": "nome_completo", "label": "Nome Completo",
     "campos": ("nome_completo", "nome"), "exige": "nome_completo"},
    # Comes from the registration act and is REQUIRED — `stage_gate.py` refuses
    # to move an atendimento whose titular has no phone. It ticks itself for
    # every phone-keyed cliente, which is most of them.
    {"key": "celular", "label": "Celular",
     "campos": ("celular",), "fontes": ("chave_telefone",)},
    # Registration or later input, same shape as celular in the other
    # direction: an email-keyed cliente already has it.
    {"key": "email", "label": "Email",
     "campos": ("email",), "fontes": ("chave_email",)},
    {"key": "data_nascimento", "label": "Data de Nascimento",
     "campos": ("data_nascimento",)},
    {"key": "profissao", "label": "Profissão", "campos": ("profissao",)},
    {"key": "genero", "label": "Gênero", "campos": ("genero",)},
    {"key": "rg", "label": "RG", "documento": "rg"},
    {"key": "cpf", "label": "CPF", "documento": "cpf"},
)

ITEM_KEYS = tuple(item["key"] for item in ITENS)

#: Named readers for facts that are not simply "is this column filled in?".
#:
#: Each declares the columns it reads, so `_CLIENTE_COLUNAS` below stays
#: DERIVED from the definition. A hand-maintained select list beside a
#: definition that can grow is the drift shape this codebase gates against
#: elsewhere; there is no reason to hand-roll one here.
_FONTES: dict[str, dict[str, Any]] = {
    "chave_telefone": {
        "colunas": ("chave_canonica", "chave_tipo"),
        "ler": lambda c: (
            c.get("chave_canonica") if c.get("chave_tipo") == "telefone" else None
        ),
    },
    "chave_email": {
        "colunas": ("chave_canonica", "chave_tipo"),
        "ler": lambda c: (
            c.get("chave_canonica") if c.get("chave_tipo") == "email" else None
        ),
    },
}

#: Columns read for DISPLAY beside the checklist but never used to derive a
#: tick. `nome_oficial` is here and not in any item's `campos` on purpose —
#: see the ITENS docstring.
_CLIENTE_COLUNAS_EXIBICAO = ("nome_oficial",)

#: Columns the derivation reads. Selected explicitly rather than `*` so adding
#: a column to `clientes` cannot silently widen what this module pulls.
_CLIENTE_COLUNAS = tuple(
    dict.fromkeys(
        [col for i in ITENS for col in i.get("campos", ())]
        + [
            col
            for i in ITENS
            for fonte in i.get("fontes", ())
            for col in _FONTES[fonte]["colunas"]
        ]
        + list(_CLIENTE_COLUNAS_EXIBICAO)
    )
)


#: Extra predicates an item may require of a column value, by name. Keyed
#: rather than inlined as callables so `ITENS` stays plain data — it is
#: compared, iterated and asserted against in tests, and a function object in
#: there makes every one of those noisier.
_VALIDADORES: dict[str, Any] = {
    "nome_completo": looks_like_a_name,
}


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
        if "documento" in item:
            out[item["key"]] = item["documento"] in tipos_documento_presentes
            continue
        exige = _VALIDADORES.get(item.get("exige", ""))
        # Plain columns first, then the named readers — list order IS
        # precedence, and any one satisfying value ticks the item.
        valores = [cliente.get(col) for col in item.get("campos", ())]
        valores += [
            _FONTES[fonte]["ler"](cliente) for fonte in item.get("fontes", ())
        ]
        out[item["key"]] = any(
            _preenchido(valor) and (exige is None or exige(str(valor)))
            for valor in valores
        )
    return out


def valor_de(cliente: Optional[dict], item_key: str) -> Any:
    """The value backing one item, by the same precedence the tick uses.

    Exists so a caller that needs the VALUE — the stage gate asking "does this
    person actually have a phone?" — cannot answer it with a second, subtly
    different rule. One definition, two readers.
    """
    cliente = cliente or {}
    item = next((i for i in ITENS if i["key"] == item_key), None)
    if item is None:
        raise KeyError(item_key)
    exige = _VALIDADORES.get(item.get("exige", ""))
    valores = [cliente.get(col) for col in item.get("campos", ())]
    valores += [_FONTES[fonte]["ler"](cliente) for fonte in item.get("fontes", ())]
    for valor in valores:
        if _preenchido(valor) and (exige is None or exige(str(valor))):
            return valor
    return None


def _out(
    item: dict[str, str],
    derivado: bool,
    override: Optional[dict],
    sugestao: Optional[dict] = None,
) -> dict:
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
        # A value an extractor read but was NOT confident enough to store
        # (migration 069). It rides on the checklist item because the checklist
        # is already the "what is still missing" surface — an answer to a
        # missing item belongs next to the item, not on a separate screen the
        # operator has to think to visit.
        "sugestao": sugestao,
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

    Always returns every item, in `ITENS` order, whether or not an override row
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

    sugestoes = identidade_svc.sugestoes_pendentes(client, org_id, cliente_id)
    itens = [
        _out(
            item,
            derivado[item["key"]],
            by_key.get(item["key"]),
            sugestoes.get(item["key"]),
        )
        for item in ITENS
    ]
    # Extracted fields that are NOT checklist items — today just
    # `nome_oficial`. They ride on this response rather than getting an
    # endpoint of their own because the card already fetches this once and the
    # decision surface is the same one; giving them a separate call would mean
    # a second round-trip and a second loading state for the same panel.
    #
    # Kept OUT of `items` deliberately: anything in `items` is a requirement
    # whose absence makes a client incomplete, and the official name is not
    # that — whether we hold the document is already asked by `rg` / `cpf`.
    extras = {
        key: valor for key, valor in sugestoes.items()
        if key not in {i["key"] for i in ITENS}
    }

    return {
        "items": itens,
        "total": len(itens),
        "concluidos": sum(1 for i in itens if i["concluido"]),
        "sugestoes_extras": extras,
        "nome_oficial": (cliente or {}).get("nome_oficial"),
        "nome_registro": _nome_registro(cliente),
    }


def _nome_registro(cliente: Optional[dict]) -> Optional[str]:
    """The best registration name we hold, for display beside `nome_oficial`.

    Same precedence as `vw_nome_conferencia` (migration 071): the explicit
    `nome_completo` when an operator filled it, else the `nome` every intake
    path writes. Kept in step with the view by having exactly one rule, stated
    in both places, rather than two that drift.
    """
    cliente = cliente or {}
    for col in ("nome_completo", "nome"):
        valor = cliente.get(col)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


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
    "valor_de",
]
