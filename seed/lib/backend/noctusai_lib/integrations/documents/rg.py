"""Read an RG (registro geral) number and its issuing body off a document.

Fifth sibling of `birthdate.py`, `name.py`, `gender.py` and `cpf.py`, and the
same shape on purpose: pure, label-anchored, import-free of the rest of the
package, returning `(value, confidence, matched_label)` with confidence as a
plain string — plus `find_rg_orgao(text)` for the issuer, which travels with
the number.

🔴 THE RG IS THE HARDEST OF THE FIVE, AND THE REASON IS STRUCTURAL
-------------------------------------------------------------------
There is no national RG format and no national check digit. Each state issues
its own, so `52.179.965-X` (SP, nine characters, alphanumeric check) and
`M-1.234.567` (MG, letter prefix) and a bare seven-digit number are all valid
RGs. That removes both anchors the other parsers rely on:

- Unlike `cpf`, there is no checksum to verify a candidate against. A run of
  eight digits is just a run of eight digits.
- Unlike `birthdate`, the value has no self-evident structure. A well-formed
  date is itself evidence; `52179965` is equally consistent with an RG, a
  matrícula, a protocol number, a CEP with a suffix, or half a phone number.

So this parser is **label-anchored or nothing**, the same discipline
`gender.py` applies to a bare `M`. There is exactly one exception, and it is
earned by punctuation rather than by a label — see `find_rg`.

🔴 AN RG IS NEVER AN ELEVEN-DIGIT NUMBER THAT PASSES THE CPF CHECK
-------------------------------------------------------------------
Both numbers are printed on the same card, frequently one line apart. Without
this guard, a CPF sitting under a `RG` label two lines up would be read as the
RG — a wrong value that is well-formed, plausible, and silently overwrites a
correct one. The `cpf` module's validator is the discriminator, and it is the
one place this module reaches outside itself: a shared *pure function*, no
package state, so the import-free property that matters (no cycles, no IO)
holds.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.labels import Achado, label_before

#: Same window as every sibling — these are the same document layouts.
_LABEL_WINDOW = 48

#: Labels that genuinely introduce the holder's own RG.
_RG_LABELS = (
    "REGISTRO GERAL",
    "CARTEIRA DE IDENTIDADE",
    "CEDULA DE IDENTIDADE",
    "DOC. IDENTIDADE",
    "DOCUMENTO DE IDENTIDADE",
    "IDENTIDADE",
    "R.G",
    "RG",
)

#: Labels that introduce somebody else's number, or a different number.
#:
#: `CPF` is the load-bearing decoy here for the reason in the module docstring.
#: `REGISTRO DE IMOVEIS` and `MATRICULA` matter because this same extractor
#: runs over documents uploaded to a property's file, where an eight-digit
#: number under the word "REGISTRO" is a matrícula, not a person.
_BLOCO_LABELS = (
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "NOME DA MAE",
    "NOME DO PAI",
    "RESPONSAVEL",
)

#: Labels naming a DIFFERENT KIND of number. `CPF` is the load-bearing one for
#: the reason in the module docstring; `MATRICULA` and `REGISTRO DE IMOVEIS`
#: matter because this same extractor runs over documents uploaded to a
#: property's file, where an eight-digit number is a matrícula, not a person.
_VALOR_LABELS = (
    "CPF",
    "C.P.F",
    "CNPJ",
    "MATRICULA",
    "REGISTRO DE IMOVEIS",
    "PIS",
    "PASEP",
    "CNS",
    "TITULO DE ELEITOR",
    "CERTIDAO",
)

#: `52.179.965-X`, `52.179.965-1`, `52179965X`, `1234567`.
#:
#: 5–10 digits in the body: below five is not an RG anywhere, and eleven or
#: more is a CPF or something longer. The optional check character is a digit
#: or `X` — `X` is a real check value in São Paulo, not a placeholder.
#:
#: The lookarounds stop the pattern from biting a slice out of a longer run.
_RG_RE = re.compile(
    r"(?<![\dXx.\-/])("
    r"\d{1,3}(?:\.\d{3})+-[\dXx]"       # 52.179.965-X
    r"|\d{1,3}(?:\.\d{3})+"             # 52.179.965
    r"|\d{5,10}-[\dXx]"                 # 52179965-X
    r"|\d{5,10}[Xx]"                    # 52179965X
    r"|\d{5,10}"                        # 52179965
    r")(?![\dXx.\-/])"
)

#: `SSP/SP`, `SSP-SP`, `SSP SP`, `DETRAN/RJ`, `PC/MG`, `SDS/PE`, `IFP/RJ`.
#: The issuer is 2–8 letters, the UF exactly two.
#: 🔴 THE SEPARATOR IS MANDATORY, and that is not cosmetic. With it optional,
#: `[A-Z]{2,8}` happily splits a single word: `NATURAL` matched as `NATUR` +
#: `AL` (Alagoas), yielding a confident `NATUR/AL` issuer out of an address
#: line. Requiring a real separator makes the acronym and the UF two tokens.
_ORGAO_RE = re.compile(
    r"\b([A-Z]{2,8})\s*(?:[/\-]\s*|\s+)"
    r"(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b"
)

#: Words that precede a state abbreviation without being an issuing body —
#: an address line ending in a city and UF is the common one.
_ORGAO_NAO = frozenset({
    "NASCIDO", "NATURAL", "NATURALIDADE", "CIDADE", "MUNICIPIO",
    "BAIRRO", "RUA", "AV", "AVENIDA", "CEP", "UF", "EM", "DE", "DO", "DA",
})


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed. As the siblings do."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


def only_alnum(value: str) -> str:
    """Digits and letters, punctuation dropped, upper-cased.

    Mirrors `social_wiring.normalizar_documento()` so a value compared in the
    database and a value compared here reduce identically.
    """
    return re.sub(r"[^0-9A-Z]", "", (value or "").upper())


def _label_before(haystack: str, at: int) -> Achado:
    """Delegate to the shared label window — see `labels.py`.

    The end-position-then-length rule there is what makes `CARTEIRA DE
    IDENTIDADE` win over the `IDENTIDADE` nested inside it.
    """
    return label_before(
        haystack,
        at,
        labels=_RG_LABELS,
        blocos=_BLOCO_LABELS,
        valores=_VALOR_LABELS,
        window=_LABEL_WINDOW,
    )


def _e_um_cpf(bruto: str) -> bool:
    """Is this candidate actually the CPF printed on the same card?

    See the module docstring — this is the guard that stops a CPF two lines
    below an `RG` label from being written as the RG.
    """
    apenas_digitos = re.sub(r"\D", "", bruto)
    return len(apenas_digitos) == 11 and _cpf_is_valid(apenas_digitos)


def find_rg(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the holder's RG number.

    Returns `(value, confidence, matched_label)`, the value **verbatim as
    printed** (`52.179.965-X`), confidence one of `"alta"` / `"baixa"` /
    `"nenhuma"`.

    - **alta** — label-anchored, and every labelled reading agrees.
    - **baixa** — unlabelled, but punctuated in the RG's own shape
      (`52.179.965-X`: dotted thousands plus a check character). That
      punctuation is the one piece of self-evidence an RG carries; a bare run
      of digits has none, so it is rejected outright rather than downgraded.
    - **nenhuma** — nothing, or readings that disagree. Disagreement is
      reported as absence, never resolved by preferring one.

    🔴 The value is NOT reformatted, unlike `cpf.find_cpf`. There is no
    canonical RG format to normalise to — imposing São Paulo's dotted form on
    a Minas Gerais number would invent punctuation the document does not
    have. Comparison is `only_alnum`'s job; storage keeps what was printed.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    rotulados: list[tuple[str, str]] = []
    pontuados: list[str] = []

    for m in _RG_RE.finditer(norm):
        bruto = m.group(1)
        if _e_um_cpf(bruto):
            continue

        achado = _label_before(norm, m.start())
        if achado.rejeitado:
            continue

        if achado.rotulo:
            # A labelled RG inside a filiação block is ambiguous, not wrong.
            # It joins the punctuated (low-confidence) pile rather than the
            # trusted one, so a human confirms whose document it is.
            if achado.rebaixado:
                pontuados.append(bruto)
            else:
                rotulados.append((bruto, achado.rotulo))
            continue

        # Unlabelled: only the fully punctuated shape survives. Dotted
        # thousands AND a check character — either alone is too common.
        if "." in bruto and "-" in bruto:
            pontuados.append(bruto)

    if rotulados:
        distintos = {only_alnum(v) for v, _ in rotulados}
        if len(distintos) == 1:
            return (rotulados[0][0], "alta", rotulados[0][1])
        return (None, "nenhuma", None)

    if pontuados:
        distintos = {only_alnum(v) for v in pontuados}
        if len(distintos) == 1:
            return (pontuados[0], "baixa", None)

    return (None, "nenhuma", None)


def find_rg_orgao(text: str) -> tuple[Optional[str], str]:
    """Extract the issuing body and UF — `SSP/SP`.

    Returns `(value, confidence)`. No matched label: the issuer is identified
    by its own SHAPE (an acronym bound to a state abbreviation), not by a
    label preceding it, so there is nothing to report.

    - **alta** — exactly one issuer-shaped token in the text.
    - **baixa** — several, and they disagree. The FIRST is returned rather
      than nothing, because on these layouts the issuer is printed adjacent to
      the RG and the later matches are almost always an address line; a human
      confirms. This is the one place in the family where a disagreement is
      not reported as absence, and the reason is that the alternative — an RG
      number stored with no issuer — is itself an incomplete qualification.
    - **nenhuma** — none.

    Normalised to `ORGAO/UF` regardless of the separator printed.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma")

    achados: list[str] = []
    for m in _ORGAO_RE.finditer(norm):
        orgao, uf = m.group(1), m.group(2)
        if orgao in _ORGAO_NAO or orgao == uf:
            continue
        achados.append(f"{orgao}/{uf}")

    if not achados:
        return (None, "nenhuma")
    if len(set(achados)) == 1:
        return (achados[0], "alta")
    return (achados[0], "baixa")


__all__ = ["find_rg", "find_rg_orgao", "normalize", "only_alnum"]
