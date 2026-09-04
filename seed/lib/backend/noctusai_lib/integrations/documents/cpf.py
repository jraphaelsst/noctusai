"""Read a CPF off a Brazilian identity document.

Fourth sibling of `birthdate.py`, `name.py` and `gender.py`, and the same shape
on purpose: pure, label-anchored, import-free of the rest of the package,
returning `(value, confidence, matched_label)` with confidence as a plain
string.

🔴 WHY THIS FIELD CAN BE TRUSTED UNLABELLED, WHEN `gender` CANNOT
-----------------------------------------------------------------
`gender.py` refuses every unlabelled single letter because its alphabet has two
elements, so a stray `M` is indistinguishable from a real reading. A CPF is the
opposite case: it carries its own **check digits**. Two of its eleven digits are
a mod-11 function of the other nine, so a random eleven-digit run has roughly a
1-in-100 chance of passing, and an OCR digit confusion (`0/O`, `5/S`, `8/B`)
almost always breaks it.

That makes the check digit the anchor that a label is for the other fields:

- **alta** — the number sits next to a CPF label AND the check digits verify.
- **baixa** — one of the two, not both. A verified number with no label (very
  common: the CPF is printed bare under the photo on a modern RG), or a
  labelled number whose check digits fail (almost always an OCR misread of a
  real CPF — worth showing a human, never worth writing unattended).
- **nenhuma** — nothing, or readings that disagree.

🔴 DISAGREEMENT IS ABSENCE, NOT A VOTE
---------------------------------------
Same rule the sibling parsers follow. An RG commonly prints the holder's CPF
*and* a parent's; if two different labelled CPFs are found, the layout was
misread and picking one would write a coin-flip onto a person's record.

🔴 THE FORMATTED FORM IS RETURNED, NOT THE DIGITS
--------------------------------------------------
`412.954.238-98`, always, however it was found. The consuming column
(`social_wiring.clientes.cpf`) is compared through `normalizar_documento()`, so
storage does not depend on punctuation — but a human reading the card, and a
contract printing the qualification, both want the canonical form. Normalising
here means no consumer has to.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from noctusai_lib.integrations.documents.labels import Achado, label_before

#: How far back from a value to look for its label. Matches the window the
#: sibling parsers use — these are the same document layouts.
_LABEL_WINDOW = 48

#: Labels that genuinely introduce the holder's own CPF.
_CPF_LABELS = (
    "CPF",
    "C.P.F",
    "CADASTRO DE PESSOA FISICA",
    "CADASTRO DE PESSOAS FISICAS",
    "CAD. PESSOA FISICA",
)

#: Block openers naming a DIFFERENT PERSON. A `CPF` label after one of these
#: is ambiguous rather than wrong — the block may have ended — so it demotes
#: the reading instead of dropping it. See `labels.py`.
_BLOCO_LABELS = (
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "NOME DA MAE",
    "NOME DO PAI",
    "RESPONSAVEL",
    "TITULAR",
)

#: Labels naming a DIFFERENT KIND of number for the same person. Unambiguous:
#: if one of these is nearest, the value is not a CPF. A CNPJ is fourteen
#: digits so it cannot be mistaken by length either — it is listed so a future
#: looser numeric pattern cannot reintroduce the confusion.
_VALOR_LABELS = (
    "CNPJ",
    "PIS",
    "PASEP",
    "INSCRICAO ESTADUAL",
)

#: `412.954.238-98` or `41295423898`. The lookarounds are load-bearing: without
#: them the bare-digit alternative would match the first eleven digits of a
#: longer run — a fourteen-digit CNPJ, or a matrícula.
_CPF_RE = re.compile(r"(?<![\d.-])(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?![\d.-])")


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed.

    Same normalisation the sibling parsers apply, for the same reason: an OCR
    pass produces `C.P.F.` and `Cpf` in equal measure.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


def only_digits(value: str) -> str:
    """The eleven digits, whatever punctuation they arrived in."""
    return re.sub(r"\D", "", value or "")


def is_valid(value: str) -> bool:
    """Do this CPF's two check digits verify?

    The standard mod-11 algorithm. Rejects the ten repdigit strings
    (`00000000000` … `99999999999`) explicitly: every one of them satisfies the
    arithmetic, and all ten are invalid CPFs. They are also what a form filled
    with placeholder data looks like, so accepting them would let test data
    through the one gate this module has.
    """
    digits = only_digits(value)
    if len(digits) != 11 or digits == digits[0] * 11:
        return False

    for tamanho in (9, 10):
        soma = sum(
            int(digits[i]) * (tamanho + 1 - i) for i in range(tamanho)
        )
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != int(digits[tamanho]):
            return False
    return True


def format_cpf(value: str) -> Optional[str]:
    """`41295423898` → `412.954.238-98`. None when it is not eleven digits."""
    digits = only_digits(value)
    if len(digits) != 11:
        return None
    return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"


def _label_before(haystack: str, at: int) -> Achado:
    """Delegate to the shared label window — see `labels.py`."""
    return label_before(
        haystack,
        at,
        labels=_CPF_LABELS,
        blocos=_BLOCO_LABELS,
        valores=_VALOR_LABELS,
        window=_LABEL_WINDOW,
    )


def find_cpf(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the holder's CPF.

    Returns `(value, confidence, matched_label)` — the value formatted as
    `412.954.238-98`, confidence one of `"alta"` / `"baixa"` / `"nenhuma"`
    (the string values of `types.ExtractionConfidence`, kept as plain strings
    so this module stays import-free of the rest of the package).

    See the module docstring for why an unlabelled CPF is acceptable at low
    confidence when an unlabelled gender is not.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    #: (formatted, label or None, trusted) — `trusted` folds together the two
    #: things that can demote a reading: a failed checksum, and a label sitting
    #: inside somebody else's block.
    achados: list[tuple[str, Optional[str], bool]] = []

    for m in _CPF_RE.finditer(norm):
        bruto = m.group(1)
        formatado = format_cpf(bruto)
        if formatado is None:
            continue
        achado = _label_before(norm, m.start())
        if achado.rejeitado:
            continue
        achados.append(
            (formatado, achado.rotulo, is_valid(bruto) and not achado.rebaixado)
        )

    if not achados:
        return (None, "nenhuma", None)

    # Labelled AND verified — the only combination trusted unattended.
    fortes = [(v, r) for v, r, ok in achados if r is not None and ok]
    if fortes:
        distintos = {v for v, _ in fortes}
        if len(distintos) == 1:
            return (fortes[0][0], "alta", fortes[0][1])
        return (None, "nenhuma", None)

    # Verified but unlabelled — the bare CPF under the photo on a modern RG.
    verificados = [(v, r) for v, r, ok in achados if ok]
    if verificados:
        distintos = {v for v, _ in verificados}
        if len(distintos) == 1:
            return (verificados[0][0], "baixa", verificados[0][1])
        return (None, "nenhuma", None)

    # Labelled but the checksum fails — almost always an OCR digit confusion
    # over a real CPF. Worth a human's eyes; never worth writing.
    rotulados = [(v, r) for v, r, _ in achados if r is not None]
    if rotulados:
        distintos = {v for v, _ in rotulados}
        if len(distintos) == 1:
            return (rotulados[0][0], "baixa", rotulados[0][1])

    return (None, "nenhuma", None)


__all__ = ["find_cpf", "format_cpf", "is_valid", "normalize", "only_digits"]
