"""The `IMÓVEL:` quote's text rules — how the office assembles it.

Derived from the 30 signed contracts whose answer keys carry a quote
(`tests/e2e_contrato/README.md`); counts at the foot of this docstring.

The quote is: the matrícula's own `descricao_imovel` block, THEN each
averbação the operator selected (`PUT /api/matriculas/contratos/{id}/atos`)
as `Conforme AV.<n>, <the act's own wording>`, THEN the template's fixed
"Imóvel devidamente cadastrado … sob nº <inscrição municipal> …" sentence.

* The act wording is the matrícula's, copied: only its register header
  (`AV-4/12.345 - Em 5 de maio de 2010.`) and a leading ALL-CAPS title
  (`CADASTRO - `) are dropped, whitespace is flowed.
* Only `AV` acts that change the physical description are carried
  (`politica.AVERBACOES_CITADAS`); selected ônus/cancelamento/casamento/
  cadastro acts feed other clauses, never this quote.
* Only `AV` acts are carried; `R` acts (títulos, ônus) never are — the
  título aquisitivo has its own clause.
* The matrícula's own `INSCRIÇÃO CADASTRAL: …` / `CONTRIBUINTE …` line is
  never printed: the only cadastral number in a signed quote is the
  prefeitura one, from the imóvel data (kept in data, printed by the
  template sentence).
* Matrícula measures are pt-BR with a decimal comma. `11.500m2` (a dot the
  matrícula, or the typed card, used as a decimal) reads as thousands in
  pt-BR, so it is re-spelled `11,500m2` here — the single point where the
  quote's numbers are rendered.

Corpus (30 keys): 8 carry >=1 averbação (10 `Conforme AV` acts in all; 7
mention construction/habite-se, 7 an official street number — overlapping);
0 carry a matrícula inscrição cadastral line; 29 print the prefeitura
sentence (28 once, 1 twice), 1 none; 0 print a dot-thousands area with no
decimals.
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

from app.modules.card_hub.contrato_gerador.politica import AVERBACOES_CITADAS, AVERBACOES_NAO_CITADAS

from noctusai_lib.integrations.documents.formatting import FormatRange
from noctusai_lib.primitives.accents import fold_accents_ascii

_DATA_DO_ATO = r"(?:\d{1,2}\s+de\s+\w+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
#: The register header, in every shape seen: `AV-4/12.345 - Em 5 de maio de
#: 2010.` · `Av.99, em 9 de janeiro de 2020. -` · `AV. 9 – em 9 de março de
#: 2020 (NUMERAÇÃO)` + `(prenotado em … protocolo nº …)`.
_CABECALHO_AV = re.compile(
    r"^\s*AV[\s.\-]*\d+(?:\s*/\s*\d[\d.]*)?\s*[-–—,]?\s*"
    rf"(?:em\s+{_DATA_DO_ATO}\s*\.?\s*[-–—]?\s*)?(?:\([^)\n]*\)\s*)*",
    re.IGNORECASE,
)
#: A leading ALL-CAPS nature title (`CADASTRO - `, `CONSTRUÇÃO / LOGRADOURO\n`).
_TITULO_CAIXA_ALTA = re.compile(r"^[A-ZÀ-Ú][A-ZÀ-Ú /]{2,}?\s*(?:[-–—:]\s*|\n\s*)(?=\S)")
#: Registry page furniture / signature lines: never part of the act's body.
_LINHA_MOBILIARIO = re.compile(
    r"^\W*(?:(?:continua|segue)\b.*\b(?:ficha|verso)|CN[MJS]\b|LIVRO\s+N|REGISTRO\s+GERAL|SERVENTIA\b"
    r"|REGISTRO\s+DE\s+IM[ÓO]VEIS|E\s+CIVIL\s+DE\s+PESSOAS|(?:matr[ií]cula|data|ficha|folha)\W*$"
    r"|MOD\.?\s*\d|selo\b|escrevente\b|oficial\W*$|substitut|tabeli|EU,|digitei|D\.?\s?R\$|emolumentos|prot\.)"
    r"|^[\W\d.]*$"
    r"|[-–—]\s*(?:escrevente|oficial|substituto)\W*$"
    r"|^[^\d\n,]{2,40},\s*(?:\d{1,2}\s+)?de\s+\S+(?:\s+de\s+\S+)?\W*$",
    re.IGNORECASE,
)
#: The closing administrative sentences (CND presented, attributed value) —
#: the office stops the quote before them.
_FECHO_ADMINISTRATIVO = re.compile(r"\s*\b(?:Foi|Fora)\s+apresentad", re.IGNORECASE)
_HIFEN_DE_QUEBRA = re.compile(r"(?<=[a-zà-ú])-\s+(?=[a-zà-ú])")
_NUMERO_NO_CABECALHO = re.compile(r"^\s*AV[\s.\-]*(\d+)", re.IGNORECASE)

#: The matrícula's own cadastral-number line, up to the end of its sentence.
_INSCRICAO_PROPRIA = re.compile(
    r"(?:INSCRI[ÇC][ÃA]O\s+CADASTRAL|CONTRIBUINTE|CADASTRO\s+MUNICIPAL)\b[^\n]*?"
    r"(?:\.\s*(?=\n|$|[A-ZÀ-Ú])|\n|$)",
    re.IGNORECASE,
)

#: `11.500m2` / `3.200 m²` — dot-thousands glued to an area unit, no decimals.
_AREA_PONTO = re.compile(r"(?<![\d.,])(\d{1,3})\.(\d{3})(?![\d.,])(?=\s?(?:m²|m2|m\b))")


def normalizar_areas(texto: str) -> str:
    """Same length as the input (`.` → `,`), so formatting ranges stay valid."""
    return _AREA_PONTO.sub(lambda m: f"{m.group(1)},{m.group(2)}", texto)


def _remover(texto: str, ranges: Sequence[FormatRange], spans: list[tuple[int, int]]):
    """`texto` minus `spans`, with `ranges` re-based onto the shorter text."""
    if not spans:
        return texto, list(ranges)
    saida: list[str] = []
    cursor = 0
    mapa: list[tuple[int, int, int]] = []  # (orig_ini, orig_fim, novo_ini)
    novo = 0
    for s, e in spans:
        if s > cursor:
            saida.append(texto[cursor:s])
            mapa.append((cursor, s, novo))
            novo += s - cursor
        cursor = max(cursor, e)
    if cursor < len(texto):
        saida.append(texto[cursor:])
        mapa.append((cursor, len(texto), novo))
    novos: list[FormatRange] = []
    for r in ranges:
        for ini, fim, base in mapa:
            lo, hi = max(r.start, ini), min(r.end, fim)
            if lo < hi:
                novos.append(
                    FormatRange(base + lo - ini, base + hi - ini, bold=r.bold, underline=r.underline)
                )
    return "".join(saida), novos


def sem_inscricao_da_matricula(texto: str, ranges: Sequence[FormatRange] = ()):
    spans = [m.span() for m in _INSCRICAO_PROPRIA.finditer(texto)]
    return _remover(texto, ranges, spans)


def _dobrar(texto: str) -> str:
    sem = fold_accents_ascii(texto)
    return re.sub(r"\s+", " ", sem.lower()).strip()


def averbacao_deve_ser_citada(texto: str) -> bool:
    """Does this act change the property's description (the office quotes
    only those — `politica.AVERBACOES_CITADAS`)? A veto term in the act's
    title/opening (first 80 chars after the header) always wins; a quoting
    term is looked for in the first 250."""
    corpo = _dobrar(_CABECALHO_AV.sub("", texto or "", count=1))
    if any(t in corpo[:80] for t in AVERBACOES_NAO_CITADAS):
        return False
    return any(t in corpo[:250] for t in AVERBACOES_CITADAS)


def corpo_do_ato(texto: str) -> str:
    """The act's BODY only: header (once) and nature title dropped, registry
    page furniture / signature lines dropped, the closing "Foi apresentada
    …" administrative sentences cut, whitespace flowed, line-break
    hyphenation (`to- tal`, lowercase both sides only) rejoined."""
    corpo = texto
    for _ in range(2):  # a duplicated header is dropped, not printed twice
        corpo = _CABECALHO_AV.sub("", corpo, count=1)
    corpo = _TITULO_CAIXA_ALTA.sub("", corpo, count=1)
    linhas = [ln for ln in corpo.split("\n") if not _LINHA_MOBILIARIO.search(ln.strip() or "x")]
    corpo = re.sub(r"\s+", " ", " ".join(linhas)).strip()
    achado = _FECHO_ADMINISTRATIVO.search(corpo)
    if achado:
        corpo = corpo[: achado.start()].rstrip()
    return _HIFEN_DE_QUEBRA.sub("", corpo)


def averbacao_citada(numero: Optional[object], texto: str) -> Optional[str]:
    """`Conforme AV.<n>, <wording>.` for one selected averbação; `None` when
    nothing remains after the header (an empty act is never quoted)."""
    n = str(numero).strip() if numero not in (None, "") else None
    if n is None:
        achado = _NUMERO_NO_CABECALHO.match(texto or "")
        n = achado.group(1) if achado else None
    corpo = corpo_do_ato(texto or "")
    if not corpo:
        return None
    if corpo[-1] not in ".;!?":
        corpo += "."
    return f"Conforme AV.{n}, {corpo}" if n else f"Conforme averbação, {corpo}"


def citacao(
    texto: str,
    ranges: Sequence[FormatRange],
    averbacoes: Sequence[tuple[object, str]] = (),
):
    """The final quote `(texto, ranges)`: description minus the matrícula's
    own inscrição, plus the selected averbações, areas pt-BR-normalised."""
    texto, ranges = sem_inscricao_da_matricula(texto.rstrip(), ranges)
    texto = texto.rstrip()
    ranges = [r for r in ranges if r.end <= len(texto)]
    citadas = [
        c
        for c in (averbacao_citada(n, t) for n, t in averbacoes if averbacao_deve_ser_citada(t))
        if c
    ]
    if citadas:
        texto = f"{texto} {' '.join(citadas)}"
    return normalizar_areas(texto), ranges
