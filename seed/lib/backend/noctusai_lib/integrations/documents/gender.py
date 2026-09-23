"""Read the holder's sex/gender off a Brazilian identity document.

Third sibling of `birthdate.py` and `name.py`, and the same shape on purpose:
pure, label-anchored, import-free of the rest of the package, returning
`(value, confidence, matched_label)` with confidence as a plain string.

🔴 WHY THIS FIELD IS *EASIER* TO READ THAN THE OTHERS, AND WHY THAT IS A TRAP
-----------------------------------------------------------------------------
A birthdate is eight digits that OCR routinely mangles; a name is free text. A
sex field is one character from a two-element alphabet, so the naive reading is
"just find M or F" — and that is exactly the failure mode.

A single letter appears everywhere on an RG: in the issuing state (`SP`), in
`FILIACAO`, in a middle initial, in `DOC. ORIGEM`, in the word `MASC` inside
some other word. A bare letter scan would return a confident answer on almost
any document and be wrong on many. So an unlabelled single letter is NEVER
accepted here — unlike `birthdate`, which does allow a lone plausible date as a
low-confidence guess, because a well-formed date is itself strong evidence.

The rule is therefore: the value must sit next to a sex label, or it does not
exist. A full word (`MASCULINO`) is accepted unlabelled at LOW confidence,
because that word has no other reason to be on the document.

WHY IT NORMALISES TO WORDS
--------------------------
The consuming column holds "Masculino" / "Feminino" verbatim — it is what the
UI's dropdown offers and what an operator would have typed. Returning `"M"`
would mean every reader decoding it, and the first reader that forgot would
store a letter where the rest of the product expects a word.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from noctusai_lib.integrations.documents.labels import Achado, label_before

MASCULINO = "Masculino"
FEMININO = "Feminino"

#: How far back from a value to look for its label. Matches `birthdate`'s
#: window — the layouts are the same documents.
_LABEL_WINDOW = 48

#: Labels that genuinely introduce the holder's sex. `SEXO` is what the RG and
#: the CNH both print.
_SEX_LABELS = (
    "SEXO",
    "GENERO",
    "SEX",
)

#: Labels that introduce SOMEBODY ELSE's sex, or something that is not a sex at
#: all but sits next to a lone letter. Same decoy discipline `birthdate` uses
#: for `DATA DE EMISSAO` — the field exists, it is simply not ours.
#:
#: `FILIACAO` is the important one: a parent's name block is where a stray
#: initial is most likely to be found, and attributing a parent's anything to
#: the holder is the error this whole module family is built to avoid.
#: 🔴 ALL of these are BLOCK OPENERS, not value-type decoys — see `labels.py`.
#: That distinction was invisible while this module owned its own window, and
#: it was wrong here: `FILIACAO MARIA DE TAL SEXO: F` returned Feminino at
#: HIGH confidence, attributing a parent's sex to the holder and writing it
#: unattended. It now demotes to `baixa` and lands in the confirm queue.
_BLOCO_LABELS = (
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "NOME DA MAE",
    "NOME DO PAI",
)

#: Whole words, which are unambiguous wherever they appear.
_PALAVRAS = {
    "MASCULINO": MASCULINO,
    "MASC": MASCULINO,
    "HOMEM": MASCULINO,
    "FEMININO": FEMININO,
    "FEM": FEMININO,
    "MULHER": FEMININO,
}

#: Single letters, accepted ONLY immediately after a sex label.
_LETRAS = {"M": MASCULINO, "F": FEMININO}

_PALAVRA_RE = re.compile(
    r"\b(" + "|".join(sorted(_PALAVRAS, key=len, reverse=True)) + r")\b"
)
_LETRA_RE = re.compile(r"\b([MF])\b")


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed.

    Same normalisation the sibling parsers apply, for the same reason: an OCR
    pass over a photographed card produces `SÉXO` and `Masculino` in equal
    measure, and matching against every casing/accent variant is a losing game.
    """
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
        labels=_SEX_LABELS,
        blocos=_BLOCO_LABELS,
        window=_LABEL_WINDOW,
    )


def canonical_gender(valor: Optional[str]) -> Optional[str]:
    """Any spelling of a sex value -> the canonical `Masculino`/`Feminino`.

    The single normaliser for every writer of `clientes.genero`-shaped
    columns: this module's own reads already use the words, but a matrícula
    qualificação (`matricula_qualificacao`) carries `m`/`f` codes, and an
    operator may have typed `masc`. Writing a code where the rest of the
    product expects a word turned every comparison between two sources into a
    false disagreement (`"Masculino" != "m"`) — a conflict for a human to
    resolve about a fact that never actually differed.

    Returns None for anything that is not unambiguously one of the two —
    never a guess.
    """
    s = re.sub(r"[^A-Z ]", " ", normalize(valor or "")).strip()
    if not s:
        return None
    if s in _LETRAS:
        return _LETRAS[s]
    palavra = s.split()[0]
    if palavra in _PALAVRAS:
        return _PALAVRAS[palavra]
    if palavra in {"MASCULINA", "MASCULINE", "MALE"}:
        return MASCULINO
    if palavra in {"FEMININA", "FEMALE"}:
        return FEMININO
    return None


# ─── Machine-readable zone (CIN / passport back side) ──────────────────────
#
# The new Carteira de Identidade Nacional carries an ICAO 9303 TD1 MRZ. Its
# second line is `YYMMDD C S YYMMDD C NAT ...` — birthdate + check digit, the
# SEX letter, expiry + check digit, nationality. Unlike a lone `M` anywhere
# else on the card, that letter is structurally anchored: it sits between two
# dates whose check digits must both verify, so an OCR misread of the
# surrounding digits kills the match instead of producing a wrong value.

_MRZ_RE = re.compile(r"(?<![0-9A-Z<])(\d{6})(\d)([MF])(\d{6})(\d)([A-Z<]{3})")
_MRZ_PESOS = (7, 3, 1)


def _mrz_check(digitos: str) -> int:
    return sum(int(c) * _MRZ_PESOS[i % 3] for i, c in enumerate(digitos)) % 10


def _gender_from_mrz(text: str) -> Optional[str]:
    """The sex letter off a TD1 MRZ line, only when both date check digits
    verify. Spaces an OCR pass inserts inside the line are ignored. Takes the
    RAW text: `normalize` collapses line breaks, and the MRZ is a per-line
    structure."""
    achados = set()
    for linha in (text or "").splitlines():
        compacta = normalize(linha).replace(" ", "")
        for m in _MRZ_RE.finditer(compacta):
            nasc, c1, sexo, validade, c2, _nat = m.groups()
            if _mrz_check(nasc) == int(c1) and _mrz_check(validade) == int(c2):
                achados.add(_LETRAS[sexo])
    return achados.pop() if len(achados) == 1 else None


# ─── Table layout (CIN front, some CNH text layers) ─────────────────────────
#
# A card laid out as a table prints its labels on ONE line and their values on
# the NEXT: `SEXO / SEX   NACIONALIDADE   DATA DE NASCIMENTO` then
# `F   BRA   01/01/1990`. The value then sits further than the label window
# from its label, and the label-before rule above rejects it. Accepted here
# only when the header line carries a sex label AND the very next non-empty
# line holds exactly one standalone `M`/`F` — at `baixa`, because the column
# pairing is positional, not labelled.

_SEX_HEADER_RE = re.compile(r"\b(?:SEXO|SEX|GENERO)\b")


def _gender_from_table(text: str) -> Optional[str]:
    """RAW text in, for the same reason as `_gender_from_mrz`."""
    linhas = [normalize(l) for l in (text or "").splitlines()]
    achados = set()
    for i, linha in enumerate(linhas):
        if not _SEX_HEADER_RE.search(linha):
            continue
        # Same-line value is the labelled case the main parser already owns.
        for prox in linhas[i + 1 : i + 3]:
            if not prox.strip():
                continue
            letras = _LETRA_RE.findall(prox)
            if len(letras) == 1 and not _PALAVRA_RE.search(prox):
                achados.add(_LETRAS[letras[0]])
            break
    return achados.pop() if len(achados) == 1 else None


def find_gender(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the holder's sex.

    Returns `(value, confidence, matched_label)`, confidence being one of
    `"alta"` / `"baixa"` / `"nenhuma"` — the string values of
    `types.ExtractionConfidence`, kept as plain strings so this module stays
    import-free of the rest of the package.

    - **alta** — found next to a sex label, and every labelled reading agrees.
    - **baixa** — a whole word (`MASCULINO`) with no label. Unambiguous as a
      token, but unanchored, so a human confirms.
    - **nenhuma** — nothing, or readings that disagree. 🔴 Disagreement is
      reported as ABSENCE, never resolved by preferring one: two different sex
      values on one document means the layout was misread, and picking a winner
      would write a coin-flip onto a person's record.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    rotulados: list[tuple[str, str]] = []
    soltos: list[str] = []

    # Whole words — valid anywhere, better when labelled.
    for m in _PALAVRA_RE.finditer(norm):
        valor = _PALAVRAS[m.group(1)]
        achado = _label_before(norm, m.start())
        if achado.rejeitado:
            continue
        # A sex label inside a filiação block may be the holder's (the block
        # ended) or a parent's. Ambiguous from text, so it joins the
        # low-confidence pile rather than the trusted one.
        if achado.rotulo and not achado.rebaixado:
            rotulados.append((valor, achado.rotulo))
        else:
            soltos.append(valor)

    # Bare letters — ONLY when a sex label introduces them. See the module
    # docstring: an unlabelled `M` is far more likely to be a state code or an
    # initial than the holder's sex.
    for m in _LETRA_RE.finditer(norm):
        achado = _label_before(norm, m.start())
        if achado.rejeitado or not achado.rotulo:
            continue
        if achado.rebaixado:
            soltos.append(_LETRAS[m.group(1)])
        else:
            rotulados.append((_LETRAS[m.group(1)], achado.rotulo))

    # The MRZ joins the TRUSTED pile: a letter between two check-digit-
    # verified dates is structural evidence, like the CPF's own check digits.
    mrz = _gender_from_mrz(text)
    if mrz is not None:
        rotulados.append((mrz, "MRZ"))

    if not rotulados:
        tabela = _gender_from_table(text)
        if tabela is not None:
            soltos.append(tabela)

    if rotulados:
        distintos = {v for v, _ in rotulados}
        if len(distintos) == 1:
            valor, rotulo = rotulados[0]
            return (valor, "alta", rotulo)
        return (None, "nenhuma", None)

    if soltos:
        distintos = set(soltos)
        if len(distintos) == 1:
            return (soltos[0], "baixa", None)

    return (None, "nenhuma", None)


__all__ = ["FEMININO", "MASCULINO", "canonical_gender", "find_gender", "normalize"]
