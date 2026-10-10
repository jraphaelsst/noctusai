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
from noctusai_lib.integrations.documents.rg import mesmo_rg, only_alnum

from app.modules.card_hub import documentos_service as docs_svc
from app.modules.card_hub import identidade_extracao_service as identidade_svc
from app.modules.card_hub.services import (
    _now,
    _paged_rows,
    _t,
    ensure_cliente,
    tem_permuta_ativa,
)

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
#: The identity data the ONE `identidade` item asks for — exactly the
#: document-borne slice of `_CAMPOS_QUALIFICACAO_CONTRATO` (the contract's
#: qualificação), in that tuple's order, so the tick and the contract gate
#: agree on what "complete" means. `nacionalidade`/`profissao`/`estado_civil`
#: are qualificação too but are NOT identity-document facts (a CNH does not
#: settle a marriage), so they stay their own concerns. A test pins this
#: tuple as a subsequence of the contract's, and pins
#: `contrato_gerador.derivacao._CHAVES_DO_DOCUMENTO_DE_IDENTIDADE` to it.
CAMPOS_DOCUMENTO_IDENTIDADE: tuple[str, ...] = (
    "nome_oficial", "rg", "rg_orgao_expedidor", "cpf",
)

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
    # 🔴 ONE item for the identity data (owner directives 2026-09-23 and
    # 2026-09-30) — it replaced the separate `rg` and `cpf` items. See
    # `_IDENTIDADE_*` below for the whole rule; in short: satisfied when the
    # identity data the CONTRACT needs (`CAMPOS_DOCUMENTO_IDENTIDADE`) is on
    # the record — read off whichever of RG/CPF, CNH or CIN was uploaded, or
    # typed by the operator — never by a file alone, and it names which
    # fields are still missing.
    {"key": "identidade", "label": "Documento de identidade (RG/CPF, CNH ou CIN)",
     "campos_todos": CAMPOS_DOCUMENTO_IDENTIDADE,
     "ressalvas": ("rg_so_da_cnh",),
     "documentos": ("rg", "cnh", "cin"),
     "documentos_legado": ("cpf",),
     "dica": (
         "Basta um documento (RG/CPF, CNH ou CIN), desde que dele se leiam "
         "nome, CPF, RG e órgão expedidor; se faltar algum, envie outro."
     )},
    # P0c contract §F/§H8 — scoped to certificandos only (vendedores, their
    # cônjuges, and compradores/cônjuges when the deal `tem_permuta`); see
    # `_certificando` and `listar`'s own filtering. `documento`+`documentos`
    # both name `serasa_crednet`: `documento` is `derivar`'s ordinary
    # "a file of this type exists" satisfaction (the same mechanism every
    # plain document-backed item already uses), `documentos` is the upload
    # slot `_extras_do_item`/`_identidade_slots` render — a single-entry
    # tuple, generalizing that helper past its identity-only origin (it
    # already keys purely off `item["documentos"]`, no special-casing).
    {"key": "serasa_crednet", "label": "Serasa Crednet",
     "documento": "serasa_crednet", "documentos": ("serasa_crednet",)},
    # Migration 191 — scoped (``escopo``, see `_ESCOPOS`): shown only when
    # the party's regime de bens is one a pacto antenupcial must establish
    # (or a pacto is already on file), so a comunhão-parcial or single
    # party's card never asks for a document that does not exist for them.
    # No ``documentos`` slot here: the married party's named
    # `pacto_antenupcial` slot (FE `SLOTS_DO_CASAMENTO`) is the upload.
    {"key": "pacto_antenupcial", "label": "Pacto antenupcial",
     "documento": "pacto_antenupcial", "escopo": "pacto_antenupcial"},
)

ITEM_KEYS = tuple(item["key"] for item in ITENS)

#: 🔴 THE IDENTITY ITEM — WHY ONE ITEM, WHY VALUES, WHY THREE SLOTS
#: ------------------------------------------------------------------
#: [Owner directive, 2026-09-23] "make rg/cpf 1 single checklist item. then i
#: need the CIN field and the CNH field. only one of those fields need to be
#: filled, if they are able to extract rg and cpf from it, otherwise the
#: mechanism shall block generation missing one of those fields (rg/cpf)."
#:
#: [Owner directive, 2026-09-30] "Also separate the rg cpf cin cnh upload. I
#: want “rg/cpf” in one item, then cnh, then cin. Data comes from whichever
#: is uploaded and not all need to be uploaded, as long as data is complete".
#:
#: - ``campos_todos`` — done only when EVERY listed column is filled (the
#:   ordinary ``campos`` is ANY-of): `CAMPOS_DOCUMENTO_IDENTIDADE`, the
#:   document-borne slice of the contract's qualificação. Any ONE document is
#:   enough exactly when all of it was read off that document (or typed);
#:   when one is not enough (a CNH with no órgão, an RG card with no CPF),
#:   the item names the missing fields so the operator knows another
#:   document — or a typed value — is needed. An uploaded file whose data
#:   was never read satisfies nothing.
#: - ``ressalvas`` — a FILLED column that still does not count, by a named
#:   rule in `_RESSALVAS`. Today only `rg_so_da_cnh`: a CNH prints the RG
#:   without its check digit (measured: 39% agreement with the RG card, see
#:   `app.services.divergencia_resolucao`), so an RG resting ONLY on an
#:   unconfirmed CNH reading is reported missing — the same machine-pending
#:   value the contract gate (`contrato_gerador.validacao_extracao`) already
#:   refuses to print unconfirmed. It clears on a human confirmation, a typed
#:   value, a newer reading from another document, or an RG-card reading of
#:   the SAME number (corroboration — the RG card carries the DV; stored RG stays as printed).
#: - ``documentos`` — the upload slots, in the owner's order: RG/CPF (filed
#:   as `rg`: the RG card carries the CPF; `cpf` stays catalogued but is not
#:   a slot — one card, one slot), CNH, CIN. All three are read
#:   automatically (`proveniencia.fontes.FONTES`). A CIN prints the CPF AS
#:   its identity number (órgão IIGDR) — RG == CPF is its valid state (owner
#:   directive 2026-09-23, contract 08), so a CIN alone can complete the item.
#: - ``documentos_legado`` — `cpf`-typed files already on record, shown
#:   read-only (no new uploads under that type from this item). Rows are
#:   never retyped; a CNH filed as `rg` before `cnh` existed (migration 142)
#:   now simply shows in the RG/CPF slot.
#:
#: Keys: `rg`/`cpf` overrides (`cliente_documento_checklist.item_key`) are
#: orphaned by the collapse — a per-number override does not say anything
#: about the pair, so carrying it onto `identidade` would invent a decision
#: nobody made.
#: Upload-slot labels — no longer identity-only (`_identidade_slots`/
#: `_extras_do_item` are generic over any item's `documentos` tuple; P0c
#: contract §F widened `_extras_do_item` past the identity item's origin).
_IDENTIDADE_ROTULOS: dict[str, str] = {
    "rg": "RG/CPF",
    "cin": "CIN",
    "cnh": "CNH",
    "cpf": "Arquivado como CPF",
    "serasa_crednet": "Serasa Crednet",
}

#: Label per identity column, for the "which ones are missing" read-out.
#: Same wording as `contrato_gerador.derivacao.ROTULO_QUALIFICACAO`, so the
#: checklist and the contract refusal name a field the same way.
_IDENTIDADE_CAMPO_ROTULOS: dict[str, str] = {
    "nome_oficial": "Nome oficial",
    "rg": "RG",
    "rg_orgao_expedidor": "Órgão expedidor do RG",
    "cpf": "CPF",
}


def _rg_so_da_cnh(cliente: dict, documentos: dict[str, dict]) -> bool:
    """Does the RG on record rest ONLY on an unconfirmed CNH reading?

    See the ``ressalvas`` bullet above. Corroborated (→ False) when a live
    `rg`-typed document read the same number: the RG card carries the check
    digit, so agreeing with it means the CNH's reading was complete.
    """
    if cliente.get("rg_origem") != "cnh" or _preenchido(cliente.get("rg_confirmado_em")):
        return False
    rg = only_alnum(str(cliente.get("rg") or "")).upper()
    cartao = documentos.get("rg") or {}
    lido = only_alnum(str(cartao.get("extracao_rg") or "")).upper()
    # `mesmo_rg` bridges the CNH's printed-without-DV `18.568.536` and the RG
    # card's `18.568.536-5` (comparison only — no DV is ever written).
    return not (rg and (lido == rg or mesmo_rg(rg, lido) is True))


#: Named rules under which a FILLED ``campos_todos`` column still does not
#: count. Keyed rather than inlined, like `_VALIDADORES`, so `ITENS` stays
#: plain data. ``colunas`` are the extra `clientes` columns the rule reads —
#: folded into `_CLIENTE_COLUNAS` so the select list stays derived.
_RESSALVAS: dict[str, dict[str, Any]] = {
    "rg_so_da_cnh": {
        "coluna": "rg",
        "colunas": ("rg_origem", "rg_confirmado_em"),
        "pendente": _rg_so_da_cnh,
        "rotulo": (
            "RG com dígito verificador (lido só da CNH, que costuma omiti-lo — "
            "confirme o número ou envie o RG/CPF)"
        ),
    },
}


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

#: Regimes a pacto antenupcial must establish (CC arts. 1.640 par. único,
#: 1.653): the convencional separação, participação final nos aquestos,
#: and comunhão universal for a marriage under Lei 6.515/77 (in force
#: 26/12/1977 — before it, comunhão universal was the legal default and
#: needed no pacto). `separacao_obrigatoria` is imposed by law, never by a
#: pacto; `comunhao_parcial` is the default regime.
_REGIMES_COM_PACTO = frozenset({"separacao_total", "participacao_final_aquestos"})
_INICIO_LEI_DIVORCIO = "1977-12-26"


def _exige_pacto_antenupcial(cliente: dict, documentos: dict[str, dict]) -> bool:
    if "pacto_antenupcial" in documentos:
        return True
    regime = cliente.get("regime_bens")
    if regime in _REGIMES_COM_PACTO:
        return True
    if regime == "comunhao_universal":
        casamento = str(cliente.get("data_casamento") or "")[:10]
        return not casamento or casamento >= _INICIO_LEI_DIVORCIO
    return False


#: Scoped items (``escopo``): the item is LISTED only when its predicate
#: holds — the same "drop, don't untick" posture `serasa_crednet` takes, so
#: an item that cannot apply to this person is never a permanently-red row.
_ESCOPOS: dict[str, dict[str, Any]] = {
    "pacto_antenupcial": {
        "colunas": ("regime_bens", "data_casamento"),
        "visivel": _exige_pacto_antenupcial,
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
            for nome in i.get("ressalvas", ())
            for col in _RESSALVAS[nome]["colunas"]
        ]
        + [
            col
            for i in ITENS
            for fonte in i.get("fontes", ())
            for col in _FONTES[fonte]["colunas"]
        ]
        + [
            col
            for i in ITENS
            if i.get("escopo")
            for col in _ESCOPOS[i["escopo"]]["colunas"]
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
    documentos: Optional[dict[str, dict]] = None,
) -> dict[str, bool]:
    """The rule, as a pure function: item key → is it satisfied?

    Pure and dependency-free on purpose. This is the part that decides whether
    a card claims a client's paperwork is complete, so it is testable without a
    database, an org, or an HTTP request.

    `documentos` (`tipo -> live row`, `_documentos_por_tipo`'s shape) feeds
    the ``ressalvas`` rules only — see `campos_faltando`.
    """
    cliente = cliente or {}
    out: dict[str, bool] = {}
    for item in ITENS:
        # ALL-of items (the identity item) — values only; a file never
        # satisfies one on its own. See `_IDENTIDADE_ROTULOS`' docblock.
        if item.get("campos_todos"):
            out[item["key"]] = not campos_faltando(cliente, item["key"], documentos)
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


def _ressalvas_pendentes(
    item: dict, cliente: dict, documentos: Optional[dict[str, dict]]
) -> dict[str, str]:
    """`column -> ressalva name` for every ``ressalvas`` rule of `item` that
    currently disqualifies a FILLED column. Empty columns are simply missing
    and never carry a ressalva."""
    out: dict[str, str] = {}
    for nome in item.get("ressalvas", ()):
        regra = _RESSALVAS[nome]
        col = regra["coluna"]
        if _preenchido(cliente.get(col)) and regra["pendente"](cliente, documentos or {}):
            out.setdefault(col, nome)
    return out


def campos_faltando(
    cliente: Optional[dict],
    item_key: str,
    documentos: Optional[dict[str, dict]] = None,
) -> list[str]:
    """The ``campos_todos`` columns of one item still missing, in declared order.

    Missing = empty, or filled but disqualified by one of the item's
    ``ressalvas`` (e.g. an RG resting only on an unconfirmed CNH reading).
    `documentos` (`tipo -> live row`) is what a ressalva may consult for
    corroboration; omitted, a ressalva sees no documents.

    `[]` for an item with no ``campos_todos`` — "nothing missing" is the
    honest answer for a question the item does not ask. Pure, like `derivar`,
    which reads its verdict off this same function so the tick and the
    "which one is missing" read-out can never disagree.
    """
    item = next((i for i in ITENS if i["key"] == item_key), None)
    if item is None:
        raise KeyError(item_key)
    cliente = cliente or {}
    ressalvas = _ressalvas_pendentes(item, cliente, documentos)
    return [
        col for col in item.get("campos_todos", ())
        if not _preenchido(cliente.get(col)) or col in ressalvas
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
    item: dict,
    cliente: Optional[dict],
    documentos: dict[str, dict],
    sugestoes: Optional[dict] = None,
) -> dict:
    """Additive keys: an ALL-of item's slots/missing-fields/hint, OR (P0c
    contract §F) a plain document item's upload slots alone.

    For an ALL-of item:
    - ``faltando`` / ``faltando_rotulos`` — the missing columns and their
      labels; a column disqualified by a ressalva carries the ressalva's own
      label, which says what to do about it.
    - ``ressalvas`` — `column -> ressalva name` for those columns.
    - ``faltando_com_sugestao`` — the missing columns for which a document
      reading is already waiting for a decision (`sugestoes`, keyed by column
      — `identidade_extracao_service.sugestoes_pendentes`), so the card can
      say "confirm the reading below" instead of "send another document".

    Empty for every item declaring neither `campos_todos` nor `documentos`,
    so their line shape is unchanged.
    """
    if item.get("campos_todos"):
        cliente_ = cliente or {}
        faltando = campos_faltando(cliente_, item["key"], documentos)
        ressalvas = _ressalvas_pendentes(item, cliente_, documentos)
        return {
            "faltando": faltando,
            "faltando_rotulos": [
                _RESSALVAS[ressalvas[c]]["rotulo"]
                if c in ressalvas
                else _IDENTIDADE_CAMPO_ROTULOS.get(c, c)
                for c in faltando
            ],
            "ressalvas": ressalvas,
            "faltando_com_sugestao": [c for c in faltando if (sugestoes or {}).get(c)],
            "documentos": _identidade_slots(item, documentos),
            "dica": item.get("dica"),
        }
    if item.get("documentos"):
        return {"documentos": _identidade_slots(item, documentos)}
    return {}


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


#: P0c contract §H8 — the Serasa Crednet item is scoped to certificandos
#: only (vendedores, their cônjuges, and compradores/cônjuges when the deal
#: `tem_permuta`), hidden for everyone else.
_ITEM_KEY_SERASA_CREDNET = "serasa_crednet"


def _e_certificando_no_atendimento(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str
) -> bool:
    """Is this cliente a certificando on THIS ONE (already-resolved,
    already-open) atendimento? The per-atendimento half of `_e_certificando`
    — pulled out so a cliente party to more than one open atendimento can be
    checked on each (see `_e_certificando`'s docstring for why that matters)."""
    rows = (
        _t(client, "atendimentos")
        .select("id, cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", atendimento_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return False
    atendimento = rows[0]
    if str(atendimento["cliente_id"]) == str(cliente_id):
        # The titular — always a comprador (migration 073's header).
        return tem_permuta_ativa(client, org_id, atendimento_id)

    partes = (
        _t(client, "atendimento_partes")
        .select("lado")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", atendimento_id)
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []
    if partes:
        lado = partes[0].get("lado") or "comprador"
        if lado == "vendedor":
            return True
        return tem_permuta_ativa(client, org_id, atendimento_id)

    # Not the titular, not a direct parte — a vendedor's registered spouse
    # counts too, even without their own `atendimento_partes` row.
    vendedores = (
        _t(client, "atendimento_partes")
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", atendimento_id)
        .eq("lado", "vendedor")
        .execute()
    ).data or []
    # PJ vendedor parties (migration 179) carry no cliente_id — a None in the
    # `in_` list is a bad filter, and a company has no spouse anyway.
    vendedores = [r for r in vendedores if r.get("cliente_id")]
    if vendedores:
        conjuge = (
            _t(client, CLIENTES_TABLE)
            .select("id")
            .eq("org_id", str(org_id))
            .eq("conjuge_cliente_id", str(cliente_id))
            .in_("id", [r["cliente_id"] for r in vendedores])
            .limit(1)
            .execute()
        ).data or []
        if conjuge:
            return True
    return False


def _e_certificando(client: Any, org_id: UUID, cliente_id: UUID) -> bool:
    """Is this cliente CURRENTLY a certificando on ANY of their open
    atendimentos?

    🔴 Fixed in this pass (P1, folder 883, 2026-09-24): this used to resolve
    "the" atendimento via `services.resolve_atendimento_id`, which only ever
    looks at `atendimentos.cliente_id` — the titular column. A vendedor (or
    a comprador's/vendedor's spouse) is NEVER that titular, so for them the
    lookup always found zero rows, raised `AmbiguousAtendimento([])`, and
    this function silently returned `False` — the `serasa_crednet` slot
    vanished for every vendedora added via "Adicionar vendedor", and the
    parte/cônjuge branches below (now `_e_certificando_no_atendimento`) were
    dead code: nothing ever reached them for a non-titular cliente.

    THE MULTI-ATENDIMENTO RULE (`services.atendimentos_abertos_
    certificaveis`): a cliente can be on more than one open atendimento at
    once. Rather than picking one (or refusing, as a WRITE-scoping resolver
    must), this checks EVERY one the cliente is currently on — as titular,
    as a parte, or as a vendedor's registered cônjuge — and shows the item
    the moment ANY of them says yes. No/ambiguous atendimento was already
    "nothing to show" before this fix and stays that way: zero candidates
    -> the loop below never runs -> `False`, same posture `empresas_service.
    listar` takes for its own empty case.
    """
    from app.modules.card_hub.services import atendimentos_abertos_certificaveis

    atendimento_ids = atendimentos_abertos_certificaveis(client, org_id, cliente_id)
    return any(
        _e_certificando_no_atendimento(client, org_id, cliente_id, atendimento_id)
        for atendimento_id in atendimento_ids
    )


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Every canonical item, derived, with any human override applied.

    Always returns every item, in `ITENS` order, whether or not an override row
    exists — the list is the contract, the rows are just opinions about it.
    The one exception is `serasa_crednet`, scoped to certificandos (§H8) —
    it is DROPPED from the response entirely for everyone else, not merely
    ticked/unticked, so a non-certificando's card never asks a document it
    does not need.
    """
    ensure_cliente(client, org_id, cliente_id)

    cliente = _cliente_row(client, org_id, cliente_id)
    documentos = _documentos_por_tipo(client, org_id, cliente_id)
    derivado = derivar(cliente, frozenset(documentos), documentos)

    res = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    )
    by_key = {r["item_key"]: r for r in (res.data or [])}

    itens_visiveis = tuple(
        i for i in ITENS
        if not i.get("escopo") or _ESCOPOS[i["escopo"]]["visivel"](cliente or {}, documentos)
    )
    if not _e_certificando(client, org_id, cliente_id):
        itens_visiveis = tuple(
            i for i in itens_visiveis if i["key"] != _ITEM_KEY_SERASA_CREDNET
        )

    sugestoes = identidade_svc.sugestoes_pendentes(client, org_id, cliente_id)
    itens = [
        _out(
            item,
            derivado[item["key"]],
            by_key.get(item["key"]),
            sugestoes.get(item["key"]),
            docs_svc.documento_resumo(documentos.get(item.get("documento", ""))),
            _extras_do_item(item, cliente, documentos, sugestoes),
        )
        for item in itens_visiveis
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
    # by COLUMN (`nome_oficial`, `rg`, `rg_orgao_expedidor`, `cpf`), which is
    # the shape the "Dados pessoais" form already reads.
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
    derivado = derivar(cliente, frozenset(documentos), documentos)
    # Same line shape the GET returns, `documento` included — the card writes
    # the PATCH response straight back into its list, so a narrower shape here
    # would blank the trash button until the next refetch. The pending
    # readings are read only for an ALL-of item, whose
    # `faltando_com_sugestao` needs them; every other item keeps `None`.
    sugestoes = (
        identidade_svc.sugestoes_pendentes(client, org_id, cliente_id)
        if item.get("campos_todos")
        else None
    )
    return _out(
        item,
        derivado[item["key"]],
        merged,
        None,
        docs_svc.documento_resumo(documentos.get(item.get("documento", ""))),
        _extras_do_item(item, cliente, documentos, sugestoes),
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
#: is deliberately absent: most addresses genuinely have none. So is
#: `endereco_bairro` (owner decision 2026-10-03: a missing bairro WARNS —
#: `ENDERECO_SEM_BAIRRO` in the contract derivation — it never blocks; signed
#: contracts sometimes omit it). The bairro column is still READ
#: (`_COLUNAS_QUALIFICACAO_CONTRATO`) so the aviso can fire.
_ENDERECO_CAMPOS_OBRIGATORIOS: tuple[str, ...] = (
    "endereco_logradouro", "endereco_numero",
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
    *_ENDERECO_CAMPOS_OBRIGATORIOS, "endereco_bairro",
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
