"""Label-anchored full-name extraction from Brazilian identity-document text.

Pure — no IO, no LLM, no network. Text in, name and confidence out.

WHY THIS IS HARDER THAN THE DATE
--------------------------------
A date is self-delimiting: `12/05/1980` is recognisable as a date with no
context at all, so `birthdate` can find every candidate first and use
labels only to CHOOSE between them. A name has no shape. `FULANO DE TAL
SILVA` and `SECRETARIA DE SEGURANCA PUBLICA` are the same kind of string
to a regex. So here the label is not a tie-breaker, it is the ONLY
evidence — an unlabelled line is never read as a name, at any confidence.

THE DECOY THAT MATTERS: FILIAÇÃO
--------------------------------
Every Brazilian RG prints the holder's name and then, directly beneath it,
the names of BOTH PARENTS under `FILIAÇÃO`. Those are real, perfectly
well-formed Brazilian full names sitting two lines from the right answer.
Any approach that scores "does this look like a name?" picks one of them a
large fraction of the time — and produces a plausible human name, so
nothing downstream can tell it went wrong.

Two independent guards therefore exist, and both are load-bearing:

1. Labels like `NOME DO PAI` / `NOME DA MAE` are matched LONGEST-FIRST, so
   they are recognised as decoys rather than as the bare `NOME` nested
   inside them.
2. A `FILIAÇÃO` header poisons the lines that follow it, because the
   common layout puts the parents on their own unlabelled lines under it.

THE INSTITUTIONAL BLOCKLIST
---------------------------
ID documents are covered in official phrases that pass every structural
name test: `REPUBLICA FEDERATIVA DO BRASIL`, `SECRETARIA DE SEGURANCA
PUBLICA`, `CADASTRO DE PESSOAS FISICAS`. They are rejected by name rather
than by cleverness, because a heuristic that could tell them apart from a
person's name would be a heuristic that sometimes rejects real people.

ONE DELIBERATE OMISSION
-----------------------
**No unlabelled fallback.** `birthdate` will return a lone plausible date
at `baixa` when nothing is labelled. The equivalent here would be "the
longest name-shaped line", which on an RG is frequently a parent. Absence
is reported instead.
"""
from __future__ import annotations

import re
from typing import Optional

from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper

#: Bounds on a stored name. The floor rejects label noise (`RG`, `ID`);
#: the ceiling rejects a run-on line that swallowed the next field.
MIN_NAME_LEN = 4
MAX_NAME_LEN = 80
MIN_WORDS = 2
MAX_WORDS = 8

#: Portuguese name particles. They are the reason a plain "every word must
#: be at least two letters" rule does not work — `FULANO E SILVA` is a
#: real name shape.
_PARTICLES = frozenset({"DA", "DE", "DO", "DAS", "DOS", "E", "D", "DI", "DU", "VON", "VAN"})

#: Labels that introduce the DOCUMENT HOLDER's name. Order is irrelevant;
#: `_label_at` always takes the longest match at a position.
_NAME_LABELS = (
    "NOME COMPLETO",
    "NOME E SOBRENOME",
    "NOME CIVIL",
    "NOME",
)

#: Labels that introduce SOMEONE ELSE's name, or a name-shaped value that
#: is not a person. Longest-first matching is what makes these win over
#: the bare `NOME` they contain.
_DECOY_NAME_LABELS = (
    "NOME DO PAI",
    "NOME DA MAE",
    "NOME DO CONJUGE",
    "NOME DA MAE OU PAI",
    "NOME DO RESPONSAVEL",
    "NOME DO ORGAO",
    "NOME DA EMPRESA",
    "NOME DO AGENTE",
    "NOME EMPRESARIAL",
    "NOME FANTASIA",
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "RESPONSAVEL",
)

#: Lines that begin a section whose following lines are other people.
_POISONING_HEADERS = ("FILIACAO",)

#: How many lines after a poisoning header stay poisoned. Two, because a
#: Brazilian RG lists exactly two parents.
_POISON_SPAN = 2

#: Official phrases that are structurally indistinguishable from names.
_INSTITUTIONAL = frozenset(
    {
        "REPUBLICA FEDERATIVA DO BRASIL",
        "MINISTERIO DA FAZENDA",
        "MINISTERIO DA ECONOMIA",
        "SECRETARIA DA RECEITA FEDERAL",
        "RECEITA FEDERAL",
        "CADASTRO DE PESSOAS FISICAS",
        "SECRETARIA DE SEGURANCA PUBLICA",
        "SECRETARIA DE ESTADO DA SEGURANCA PUBLICA",
        "INSTITUTO DE IDENTIFICACAO",
        "CARTEIRA DE IDENTIDADE",
        "REGISTRO GERAL",
        "REGISTRO NACIONAL",
        "VALIDA EM TODO O TERRITORIO NACIONAL",
        "DOCUMENTO DE IDENTIDADE",
        "CARTEIRA NACIONAL DE HABILITACAO",
        "DEPARTAMENTO DE TRANSITO",
        "LEI N 7 116 DE 29 08 83",
        "ASSINATURA DO TITULAR",
        "POLEGAR DIREITO",
    }
)

#: Words that never appear inside a personal name but do appear in the
#: institutional strings above. A second, cheaper net for phrasings the
#: exact blocklist has not seen.
_INSTITUTIONAL_TOKENS = frozenset(
    {
        "REPUBLICA", "FEDERATIVA", "MINISTERIO", "SECRETARIA", "RECEITA",
        "CADASTRO", "PESSOAS", "FISICAS", "SEGURANCA", "PUBLICA", "INSTITUTO",
        "IDENTIFICACAO", "CARTEIRA", "IDENTIDADE", "REGISTRO", "NACIONAL",
        "TERRITORIO", "DOCUMENTO", "HABILITACAO", "DEPARTAMENTO", "TRANSITO",
        "ASSINATURA", "TITULAR", "POLEGAR", "VALIDA", "VALIDO", "EXPEDICAO",
        "EMISSAO", "VALIDADE", "NATURALIDADE", "FILIACAO", "ORGAO", "EMISSOR",
        "ESTADO", "MUNICIPIO", "COMARCA", "CARTORIO", "LIVRO", "FOLHA", "TERMO",
        "OBSERVACOES", "ASSINADO", "DIGITALMENTE",
    }
)

#: Characters a Brazilian personal name may contain once accents are
#: stripped. Digits are absent on purpose — a "name" with a digit in it is
#: a misread label or a document number.
_NAME_CHARS = re.compile(r"^[A-Z' -]+$")

#: Separators that sit between a label and its value.
_SEPARATORS = " :\t-–—.|"


def _label_at(line: str, pos: int) -> tuple[Optional[str], bool]:
    """Longest label starting at `pos`, and whether it is a decoy.

    Longest-first is the entire defence against `NOME DO PAI` being read
    as `NOME` followed by a value of `DO PAI`.
    """
    best: tuple[str, bool] | None = None
    for label, is_decoy in (
        [(x, True) for x in _DECOY_NAME_LABELS] + [(x, False) for x in _NAME_LABELS]
    ):
        if not line.startswith(label, pos):
            continue
        # A label must end at a word boundary, else `NOMEACAO` matches `NOME`.
        end = pos + len(label)
        if end < len(line) and line[end].isalnum():
            continue
        if best is None or len(label) > len(best[0]):
            best = (label, is_decoy)
    return best if best is not None else (None, False)


def _find_label(line: str) -> tuple[Optional[str], bool, int]:
    """First label occurring in `line`, its decoy flag, and where it ends."""
    for i in range(len(line)):
        label, is_decoy = _label_at(line, i)
        if label is not None:
            return (label, is_decoy, i + len(label))
    return (None, False, -1)


def looks_like_a_name(candidate: str) -> bool:
    """Structural plausibility for a Brazilian personal name.

    Deliberately strict. A false accept writes a wrong name onto a client
    record; a false reject leaves a field empty, which is visible.

    Normalises its own input, so callers outside this module (the checklist
    derivation asks "is this registration value a full name?") can pass raw
    mixed-case, accented text. `find_name` passes text that is already
    normalised, and normalisation is idempotent.
    """
    value = " ".join(strip_accents_upper(candidate or "").split())
    value = value.strip(_SEPARATORS).strip()
    if not (MIN_NAME_LEN <= len(value) <= MAX_NAME_LEN):
        return False
    if not _NAME_CHARS.match(value):
        return False
    if value in _INSTITUTIONAL:
        return False

    words = value.split()
    if not (MIN_WORDS <= len(words) <= MAX_WORDS):
        return False
    if any(w in _INSTITUTIONAL_TOKENS for w in words):
        return False

    substantive = [w for w in words if w not in _PARTICLES]
    if len(substantive) < 2:
        return False
    if any(len(w) < 2 for w in substantive):
        return False
    return True


def find_name(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the document holder's full name.

    Returns `(value, confidence, matched_label)` where confidence is
    `"alta"` / `"nenhuma"` — the string values of
    `types.ExtractionConfidence`, kept as plain strings so this module
    stays import-free of the rest of the package.

    `"baixa"` is never returned from here. A name is either label-anchored
    (in which case the evidence is as good as this parser can get) or it
    is not found. Downgrading to `baixa` on account of the TEXT SOURCE is
    the adapter's job, because only the adapter knows whether the text
    came off a PDF text layer or a vision pass.
    """
    lines = normalize_lines(text)
    if not lines:
        return (None, "nenhuma", None)

    poisoned_until = -1
    candidates: list[tuple[str, str]] = []

    for idx, line in enumerate(lines):
        if any(line.startswith(h) for h in _POISONING_HEADERS):
            poisoned_until = idx + _POISON_SPAN
            continue
        if idx <= poisoned_until:
            continue

        label, is_decoy, end = _find_label(line)
        if label is None or is_decoy:
            continue

        # Value on the same line, e.g. `NOME: FULANO DE TAL`.
        tail = line[end:].strip(_SEPARATORS).strip()
        if tail and looks_like_a_name(tail):
            candidates.append((tail, label))
            continue

        # Value on the NEXT line, e.g. `NOME` / `FULANO DE TAL`. Only when
        # the label line carried no value of its own — otherwise a label
        # whose value failed validation would reach past it and claim the
        # following field.
        if not tail and idx + 1 < len(lines):
            nxt = lines[idx + 1]
            n_label, n_decoy, _ = _find_label(nxt)
            if n_label is None and looks_like_a_name(nxt):
                candidates.append((nxt.strip(_SEPARATORS).strip(), label))

    if not candidates:
        return (None, "nenhuma", None)

    distinct = {v for v, _ in candidates}
    if len(distinct) > 1:
        # Two different strings both labelled as the holder's name means
        # the layout was misread. Report the ambiguity; do not pick.
        return (None, "nenhuma", None)

    value, label = candidates[0]
    return (value, "alta", label)


__all__ = [
    "MAX_NAME_LEN",
    "MAX_WORDS",
    "MIN_NAME_LEN",
    "MIN_WORDS",
    "find_name",
    "looks_like_a_name",
]
