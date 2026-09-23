"""Read the holder's profissão off a Brazilian document.

Sibling of `gender.py` / `nacionalidade.py`: pure, label-anchored, returning
`(value, confidence, matched_label)` with confidence as a plain string.

WHERE A PROFISSÃO IS PRINTED
----------------------------
Not on an RG, a CIN or a CNH — none of them carry one. It is printed on:

- a certidão de casamento, per spouse — the older "inteiro teor" model says
  "FULANO, de profissão comerciante, nascido ..." and the form model carries a
  `PROFISSÃO` box under each spouse's qualification;
- a certidão de nascimento's parents' block (the PARENTS' profissão — never the
  holder's, see `_DE_OUTRA_PESSOA`);
- forms (fichas cadastrais, propostas) with a `Profissão:` / `Ocupação:` field.

🔴 LABEL-ANCHORED, NEVER VOCABULARY-DRIVEN
------------------------------------------
There is no closed vocabulary of professions, so an unlabelled word can never
be recognised as one: "comerciante" in a sentence is not evidence of anything.
Only a value sitting right after a `PROFISSÃO` / `OCUPAÇÃO` label is read.

🔴 TWO DIFFERENT LABELLED READINGS -> ABSENCE
---------------------------------------------
A certidão de casamento names two spouses, so a whole-document read finds two
profissões. `find_profissao` reports that as `nenhuma` (same rule as every
sibling: two labelled readings that disagree are a layout this parser cannot
attribute). Per-spouse attribution is `conjuges.find_conjuges`' job — it calls
`find_profissoes` on each spouse's own qualification segment.

WHY THE VALUE IS LOWER-CASED
----------------------------
A qualification prints the profissão in running prose ("brasileiro, casado,
engenheiro civil, ..."), and the contract renderer lower-cases it anyway. The
document's accents are kept — the value is sliced from the ORIGINAL text via
the same offset map `matricula_atos` uses, never re-typed from the normalised
copy.
"""
from __future__ import annotations

import re
from typing import Optional

from noctusai_lib.integrations.documents.matricula_atos import normalized_with_offsets

#: The label, with the "de profissão" prose form, an optional "/OCUPAÇÃO"
#: combo, and any separator before the value — possibly a line break (form
#: layouts print the label in one box and the value in the next line).
_ROTULO_RE = re.compile(
    r"\b(?P<rotulo>(?:DE\s+)?PROFISSAO(?:\s*/\s*OCUPACAO)?|OCUPACAO(?:\s+PRINCIPAL)?)\b"
    r"[ \t]*[:\-–]?[ \t]*\n?[ \t]*"
)

#: Characters a profissão value may contain once normalised.
_VALOR_RE = re.compile(r"[A-Z][A-Z .'/()-]{1,58}")

#: Where a value ends when the document runs on in prose.
_TERMINADORES = re.compile(
    r"\s*(?:[,;\n|]|\.(?:\s|$)|$)"
    r"|\s+(?=(?:NASCID|RESIDENT|DOMICILIAD|PORTADOR|INSCRIT|NATURAL\b|FILH[OA]\b|"
    r"ESTADO\s+CIVIL|NACIONALIDADE|CPF\b|RG\b|CARTEIRA|DATA\b|SEXO\b|NOME\b|"
    r"ENDERECO|RESIDENCIA|E-?MAIL|TELEFONE))"
)

#: A "value" that is really the NEXT label (an empty form box) or a
#: "not stated" marker. Neither is a profissão.
_NAO_VALOR = re.compile(
    r"^(?:NAO\s+(?:CONSTA|DECLARAD[OA]|INFORMAD[OA])|IGNORAD[OA]|SEM\s+PROFISSAO|"
    r"NACIONALIDADE|NATURALIDADE|CPF|RG|ESTADO\s+CIVIL|DATA|NOME|SEXO|ENDERECO|"
    r"FILIACAO|DOCUMENTO|IDENTIDADE|REGIME|MATRICULA|---+|\*+)"
)

#: A profissão label that belongs to SOMEONE ELSE — the parents' block of a
#: certidão de nascimento ("PROFISSÃO DO PAI"). Skipped outright: attributing
#: a parent's profissão to the holder is the error this family exists to
#: avoid.
_DE_OUTRA_PESSOA = re.compile(r"^(?:D[OA]S?\s+(?:PAI|MAE|GENITOR|GENITORA|PAIS|CONJUGE))\b")

#: Minimum letters for a value — two-letter noise ("DE") is not a profissão.
_MIN_LETRAS = 3


def _limpar(valor: str) -> str:
    valor = " ".join(valor.split())
    return valor.strip(" .,-–/").lower()


def find_profissoes(text: str) -> list[tuple[str, str, int]]:
    """Every labelled profissão reading, in document order.

    Returns `(valor, rotulo, posicao)` triples — `valor` lower-cased and
    sliced from the ORIGINAL text, `posicao` the reading's offset in the
    original text (so a caller segmenting per person can attribute it).
    """
    if not text:
        return []
    norm, origem = normalized_with_offsets(text)
    out: list[tuple[str, str, int]] = []
    for m in _ROTULO_RE.finditer(norm):
        inicio = m.end()
        resto = norm[inicio:]
        if _DE_OUTRA_PESSOA.match(resto):
            continue
        vm = _VALOR_RE.match(resto)
        if not vm:
            continue
        bruto = vm.group(0)
        corte = _TERMINADORES.search(bruto)
        if corte is not None:
            bruto = bruto[: corte.start()]
        bruto = bruto.rstrip(" .-/")
        if not bruto or _NAO_VALOR.match(bruto):
            continue
        if sum(c.isalpha() for c in bruto) < _MIN_LETRAS:
            continue
        a = inicio
        b = inicio + len(bruto)
        if b > len(origem) or a >= b:
            continue
        literal = text[origem[a] : origem[b - 1] + 1]
        valor = _limpar(literal)
        if valor:
            out.append((valor, " ".join(m.group("rotulo").split()), origem[a]))
    return out


def find_profissao(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """The holder's profissão: `(value, confidence, matched_label)`.

    - **alta** — labelled, and every labelled reading agrees.
    - **nenhuma** — nothing labelled, or readings that disagree (a
      two-spouse certidão — see the module docstring).
    """
    leituras = find_profissoes(text)
    if not leituras:
        return (None, "nenhuma", None)
    distintos = {v for v, _, _ in leituras}
    if len(distintos) != 1:
        return (None, "nenhuma", None)
    valor, rotulo, _ = leituras[0]
    return (valor, "alta", rotulo)


__all__ = ["find_profissao", "find_profissoes"]
