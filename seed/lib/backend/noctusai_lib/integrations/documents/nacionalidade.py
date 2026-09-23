"""Read the holder's nationality (gentílico) off a Brazilian identity
document or certidão.

Resolves `NOC-REMEDIATE[nacionalidade-identity-parser]` (`types.py`,
2026-09-21): the contract generator's readiness gate hard-requires
`nacionalidade` for every party, the new-model CNH prints it
("NACIONALIDADE\\nBRASILEIRO") and a certidão de casamento/nascimento
routinely asserts it twice ("de nacionalidade brasileira", once per spouse
or per parent), yet nothing in this family read it before this module.

Ninth sibling of `birthdate.py` / `name.py` / `gender.py` / `cpf.py` /
`rg.py` / `civil_status.py`, and closest in shape to `gender.py`: a small,
CLOSED vocabulary read off a value-type label, never inferred.

🔴 WHY THIS FIELD IS NEVER GUESSED, UNLIKE `gender.py`'S WHOLE WORDS
----------------------------------------------------------------------
`gender.py` accepts an unlabelled `MASCULINO`/`FEMININO` at `baixa`, because
those words have essentially no other reason to appear in a Brazilian legal
document. A gentílico does not get that pass: "brasileiro" appears
constantly in narrative prose that has nothing to do with anyone's
qualification — "sociedade brasileira", "moeda corrente nacional", "leis
brasileiras", "em conformidade com a legislação brasileira". Accepting an
unlabelled reading would be a guess wearing a confidence score, exactly the
trap `civil_status.py`'s "NEVER GUESS" section warns about for
`estado_civil`. So this module follows THAT precedent, not `gender.py`'s: a
value is returned only when it sits next to an explicit `NACIONALIDADE`
label. A document that simply does not carry the field returns
`(None, "nenhuma", None)`, never a guess.

🔴 CANONICALISED ACROSS GRAMMATICAL GENDER — AND WHY THAT IS THE FIX, NOT A
COMPLICATION
----------------------------------------------------------------------------
Every sibling parser treats two labelled readings that disagree as a
misread and reports absence (`gender.py`'s "disagreement is absence"). A
certidão de casamento names BOTH spouses' nationalities, each printed in
that person's own grammatical gender — "de nacionalidade brasileira" for
the wife, "de nacionalidade brasileiro" for the husband. Compared as raw
strings those two readings are DIFFERENT, so the naive port of the
sibling rule would report `nenhuma` on the single most common certidão
this module exists to read.

The fix is not a special case for certidões — it is applying the same
"is this really a disagreement" question `civil_status.py` asks of an
AVERBAÇÃO, one level down: `brasileiro` and `brasileira` are not two
facts, they are one fact spelled two ways by Portuguese grammatical
agreement. So every reading is mapped to a CANONICAL (masculine) token
before the agreement check runs — see `_GENTILICOS` — and it is that
canonical value the "distinct readings" comparison is over. Two spouses
who are BOTH Brazilian now correctly agree at `alta`; two spouses of
genuinely different nationalities still, correctly, disagree and collapse
to `nenhuma` — real disagreement is not swallowed, only the grammatical-
gender false positive is.

The canonical form is deliberately the MASCULINE spelling, WITH its proper
Portuguese accent (`português`, not `PORTUGUES`) — this is the value
`clientes.nacionalidade` stores and the contract generator's own
inflection (`nacionalidade_flex`, `contrato_gerador/frases.py`) re-genders
back to feminine when the party's `genero` calls for it. Storing the
document's own grammatical gender instead would mean the STORED value
depends on which spouse's document happened to be read, which is not a
fact about the person worth persisting.

🔴 A GENUINE TWO-NATIONALITY DISAGREEMENT HAS NO RESOLUTION HERE
--------------------------------------------------------------------
Unlike `nome`/`cpf` (`real.py`'s `TitularEsperado` hint, `find_name_conflitos`
/ `find_cpf_conflitos`), this module does not expose a conflict-selection
path: doing so correctly would need to know WHICH of the two candidate
readings sits nearest which spouse's own name block — positional
machinery no sibling parser in this family currently shares, and building
it for one field would be scope creep this slice declines. A genuinely
disagreeing pair (two different nationalities) is reported as `nenhuma`,
the same "cannot choose, will not guess" answer every sibling gives.
Filed as `NOC-REMEDIATE[nacionalidade-titular-hint]` (see the marker
above `find_nacionalidade`, below) for whoever picks this up later.

🔴 FILIAÇÃO IS NOT THE HOLDER'S
-----------------------------------
An RG/CNH's `FILIAÇÃO` field names the holder's parents; a nationality
label demoted into that block (or `PAI`/`MAE`/`CONJUGE`) may belong to a
parent instead. Same block-opener discipline every sibling applies via
`labels.py` — a demoted reading is DROPPED, not queued at low confidence
(mirroring `civil_status.py`'s "never guess" treatment, not `gender.py`'s
baixa fallback, for the reason given above: this field has too many
narrative reasons to appear loose in text to trust an unanchored reading
at all).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from noctusai_lib.integrations.documents.labels import Achado, label_before

#: Same window every sibling parser uses — these are the same document
#: layouts.
_LABEL_WINDOW = 48

#: `NACIONALIDADE` alone already matches inside `DE NACIONALIDADE` (it is a
#: suffix of it) — both are listed anyway so the reported label is the
#: fuller, more legible one where it is present (see `labels.py`'s
#: "ends latest, longest wins" rule).
_NACIONALIDADE_LABELS = ("NACIONALIDADE", "DE NACIONALIDADE")

#: Same block-opener discipline every sibling applies: a value sitting
#: inside a FILIACAO/CONJUGE block may be a different person's — see the
#: module docstring.
_BLOCO_LABELS = (
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "NOME DA MAE",
    "NOME DO PAI",
    "RESPONSAVEL",
)

#: The closed gentílico vocabulary (per brief: at least these nineteen).
#: Each pattern matches EITHER grammatical gender the document might print;
#: the canonical value is always the masculine spelling, WITH its proper
#: accent — see the module docstring for why. Patterns are matched against
#: already-normalised (upper-case, accent-stripped) text, so no entry here
#: carries an accent itself.
#:
#: Ordered as a list of (pattern, canonical) pairs rather than a
#: word -> canonical dict, mirroring `civil_status._REGIME_BENS_PADROES`:
#: several of these need a hyphen-or-space variant (`norte-americano`) that
#: a single reverse-lookup dict cannot express as cleanly.
#: 🔴 EVERY PATTERN CARRIES AN OPTIONAL TRAILING `S?` FOR THE PLURAL
#: (2026-09-23, real, measured). `\bBRASILEIR[OA]\b` never matched
#: "BRASILEIROS" at all — the `O` in `[OA]` is a word character, and the
#: following `S` is ALSO a word character, so `\b` (a boundary between a
#: word char and a non-word char) never fires between them; the whole
#: pattern silently failed on a certidão's collective "somos brasileiros"
#: / "ambos... brasileiros" phrasing, the single most common gentílico
#: shape after the singular. Canonicalisation is unaffected: the plural
#: still maps to the SAME singular canonical token, exactly like the
#: masculine/feminine collapse this module already does.
_GENTILICOS: tuple[tuple["re.Pattern[str]", str], ...] = (
    (re.compile(r"\bBRASILEIR[OA]S?\b"), "brasileiro"),
    # -ês/-esa family: masc plural adds `ES` (não apenas `S`) — "português"
    # -> "portugueses", not "*portugueses" via a bare `S`. `[A]?S?` alone
    # can reach "portuguesa"/"portuguesas" but never "portugueses"; every
    # sibling in this family (japonês, chinês, francês, libanês) shares the
    # same irregular masculine plural and gets the same fix.
    (re.compile(r"\bPORTUGUES(?:ES|AS|A)?\b"), "português"),
    (re.compile(r"\bITALIAN[OA]S?\b"), "italiano"),
    # "espanhol" -> "espanhóis" (masc plural, `-OL` -> `-OIS`, irregular —
    # not a suffix of the singular stem); "espanhola"/"espanholas" are
    # regular. Kept as an explicit alternative rather than forced into the
    # generic optional-suffix shape the rest of this table uses.
    (re.compile(r"\b(?:ESPANHOL(?:A|AS)?|ESPANHOIS)\b"), "espanhol"),
    (re.compile(r"\bARGENTIN[OA]S?\b"), "argentino"),
    (re.compile(r"\bNORTE[- ]AMERICAN[OA]S?\b"), "norte-americano"),
    # ALEMA (fem sing "alemã") / ALEMAO (masc sing "alemão") / ALEMAS (fem
    # plural "alemãs") / ALEMAES (masc plural "alemães", O -> E in the
    # plural) — the one gentílico whose plural does not just append `S` to
    # the singular, so it cannot share the generic `S?` shape the rest do.
    (re.compile(r"\bALEMA(?:O|ES|S)?\b"), "alemão"),
    (re.compile(r"\bJAPONES(?:ES|AS|A)?\b"), "japonês"),
    (re.compile(r"\bCHINES(?:ES|AS|A)?\b"), "chinês"),
    (re.compile(r"\bFRANCES(?:ES|AS|A)?\b"), "francês"),
    (re.compile(r"\bURUGUAI[OA]S?\b"), "uruguaio"),
    (re.compile(r"\bPARAGUAI[OA]S?\b"), "paraguaio"),
    (re.compile(r"\bBOLIVIAN[OA]S?\b"), "boliviano"),
    (re.compile(r"\bPERUAN[OA]S?\b"), "peruano"),
    (re.compile(r"\bCHILEN[OA]S?\b"), "chileno"),
    (re.compile(r"\bCOLOMBIAN[OA]S?\b"), "colombiano"),
    (re.compile(r"\bVENEZUELAN[OA]S?\b"), "venezuelano"),
    (re.compile(r"\bANGOLAN[OA]S?\b"), "angolano"),
    (re.compile(r"\bLIBANES(?:ES|AS|A)?\b"), "libanês"),
)

#: Every canonical (masculine) token this module can return, in the order
#: declared above — the closed vocabulary `clientes.nacionalidade` (an
#: unconstrained TEXT column, like `estado_civil`) now has a real answer
#: for. Deduplicated defensively; today every pattern maps to a distinct
#: canonical already.
NACIONALIDADE_VALORES: tuple[str, ...] = tuple(
    dict.fromkeys(canonico for _, canonico in _GENTILICOS)
)

#: Canonical masculine -> feminine, for the contract generator's own
#: agreement (`contrato_gerador/frases.py::nacionalidade_flex`). Exported as
#: a function (`feminino`) rather than this dict directly, so the module
#: stays free to change its internal representation without breaking the
#: one product consumer.
_FEMININO: dict[str, str] = {
    "brasileiro": "brasileira",
    "português": "portuguesa",
    "italiano": "italiana",
    "espanhol": "espanhola",
    "argentino": "argentina",
    "norte-americano": "norte-americana",
    "alemão": "alemã",
    "japonês": "japonesa",
    "chinês": "chinesa",
    "francês": "francesa",
    "uruguaio": "uruguaia",
    "paraguaio": "paraguaia",
    "boliviano": "boliviana",
    "peruano": "peruana",
    "chileno": "chilena",
    "colombiano": "colombiana",
    "venezuelano": "venezuelana",
    "angolano": "angolana",
    "libanês": "libanesa",
}


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed. As every sibling
    parser in this package does."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


def _label_before(haystack: str, at: int) -> Achado:
    """Delegate to the shared label window — see `labels.py`."""
    return label_before(
        haystack,
        at,
        labels=_NACIONALIDADE_LABELS,
        blocos=_BLOCO_LABELS,
        window=_LABEL_WINDOW,
    )


def canonico(bruto: str) -> Optional[str]:
    """The canonical (masculine) gentílico a raw word/phrase names,
    regardless of which grammatical gender it was spelled in — or `None`
    when it is not one of ours.

    Whole-value matching (`fullmatch`), not a substring search: this is a
    LOOKUP over an already-isolated candidate value (a stored
    `clientes.nacionalidade`, or a human-typed form field), not a scan over
    document prose — `find_nacionalidade` below does that half, with its
    own label-anchoring and block-exclusion rules. Free text that is not in
    the vocabulary (a typo, a nationality this table does not yet carry)
    returns `None` so the caller can fall back to passing it through
    untouched, exactly as `contrato_gerador/frases.py::nacionalidade_flex`
    already did for "brasileiro(a)"-shaped legacy input before this
    function generalised the idea.
    """
    norm = normalize(bruto or "").strip()
    if not norm:
        return None
    for padrao, valor in _GENTILICOS:
        if padrao.fullmatch(norm):
            return valor
    return None


def feminino(nacionalidade_canonica: str) -> Optional[str]:
    """The feminine spelling of a CANONICAL (masculine) gentílico, or
    `None` when the input is not one of ours — a caller (the contract
    generator) is expected to fall back to the raw value in that case, the
    same "free text passes through untouched" contract `canonico` states."""
    return _FEMININO.get(nacionalidade_canonica)


# NOC-REMEDIATE[nacionalidade-titular-hint]: no `titular`-hint tie-break for
# a genuinely disagreeing two-nationality certidão exists here (mirroring
# `real.py`'s `_selecionar_nome`/`_selecionar_cpf` for `nome`/`cpf`) — it
# would need positional machinery (which candidate reading sits nearest
# which spouse's own name block) no sibling parser in this family shares
# yet, and building it for one field was scope creep this slice declined.
# See the module docstring's "A GENUINE TWO-NATIONALITY DISAGREEMENT" note
# for the full reasoning. — 2026-09-21
def find_nacionalidade(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the holder's nationality.

    Returns `(value, confidence, matched_label)` — value one of
    :data:`NACIONALIDADE_VALORES` (always the canonical MASCULINE spelling,
    whichever grammatical gender the document printed), confidence one of
    `"alta"` / `"nenhuma"` (the string values of `types.ExtractionConfidence`,
    kept as plain strings so this module stays import-free of the rest of
    the package — same shape as every sibling parser).

    - **alta** — every labelled reading, once canonicalised across
      grammatical gender, names the SAME nationality. Covers both the
      one-person case (an RG/CNH) and a certidão de casamento naming two
      spouses of the same nationality — see the module docstring.
    - **nenhuma** — no explicit `NACIONALIDADE` label anywhere (never
      guessed from an unlabelled gentílico — see the module docstring), or
      two labelled readings that disagree even after canonicalisation
      (a genuinely binational couple, or a misread).
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    rotulados: list[tuple[str, str]] = []
    for padrao, valor in _GENTILICOS:
        for m in padrao.finditer(norm):
            achado = _label_before(norm, m.start())
            if achado.rejeitado:
                continue
            if achado.rotulo and not achado.rebaixado:
                rotulados.append((valor, achado.rotulo))
            # Unlabelled or FILIAÇÃO-demoted: dropped, never queued at low
            # confidence — see the module docstring's "never guess" section.

    if not rotulados:
        return (None, "nenhuma", None)

    distintos = {v for v, _ in rotulados}
    if len(distintos) == 1:
        valor, rotulo = rotulados[0]
        return (valor, "alta", rotulo)
    return (None, "nenhuma", None)


__all__ = [
    "NACIONALIDADE_VALORES",
    "canonico",
    "feminino",
    "find_nacionalidade",
    "normalize",
]
