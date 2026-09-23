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

from noctusai_lib.integrations.documents import ESTADO_CIVIL_VALORES, looks_like_a_name

from app.modules.card_hub import documentos_service as docs_svc
from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.services import _now, _paged_rows, _t, ensure_cliente

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
#: - ``campos_todos`` — done only when EVERY listed column is non-empty; a
#:                   file never satisfies it alone. ``documentos`` /
#:                   ``documentos_legado`` name its upload slots. Today only
#:                   `identidade` — see `_IDENTIDADE_ROTULOS`.
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
#: 🔴 DECISION CHANGED 2026-08-24 — `nome_oficial` NOW SATISFIES THIS ITEM.
#:
#: It used to be excluded, on the argument that the document name is held for
#: COMPARISON against the registration (migration 071) and that letting it
#: satisfy "do we know their name?" would collapse the two facts the comparison
#: exists to keep apart.
#:
#: The product owner has ruled otherwise, and the ruling is about what the
#: WORKFLOW is: the WhatsApp push name is what the lead arrives with and is all
#: the funil gate requires; the person's legal full name is expected to arrive
#: LATER, off their uploaded RG. Under that workflow the old rule made this item
#: permanently red for exactly the clients who had done everything asked of
#: them — they sent the document, the name was read off it, and the checklist
#: still said "Nome Completo: pending".
#:
#: Nothing is collapsed by this. Both columns still exist, still hold different
#: values, and `vw_nome_conferencia` (071) still measures the gap between them;
#: the card still renders them side by side via `NomeOficial`. What changed is
#: only whether holding a document-read name COUNTS as knowing the person's
#: name. It does.
#:
#: Precedence is explicit-first: an operator-typed `nome_completo`, then the
#: document read, then the channel-supplied `nome` — which still has to pass
#: `looks_like_a_name`, so "Ana" continues not to satisfy it.
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
     "campos": ("nome_completo", "nome_oficial", "nome"),
     "exige": "nome_completo"},
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
    # 🔴 ONE item for RG + CPF (owner directive, 2026-09-23) — it replaced the
    # separate `rg` and `cpf` items. See `_IDENTIDADE_*` below for the whole
    # rule; in short: satisfied when BOTH numbers are on the record (read off
    # the CIN/CNH and confirmed, or typed by the operator), never by a file
    # alone, and it names which of the two is still missing.
    {"key": "identidade", "label": "Documento de identidade (RG e CPF)",
     "campos_todos": ("rg", "cpf"),
     "documentos": ("cin", "cnh"),
     "documentos_legado": ("rg", "cpf"),
     "dica": "Basta um dos dois (CIN ou CNH), desde que dele se leiam o RG e o CPF."},
)

ITEM_KEYS = tuple(item["key"] for item in ITENS)

#: 🔴 THE IDENTITY ITEM — WHY ONE ITEM, WHY VALUES, WHY TWO SLOTS
#: ----------------------------------------------------------------
#: [Owner directive, 2026-09-23] "make rg/cpf 1 single checklist item. then i
#: need the CIN field and the CNH field. only one of those fields need to be
#: filled, if they are able to extract rg and cpf from it, otherwise the
#: mechanism shall block generation missing one of those fields (rg/cpf)."
#:
#: - ``campos_todos`` — done only when EVERY listed column is filled (the
#:   ordinary ``campos`` is ANY-of). A CIN or a CNH carries both numbers, so
#:   one document is enough exactly when both were read off it (and
#:   confirmed) or the operator typed them in; an uploaded file whose numbers
#:   were never read satisfies nothing. That keeps this item and the contract
#:   gate (`_CAMPOS_QUALIFICACAO_CONTRATO` — `rg` and `cpf` stay separate
#:   there, so the refusal names WHICH one is missing) on one fact.
#: - ``documentos`` — the upload slots, in order: CIN, CNH. A CIN is never
#:   extracted (no real one exists yet; migration 164) — its numbers are
#:   validated by hand. A CIN's RG legitimately equals its CPF (órgão IIGDR);
#:   nothing here compares the two.
#: - ``documentos_legado`` — `rg`/`cpf`-typed files already on record. Shown
#:   read-only (no new uploads under those types from this item) so a CNH
#:   that was filed as `rg` before `cnh` existed (migration 142) stays
#:   visible and keeps counting through the numbers read off it. Rows are
#:   never retyped.
#:
#: Keys: `rg`/`cpf` overrides (`cliente_documento_checklist.item_key`) are
#: orphaned by the collapse — a per-number override does not say anything
#: about the pair, so carrying it onto `identidade` would invent a decision
#: nobody made.
_IDENTIDADE_ROTULOS: dict[str, str] = {
    "cin": "CIN",
    "cnh": "CNH",
    "rg": "Arquivado como RG",
    "cpf": "Arquivado como CPF",
}

#: Label per identity column, for the "which one is missing" read-out.
_IDENTIDADE_CAMPO_ROTULOS: dict[str, str] = {"rg": "RG", "cpf": "CPF"}

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
#: tick.
#:
#: Empty since 2026-08-24: `nome_oficial` was its only member and is now a real
#: derivation input for `nome_completo` (see the ITENS docstring). Kept rather
#: than deleted because the DISTINCTION is still meaningful — the next
#: extracted-but-not-required field belongs here, not in an item.
_CLIENTE_COLUNAS_EXIBICAO: tuple[str, ...] = ()

#: Columns the derivation reads. Selected explicitly rather than `*` so adding
#: a column to `clientes` cannot silently widen what this module pulls.
_CLIENTE_COLUNAS = tuple(
    dict.fromkeys(
        [col for i in ITENS for col in i.get("campos", ())]
        + [col for i in ITENS for col in i.get("campos_todos", ())]
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
        # ALL-of items (the identity item) — values only; a file never
        # satisfies one on its own. See `_IDENTIDADE_ROTULOS`' docblock.
        if item.get("campos_todos"):
            out[item["key"]] = not campos_faltando(cliente, item["key"])
            continue
        # 🔴 EITHER SATISFIES, and the `or` replaced an early `continue`.
        #
        # Until migration 097 the two ways of satisfying an item were disjoint:
        # `rg`/`cpf` were upload-only (we held the scan, never the number) and
        # everything else was column-only. Now the extractor writes
        # `clientes.cpf` / `clientes.rg` and an operator can type them, so an
        # item can be satisfied by a value, by a document, or by both.
        #
        # The old `continue` would have made a document-bearing item ignore its
        # columns entirely — so a client whose CPF was typed in by hand would
        # show "CPF" unticked until somebody also uploaded the scan. That reads
        # as missing paperwork when the fact is on file.
        por_documento = (
            "documento" in item
            and item["documento"] in tipos_documento_presentes
        )

        exige = _VALIDADORES.get(item.get("exige", ""))
        # Plain columns first, then the named readers — list order IS
        # precedence, and any one satisfying value ticks the item.
        valores = [cliente.get(col) for col in item.get("campos", ())]
        valores += [
            _FONTES[fonte]["ler"](cliente) for fonte in item.get("fontes", ())
        ]
        por_campos = any(
            _preenchido(valor) and (exige is None or exige(str(valor)))
            for valor in valores
        )

        out[item["key"]] = por_documento or por_campos
    return out


def campos_faltando(cliente: Optional[dict], item_key: str) -> list[str]:
    """The ``campos_todos`` columns of one item still empty, in declared order.

    `[]` for an item with no ``campos_todos`` — "nothing missing" is the
    honest answer for a question the item does not ask. Pure, like `derivar`,
    which reads its verdict off this same function so the tick and the
    "which one is missing" read-out can never disagree.
    """
    item = next((i for i in ITENS if i["key"] == item_key), None)
    if item is None:
        raise KeyError(item_key)
    cliente = cliente or {}
    return [
        col for col in item.get("campos_todos", ())
        if not _preenchido(cliente.get(col))
    ]


def _identidade_slots(item: dict, documentos: dict[str, dict]) -> list[dict]:
    """The upload slots (CIN, CNH) plus any legacy `rg`/`cpf` file on record.

    Upload slots are always present — an empty one is what the operator
    fills. Legacy entries appear only when a file of that type exists, and
    are marked ``upload=False``: this item never files anything new as
    `rg`/`cpf`, it only keeps what is already there visible.
    """
    slots = [
        {
            "tipo_documento": tipo,
            "rotulo": _IDENTIDADE_ROTULOS.get(tipo, tipo),
            "upload": True,
            "documento": docs_svc.documento_resumo(documentos.get(tipo)),
        }
        for tipo in item.get("documentos", ())
    ]
    slots += [
        {
            "tipo_documento": tipo,
            "rotulo": _IDENTIDADE_ROTULOS.get(tipo, tipo),
            "upload": False,
            "documento": docs_svc.documento_resumo(documentos[tipo]),
        }
        for tipo in item.get("documentos_legado", ())
        if documentos.get(tipo)
    ]
    return slots


def _extras_do_item(
    item: dict, cliente: Optional[dict], documentos: dict[str, dict]
) -> dict:
    """Additive keys for an ALL-of item: its slots, what is missing, the hint.

    Empty for every other item, so their line shape is unchanged.
    """
    if not item.get("campos_todos"):
        return {}
    faltando = campos_faltando(cliente, item["key"])
    return {
        "faltando": faltando,
        "faltando_rotulos": [_IDENTIDADE_CAMPO_ROTULOS.get(c, c) for c in faltando],
        "documentos": _identidade_slots(item, documentos),
        "dica": item.get("dica"),
    }


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
    documento: Optional[dict] = None,
    extras: Optional[dict] = None,
) -> dict:
    """One checklist line: the canonical definition + derivation + override.

    `concluido` stays the single boolean the UI reads, so the response shape is
    unchanged for existing consumers. `origem` is additive and says WHY, which
    is what lets the card explain a tick the user did not make — and, just as
    importantly, a tick that is stuck on because someone forced it.

    `documento` NAMES the file behind a document-satisfied tick. The boolean
    alone could say only *that* an RG had been uploaded, so the card could
    render a tick but not a trash button — there was nothing to point it at,
    and the operator had to leave the checklist for the Documentos tab to
    delete the wrong scan they had just noticed. It is `None` for every item
    with no `documento` key in its definition, always: a typed item is
    satisfied by a column and there is no file to name. The key is emitted for
    both kinds so the frontend renders one row shape, not two.
    """
    manual = override.get("concluido_manual") if override else None
    concluido = derivado if manual is None else bool(manual)
    return {
        "key": item["key"],
        "label": item["label"],
        "concluido": concluido,
        "documento": documento if "documento" in item else None,
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
        # The identity item's slots / missing numbers / hint
        # (`_extras_do_item`). Absent on every other item.
        **(extras or {}),
    }


def _documentos_por_tipo(
    client: Any, org_id: UUID, cliente_id: UUID
) -> dict[str, dict]:
    """`tipo_documento -> the live document satisfying it`, for this client.

    ONE read backs BOTH the tick and the file it names. The obvious shape — a
    frozenset of types for the derivation, then a lookup per document item to
    find the row — is two round-trips for a card that already renders eight
    lines, and it can disagree with itself: the second read happens after the
    first, so a document deleted in between produces a ticked item with no
    document attached.

    Soft-deleted rows are excluded: a document the client asked us to delete
    cannot go on satisfying a requirement it no longer backs.

    Most recent wins when a client has uploaded the same type twice. It is the
    one the operator just sent and the one the card is showing, so it is also
    the one a per-row trash button must discard. `created_at` is coalesced to
    `""` because a row may legitimately predate the column being populated —
    sorting must not raise on it.
    """
    rows = _paged_rows(
        client,
        DOCUMENTOS_TABLE,
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    rows.sort(key=lambda r: r.get("created_at") or "")
    return {r["tipo_documento"]: r for r in rows if r.get("tipo_documento")}


#: `_tipos_presentes` used to live here and returned only the set of types.
#: Both callers now need the rows themselves (to name the file behind a tick),
#: so it was folded into `_documentos_por_tipo` rather than left as a wrapper
#: nothing calls — `frozenset(_documentos_por_tipo(...))` at the two call sites
#: is the same fact with no second name to keep in step.


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


def cliente_para_derivacao(
    client: Any, org_id: UUID, cliente_id: UUID
) -> Optional[dict]:
    """The cliente row this module derives from, for a second reader.

    Public so `pipeline.stage_gate` can ask its `nome` question against the
    SAME projection the checklist reads — not so it can re-derive a tick. The
    gate's `nome` requirement is deliberately weaker than the checklist's
    "Nome Completo" item, so it needs the row rather than the verdict; sharing
    the row keeps the column list in one place even when the questions differ.
    """
    return _cliente_row(client, org_id, cliente_id)


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Every canonical item, derived, with any human override applied.

    Always returns every item, in `ITENS` order, whether or not an override row
    exists — the list is the contract, the rows are just opinions about it.
    """
    ensure_cliente(client, org_id, cliente_id)

    cliente = _cliente_row(client, org_id, cliente_id)
    documentos = _documentos_por_tipo(client, org_id, cliente_id)
    derivado = derivar(cliente, frozenset(documentos))

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
            docs_svc.documento_resumo(documentos.get(item.get("documento", ""))),
            _extras_do_item(item, cliente, documentos),
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
    # that — whether we hold the document is already asked by `identidade`.
    #
    # The RG and CPF readings land here too since the `rg`/`cpf` items
    # collapsed into `identidade` (2026-09-23): their suggestion keys are
    # COLUMNS, and the single item that now asks for both has no one column
    # to hang a single suggestion on. The card renders them beside the
    # checklist like the other qualificação extras.
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
        # The VALUES behind the ticks, so the card can offer a form to fill
        # them in. It rides on this response rather than getting an endpoint of
        # its own for the same reason `sugestoes_extras` does: the checklist is
        # already the "what is still missing" surface and the card already
        # fetches it once — a second call would mean a second loading state for
        # the same panel.
        #
        # Derived from `ITENS` rather than hand-listed, so an item added later
        # becomes editable without anyone remembering to widen this dict.
        "valores": valores_editaveis(cliente),
    }


#: Items whose value can be TYPED, whether or not a document also satisfies
#: them. `rg`/`cpf` joined this set in migration 097 and, since they became
#: the ONE `identidade` item (2026-09-23), are emitted per column below. The predicate is
#: `"campos" in item`, not `"documento" not in item` — keying it on the ABSENCE
#: of a document would have silently kept both out of the form.
def valores_editaveis(cliente: Optional[dict]) -> dict:
    """`item_key -> current value` for every item a human fills in by hand.

    Reads through `valor_de`, so the value shown in the form is the same one
    the tick was decided from — a form seeded by a second, subtly different
    rule would show an empty "Celular" box beside a ticked "Celular" item.
    """
    valores = {
        item["key"]: valor_de(cliente, item["key"])
        for item in ITENS
        if item.get("campos")
    }
    # An ALL-of item has no single value — it edits each of its columns, keyed
    # by COLUMN (`rg`, `cpf`), which is the shape the form already reads.
    for item in ITENS:
        for col in item.get("campos_todos", ()):
            valor = (cliente or {}).get(col)
            valores[col] = valor if _preenchido(valor) else None
    return valores


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
    documentos = _documentos_por_tipo(client, org_id, cliente_id)
    cliente = _cliente_row(client, org_id, cliente_id)
    derivado = derivar(cliente, frozenset(documentos))
    # Same line shape the GET returns, `documento` included — the card writes
    # the PATCH response straight back into its list, so a narrower shape here
    # would blank the trash button until the next refetch.
    return _out(
        item,
        derivado[item["key"]],
        merged,
        None,
        docs_svc.documento_resumo(documentos.get(item.get("documento", ""))),
        _extras_do_item(item, cliente, documentos),
    )


# ─── Contract completeness (migration 110) ───────────────────────────────
#
# Deliberately SEPARATE from `ITENS`/`derivar` above, not a parallel
# mechanism doing the same job twice. The Documentos-tab checklist answers
# "has SOMETHING plausible been collected for this column" and, by product
# ruling (2026-08-24), accepts a channel-supplied `nome` for "Nome Completo".
# A signed "Promessa de Venda e Compra" asks a stricter question — the
# LEGAL name off a document, not a WhatsApp push name — and a question
# `derivar`'s plain-boolean, always-required model cannot express at all:
# `regime_bens` is required only for a married party, and a married party
# additionally needs a linked cônjuge who is THEMSELVES qualified. Both are
# facts about the PAIR, not a tick on one row, so they get their own
# function rather than bending the checklist's pinned "verbatim contract"
# item list to fit them.

#: The columns a signed instrument needs from ONE party, beyond what
#: `_ENDERECO_CAMPOS_OBRIGATORIOS` / the married-state branch below add.
#: `nome_oficial` specifically — not `nome_completo` — because the document
#: name is the legal one; see the section docstring.
_CAMPOS_QUALIFICACAO_CONTRATO: tuple[str, ...] = (
    "nome_oficial", "nacionalidade", "profissao", "estado_civil",
    "rg", "rg_orgao_expedidor", "cpf",
)

#: `endereco` is satisfied only when every one of these is filled — a street
#: with no city is not an address a contract can print. `endereco_complemento`
#: is deliberately absent: most addresses genuinely have none.
_ENDERECO_CAMPOS_OBRIGATORIOS: tuple[str, ...] = (
    "endereco_logradouro", "endereco_numero", "endereco_bairro",
    "endereco_cidade", "endereco_uf", "endereco_cep",
)

#: CC art. 1.647 — the states that make a spouse's outorga part of the
#: instrument. Both `regime_bens`'s own requirement and the cônjuge
#: requirement below key off this same set.
_ESTADOS_QUE_EXIGEM_CONJUGE: frozenset[str] = frozenset({"casado", "uniao_estavel"})

#: `clientes.estado_civil` is unconstrained TEXT (migration 097) and
#: `ClientePatchBody.estado_civil` accepts any string, so a value typed
#: through an OLDER version of the qualificação form — before this field's
#: vocabulary was the extractor's closed snake_case set,
#: `noctusai_lib.integrations.documents.civil_status.ESTADO_CIVIL_VALORES` —
#: may still read "Casado(a)" rather than "casado". Mapped ON READ, here,
#: rather than rewritten in the database: rewriting stored data was out of
#: scope for this pass (existing rows may already disagree with each other
#: in ways a blind rewrite would paper over), so every reader that needs the
#: CANONICAL token goes through `_estado_civil_normalizado` instead of
#: repeating this table.
_ESTADO_CIVIL_LEGADO: dict[str, str] = {
    "CASADO": "casado", "CASADO(A)": "casado", "CASADA": "casado",
    "SOLTEIRO": "solteiro", "SOLTEIRO(A)": "solteiro", "SOLTEIRA": "solteiro",
    "DIVORCIADO": "divorciado", "DIVORCIADO(A)": "divorciado",
    "DIVORCIADA": "divorciado",
    "VIUVO": "viuvo", "VIUVO(A)": "viuvo", "VIUVA": "viuvo",
    "VIÚVO": "viuvo", "VIÚVO(A)": "viuvo", "VIÚVA": "viuvo",
    "SEPARADO": "separado_judicialmente", "SEPARADO(A)": "separado_judicialmente",
    "SEPARADO JUDICIALMENTE": "separado_judicialmente",
    "UNIAO ESTAVEL": "uniao_estavel", "UNIÃO ESTÁVEL": "uniao_estavel",
    "UNIAO_ESTAVEL": "uniao_estavel",
}

#: Explicit column list for the contract-completeness read — decoupled from
#: `_CLIENTE_COLUNAS` (which is DERIVED from `ITENS` and must stay that way)
#: so a future edit to the Documentos checklist cannot silently narrow what
#: this stricter surface reads.
_COLUNAS_QUALIFICACAO_CONTRATO: tuple[str, ...] = (
    "id", "nome_completo", "nome", "nome_oficial", "nacionalidade",
    "profissao", "estado_civil", "regime_bens", "data_casamento",
    "conjuge_cliente_id",
    "cpf", "rg", "rg_orgao_expedidor",
    *_ENDERECO_CAMPOS_OBRIGATORIOS,
)

#: Migration 117 (contract F6). The office's Lei 6.515/77 citation depends on
#: which side of 26/12/1977 the marriage fell — a `casado` party the
#: instrument cannot cite correctly without this date. Deliberately NARROWER
#: than `_ESTADOS_QUE_EXIGEM_CONJUGE`: a `uniao_estavel` party has no
#: "casamento" to date, so it is not required there.
_ESTADO_QUE_EXIGE_DATA_CASAMENTO = "casado"


def _estado_civil_normalizado(valor: Optional[str]) -> Optional[str]:
    """The canonical seed token for a possibly-legacy `estado_civil` value.

    An already-canonical value passes straight through unchanged; an unknown
    (neither canonical nor a mapped legacy spelling) value returns `None` —
    treated as "not stated" rather than guessed at, the same "never guess"
    discipline `civil_status.py` itself applies to a document read.
    """
    if not valor:
        return None
    if valor in ESTADO_CIVIL_VALORES:
        return valor
    return _ESTADO_CIVIL_LEGADO.get(valor.strip().upper())


def _cliente_row_qualificacao(
    client: Any, org_id: UUID, cliente_id: UUID
) -> Optional[dict]:
    rows = (
        _t(client, CLIENTES_TABLE)
        .select(",".join(_COLUNAS_QUALIFICACAO_CONTRATO))
        .eq("org_id", str(org_id))
        .eq("id", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _faltantes_qualificacao(cliente: dict) -> list[str]:
    """Missing-field keys for ONE party's contract qualification.

    Pure — same reasoning `derivar` is pure — so the rule is testable
    without a database. Does NOT look at the cônjuge; `completude_contratual`
    composes that separately, since it is a fact about a PAIR, not this row.
    """
    faltando = [
        campo for campo in _CAMPOS_QUALIFICACAO_CONTRATO
        if not _preenchido(cliente.get(campo))
    ]
    if not all(_preenchido(cliente.get(c)) for c in _ENDERECO_CAMPOS_OBRIGATORIOS):
        faltando.append("endereco")

    estado_civil = _estado_civil_normalizado(cliente.get("estado_civil"))
    if estado_civil in _ESTADOS_QUE_EXIGEM_CONJUGE and not _preenchido(
        cliente.get("regime_bens")
    ):
        faltando.append("regime_bens")

    if estado_civil == _ESTADO_QUE_EXIGE_DATA_CASAMENTO and not _preenchido(
        cliente.get("data_casamento")
    ):
        faltando.append("data_casamento")

    return faltando


def completude_contratual(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Is this party qualified enough to go on the instrument?

    Per-party: the fields a signed "Promessa de Venda e Compra" needs off
    THIS person, plus — when `estado_civil` names a married state (CC art.
    1.647) — a linked cônjuge who is ALSO qualified. A married party with no
    cônjuge, or a cônjuge who is not themselves qualified, is not
    contract-ready even when every one of THEIR OWN fields is filled.

    Recurses exactly ONE level (into the cônjuge, never the cônjuge's own
    cônjuge): `clientes_conjuge_nao_e_proprio` (migration 097) already
    forbids a self-loop, and the pair is symmetric by construction
    (`compradores_service._casar` writes both directions), so a second level
    would only ever re-examine THIS same party.
    """
    ensure_cliente(client, org_id, cliente_id)
    cliente = _cliente_row_qualificacao(client, org_id, cliente_id)
    faltando = _faltantes_qualificacao(cliente or {})

    conjuge_info: Optional[dict] = None
    estado_civil = _estado_civil_normalizado((cliente or {}).get("estado_civil"))
    if estado_civil in _ESTADOS_QUE_EXIGEM_CONJUGE:
        conjuge_id = (cliente or {}).get("conjuge_cliente_id")
        if not conjuge_id:
            faltando.append("conjuge")
        else:
            conjuge = _cliente_row_qualificacao(
                client, org_id, UUID(str(conjuge_id))
            )
            conjuge_faltando = (
                _faltantes_qualificacao(conjuge) if conjuge else ["conjuge"]
            )
            conjuge_info = {
                "cliente_id": str(conjuge_id),
                "nome": _nome_registro(conjuge) if conjuge else None,
                "completo": not conjuge_faltando,
                "faltando": conjuge_faltando,
            }
            if conjuge_faltando:
                faltando.append("conjuge_qualificacao")

    # Migration 117 (contract F6). Informational, not a `faltando` gate: the
    # office's 90-day-freshness rule is checked AT SIGNING by the contract
    # generator (out of this module's scope), not here — this only surfaces
    # the fact the generator needs. `None` when the party has no qualifying
    # certidão with a recorded emission date yet.
    certidao_estado_civil = identidade_svc.certidao_estado_civil_mais_recente(
        client, org_id, cliente_id
    )

    return {
        "cliente_id": str(cliente_id),
        "estado_civil": estado_civil,
        "completo": not faltando,
        "faltando": faltando,
        "conjuge": conjuge_info,
        "certidao_estado_civil": certidao_estado_civil,
    }


__all__ = [
    "ITENS",
    "ITEM_KEYS",
    "TABLE",
    "completude_contratual",
    "derivar",
    "listar",
    "marcar",
    "campos_faltando",
    "cliente_para_derivacao",
    "valor_de",
    "valores_editaveis",
]
