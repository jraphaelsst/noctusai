"""Typed blocks of a matrícula's abertura — the labelled opening section.

`matricula_atos.py` returns the abertura (everything before the first `R-`/
`AV-` header) as a single opaque span. It is not opaque in the source
document: it is a sequence of labelled blocks — `IMÓVEL:`, `CADASTRO
MUNICIPAL:`, `PROPRIETÁRIOS:`, `REGISTRO ANTERIOR:` — and a deed template
quotes each one into its own field (`{{r imovel.descricao_matricula }}` and
siblings). This module finds those blocks, as offsets, over the abertura span
`segment_matricula_atos` already isolated.

🔴 OFFSETS, NEVER TEXT — same contract as `matricula_atos.py` and
`matricula_ruido.py`. A block is `text[block.start:block.end]`, byte-identical
to the source.

🔴 A LABEL NOT CONFIDENTLY MATCHED YIELDS NO BLOCK, NEVER A WRONG SPAN
-----------------------------------------------------------------------
Real coverage across signed certidões is uneven: `IMÓVEL` and `CADASTRO
MUNICIPAL` are on essentially every document, `REGISTRO ANTERIOR` on most,
`PROPRIETÁRIOS` on a minority (it is often folded into the same paragraph as
the imóvel description, with no label of its own). A missing label is the
normal case and must come back as "no block for that field", never a guess.

To keep the false-positive rate low — "imóvel"/"registro anterior" are
ordinary Portuguese words that show up in prose describing a completely
different field — a label is only recognised at the START OF A LINE
(optional leading horizontal whitespace), mirroring the real templates this
was built against, where these are block headers, not words embedded in a
sentence.

Label matching tolerates: accent/case folding (`normalize`, reused rather
than re-derived — see `matricula_atos.normalized_with_offsets`, which does
the same per-character trick these blocks need to keep line-start regex
matching valid while still mapping back to literal offsets), singular vs.
plural (`PROPRIETÁRIO`/`PROPRIETÁRIOS`/`PROPRIETÁRIA`/`PROPRIETÁRIAS`), and
an optional `:`/`-` separator with surrounding whitespace.

`descricao_imovel` EXCLUDES the `IMÓVEL:` label itself: the docx template
already renders the label, so the block starts right after the label (and
its separator), never before it.

🔴 THE LAST BLOCK DOES NOT RUN BLINDLY TO `end`
-------------------------------------------------
Every block but the last is already bounded by the NEXT recognised label —
only the last one had nothing to stop at, so it silently swallowed whatever
follows the abertura: the closing locale+date line (`Carapicuiba, 03 de maio
de 2011.`) and the registry officer's signature (`O Oficial,` /
`O Oficial Substituto,`). That is real registry content, but it belongs to
neither `registro_anterior` nor any other field — a value that ends there is
a different (wrong) value.

The fix reuses the shape `matricula_ato_detalhes._FIM_BLOCO` already solved
for the same problem one level down (a party block with no label of its
own): a label-less terminator found via `.search`, not re-derived. Real
documents so far show two spellings — `O Oficial,` and `O Oficial
Substituto,` — always preceded, on its own line, by the closing locale+date.
Same confidence rule as everything else here: if `_FIM_ABERTURA` is not
found, the last block still runs to `end` — a guessed cut is worse than an
over-long value a human will notice.

🔴 KNOWN GAP — NOT COVERED
----------------------------
An abertura that itself straddles a page break (so its text is interleaved
with `matricula_ruido.py`-class furniture) is unvalidated, not
known-broken: every real document seen so far has a page-1-only abertura.
Composing `subtrair_ruido` over a `BlocoAbertura` span would be the shape of
a fix if this turns out to matter — not built speculatively.

Every block is trimmed of leading/trailing whitespace: the blank line
between blocks (and, for the last block, whatever follows `_FIM_ABERTURA`)
is a paragraph SEPARATOR, not part of any value — a contract quoting a
value with a trailing blank line into a `{{r }}` slot is not byte-identical
to the registry's own text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from noctusai_lib.integrations.documents.matricula_atos import (
    normalized_with_offsets,
)

CampoAbertura = Literal[
    "descricao_imovel", "cadastro_municipal", "proprietarios", "registro_anterior"
]

#: campo -> the normalised label alternation (accent/case already folded by
#: the time this is matched, so no accents appear here).
_ROTULOS: tuple[tuple[CampoAbertura, str], ...] = (
    ("descricao_imovel", r"IMOVEL"),
    ("cadastro_municipal", r"CADASTRO\s+MUNICIPAL"),
    ("proprietarios", r"PROPRIETARI[OA]S?"),
    ("registro_anterior", r"REGISTRO\s+ANTERIOR"),
)

#: Line-start only (block headers in the real templates never sit mid-line);
#: the label itself must not be glued to a following letter (so `IMOVEL`
#: does not match inside a longer word), then an optional `:`/`-` separator
#: with surrounding horizontal whitespace is consumed as part of the match
#: so the block's start lands right past it.
_ROTULO = re.compile(
    r"(?m)^[ \t]*(?P<rotulo>"
    + "|".join(f"(?P<{campo}>{corpo})" for campo, corpo in _ROTULOS)
    + r")(?![A-Z])[ \t]*[:\-–—]?[ \t]*"
)

#: Label-less end of the ABERTURA (only ever searched for the LAST block —
#: every other block is already bounded by the next recognised label): the
#: closing `<Cidade>, <dia> DE <mês> DE <ano>.` line, and/or the officer's
#: signature line right after it. Line-start anchored for the same reason
#: `_ROTULO` is: a bare date or "oficial" mid-sentence is not the closing.
_FIM_ABERTURA = re.compile(
    r"(?m)^[ \t]*(?:"
    r"(?:O\s+)?OFICIAL(?:\s+SUBSTITUTO)?\s*,"
    r"|[A-Z][A-Z' \-]*,\s*\d{1,2}\s+DE\s+[A-Z]+\s+DE\s+\d{4}\s*\."
    r")"
)


@dataclass(frozen=True)
class BlocoAbertura:
    """One labelled block of the abertura, as offsets into the caller's
    full document text (the same `text` `segmentar_abertura` was called
    with — `start`/`end` are NOT relative to the abertura span)."""

    campo: CampoAbertura
    start: int
    end: int
    rotulo_start: int
    rotulo_end: int


def _aparar(text: str, a: int, b: int) -> tuple[int, int]:
    """`[a, b)` with leading/trailing whitespace trimmed — a value never
    starts or ends on the blank line that separates it from a neighbour."""
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def segmentar_abertura(text: str, start: int, end: int) -> tuple[BlocoAbertura, ...]:
    """Typed blocks of the abertura span `[start, end)`. Offsets, never text.

    A block runs from just after its recognised label to the start of the
    next recognised label — or, for the last one, to the abertura's closing
    (`_FIM_ABERTURA`) when confidently found, else to `end`. Every value is
    trimmed of leading/trailing whitespace. Blocks come back in document
    order; a label not confidently recognised yields no block for that field
    rather than a wrong span (see module docstring).
    """
    if end <= start:
        return ()
    janela = text[start:end]
    norm, origem = normalized_with_offsets(janela)

    def para_orig_inicio(k: int) -> int:
        return start + (origem[k] if k < len(origem) else len(janela))

    def para_orig_fim(k: int) -> int:
        return start + (origem[k - 1] + 1 if k > 0 else 0)

    matches = list(_ROTULO.finditer(norm))
    blocos: list[BlocoAbertura] = []
    for idx, m in enumerate(matches):
        campo = next(c for c, _ in _ROTULOS if m.group(c))
        valor_inicio_norm = m.end()
        valor_fim_norm: Optional[int]
        if idx + 1 < len(matches):
            valor_fim_norm = matches[idx + 1].start()
        else:
            fecho = _FIM_ABERTURA.search(norm, valor_inicio_norm)
            valor_fim_norm = fecho.start() if fecho else None

        bruto_fim = (
            para_orig_inicio(valor_fim_norm) if valor_fim_norm is not None else end
        )
        bloco_start, bloco_end = _aparar(text, para_orig_fim(valor_inicio_norm), bruto_fim)
        blocos.append(
            BlocoAbertura(
                campo=campo,
                start=bloco_start,
                end=bloco_end,
                rotulo_start=para_orig_inicio(m.start("rotulo")),
                rotulo_end=para_orig_fim(m.end("rotulo")),
            )
        )
    return tuple(blocos)


__all__ = ["CampoAbertura", "BlocoAbertura", "segmentar_abertura"]
