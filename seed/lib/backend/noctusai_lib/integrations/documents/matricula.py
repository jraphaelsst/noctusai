"""Read the número de matrícula off a Brazilian certidão de matrícula.

Fourth sibling of `birthdate.py`, `name.py` and `gender.py`, same contract:
pure, label-anchored, import-free of the rest of the package, returning
`(value, confidence, matched_label)` with confidence as a plain string.

🔴 WHY THIS IS HARDER THAN IT LOOKS
------------------------------------
A matrícula is wall-to-wall numbers. The first page alone carries the
matrícula number, a livro number, a folha number, a CNM/CNS code, an IPTU
inscription, a CEP, a CPF or two, several dates, an área in m², and a protocol
number — most of them 4–8 digits, i.e. indistinguishable from the answer by
shape alone.

So "find the longest number" and "find the first number" are both wrong, and
wrong in the worst way: they return something plausible on every document. The
only reliable signal is the LABEL, and this parser accepts nothing without one.

There is no low-confidence fallback for an unlabelled number, unlike
`birthdate` (where a well-formed date is itself evidence). An unlabelled
integer on a matrícula is evidence of nothing.

🔴 AND WHY THE FIRST PAGE MATTERS
---------------------------------
A matrícula's body TEXT cites other matrículas constantly — "originada da
matrícula 12.345", "conforme matrícula nº 9.876 deste registro". Those are real
labelled matches for a DIFFERENT property. Taking "the first labelled match"
would usually be right and occasionally attach a neighbour's registry number to
this sale, which is the kind of error nobody catches until a cartório rejects
the paperwork.

The rule that survives this: the document's OWN number is the one in the
heading, before the body starts. So matches are scored by how early they
appear, and a match that arrives after a body-opening marker is discarded
outright.

🔴 P2 CORPUS (2026-09): 4 OF 10 REAL READS WERE WRONG
------------------------------------------------------
Measured against 10 real certidões de matrícula (signed-contract answer
keys), the label-proximity rule above still returned a completely different
property's number on 4 of 10 documents, via three shapes:

1. **Stacked header** — the labels print on one row (`MATRICULA ... FICHA`),
   the values on the next. `_label_before` only sees FICHA, the nearer decoy,
   so the heading yields nothing even though the number IS right there.
2. **Body fallback grabs a citation** — once the heading yields nothing, the
   earliest labelled body match is offered as a low-confidence guess, and on
   every failing document that match was `REGISTRO ANTERIOR: ... MATRICULA
   Nº X` or an `M-X` citation of the PARENT property, not this one.
3. **Unlabelled heading** — some layouts print the number with no adjacent
   real label at all (only decoys within the 40-char window), so nothing
   passes the "must have a label" bar even though the CNM alongside it does.

The fix for (3), and a second opinion for (1): the **CNM** (Código Nacional
de Matrícula, Provimento CNJ 143/2023) is `CCCCCC.L.NNNNNNN-DD` — a 6-digit
CNS, a 1-digit livro (`2` = matrícula), a 7-digit zero-padded matrícula
number, and 2 check digits computed ISO 7064 MOD 97-10 over the 14 leading
digits. Unlike every other number on the page, a DV-valid CNM is
self-checking, so it OUTRANKS the label-proximity heading: it wins on
disagreement, fills in when the heading is empty, and is ignored outright
when its own check digits don't validate or when two valid CNMs disagree
with each other (disagreement is still absence, same rule as two heading
labels). It is only trusted for `livro == "2"` — other livro digits name a
different book (e.g. transcrição), not a matrícula. CNM search is scoped to
the heading zone (before the first body marker): the module's whole premise
is "the document's own number lives in the heading," and a body citation
could in principle carry its OWN valid CNM for the cited (different)
property.

The fix for (2): a body-fallback candidate whose left context names a
citation (`REGISTRO ANTERIOR`, `MATRICULA MAIOR`, `ORIGINADA`, `ORIUNDA`,
`PROVENIENTE`, or an `M-`/`R.<n>/M-` prefix directly before it) is excluded,
not offered. A blank ("nenhuma") beats confidently attaching a neighbour's
registry number to this sale.
"""
from __future__ import annotations

import re
from typing import Optional
from noctusai_lib.integrations.documents.text import fold_upper_collapsed

#: How far back from a number to look for its label.
_LABEL_WINDOW = 40

#: Labels that introduce THIS document's matrícula number.
_MATRICULA_LABELS = (
    "MATRICULA N",
    "MATRICULA NO",
    "MATRICULA NUMERO",
    "MATRICULA",
    "MAT.",
)

#: Labels that introduce a DIFFERENT number that sits in the same visual block.
#: Livro/folha are the dangerous ones: on most layouts they are printed inches
#: from the matrícula number, in the same typeface, on the same line.
_DECOY_LABELS = (
    "LIVRO",
    "FOLHA",
    "FLS",
    "FICHA",
    "PROTOCOLO",
    # 🔴 P1/883 live bug (2026-09-24): the running header print style
    # "Mat. 3917 - Página 1/3 - Prot. 123456" abbreviates it, and the
    # abbreviation is a DIFFERENT string than "PROTOCOLO" — rfind never
    # matches it, so the protocol number fell through to the nearest REAL
    # label ("MAT.") within its 40-char window and was misread as a SECOND
    # matrícula number. `TestDisagreementIsAbsence` then did its job
    # exactly as designed and reported "nenhuma" — correct given a false
    # disagreement, but the disagreement itself was the bug.
    "PROT.",
    "CNM",
    "CNS",
    "INSCRICAO",
    "IPTU",
    "CONTRIBUINTE",
    "CEP",
    "CPF",
    "CNPJ",
    "PROCESSO",
    "AREA",
)

#: Text that means the heading is over and the narrative has begun. Everything
#: after the FIRST of these is body, and every matrícula number in the body
#: belongs to some other property.
_BODY_MARKERS = (
    "ORIGINADA DA",
    "ORIUNDA DA",
    "PROVENIENTE DA",
    "AV.1",
    "AV-1",
    "AVERBACAO",
    "R.1",
    "R-1",
    "REGISTRO ANTERIOR",
    "PROPRIETARIO",
)

#: 3–12 digits, optionally dotted as thousands. Deliberately NOT anchored to a
#: fixed width: matrícula numbering is per-cartório and ranges from three
#: digits in small comarcas to eight or more in São Paulo.
_NUMERO = re.compile(r"\b(\d{1,3}(?:\.\d{3})+|\d{3,12})\b")

#: The CNM (Código Nacional de Matrícula, Provimento CNJ 143/2023):
#: CNS(6) . livro(1) . número-de-matrícula(7, zero-padded) - dígitos
#: verificadores(2). OCR loves to insert stray spaces around the `.`/`-`
#: separators (and sometimes wraps the whole thing in parentheses, which this
#: pattern doesn't need to match explicitly — the digits/dots/dash are enough).
_CNM = re.compile(r"\b(\d{6})\s*\.\s*(\d)\s*\.\s*(\d{7})\s*-\s*(\d{2})\b")

#: The stacked-header layout: labels on one row ("MATRICULA ... FICHA"),
#: values on the next, so `_label_before` only ever sees FICHA (the nearer
#: decoy) and the heading yields nothing. Matched as its own shape: MATRICULA,
#: then — separated only by pipes/dashes/underscores/whitespace, never digits
#: — FICHA, then the first following number is the matrícula, the second the
#: ficha. The ficha number is deliberately allowed to be as short as 1 digit
#: (it's usually just a page index like "01").
_STACKED_HEADER = re.compile(
    r"MATRICULA\s*(?:NO|N\.)?\s*[|\-_\s]*FICHA\s*[|\-_\s]*"
    r"(\d{1,3}(?:\.\d{3})+|\d{3,12})\s*[|\-_\s]*"
    r"(\d{1,3}(?:\.\d{3})+|\d{1,12})"
)

#: How far back from a body-fallback candidate to look for a citation marker.
_CITACAO_WINDOW = 60

#: A body number introduced by one of these is a citation of a DIFFERENT
#: property (the parent/predecessor), never this document's own number.
_CITACAO_MARCADORES = (
    "REGISTRO ANTERIOR",
    "MATRICULA MAIOR",
    "ORIGINADA",
    "ORIUNDA",
    "PROVENIENTE",
)

#: `R.<n>/M-<numero>` or a bare `M-<numero>` directly in front of the number —
#: the cartório shorthand for "averbação <n> of matrícula <numero>", i.e. a
#: citation of another property regardless of how far back a marker word is.
_CITACAO_PREFIXO = re.compile(r"(?:R\.\d+\s*/\s*)?M-\s*$")


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed."""
    return fold_upper_collapsed(text)


def _limpar(numero: str) -> str:
    """Drop thousands dots. `12.345` and `12345` are the same matrícula, and
    storing both spellings would make the column fail to match itself."""
    return numero.replace(".", "")


def _corpo_comeca_em(texto: str) -> int:
    """Offset of the first body marker, or len(texto) if the heading is all
    there is (a short certidão, or a transcription that lost its structure)."""
    posicoes = [texto.find(m) for m in _BODY_MARKERS]
    reais = [p for p in posicoes if p >= 0]
    return min(reais) if reais else len(texto)


def _label_before(haystack: str, at: int) -> tuple[Optional[str], bool]:
    """Nearest label preceding `at`, and whether it is a decoy.

    Proximity decides: on these layouts a number belongs to whichever label sits
    closest to its left, and a decoy that is nearer than a real label means the
    number is the decoy's.
    """
    window = haystack[max(0, at - _LABEL_WINDOW) : at]
    melhor: Optional[str] = None
    melhor_pos = -1
    decoy = False
    for rotulo in _MATRICULA_LABELS + _DECOY_LABELS:
        pos = window.rfind(rotulo)
        # `>=` so that on a tie the LONGER, more specific label wins —
        # "MATRICULA N" must beat the "MATRICULA" prefix inside it.
        if pos > melhor_pos or (pos == melhor_pos and pos >= 0 and melhor and len(rotulo) > len(melhor)):
            melhor_pos = pos
            melhor = rotulo
            decoy = rotulo in _DECOY_LABELS
    if melhor is None or melhor_pos < 0:
        return (None, False)
    return (melhor, decoy)


def _cnm_dv_valido(bloco14: str, dv: str) -> bool:
    """ISO 7064 MOD 97-10 over the 14 leading digits (CNS + livro + número)."""
    esperado = (98 - (int(bloco14) * 100) % 97) % 97
    return esperado == int(dv)


def _cnm_sinal(texto: str) -> Optional[str]:
    """The matrícula number carried by a DV-valid, livro-2 CNM in `texto` —
    or `None` if there isn't exactly one.

    A DV-valid CNM is self-checking, unlike anything else on the page — no
    other number here carries its own arithmetic proof. Multiple valid CNMs
    that disagree with each other are exactly as untrustworthy as two
    disagreeing heading labels: the rung is dropped, not resolved by
    guessing which one is right.
    """
    candidatos = set()
    for m in _CNM.finditer(texto):
        cns, livro, numero, dv = m.groups()
        if livro != "2":
            continue
        if not _cnm_dv_valido(cns + livro + numero, dv):
            continue
        candidatos.add(str(int(numero)))
    if len(candidatos) == 1:
        return next(iter(candidatos))
    return None


def _e_citacao(haystack: str, at: int) -> bool:
    """Is the number starting at `at` introduced by a citation of another
    property (a parent/predecessor matrícula named in this one's body)?"""
    window = haystack[max(0, at - _CITACAO_WINDOW) : at]
    if any(marcador in window for marcador in _CITACAO_MARCADORES):
        return True
    return bool(_CITACAO_PREFIXO.search(window))


def find_matricula(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract this document's própria matrícula number.

    Returns `(value, confidence, matched_label)`, confidence being one of
    `"alta"` / `"baixa"` / `"nenhuma"` — the string values of
    `types.ExtractionConfidence`, kept as plain strings so this module stays
    import-free of the rest of the package.

    - **alta** — label-anchored, in the heading, and every heading match
      agrees; OR a DV-valid CNM (see module docstring), which is trusted at
      alta on its own and overrides a disagreeing/absent heading.
    - **baixa** — label-anchored but only found in the BODY, i.e. the heading
      did not survive transcription, and that body match isn't a citation of
      another property. Plausible and worth offering, not worth writing
      unattended.
    - **nenhuma** — no labelled, non-cited number anywhere, or heading matches
      that disagree with no CNM to arbitrate.
      🔴 Disagreement is absence: two different numbers both labelled
      "matrícula" in the heading means the layout was misread, and choosing one
      would attach a registry number to a property at random.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    fim_do_cabecalho = _corpo_comeca_em(norm)
    cabecalho: list[tuple[str, str]] = []
    corpo: list[tuple[str, str]] = []

    for m in _NUMERO.finditer(norm):
        rotulo, decoy = _label_before(norm, m.start())
        if decoy or not rotulo:
            continue
        valor = _limpar(m.group(1))
        if m.start() < fim_do_cabecalho:
            cabecalho.append((valor, rotulo))
        elif not _e_citacao(norm, m.start()):
            corpo.append((valor, rotulo))

    # Stacked header: labels on one row, values on the next — `_label_before`
    # never sees this, so it's matched as its own shape and fed in as a
    # heading match.
    empilhado = _STACKED_HEADER.search(norm)
    if empilhado and empilhado.start() < fim_do_cabecalho:
        cabecalho.append((_limpar(empilhado.group(1)), "MATRICULA FICHA"))

    if cabecalho:
        distintos = {v for v, _ in cabecalho}
        if len(distintos) == 1:
            valor, rotulo = cabecalho[0]
            resultado = (valor, "alta", rotulo)
        else:
            resultado = (None, "nenhuma", None)
    elif corpo:
        # The heading did not survive. The EARLIEST labelled, non-cited number
        # is the best remaining guess, and it is offered as a guess.
        valor, rotulo = corpo[0]
        resultado = (valor, "baixa", rotulo)
    else:
        resultado = (None, "nenhuma", None)

    # The CNM is self-checking and outranks everything above it: it confirms
    # an agreeing heading, fills in an absent one, and overrides a
    # disagreeing one. Scoped to the heading zone — a body citation could in
    # principle carry its own valid CNM for the CITED (different) property.
    cnm_valor = _cnm_sinal(norm[:fim_do_cabecalho])
    if cnm_valor is not None and not (resultado[1] == "alta" and resultado[0] == cnm_valor):
        return (cnm_valor, "alta", "CNM")

    return resultado


__all__ = ["find_matricula", "normalize"]
