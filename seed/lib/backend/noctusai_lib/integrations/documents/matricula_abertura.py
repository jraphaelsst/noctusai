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
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

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


def segmentar_abertura(text: str, start: int, end: int) -> tuple[BlocoAbertura, ...]:
    """Typed blocks of the abertura span `[start, end)`. Offsets, never text.

    A block runs from just after its recognised label to the start of the
    next recognised label, or to `end` for the last one. Blocks come back in
    document order; a label not confidently recognised yields no block for
    that field rather than a wrong span (see module docstring).
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
        valor_fim_norm = matches[idx + 1].start() if idx + 1 < len(matches) else len(norm)
        blocos.append(
            BlocoAbertura(
                campo=campo,
                start=para_orig_fim(m.end()),
                end=para_orig_inicio(valor_fim_norm) if idx + 1 < len(matches) else end,
                rotulo_start=para_orig_inicio(m.start("rotulo")),
                rotulo_end=para_orig_fim(m.end("rotulo")),
            )
        )
    return tuple(blocos)


__all__ = ["CampoAbertura", "BlocoAbertura", "segmentar_abertura"]
