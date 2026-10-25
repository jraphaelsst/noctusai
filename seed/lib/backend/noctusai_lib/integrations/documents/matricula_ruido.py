"""Detect page furniture (running headers/footers) in a joined transcription.

A matrícula certidão is transcribed page-by-page (`transcription.py`) and the
pages are joined into one `Transcription.text` that gets quoted verbatim into
a legal deed (`matricula_atos.py`). The problem: page furniture — running
headers, watermarks, "continua no verso", validation URLs, a requester
watermark bearing a CPF — is interleaved into that joined text, so it lands
INSIDE act spans and would print into a deed.

🔴 POSITION, NOT REPETITION
----------------------------
The naive rule "a line that repeats is furniture" is WRONG. A registry
officer's signature line (`Oficial, ________ <nome>`, `O Oficial Substituto,
________ <nome>`) repeats 3-5x in a real certidão and is genuine registry
content that must be preserved. What distinguishes furniture is that it sits
at a PAGE BOUNDARY on more than one page — the maximal run of leading (or
trailing) non-blank lines of a page, when it also opens (or closes) at least
one OTHER page. A signature line mid-page never qualifies, no matter how many
times it repeats.

🔴 BE CONSERVATIVE
-------------------
A span this module is not confident about is NOT noise. Over-stripping
silently removes registry text from a deed; under-stripping is visible and
correctable by a human reviewing the extraction. Concretely: a candidate
block must be at least `_MIN_LINHAS` lines long (a single coincidentally
identical line is not enough signal), and a page's header/footer never claims
a line that isn't part of ITS OWN leading/trailing non-blank run — the tests
in `test_matricula_ruido.py` pin both of these.

OFFSETS, NEVER TEXT
--------------------
Same contract as `matricula_atos.py`: every span is `(start, end)` into the
JOINED text, not a rewritten string.

THE JOIN
--------
`detectar_ruido` computes offsets against the exact join `Transcription.text`
produces (`"\\n\\n"` between pages, blank pages dropped — see
`Transcription.formatting`, which documents and uses the same rule). `text`
itself comes straight from `Transcription(pages=...).text`; the per-page
`[start, end)` bounds are the same accumulation `Transcription.formatting`
already performs, kept in lockstep with it on purpose so an offset from here
is always valid against a `Transcription` built from the same pages.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

from noctusai_lib.integrations.documents.matricula import normalize
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)

RuidoKind = Literal["cabecalho_pagina", "rodape_pagina"]

#: A candidate block shorter than this is too easy to hit by chance (one
#: incidentally identical short line) — see the module docstring's
#: conservative-bias note.
_MIN_LINHAS = 2

_DIGITOS = re.compile(r"\d+")


@dataclass(frozen=True)
class RuidoSpan:
    """One page's occurrence of a running header/footer block.

    `start`/`end` are offsets into the joined text — `text[start:end]` is
    exactly that block, nothing more. `paginas` names every page (in the
    input, 1-based, as `TranscribedPage.number`) whose leading/trailing run
    matched this same block, INCLUDING the page this span itself sits on —
    so a caller can tell "this pattern also showed up on pages X, Y" without
    correlating multiple spans by hand.
    """

    start: int
    end: int
    kind: RuidoKind
    paginas: tuple[int, ...]


def _linha_normalizada(linha: str) -> str:
    """Accent/case folded (`normalize`), digit runs wildcarded — so
    `Página 1/3` matches `Página 2/3` and `ficha 01` matches `ficha 02`."""
    return _DIGITOS.sub("#", normalize(linha)).strip()


def _linhas_com_spans(texto: str) -> list[tuple[int, int, str]]:
    """`(start, end, content)` per `\\n`-split line, offsets into `texto`."""
    linhas: list[tuple[int, int, str]] = []
    pos = 0
    for linha in texto.split("\n"):
        linhas.append((pos, pos + len(linha), linha))
        pos += len(linha) + 1
    return linhas


def _paginas_com_offsets(
    pages: Sequence[TranscribedPage],
) -> tuple[str, tuple[tuple[TranscribedPage, int, int], ...]]:
    """The joined text (from `Transcription.text`, not a second hand-rolled
    join) plus each surviving page's `[start, end)` into it — the same
    accumulation `Transcription.formatting` documents and performs."""
    texto = Transcription(pages=tuple(pages)).text
    resultado: list[tuple[TranscribedPage, int, int]] = []
    offset = 0
    primeira = True
    for page in pages:
        if not page.text:
            continue
        if not primeira:
            offset += 2  # the "\n\n" join
        inicio = offset
        offset += len(page.text)
        resultado.append((page, inicio, offset))
        primeira = False
    return texto, tuple(resultado)


def _run_nao_em_branco(
    linhas: Sequence[tuple[int, int, str]], do_fim: bool, teto: int
) -> int:
    """How many leading (or, `do_fim`, trailing) non-blank lines, capped at
    `teto` (used to keep a footer run from eating into an already-claimed
    header on a short page)."""
    total = len(linhas)
    n = 0
    for i in range(min(total, teto)):
        idx = total - 1 - i if do_fim else i
        if not linhas[idx][2].strip():
            break
        n += 1
    return n


def _fatia_normalizada(
    normalizadas: Sequence[str], do_fim: bool, n: int
) -> tuple[str, ...]:
    total = len(normalizadas)
    if n <= 0 or n > total:
        return ()
    return tuple(normalizadas[total - n : total] if do_fim else normalizadas[0:n])


def _detectar_lado(
    linhas_por_pagina: dict[int, list[tuple[int, int, str]]],
    offsets_por_pagina: dict[int, tuple[int, int]],
    *,
    do_fim: bool,
    kind: RuidoKind,
    reservas: dict[int, int],
) -> tuple[list[RuidoSpan], dict[int, int]]:
    """One side (header or footer) of the detection. Returns the spans plus
    the chosen block length per page (so the caller can reserve those lines
    against the other side, keeping a header and footer from overlapping on
    a short page)."""
    normalizadas_por_pagina = {
        pn: [_linha_normalizada(l[2]) for l in linhas]
        for pn, linhas in linhas_por_pagina.items()
    }

    escolhidos: dict[int, int] = {}
    for pn, linhas in linhas_por_pagina.items():
        teto = len(linhas) - reservas.get(pn, 0)
        if teto < _MIN_LINHAS:
            continue
        maximo = _run_nao_em_branco(linhas, do_fim, teto)
        if maximo < _MIN_LINHAS:
            continue
        normalizadas = normalizadas_por_pagina[pn]
        for n in range(maximo, _MIN_LINHAS - 1, -1):
            alvo = _fatia_normalizada(normalizadas, do_fim, n)
            achou_par = any(
                outra != pn
                and len(linhas_por_pagina[outra]) >= n
                and _fatia_normalizada(normalizadas_por_pagina[outra], do_fim, n)
                == alvo
                for outra in linhas_por_pagina
            )
            if achou_par:
                escolhidos[pn] = n
                break

    spans: list[RuidoSpan] = []
    for pn, n in escolhidos.items():
        linhas = linhas_por_pagina[pn]
        total = len(linhas)
        primeira_linha = linhas[total - n] if do_fim else linhas[0]
        ultima_linha = linhas[-1] if do_fim else linhas[n - 1]
        pagina_inicio, _ = offsets_por_pagina[pn]
        alvo = _fatia_normalizada(normalizadas_por_pagina[pn], do_fim, n)
        grupo = tuple(
            sorted(
                outra
                for outra, normalizadas in normalizadas_por_pagina.items()
                if len(linhas_por_pagina[outra]) >= n
                and _fatia_normalizada(normalizadas, do_fim, n) == alvo
            )
        )
        spans.append(
            RuidoSpan(
                start=pagina_inicio + primeira_linha[0],
                end=pagina_inicio + ultima_linha[1],
                kind=kind,
                paginas=grupo,
            )
        )
    return spans, escolhidos


#: Furniture a registry prints with a fixed SHAPE (digits wildcarded to `#`
#: by `_linha_normalizada`), recognised without any cross-page repetition.
#: Needed because page 1 carries the full letterhead (livro, ofício, ficha,
#: CNS inscription) while pages 2+ carry only the short "Mat. N - Página i/n"
#: head — the repeated prefix is 1-2 lines, so the repetition rule leaves the
#: rest of page 1's letterhead in the abertura (F44: it then printed into the
#: contract's objeto clause).
_MOBILIARIO_CONHECIDO = re.compile(
    r"^(?:"
    r"MAT(?:RICULA)?\.?\s*N?[O°]?\.?\s*[#.\s]+-\s*PAGINA\s*#+\s*/\s*#+.*"
    r"|CNM\b\s*[:.]?\s*[#.\-\s]*"
    r"|LIVRO\s+N[O°]?\.?\s*[#A-Z]*\s*-\s*REGISTRO\s+GERAL.*"
    r"|(?:O\s+)?OFICIAL\s+DE\s+REGISTRO\s+DE\s+IMOVEIS\b.*"
    r"|[-–—]+\s*MATRICULA\s*[-–—]+\s*[#.\s]+[-–—]+\s*FICHA\s*[-–—]*\s*[#.\s]*"
    r"|INSCRICAO\s+N[O°]?\b.*SERVENTIAS.*"
    r"|CODIGO\s+NACIONAL\s+DE\s+SERVENTIAS.*"
    r"|\(?CONTINUA\s+(?:NO\s+VERSO|NA\s+PROXIMA\s+PAGINA|NA\s+(?:FICHA|FOLHA|PAGINA)\b.*)\)?\.?"
    r"|MOD(?:ELO)?\.?\s*[#.\-\s]*"
    r"|\(?VERSO\)?\.?"
    r"|(?:FLS?\.?|FOLHAS?|FICHA)\s*(?:N[O°]?\.?)?\s*[#.\-/\s]*\s*\(?VERSO\)?\.?"
    r")$"
)


def _detectar_mobiliario_conhecido(
    com_offsets: Sequence[tuple[TranscribedPage, int, int]],
) -> tuple[RuidoSpan, ...]:
    """Known-shape furniture in each page's leading / trailing non-blank run
    (never mid-page: a line must be CONTIGUOUS with the page boundary)."""
    spans: list[RuidoSpan] = []
    for page, inicio, _fim in com_offsets:
        linhas = _linhas_com_spans(page.text)
        for do_fim, kind in ((False, "cabecalho_pagina"), (True, "rodape_pagina")):
            n = 0
            for i in range(len(linhas)):
                idx = len(linhas) - 1 - i if do_fim else i
                conteudo = linhas[idx][2]
                if not conteudo.strip() or not _MOBILIARIO_CONHECIDO.match(
                    _linha_normalizada(conteudo)
                ):
                    break
                n += 1
            if n == 0 or n == len(linhas):
                continue
            primeira = linhas[len(linhas) - n] if do_fim else linhas[0]
            ultima = linhas[-1] if do_fim else linhas[n - 1]
            spans.append(
                RuidoSpan(
                    start=inicio + primeira[0],
                    end=inicio + ultima[1],
                    kind=kind,  # type: ignore[arg-type]
                    paginas=(page.number,),
                )
            )
    return tuple(spans)


def neutralizar_quebra_pagina(texto: str) -> str:
    """`texto` with every page-continuation furniture LINE ("continua no
    verso", "MOD. 10", "(verso)", "fls. 2 verso", a repeated matrícula page
    head) blanked IN PLACE — replaced by spaces, same length, newlines kept.

    Run BEFORE act parsing / qualification extraction so a sentence the
    registry split across two pages reads whole ("… transmitiu o <furniture>
    imóvel desta matrícula a FULANO, …"). Length-preserving on purpose:
    every offset a caller holds into `texto` stays valid. Whole-line match
    only (the same `_MOBILIARIO_CONHECIDO` shapes `detectar_ruido` uses, but
    anywhere in the text, not just at a page boundary: a stored joined text
    may no longer carry the page structure). Conservative — a line that
    merely CONTAINS such words among other text is untouched."""
    if not texto:
        return texto
    saida: list[str] = []
    for linha in texto.split("\n"):
        if linha.strip() and _MOBILIARIO_CONHECIDO.match(_linha_normalizada(linha)):
            saida.append(" " * len(linha))
        else:
            saida.append(linha)
    return "\n".join(saida)


def _fundir(spans: Sequence[RuidoSpan]) -> tuple[RuidoSpan, ...]:
    """Sorted, disjoint: overlapping/touching spans of the same kind are
    unioned (offsets and pages)."""
    resultado: list[RuidoSpan] = []
    for sp in sorted(spans, key=lambda x: (x.start, x.end)):
        if resultado and sp.start <= resultado[-1].end and sp.kind == resultado[-1].kind:
            ant = resultado[-1]
            resultado[-1] = RuidoSpan(
                start=ant.start,
                end=max(ant.end, sp.end),
                kind=ant.kind,
                paginas=tuple(sorted(set(ant.paginas) | set(sp.paginas))),
            )
        elif resultado and sp.start < resultado[-1].end:
            continue
        else:
            resultado.append(sp)
    return tuple(resultado)


def detectar_ruido(pages: Sequence[TranscribedPage]) -> tuple[RuidoSpan, ...]:
    """Running header/footer spans as offsets into the same joined text
    `Transcription.text` produces. Sorted by start, non-overlapping.

    Requires at least 2 pages carrying text; a single-page document (or one
    where every other page is blank) yields `()` — there is nothing to
    cross-validate a boundary block against, and a lone page's leading or
    trailing lines are never called noise on their own. See the module
    docstring for the position-over-repetition rule and the conservative
    bias this function is built to honour.
    """
    _, com_offsets = _paginas_com_offsets(pages)
    if not com_offsets:
        return ()
    if len(com_offsets) < 2:
        return _fundir(_detectar_mobiliario_conhecido(com_offsets))

    linhas_por_pagina = {
        page.number: _linhas_com_spans(page.text) for page, _, _ in com_offsets
    }
    offsets_por_pagina = {
        page.number: (inicio, fim) for page, inicio, fim in com_offsets
    }

    cabecalhos, reservas = _detectar_lado(
        linhas_por_pagina,
        offsets_por_pagina,
        do_fim=False,
        kind="cabecalho_pagina",
        reservas={},
    )
    rodapes, _ = _detectar_lado(
        linhas_por_pagina,
        offsets_por_pagina,
        do_fim=True,
        kind="rodape_pagina",
        reservas=reservas,
    )
    return _fundir(
        (*cabecalhos, *rodapes, *_detectar_mobiliario_conhecido(com_offsets))
    )


def subtrair_ruido(
    start: int, end: int, ruido: Sequence[RuidoSpan]
) -> tuple[tuple[int, int], ...]:
    """`[start, end)` minus every noise span — ordered, disjoint sub-spans.

    Tolerant of overlapping/unsorted `ruido` input (only `detectar_ruido`'s
    own OUTPUT is guaranteed sorted+disjoint); a span outside `[start, end)`
    is ignored rather than raising.
    """
    if end <= start:
        return ()
    recortados = sorted(
        (max(r.start, start), min(r.end, end))
        for r in ruido
        if r.end > start and r.start < end and r.end > r.start
    )
    resultado: list[tuple[int, int]] = []
    cursor = start
    for s, e in recortados:
        if s > cursor:
            resultado.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < end:
        resultado.append((cursor, end))
    return tuple(resultado)


__all__ = ["RuidoKind", "RuidoSpan", "detectar_ruido", "neutralizar_quebra_pagina", "subtrair_ruido"]
