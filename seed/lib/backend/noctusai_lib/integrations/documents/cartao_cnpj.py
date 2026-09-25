"""Cartão CNPJ (Receita's "COMPROVANTE DE INSCRIÇÃO E DE SITUAÇÃO CADASTRAL",
printed to PDF) → typed fields.

Protocol + Fake + Real + factory, sibling of `serasa_crednet.py` and
`matricula_extractor.py` — same ladder (`ladder.py`), same confidence
vocabulary, same "not a text layer ⇒ not alta" tempering.

🔴 A BOXED FORM, NOT A TABLE — A DIFFERENT PROMPT FROM `serasa_crednet`
-------------------------------------------------------------------------
The Receita comprovante prints one value per LABELLED BOX
("NÚMERO DE INSCRIÇÃO", "DATA DE ABERTURA", ...), never a table row. So this
module's transcription prompt asks for `RÓTULO: valor`, one box per line —
the shape `serasa_crednet.DOCUMENT_PROMPT_CREDNET`'s pipe-table convention
would actively lose (a box has no columns to align). `real.py`'s own
identity-document prompt states the same "preserve THIS document's own
labels, verbatim" principle for a third, different layout.

🔴 A MASKED BOX IS `None`, NEVER THE LITERAL ASTERISKS
----------------------------------------------------------
The Receita masks some boxes (commonly "TÍTULO DO ESTABELECIMENTO" and
"SITUAÇÃO ESPECIAL") as a literal `********`. That string is not a value —
it is the document telling the reader nothing was printed there — so every
field parser here folds it to `None`, same treatment as an entirely blank
box, while the box's own label still lands in `rotulos` so a human can see
the field WAS present and masked, not silently missing from the layout.

🔴 `situacao_cadastral` IS A CLOSED VOCABULARY, THE RAW TEXT SURVIVES IN
`rotulos` WHEN IT DOESN'T MATCH
-------------------------------------------------------------------------
Migration `167_empresas_crednet_cartao_cnpj.sql` (§A.1) CHECKs
`empresas.situacao_cadastral` against exactly `'ativa' | 'baixada' |
'inapta' | 'suspensa' | 'nula'`. A read that doesn't normalise to one of
those five is `None` (never guessed, never written), but the box's raw text
is kept at `rotulos["situacao_cadastral"]` — the one field in this module
where `rotulos` carries the VALUE rather than the label, because "what did
the document actually say" is exactly what a human needs to resolve an
unrecognised situação.

🔴 THE ADDRESS BLOCK IS OFTEN MASKED IN FULL, AND EACH BOX IS READ ON ITS
OWN — NEVER SCRAPED OUT OF A NEIGHBOUR'S VALUE
---------------------------------------------------------------------------
`logradouro`/`numero`/`complemento`/`cep`/`bairro`/`municipio`/`uf` are each
their OWN labelled box, exactly like every other field here — `_campo`'s
usual same-line/next-line matching applies unchanged, cut off at the NEXT
known label so `municipio`'s value never bleeds into `uf`'s (or vice
versa). `uf` additionally validates against the 27-state whitelist
(`_UFS_BR`) — never a guess. `endereco_mascarado` is `True` when ANY of
these seven boxes was found printing the literal `********` — measured
against a real Cartão CNPJ (2026-09-24): the WHOLE address block is
routinely masked together, and a consumer needs one flag to know the
address section is unusable rather than reading seven independent `None`s
and guessing why. 🔴 An earlier version of this module tried to recover
`uf` by scanning a whole merged "city + code" value row for a trailing
UF-shaped token — that measurement's premise was wrong (the real file's
`uf=None` was masking, not a merged row) and the heuristic could, on a
document shaped differently, have picked up text belonging to a
neighbouring box. Removed; every field here is read from its own box only.

🔴 A REAL TEXT LAYER EXISTS TOO, AND IT HAS ITS OWN SHAPE — `pdftotext
-layout`'S COLUMN ALIGNMENT
-------------------------------------------------------------------------
Some Cartões are Chrome-printed PDFs (`Producer: Skia/PDF`) that carry a
genuine text layer, so rung 1 (`ladder.DocumentTextLadder`, PDF-text-first)
answers directly — no vision call, and `alta` is reachable (measured
2026-09-24). That extraction preserves visual COLUMN alignment via runs of
whitespace rather than the vision prompt's `RÓTULO: valor` convention: a
row of several short address labels prints as one line
(`"CEP  BAIRRO/DISTRITO  MUNICIPIO  UF"`), and the corresponding values as
the line right below, column-for-column (masked or not). `normalize_lines`
collapses that alignment (it exists to make LABEL matching accent/case
-insensitive, not to preserve column gaps), so this shape is read by a
SEPARATE pre-pass (`_valores_colunas_alinhadas`) over the text layer's own
raw lines, splitting on runs of 2+ spaces (a real multi-word value like
"SAO PAULO" carries only ONE space and so never splits) — tried FIRST,
falling back to the per-box `_campo` matcher above for anything it does
not resolve.

🔴 A REAL VISION TRANSCRIPTION HAS ITS OWN THIRD SHAPE TOO -- A MARKDOWN
PIPE TABLE, NOT ONE BOX PER LINE
-------------------------------------------------------------------------
Measured against a real Cartao CNPJ (2026-09-25, a BAIXADA company): the
model does not always honour "one box per line" -- several side-by-side
boxes routinely come back as ONE markdown table row, pipe-delimited, with
each box's `ROTULO valor` FUSED into its own cell (no colon: `"NUMERO DE
INSCRICAO 12.345.678/0001-90 MATRIZ | ... | DATA DE ABERTURA 15/03/2010"`),
and a `| --- | --- | --- |` header-separator row appears too. Read naively
as plain lines, this shape is actively harmful, not just unparsed: (1) the
next raw line's leading/trailing `|` leaks into whatever value `_campo`'s
"cut at the next known label" logic returns, which is exactly the `"ME |"`
/ `"... | | |"` residue measured live; (2) the document's OWN TITLE
("COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL") can land in a
"column" purely as a table-flattening artifact of the vision model, and it
contains the literal `situacao_cadastral` label text as a SUBSTRING -- a
naive scan finds THAT false match, with nothing after it, before ever
reaching the real "SITUACAO CADASTRAL BAIXADA" box further down --
measured live as `rotulos.situacao_cadastral = "|"`; (3) a masked box
comes back transcribed as a single literal `*`, not the prompt's
`********` -- `_MASCARADO` alone misses it. `_expandir_celulas_pipe_com_rotulo`
(the inline `ROTULO valor`-per-cell shape) and `_valores_tabela_pipes` (a
separate header-row-of-labels + value-row, or an alternating `LABEL |
valor |` row -- the two OTHER pipe shapes a model could plausibly choose)
both run BEFORE `_campo`, same ladder-of-fallbacks convention as the
column-aligned path above; every value, whichever path produced it, is
then defensively stripped of leftover pipe-boundary residue and
re-checked for an asterisks-only mask (`_SOMENTE_ASTERISCOS_RE`) -- never
just the literal 8-character `********`.

🔴 THE TITLE HAZARD IS NOT PIPE-TABLE-SPECIFIC -- MEASURED AGAIN IN A
CLEAN, NON-PIPED TRANSCRIPTION (2026-09-25)
-------------------------------------------------------------------------
The pipe-table fix above only filters the title out of a FUSED cell. A
LATER re-read of the same real (BAIXADA) Cartão CNPJ came back with no
pipe residue at all and the title still won `situacao_cadastral`'s
match -- this time because the model echoed the document's own title
("COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL") as its OWN LINE,
ahead of the real "SITUACAO CADASTRAL: BAIXADA" box, and `_campo`
commits to the FIRST admissible occurrence of a label it finds and never
looks further -- measured live as `rotulos.situacao_cadastral` carrying
the document's own title text. So two changes: (1) EVERY `_campo`
match, whichever shape produced the line, is now ALSO rejected when it
sits inside an occurrence of the document's own title text
(`_embutido_no_titulo`, the same "is this substring actually inside
something LONGER" contract `_embutido_em_rotulo_maior` already applies
to sibling KNOWN labels); (2) `situacao_cadastral` alone gets its own
scanner, `_campo_situacao_cadastral`, that does NOT stop at the first
admissible occurrence -- it walks every one, in document order, and
returns the FIRST whose own resolved value actually contains a closed
-vocabulary word, falling back to the first occurrence's raw text (so a
human still sees what was read) only when NONE of them do. A document
with a single admissible occurrence behaves exactly like `_campo`
always did.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.integrations.documents.cnpj import format_cnpj, is_valid as _cnpj_is_valid
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    TextSource,
)

# ─── transcription prompt (rung 2) ────────────────────────────────────────

#: `RÓTULO: valor`, one box per line — see the module header. Masked boxes
#: are transcribed AS PRINTED (the literal asterisk run); the parser, not
#: the prompt, decides that means "no value".
DOCUMENT_PROMPT_CARTAO_CNPJ = (
    "Transcreva o texto EXATO deste Comprovante de Inscrição e de Situação "
    "Cadastral (Cartão CNPJ), sem corrigir, resumir ou traduzir o CONTEÚDO "
    "de nenhum campo. O documento imprime cada campo como uma CAIXA — o "
    "rótulo (como 'NÚMERO DE INSCRIÇÃO', 'DATA DE ABERTURA', 'NOME "
    "EMPRESARIAL', 'SITUAÇÃO CADASTRAL', etc.) e, logo abaixo ou ao lado, o "
    "valor, MESMO QUE O DOCUMENTO NÃO IMPRIMA DOIS PONTOS ENTRE ELES. Você "
    "DEVE, ao transcrever, juntar cada rótulo ao seu valor em UMA ÚNICA "
    "LINHA no formato RÓTULO: valor — o rótulo exatamente como impresso, "
    "seguido de dois pontos (mesmo que o documento não os imprima) e o "
    "valor impresso naquela caixa, sem misturar o valor de uma caixa com o "
    "rótulo da caixa seguinte. Uma linha por campo. Se o valor estiver "
    "mascarado com asteriscos (********), transcreva os asteriscos "
    "literalmente. Transcreva também a linha de rodapé 'Emitido no dia ...'."
)

# ─── shared confidence tempering ──────────────────────────────────────────


def _temper(confidence: ExtractionConfidence, source: TextSource) -> ExtractionConfidence:
    """`alta` is reachable only off a PDF's own text layer — own copy, not
    shared with the sibling extractors, per this family's own convention
    (see `serasa_crednet._temper`)."""
    if confidence is ExtractionConfidence.ALTA and source is not TextSource.TEXT_LAYER:
        return ExtractionConfidence.BAIXA
    return confidence


# ─── small parsing helpers, local to this layout ──────────────────────────

_MASCARADO = "********"

#: The document's own printed TITLE (already accent-stripped/upper — see
#: `normalize_lines`) — a literal substring of `situacao_cadastral`'s own
#: label ("...E DE SITUACAO CADASTRAL"). See the module header: a vision
#: transcription can echo this as its own line, ahead of the real box, in
#: a cell, or as a same-line prefix, and a naive label scan matches it in
#: any of those shapes.
_TITULO_DOCUMENTO = "COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL"

#: Migration 167 §A.1's closed vocabulary. Keys are how the Receita prints
#: it (already accent-stripped/upper via `normalize_lines`); values are the
#: normalised snake_case the CHECK constraint accepts.
_SITUACAO_VOCAB: dict[str, str] = {
    "ATIVA": "ativa",
    "BAIXADA": "baixada",
    "INAPTA": "inapta",
    "SUSPENSA": "suspensa",
    "NULA": "nula",
}

#: Whole-word match of any `_SITUACAO_VOCAB` key, wherever it sits inside a
#: candidate value — shared by `parse_cartao_cnpj`'s own normalisation and
#: `_campo_situacao_cadastral`'s per-occurrence validation, so both use the
#: SAME vocabulary test.
_SITUACAO_VOCAB_RE = re.compile(r"\b(?:" + "|".join(_SITUACAO_VOCAB) + r")\b")

#: The 27 Brazilian UF codes — the closed set `uf` is validated against.
#: Never a guess: a token that isn't in this set is not a UF, however
#: plausible-looking.
_UFS_BR: frozenset[str] = frozenset(
    {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
        "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
        "RR", "SC", "SP", "SE", "TO",
    }
)


def _uf_valida(txt: Optional[str]) -> Optional[str]:
    """`uf`'s OWN box value, validated against `_UFS_BR` — never a guess,
    and never scraped out of a different box's text (see the module
    header). Tolerates stray punctuation/whitespace around the code
    (`"SP."`, `" SP "`, `"sp"`) but does not scan across multiple words —
    a value that isn't cleanly one of the 27 codes once trimmed is simply
    not a UF read, and reads as `None`, not a best-effort pick."""
    if not txt:
        return None
    candidato = re.sub(r"[^A-Z]", "", txt.strip().upper())
    return candidato if candidato in _UFS_BR else None


# ─── the `pdftotext -layout` column-aligned shape (real text layer) ───────


def _linhas_cruas(text: str) -> list[str]:
    """Raw lines, line-ending-normalised only — UNLIKE `normalize_lines`,
    internal whitespace runs survive, because they are the only signal a
    `pdftotext -layout` column boundary leaves behind. See the module
    header."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _colunas(linha_crua: str) -> list[str]:
    """One raw line's column segments — split on a run of 2+ spaces (the
    `-layout` column-gap convention), so a single-spaced multi-word value
    ("SAO PAULO") stays one segment."""
    return [c for c in re.split(r"\s{2,}", linha_crua.strip()) if c]


def _linha_de_rotulos_alinhados(
    linha_crua: str, todos_rotulos: Sequence[str]
) -> Optional[list[str]]:
    """This raw line's own column segments, IF EVERY ONE of them is a
    known label (accent/case-folded) — a column-HEADER row. `None` for
    anything else (prose, or a value row): a header row is never
    partially recognised, because a partial match means this line is
    something other than what it looks like."""
    segmentos = _colunas(linha_crua)
    if len(segmentos) < 2:
        return None
    normalizados = [strip_accents_upper(s).strip() for s in segmentos]
    if all(s in todos_rotulos for s in normalizados):
        return normalizados
    return None


def _valores_colunas_alinhadas(
    text: str, todos_rotulos: Sequence[str]
) -> dict[str, tuple[Optional[str], bool]]:
    """`{rótulo -> (valor, mascarado)}` for every column-aligned
    header+value row pair in `text`. The header row's OWN very next
    NON-BLANK raw line supplies the values, split the SAME way and zipped
    positionally; a value row whose column COUNT doesn't match its
    header's is a positional zip across a different count, so instead of
    guessing it every column of THAT header is recorded as `(None,
    False)` — "the label was found, its value was not readable" — so the
    per-box `_campo` fallback never independently re-derives a value from
    the very same garbled next line (it would otherwise treat the whole
    unsplit line as ONE field's value)."""
    linhas = _linhas_cruas(text)
    saida: dict[str, tuple[Optional[str], bool]] = {}
    for i, linha in enumerate(linhas):
        cabecalho = _linha_de_rotulos_alinhados(linha, todos_rotulos)
        if cabecalho is None:
            continue
        for prox in linhas[i + 1 :]:
            if not prox.strip():
                continue
            valores = _colunas(prox)
            if len(valores) == len(cabecalho):
                for rotulo, valor in zip(cabecalho, valores):
                    valor = valor.strip()
                    if valor == _MASCARADO:
                        saida[rotulo] = (None, True)
                    elif valor:
                        saida[rotulo] = (valor, False)
            else:
                for rotulo in cabecalho:
                    saida.setdefault(rotulo, (None, False))
            break
    return saida


# ─── the vision-transcribed markdown PIPE TABLE shape ──────────────────────

#: A markdown table's own header-separator row (`| --- | --- | --- |`, or
#: the `:---:`/`:--` alignment variants) — never field content.
_CELULA_SEPARADORA_RE = re.compile(r"^:?-{1,}:?$")

#: A value made ONLY of asterisks, one or more — a masked box, whatever the
#: exact run length the model transcribed (measured: a single `*`, not
#: always the prompt's literal `********`). See the module header.
_SOMENTE_ASTERISCOS_RE = re.compile(r"^\*+$")

#: A trailing run of `|`-cell-boundary residue (with whatever whitespace
#: sits around it) that leaked into a value — see the module header.
_RESIDUO_PIPE_RE = re.compile(r"(\s*\|\s*)+$")


def _celulas_de_linha_pipe(linha: str) -> Optional[list[str]]:
    """This raw line's own pipe-delimited cells, IF it looks like a
    markdown-table row (contains `|`) — `None` for anything else. The
    row's own bounding `|`s produce an empty leading/trailing cell, which
    is dropped; a genuinely empty CENTER cell survives as `""` so a
    header row and its value row still zip position-for-position."""
    if "|" not in linha:
        return None
    celulas = [c.strip() for c in linha.split("|")]
    if celulas and celulas[0] == "":
        celulas = celulas[1:]
    if celulas and celulas[-1] == "":
        celulas = celulas[:-1]
    return celulas


def _expandir_celulas_pipe_com_rotulo(text: str, todos_rotulos: Sequence[str]) -> str:
    """Every pipe-table row this document's vision transcription sometimes
    emits (see the module header) fuses several boxes' `RÓTULO valor`
    pairs into pipe-delimited CELLS of ONE raw line, rather than the
    prompt's one-box-per-line shape. Splitting each such row onto one
    line PER CELL lets `_campo` read it exactly like the normal shape, no
    separate matcher — but ONLY for a cell that itself STARTS WITH a
    known label: a cell that does not (measured: the document's own
    TITLE, table-flattened into what looks like a third "column") is
    dropped here rather than handed to `_campo`, where a known label
    buried mid-string in unrelated prose could match — not hypothetical:
    this document's title contains "...E DE SITUAÇÃO CADASTRAL", the
    literal `situacao_cadastral` label, as a SUBSTRING (measured
    2026-09-25). A markdown separator cell (`---`) never starts with a
    label either, so it is dropped by the same rule with no special case.
    A line with no `|` at all passes through unchanged."""
    linhas_saida: list[str] = []
    for linha in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        celulas = _celulas_de_linha_pipe(linha)
        if celulas is None:
            linhas_saida.append(linha)
            continue
        for celula in celulas:
            if not celula:
                continue
            if any(strip_accents_upper(celula).startswith(r) for r in todos_rotulos):
                linhas_saida.append(celula)
    return "\n".join(linhas_saida)


def _linha_pipe_de_rotulos(
    celulas: list[str], todos_rotulos: Sequence[str]
) -> Optional[list[str]]:
    """`celulas`'s own normalised text, IF EVERY cell is EXACTLY a known
    label — the pipe-table analogue of `_linha_de_rotulos_alinhados` for
    the `pdftotext -layout` shape: a true header row of pure labels,
    values on a SEPARATE following row. `None` for a partial match (a
    value row, or a row whose cells already fuse `RÓTULO valor` — see
    `_expandir_celulas_pipe_com_rotulo`)."""
    if len(celulas) < 2:
        return None
    normalizados = [strip_accents_upper(c).strip() for c in celulas]
    if all(n in todos_rotulos for n in normalizados):
        return normalizados
    return None


def _linha_pipe_alternada(
    celulas: list[str], todos_rotulos: Sequence[str]
) -> Optional[list[tuple[str, str]]]:
    """`celulas` as `[(rótulo, valor), ...]` pairs, IF every EVEN-
    positioned cell is EXACTLY a known label and the ODD-positioned ones
    are not ALL labels too (that shape is a pure header row — see
    `_linha_pipe_de_rotulos`, tried first, and given priority so a
    2-label row is never mistaken for one label + one value) — the `LABEL
    | valor |` row shape, one or more fields on a SINGLE row. `None` for
    an odd cell count or an even cell that isn't a label."""
    if len(celulas) < 2 or len(celulas) % 2 != 0:
        return None
    normalizados = [strip_accents_upper(c).strip() for c in celulas]
    if all(n in todos_rotulos for n in normalizados):
        return None  # a pure header row, not label|value pairs
    pares: list[tuple[str, str]] = []
    for i in range(0, len(celulas), 2):
        rotulo_cel = normalizados[i]
        if rotulo_cel not in todos_rotulos:
            return None
        pares.append((rotulo_cel, celulas[i + 1]))
    return pares


def _valores_tabela_pipes(
    text: str, todos_rotulos: Sequence[str]
) -> dict[str, tuple[Optional[str], bool]]:
    """`{rótulo -> (valor, mascarado)}` for every pipe-table row that
    carries a label↔value pairing OUTSIDE the fused-cell shape
    `_expandir_celulas_pipe_com_rotulo` already handles — a separate
    header-row-of-labels + its own following value row (zipped
    positionally, same count-mismatch-⇒-`(None, False)` contract as
    `_valores_colunas_alinhadas`), or a single alternating `LABEL | valor
    |` row. Both are shapes a real vision model could plausibly choose
    instead of the fused-cell one actually measured (2026-09-25) — see
    the module header."""
    linhas = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    saida: dict[str, tuple[Optional[str], bool]] = {}
    for i, linha in enumerate(linhas):
        celulas = _celulas_de_linha_pipe(linha)
        if celulas is None:
            continue

        cabecalho = _linha_pipe_de_rotulos(celulas, todos_rotulos)
        if cabecalho is not None:
            for prox in linhas[i + 1 :]:
                prox_celulas = _celulas_de_linha_pipe(prox)
                if prox_celulas is None:
                    if not prox.strip():
                        continue
                    break
                if all(
                    _CELULA_SEPARADORA_RE.fullmatch(c) for c in prox_celulas if c
                ):
                    continue  # the "| --- | --- |" separator row
                if len(prox_celulas) == len(cabecalho):
                    for rotulo, valor in zip(cabecalho, prox_celulas):
                        valor = valor.strip()
                        if _SOMENTE_ASTERISCOS_RE.fullmatch(valor):
                            saida[rotulo] = (None, True)
                        elif valor:
                            saida[rotulo] = (valor, False)
                else:
                    for rotulo in cabecalho:
                        saida.setdefault(rotulo, (None, False))
                break
            continue

        alternada = _linha_pipe_alternada(celulas, todos_rotulos)
        if alternada is not None:
            for rotulo, valor in alternada:
                valor = valor.strip()
                if not valor:
                    continue
                if _SOMENTE_ASTERISCOS_RE.fullmatch(valor):
                    saida.setdefault(rotulo, (None, True))
                else:
                    saida.setdefault(rotulo, (valor, False))
    return saida


def _sem_residuo_de_pipe(valor: Optional[str]) -> Optional[str]:
    """Strip trailing `|`-cell-boundary residue that leaked into a value —
    see the module header. Defensive: applied to EVERY value regardless
    of which path produced it, not just the pipe-shaped paths above,
    because `_campo`'s "cut at the next known label" cutoff does not know
    about table syntax and can carry a stray boundary pipe through
    unchanged."""
    if valor is None:
        return None
    sem_residuo = _RESIDUO_PIPE_RE.sub("", valor).strip()
    return sem_residuo or None


def _data_br(txt: str) -> Optional[date]:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _embutido_em_rotulo_maior(
    linha: str, pos: int, rotulo: str, todos_rotulos: Sequence[str]
) -> bool:
    """Is this match of `rotulo` actually a SUBSTRING of a longer, different
    label — at ANY position, not just the tail ("SITUACAO CADASTRAL" inside
    "DATA DA SITUACAO CADASTRAL" / "MOTIVO DE SITUACAO CADASTRAL"; "NUMERO"
    (the address box) as the literal PREFIX of "NUMERO DE INSCRICAO")?
    Checked against every OTHER known label so a shorter label never steals
    a longer sibling's own value, regardless of where inside it sits."""
    for outro in todos_rotulos:
        if outro == rotulo or len(outro) <= len(rotulo) or rotulo not in outro:
            continue
        k = outro.find(rotulo)
        inicio = pos - k
        fim = inicio + len(outro)
        if inicio >= 0 and fim <= len(linha) and linha[inicio:fim] == outro:
            return True
    return False


def _embutido_no_titulo(linha: str, pos: int) -> bool:
    """Is this match at `pos` actually sitting inside an occurrence of
    the document's own printed TITLE (`_TITULO_DOCUMENTO`) — the
    document's own line, a table-flattened cell, or a same-line prefix,
    not a real box's label? See the module header. Purely positional
    against every occurrence of the title text in `linha`."""
    inicio = 0
    while True:
        k = linha.find(_TITULO_DOCUMENTO, inicio)
        if k < 0:
            return False
        if k <= pos < k + len(_TITULO_DOCUMENTO):
            return True
        inicio = k + 1


def _proxima_ocorrencia(
    linha: str, busca: int, rotulo: str, todos_rotulos: Sequence[str]
) -> Optional[int]:
    """The next position `>= busca` in `linha` where `rotulo` genuinely
    starts a box's OWN label — never a position sitting inside a longer
    KNOWN label (`_embutido_em_rotulo_maior`) or inside the document's own
    printed title (`_embutido_no_titulo`, see the module header). `None`
    when no further admissible occurrence exists on this line."""
    while True:
        achado = linha.find(rotulo, busca)
        if achado < 0:
            return None
        if not _embutido_em_rotulo_maior(
            linha, achado, rotulo, todos_rotulos
        ) and not _embutido_no_titulo(linha, achado):
            return achado
        busca = achado + 1


def _resolver_valor_caixa(
    linhas: list[str],
    i: int,
    linha: str,
    idx: int,
    rotulo: str,
    todos_rotulos: Sequence[str],
) -> tuple[Optional[str], bool]:
    """`(valor, mascarado)` for the box whose label starts at
    `linha[idx : idx + len(rotulo)]` — the same-line/next-line resolution
    both `_campo` and `_campo_situacao_cadastral` need per ADMISSIBLE
    occurrence (see the module header on why `situacao_cadastral` alone
    needs to try more than one).

    🔴 REAL RECEITA CARTÕES DO NOT ALWAYS PRINT THE COLON THIS MODULE'S
    PROMPT ASKS FOR. Measured against a real Cartão CNPJ (2026-09-24): the
    vision transcription sometimes runs `RÓTULO valor` on one line with no
    separator at all, and sometimes prints the label alone with the value on
    the box's OWN next transcribed line — the prompt's instruction competes
    with "transcribe verbatim" and a real model does not always resolve
    that tension the same way twice. So this tries, in order: same line
    (colon or not, trimmed at the NEXT known label so two concatenated
    boxes never bleed into each other), then the next non-blank line that
    is not itself another label's own box, and not the document's own
    title line.
    """
    resto = linha[idx + len(rotulo) :].lstrip(" :").rstrip()
    corte = len(resto)
    for outro in todos_rotulos:
        if outro == rotulo:
            continue
        p = resto.find(outro)
        if p >= 0:
            corte = min(corte, p)
    resto = resto[:corte].strip(" :")

    if resto == _MASCARADO:
        return (None, True)
    if resto:
        return (resto, False)

    # The label's own line carried nothing usable — Receita boxes that
    # print the value on the NEXT line. Stop at the next line that looks
    # like it starts a DIFFERENT box, or is the document's own title.
    for prox in linhas[i + 1 :]:
        if prox == _TITULO_DOCUMENTO:
            break
        if any(o != rotulo and prox.startswith(o) for o in todos_rotulos):
            break
        if prox == _MASCARADO:
            return (None, True)
        if prox:
            return (prox, False)
    return (None, False)


def _campo(
    linhas: list[str], rotulo: str, *, todos_rotulos: Sequence[str] = ()
) -> tuple[Optional[str], Optional[str], bool]:
    """`(valor, rótulo, mascarado)` for the box labelled `rotulo` — the
    FIRST admissible occurrence only (document order), via
    `_proxima_ocorrencia` + `_resolver_valor_caixa`. `mascarado` is `True`
    only when the box's own value was the literal `********` (distinct
    from "blank"/"never found" — see `endereco_mascarado`).

    `situacao_cadastral` does NOT use this function — see
    `_campo_situacao_cadastral` and the module header for why a
    first-occurrence-wins contract is unsafe for that one field.
    """
    for i, linha in enumerate(linhas):
        idx = _proxima_ocorrencia(linha, 0, rotulo, todos_rotulos)
        if idx is None:
            continue
        valor, mascarado = _resolver_valor_caixa(linhas, i, linha, idx, rotulo, todos_rotulos)
        return (valor, rotulo, mascarado)
    return (None, None, False)


def _campo_situacao_cadastral(
    linhas: list[str], rotulo: str, todos_rotulos: Sequence[str]
) -> tuple[Optional[str], Optional[str], bool]:
    """`(valor, rótulo, mascarado)` for the "SITUAÇÃO CADASTRAL" box,
    specifically — never `_campo`'s generic first-occurrence-wins
    contract for this one field, because THIS field's label is also a
    literal substring of the document's own printed title (see the module
    header, measured live 2026-09-25). A title-echo occurrence sitting
    ABOVE the real box would otherwise win and starve the real one — even
    with `_embutido_no_titulo` filtering the title line's OWN occurrence,
    a real box could still sit further down a document whose FIRST
    admissible (non-title) occurrence happens to resolve to nothing or to
    something else.

    So this walks EVERY admissible occurrence across the whole document,
    in order, and returns the FIRST whose own resolved value contains a
    closed-vocabulary word — never a word picked up from anywhere else in
    the document. A masked occurrence returns immediately (unambiguous).
    When no occurrence resolves to the vocabulary, the FIRST occurrence's
    raw text is returned as a last-resort fallback (so a human still sees
    what was read, same as `_campo`'s single-occurrence contract always
    provided) — `parse_cartao_cnpj` is the one that decides a non
    -vocabulary value becomes `None` with the raw text kept in `rotulos`.
    """
    fallback: Optional[tuple[Optional[str], bool]] = None
    for i, linha in enumerate(linhas):
        busca = 0
        while True:
            idx = _proxima_ocorrencia(linha, busca, rotulo, todos_rotulos)
            if idx is None:
                break
            busca = idx + 1
            valor, mascarado = _resolver_valor_caixa(linhas, i, linha, idx, rotulo, todos_rotulos)
            if mascarado:
                return (None, rotulo, True)
            if valor and _SITUACAO_VOCAB_RE.search(valor):
                return (valor, rotulo, False)
            if fallback is None:
                fallback = (valor, mascarado)
    if fallback is not None:
        return (fallback[0], rotulo, fallback[1])
    return (None, None, False)


_EMITIDO_RE = re.compile(
    r"EMITIDO\s+NO\s+DIA\s+(\d{2})/(\d{2})/(\d{4})\s+AS\s+(\d{2}):(\d{2}):(\d{2})"
)


# ─── public value object ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CartaoCnpjFields:
    """What one Cartão CNPJ yielded.

    `confiancas`/`rotulos` are keyed by this dataclass's own field names —
    same per-field-dict shape `serasa_crednet.CrednetFields` uses, and for
    the same reason: this document's boxes already disambiguate each field,
    so a dict avoids fourteen near-duplicate `<campo>_confianca` attributes.
    """

    cnpj: Optional[str] = None
    cnpj_valido: bool = False
    matriz_filial: Optional[Literal["MATRIZ", "FILIAL"]] = None
    data_abertura: Optional[date] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    porte: Optional[str] = None
    natureza_juridica: Optional[str] = None
    #: Normalised to migration 167 §A.1's closed vocabulary, or `None` when
    #: the printed text does not match one of the five values — see the
    #: module header. The raw text survives at `rotulos["situacao_cadastral"]`.
    situacao_cadastral: Optional[str] = None
    #: "DATA DA SITUAÇÃO CADASTRAL" (E2) — the Cartão CNPJ is the sole
    #: source of truth for this date; see the P0c contract's tech-lead
    #: decision H4 (a Crednet-sourced date is NEVER copied here).
    data_situacao_cadastral: Optional[date] = None
    motivo_situacao: Optional[str] = None
    #: The address block — each its own box (see the module header). `uf`
    #: is validated against the 27 Brazilian states; the other six are
    #: read verbatim, no closed vocabulary.
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    cep: Optional[str] = None
    bairro: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    #: `True` when ANY of the seven address boxes above printed the literal
    #: `********` — the real document masks the WHOLE block together far
    #: more often than it masks a single field within it.
    endereco_mascarado: bool = False
    emitido_em: Optional[datetime] = None
    confiancas: Mapping[str, ExtractionConfidence] = field(default_factory=dict)
    rotulos: Mapping[str, Optional[str]] = field(default_factory=dict)
    source: TextSource = TextSource.NENHUMA
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None


# ─── pure parser ────────────────────────────────────────────────────────

#: `campo name -> the box's printed label` (already accent-stripped/upper —
#: see `normalize_lines`).
_ROTULOS: dict[str, str] = {
    "cnpj": "NUMERO DE INSCRICAO",
    "data_abertura": "DATA DE ABERTURA",
    "razao_social": "NOME EMPRESARIAL",
    "nome_fantasia": "TITULO DO ESTABELECIMENTO (NOME DE FANTASIA)",
    "porte": "PORTE",
    "natureza_juridica": "CODIGO E DESCRICAO DA NATUREZA JURIDICA",
    "logradouro": "LOGRADOURO",
    "numero": "NUMERO",
    "complemento": "COMPLEMENTO",
    "cep": "CEP",
    "bairro": "BAIRRO/DISTRITO",
    "municipio": "MUNICIPIO",
    "uf": "UF",
    "situacao_cadastral": "SITUACAO CADASTRAL",
    "data_situacao_cadastral": "DATA DA SITUACAO CADASTRAL",
    "motivo_situacao": "MOTIVO DE SITUACAO CADASTRAL",
}

#: The seven address-block field names — see `endereco_mascarado`.
_ENDERECO_CAMPOS: tuple[str, ...] = (
    "logradouro", "numero", "complemento", "cep", "bairro", "municipio", "uf",
)


def parse_cartao_cnpj(text: str, source: TextSource) -> CartaoCnpjFields:
    """Text (already ladder-read) → `CartaoCnpjFields`. Pure, never raises."""
    confiancas: dict[str, ExtractionConfidence] = {
        campo: ExtractionConfidence.NENHUMA
        for campo in (*_ROTULOS, "emitido_em", "matriz_filial")
    }
    rotulos: dict[str, Optional[str]] = {campo: None for campo in confiancas}

    todos_rotulos = tuple(_ROTULOS.values())
    # The text-layer's column-aligned shape, tried FIRST — see the module
    # header. `pipes` is the vision transcription's OWN markdown-table
    # shape — a header-row-of-labels + value row, or an alternating
    # `LABEL | valor |` row (also tried here, ahead of `_campo`).
    colunas = _valores_colunas_alinhadas(text or "", todos_rotulos)
    pipes = _valores_tabela_pipes(text or "", todos_rotulos)
    # `_campo`'s own `linhas` are read off text with every pipe-table row's
    # FUSED `RÓTULO valor` cells already expanded onto their own line —
    # see `_expandir_celulas_pipe_com_rotulo` and the module header.
    linhas = normalize_lines(_expandir_celulas_pipe_com_rotulo(text or "", todos_rotulos))

    valores: dict[str, Optional[str]] = {}
    mascarados: dict[str, bool] = {}
    for campo, rotulo in _ROTULOS.items():
        if rotulo in colunas:
            valor, mascarado = colunas[rotulo]
            achado_rotulo: Optional[str] = rotulo
        elif rotulo in pipes:
            valor, mascarado = pipes[rotulo]
            achado_rotulo = rotulo
        elif campo == "situacao_cadastral":
            # This field's label collides with the document's own title —
            # see `_campo_situacao_cadastral` and the module header.
            valor, achado_rotulo, mascarado = _campo_situacao_cadastral(
                linhas, rotulo, todos_rotulos
            )
        else:
            valor, achado_rotulo, mascarado = _campo(linhas, rotulo, todos_rotulos=todos_rotulos)
        # Defensive, whichever path produced `valor` — see
        # `_sem_residuo_de_pipe` and the module header.
        valor = _sem_residuo_de_pipe(valor)
        if valor is not None and _SOMENTE_ASTERISCOS_RE.fullmatch(valor):
            valor = None
            mascarado = True
        valores[campo] = valor
        rotulos[campo] = achado_rotulo
        mascarados[campo] = mascarado
        if valor is not None:
            confiancas[campo] = ExtractionConfidence.ALTA

    endereco_mascarado = any(mascarados.get(campo, False) for campo in _ENDERECO_CAMPOS)

    cnpj_valor: Optional[str] = None
    cnpj_valido = False
    matriz_filial: Optional[Literal["MATRIZ", "FILIAL"]] = None
    if valores["cnpj"]:
        m = re.search(r"[0-9A-Z./\-]{14,20}", valores["cnpj"])
        if m:
            cnpj_bruto = m.group()
            cnpj_valido = _cnpj_is_valid(cnpj_bruto)
            cnpj_valor = format_cnpj(cnpj_bruto) or cnpj_bruto
            confiancas["cnpj"] = (
                ExtractionConfidence.ALTA if cnpj_valido else ExtractionConfidence.BAIXA
            )
        if "MATRIZ" in valores["cnpj"]:
            matriz_filial = "MATRIZ"
        elif "FILIAL" in valores["cnpj"]:
            matriz_filial = "FILIAL"
        if matriz_filial is not None:
            # Read out of the SAME box as `cnpj` ("NÚMERO DE INSCRIÇÃO" —
            # the Receita prints MATRIZ/FILIAL right beside the number, not
            # in a box of its own), so it carries that box's own label and
            # confidence just like every other field does.
            confiancas["matriz_filial"] = ExtractionConfidence.ALTA
            rotulos["matriz_filial"] = rotulos["cnpj"]

    data_abertura = _data_br(valores["data_abertura"]) if valores["data_abertura"] else None
    if valores["data_abertura"] and data_abertura is None:
        confiancas["data_abertura"] = ExtractionConfidence.NENHUMA

    data_situacao_cadastral = (
        _data_br(valores["data_situacao_cadastral"])
        if valores["data_situacao_cadastral"]
        else None
    )
    if valores["data_situacao_cadastral"] and data_situacao_cadastral is None:
        confiancas["data_situacao_cadastral"] = ExtractionConfidence.NENHUMA

    situacao_cadastral: Optional[str] = None
    if valores["situacao_cadastral"]:
        bruto = valores["situacao_cadastral"].strip()
        # The closed vocabulary word may sit anywhere in the box's text
        # ("BAIXADA" alone, or "SITUACAO: BAIXADA" if the model re-echoed
        # the label) — matched as a whole word, never a substring of a
        # longer, unrelated word.
        achado = next(
            (v for k, v in _SITUACAO_VOCAB.items() if re.search(rf"\b{k}\b", bruto)),
            None,
        )
        if achado is not None:
            situacao_cadastral = achado
        else:
            # Doesn't match the closed vocabulary: field stays None, but the
            # RAW text is kept at rotulos so a human can see what was
            # actually printed — see the module header.
            confiancas["situacao_cadastral"] = ExtractionConfidence.NENHUMA
            rotulos["situacao_cadastral"] = bruto

    # 🔴 THE RECEITA MASKS THE ADDRESS BLOCK OF EVERY BAIXADA COMPANY
    # (verified 5/5 real Cartões, 2026-09-24). A transcription that reports
    # address VALUES here anyway is not a parser gap — it is the vision
    # model FABRICATING a plausible-looking address instead of reading the
    # mask (measured live: 6/7 fields "found" on a REALIZA Cartão whose
    # address boxes are ALL `********`). So this is a policy override, not
    # a best-effort read: every address field is forced `None` here
    # regardless of what the transcription said, the block is always
    # treated as masked, and — when the transcription DID carry values —
    # the fabrication stays VISIBLE via `aviso` rather than silently
    # discarded.
    endereco_descartado_por_baixada = False
    if situacao_cadastral == "baixada":
        if any(valores[campo] is not None for campo in _ENDERECO_CAMPOS):
            endereco_descartado_por_baixada = True
        for campo in _ENDERECO_CAMPOS:
            valores[campo] = None
            confiancas[campo] = ExtractionConfidence.NENHUMA
        endereco_mascarado = True

    uf = _uf_valida(valores["uf"])
    if valores["uf"] and uf is None:
        # The label was found but nothing in its value validated as one of
        # the 27 UFs — never guessed, so this reads as unreadable, not
        # `rotulos["uf"]` losing the label that WAS matched.
        confiancas["uf"] = ExtractionConfidence.NENHUMA

    emitido_em: Optional[datetime] = None
    m = _EMITIDO_RE.search("\n".join(linhas))
    if m:
        dia, mes, ano, hh, mm, ss = m.groups()
        try:
            emitido_em = datetime(int(ano), int(mes), int(dia), int(hh), int(mm), int(ss))
            confiancas["emitido_em"] = ExtractionConfidence.ALTA
            rotulos["emitido_em"] = "EMITIDO NO DIA"
        except ValueError:
            emitido_em = None

    avisos: list[str] = []
    if cnpj_valor is not None and not cnpj_valido:
        avisos.append("cnpj_digito_invalido")
    if endereco_descartado_por_baixada:
        avisos.append("endereco_descartado_baixada")
    aviso = ",".join(avisos) if avisos else None

    return CartaoCnpjFields(
        cnpj=cnpj_valor,
        cnpj_valido=cnpj_valido,
        matriz_filial=matriz_filial,
        data_abertura=data_abertura,
        razao_social=valores["razao_social"],
        nome_fantasia=valores["nome_fantasia"],
        porte=valores["porte"],
        natureza_juridica=valores["natureza_juridica"],
        situacao_cadastral=situacao_cadastral,
        data_situacao_cadastral=data_situacao_cadastral,
        motivo_situacao=valores["motivo_situacao"],
        logradouro=valores["logradouro"],
        numero=valores["numero"],
        complemento=valores["complemento"],
        cep=valores["cep"],
        bairro=valores["bairro"],
        municipio=valores["municipio"],
        uf=uf,
        endereco_mascarado=endereco_mascarado,
        emitido_em=emitido_em,
        confiancas={campo: _temper(c, source) for campo, c in confiancas.items()},
        rotulos=rotulos,
        source=source,
        aviso=aviso,
    )


# ─── Protocol + Fake + Real + factory ──────────────────────────────────────


@runtime_checkable
class CartaoCnpjExtractor(Protocol):
    """Bytes + mimetype → a Cartão CNPJ's typed fields.

    Implementations MUST NOT raise for an unreadable/corrupt document — they
    return `CartaoCnpjFields` with `error` set."""

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CartaoCnpjFields:
        ...


class FakeCartaoCnpjExtractor:
    """Deterministic extractor — the dev/test default.

    Uses the same real, checksum-valid CNPJ `serasa_crednet.FakeCrednetExtractor`
    does (`11.222.333/0001-81`) — see that module's Fake docstring for why an
    arithmetically invalid identifier would be the wrong default.

    Pass `result=` to script a specific outcome (`cnpj_divergente`, a masked
    address, a failure) — same convention as `fake.FakeIdentityExtractor` /
    `serasa_crednet.FakeCrednetExtractor`."""

    def __init__(self, result: Optional[CartaoCnpjFields] = None) -> None:
        self._result = result

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CartaoCnpjFields:
        if self._result is not None:
            return self._result
        if not content:
            return CartaoCnpjFields(error="empty_document", error_message="no bytes to read")
        campos = (
            "cnpj", "matriz_filial", "data_abertura", "razao_social",
            "nome_fantasia", "porte", "natureza_juridica", "situacao_cadastral",
            "data_situacao_cadastral", "motivo_situacao", "logradouro",
            "numero", "complemento", "cep", "bairro", "municipio", "uf",
            "emitido_em",
        )
        return CartaoCnpjFields(
            cnpj="11.222.333/0001-81",
            cnpj_valido=True,
            matriz_filial="MATRIZ",
            data_abertura=date(2010, 3, 15),
            razao_social="EMPRESA FAKE SINTETICA LTDA",
            nome_fantasia="FAKE SINTETICA",
            porte="DEMAIS",
            natureza_juridica="206-2 - SOCIEDADE EMPRESARIA LIMITADA",
            situacao_cadastral="ativa",
            data_situacao_cadastral=date(2010, 3, 15),
            motivo_situacao="MOTIVO FAKE SINTETICO",
            logradouro="RUA FAKE SINTETICA",
            numero="99",
            complemento="SALA FAKE",
            cep="99999-999",
            bairro="BAIRRO FAKE",
            municipio="SAO PAULO FAKE",
            uf="SP",
            endereco_mascarado=False,
            emitido_em=datetime(2026, 1, 1, 12, 0, 0),
            confiancas={campo: ExtractionConfidence.ALTA for campo in campos},
            # `matriz_filial` has no box of its own — it rides the "cnpj"
            # box's label, matching `parse_cartao_cnpj`'s own behaviour.
            rotulos={
                campo: (_ROTULOS.get("cnpj") if campo == "matriz_filial" else _ROTULOS.get(campo))
                for campo in campos
            },
            source=TextSource.TEXT_LAYER,
        )


class LadderCartaoCnpjExtractor:
    """Text-layer-first, vision-second Cartão CNPJ reader.

    Construct via `make_cartao_cnpj_extractor(real=True)`."""

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        resolver=None,
        provider: Optional[str] = None,
    ) -> None:
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=DOCUMENT_PROMPT_CARTAO_CNPJ,
            resolver=resolver,
            provider=provider,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CartaoCnpjFields:
        if not content:
            return CartaoCnpjFields(error="empty_document", error_message="no bytes to read")

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return CartaoCnpjFields(source=source, error=err[0], error_message=err[1])
        if not text.strip():
            return CartaoCnpjFields(source=source)

        return parse_cartao_cnpj(text, source)


def make_cartao_cnpj_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> CartaoCnpjExtractor:
    """Return a Cartão CNPJ extractor. Fake-by-default.

    A single page always affords the ladder's own default page count, so —
    unlike `make_crednet_extractor` — there is no `max_pages` override here.
    """
    if not real:
        return FakeCartaoCnpjExtractor()
    return LadderCartaoCnpjExtractor(org_id=org_id, provider=provider)


__all__ = [
    "CartaoCnpjExtractor",
    "CartaoCnpjFields",
    "DOCUMENT_PROMPT_CARTAO_CNPJ",
    "FakeCartaoCnpjExtractor",
    "LadderCartaoCnpjExtractor",
    "make_cartao_cnpj_extractor",
    "parse_cartao_cnpj",
]
