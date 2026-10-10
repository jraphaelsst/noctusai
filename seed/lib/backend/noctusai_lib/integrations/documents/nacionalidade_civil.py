"""Derive `nacionalidade="brasileiro"` from a Brazilian civil RG issuer, when
no document ever prints the holder's nationality at all.

🔴 THIS IS NOT `nacionalidade.py` GROWING A GUESS
----------------------------------------------------
`nacionalidade.find_nacionalidade` is deliberately "never inferred from
prose" — see that module's own docstring for why a bare gentílico cannot be
trusted unlabelled. This module does not change that contract, extend its
vocabulary, or call into it. It answers a DIFFERENT question, off a
DIFFERENT signal: not "does this text say a nationality", but "does the
BODY THAT ISSUED THIS PERSON'S RG only ever issue to Brazilians".

P2 corpus, 2026-09 (26 real identity documents): 14 print `nacionalidade`
directly and are read by `nacionalidade.py`; the other 12 (older CNH
models, some RGs/CINs) never print the field at all, so those parties stay
without a `nacionalidade` the contract generator's readiness gate hard-
requires (`documento_checklist_service._CAMPOS_QUALIFICACAO_CONTRATO`).

THE LEGAL BASIS
----------------
A civil *carteira de identidade* (RG) issued by a state identification
authority — SSP/xx, SESP, SSPDS, PC/xx, IIRGD, IFP, DETRAN-xx as RG issuer,
etc. — is issued only to Brazilian nationals. A foreigner instead receives
an RNE/RNM/CRNM ("Registro Nacional de Estrangeiros/Migratório", or the
current "Carteira de Registro Nacional Migratório") from the Polícia
Federal, never from a state civil-identification body. The new CIN
(Carteira de Identidade Nacional) follows the same rule: issued to
Brazilians, unless the document itself states otherwise.

So `rg_orgao` (`rg.find_rg_orgao`'s own `ORGAO/UF` reading, already on the
record or read off THIS document) is evidence about nationality — just
never strong enough to earn more than `baixa`, the same tier every other
unlabelled-but-not-baseless reading in this package earns.

THE CLOSED WHITELIST, AND WHY IT IS A WHITELIST NOT A BLOCKLIST
-------------------------------------------------------------------
`_ORGAOS_CIVIS_ESTADUAIS` is deliberately closed: an issuer acronym this
module does not recognise infers NOTHING, rather than assuming
"not on the foreign blocklist, so it must be a state one". The foreign set
(`_ORGAOS_ESTRANGEIROS_RE`) is listed anyway, and checked FIRST, so the
refusal to infer from an RNE/RNM/CRNM/Polícia-Federal-issued document is a
documented decision rather than a side effect of an acronym simply not
being on the whitelist.

THREE WAYS THIS NEVER OVERWRITES A BETTER FACT
---------------------------------------------------
1. `nacionalidade_lida` — a nationality the SAME document (or a certidão)
   already prints outranks any inference; when given, nothing is derived.
2. `nacionalidade_atual_confirmada` — a human already vouched for the
   party's `nacionalidade`; a low-confidence guess must never contest that,
   so nothing is derived. (Whether the party has ANY existing value at all,
   confirmed or not, is the CALLER's gate — see
   `identidade_extracao_service._nacionalidade_atual` — this flag is the
   inner, defence-in-depth half of the same rule.)
3. The closed whitelist itself — an issuer this module does not recognise,
   or one on the explicit foreign list, infers nothing.

Every derived reading is returned at `baixa` confidence with an explicit
`inferida: ...` provenance string, never `alta` — it rides through the same
machine-pending, human-gated suggestion path every other `baixa` extraction
does (`identidade_extracao_service.aplicar_campos_ao_cliente`'s D1 rule; the
contract generator's own gate still requires a human confirm it, same as
any other `nacionalidade` suggestion).
"""
from __future__ import annotations

import re
from typing import Optional
from noctusai_lib.integrations.documents.text import fold_upper_collapsed

#: The value this module ever derives. A gentílico OTHER than "brasileiro"
#: is never inferred — issuance by a state civil authority only tells us
#: the holder IS Brazilian, never which OTHER nationality they might also
#: hold.
VALOR_INFERIDO = "brasileiro"

#: Every derived reading lands here, never higher — see the module docstring.
CONFIANCA_INFERIDA = "baixa"

#: Closed whitelist of state civil identification issuing-body acronyms —
#: the half of `rg_orgao` ("SSP/SP") BEFORE the `/UF`. Every one of these is
#: a state secretariat/institute/department that issues civil RGs (or, for
#: `DETRAN`, the state body some older CNH models name as the identity
#: document's own issuer) — never a federal or foreign-national authority.
#: Deliberately not exhaustive of every state's own spelling; extend this
#: set deliberately, with a citation, the same way `rg.py`'s own tables are
#: extended — never widen it to "everything not blocked" below.
_ORGAOS_CIVIS_ESTADUAIS = frozenset({
    "SSP", "SESP", "SSPDS", "SDS", "SJTC", "SJS", "PC", "DETRAN",
    "IFP", "IGP", "ITEP", "DGPC", "DIC",
})

#: The CIN's own issuer, matched as a SUBSTRING (mirrors
#: `identidade_extracao_service.ORGAO_CIN`/`_e_cin`) rather than the exact
#: acronym-before-slash the state table above matches on: `IIGDR` is what
#: the P2 corpus actually measured a CIN print; `IIRGD` is the institute's
#: own correct initialism (Instituto de Identificação Ricardo Gumbleton
#: Daunt) — both spellings are carried so an OCR/transcription variance in
#: either direction still resolves.
_ORGAOS_CIN = ("IIGDR", "IIRGD")

#: Never inferred from — a foreign national's own document, or the federal
#: body that issues it. Checked BEFORE the whitelist so an acronym that
#: happens to also appear inside one of these (there are none today) can
#: never fall through to a state-civil match. Matched with word boundaries
#: over normalised (accent-stripped, upper-cased) text, so "Polícia
#: Federal" and "POLICIA FEDERAL" are the same check, and this never
#: partial-matches an unrelated acronym that merely CONTAINS these letters.
_ORGAOS_ESTRANGEIROS_RE = re.compile(
    r"\b(?:RNE|RNM|CRNM|PF|POLICIA FEDERAL|MRE)\b"
)


def _normalize(value: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed — same shape every
    sibling parser in this package uses."""
    return fold_upper_collapsed(value).strip()


def _acronimo(rg_orgao_normalizado: str) -> str:
    """The issuer half of an `ORGAO/UF`-shaped reading — everything before
    the first separator. Tolerant of `/`, `-` or a bare space, since a
    caller may hand this a raw label read rather than `rg.find_rg_orgao`'s
    own normalised `ORGAO/UF` output."""
    return re.split(r"[/\-\s]", rg_orgao_normalizado, maxsplit=1)[0]


def derivar_nacionalidade_civil(
    rg_orgao: Optional[str],
    nacionalidade_lida: Optional[str] = None,
    *,
    nacionalidade_atual_confirmada: bool = False,
) -> tuple[Optional[str], str, Optional[str]]:
    """`(valor, confianca, rotulo)` — `"brasileiro"` / `"baixa"` / an
    explicit `"inferida: ..."` provenance string, or `(None, "nenhuma",
    None)` when nothing may be derived.

    Never called when a document already prints a nationality
    (`nacionalidade_lida`) or the party's record already carries a human-
    confirmed one (`nacionalidade_atual_confirmada`) — either one alone is
    enough to refuse, no whitelist check even runs. Otherwise: an issuer on
    the explicit foreign list (`RNE`/`RNM`/`CRNM`/`PF`/`POLICIA
    FEDERAL`/`MRE`) never infers; a CIN issuer infers at `"inferida: CIN"`;
    an issuer on the closed state-civil whitelist infers at
    `"inferida: RG civil estadual (<acronimo>)"`; anything else — including
    no issuer at all — infers nothing.
    """
    if nacionalidade_lida or nacionalidade_atual_confirmada or not rg_orgao:
        return (None, "nenhuma", None)

    norm = _normalize(rg_orgao)
    if not norm:
        return (None, "nenhuma", None)

    if _ORGAOS_ESTRANGEIROS_RE.search(norm):
        return (None, "nenhuma", None)

    if any(marca in norm for marca in _ORGAOS_CIN):
        return (VALOR_INFERIDO, CONFIANCA_INFERIDA, "inferida: CIN")

    acronimo = _acronimo(norm)
    if acronimo in _ORGAOS_CIVIS_ESTADUAIS:
        return (
            VALOR_INFERIDO,
            CONFIANCA_INFERIDA,
            f"inferida: RG civil estadual ({acronimo})",
        )

    return (None, "nenhuma", None)


__all__ = [
    "CONFIANCA_INFERIDA",
    "VALOR_INFERIDO",
    "derivar_nacionalidade_civil",
]
