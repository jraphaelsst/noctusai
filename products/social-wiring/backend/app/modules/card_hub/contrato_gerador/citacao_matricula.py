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
import unicodedata
from typing import Optional, Sequence

from app.modules.card_hub.contrato_gerador.politica import AVERBACOES_CITADAS, AVERBACOES_NAO_CITADAS

from noctusai_lib.integrations.documents.formatting import FormatRange

#: `AV-4/12.345 - Em 5 de maio de 2010. ` / `AV.4 - ` / `AV 4/1 - Em 1/1/2010. `
_CABECALHO_AV = re.compile(
    r"^\s*AV[\s.\-]*\d+(?:\s*/\s*\d[\d.]*)?\s*[-–—]\s*(?:Em\s[^.\n]*\.\s*)?", re.IGNORECASE
)
#: A leading ALL-CAPS nature title (`CADASTRO - Pelo …`).
_TITULO_CAIXA_ALTA = re.compile(r"^[A-ZÀ-Ú][A-ZÀ-Ú ]{2,}\s*[-–—:]\s+(?=\S)")
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
    sem = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
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


def averbacao_citada(numero: Optional[object], texto: str) -> Optional[str]:
    """`Conforme AV.<n>, <wording>.` for one selected averbação; `None` when
    nothing remains after the header (an empty act is never quoted)."""
    n = str(numero).strip() if numero not in (None, "") else None
    if n is None:
        achado = _NUMERO_NO_CABECALHO.match(texto or "")
        n = achado.group(1) if achado else None
    corpo = _CABECALHO_AV.sub("", texto or "", count=1)
    corpo = _TITULO_CAIXA_ALTA.sub("", corpo, count=1)
    corpo = re.sub(r"\s+", " ", corpo).strip()
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
