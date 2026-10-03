"""Pacto antenupcial → `PactoAntenupcialLido`. Protocol + Fake + Real +
factory, sibling of `ficha_cadastral_extractor.py` — the shared ladder
(`ladder.py`: PDF text layer first, rasterize→vision second) produces the
text, `parse_pacto_antenupcial` (pure) reads it.

WHAT A "PACTO ANTENUPCIAL" FILE IS, MEASURED (P4 corpus, deal 858,
2026-10-03)
----------------------------------------------------------------------
Two documents travel under this name, and the office files either one:

1. The **escritura pública** itself, lavrada at a Tabelião de Notas — it
   carries its own livro/folhas and the date it was drawn up.
2. The **registro** of that escritura at the couple's first-domicile
   Registro de Imóveis (Livro 3 – Registro Auxiliar, "R.<n> em <data>") —
   a certidão that CITES the escritura ("Escritura Pública de Pacto
   Antenupcial lavrada em <data>, no <n>º Tabelião de Notas ... (Livro
   <x>, folhas <y>)") and adds its own registro number.

The deal-858 file is shape 2 (a 3-page image-only certidão of the
registro). The signed contract cites the ESCRITURA's own facts — "lavrada
aos <data>, pelo <n>º Tabelião de Notas, nesta Capital, no Livro nº <x>,
Página nº <y>" — so those are read from either shape; the registro's own
number/book/office is read only when the document is shape 2.

WHAT IS READ
------------
- `regime_bens` — `civil_status.find_regime_bens` (the same unlabelled,
  canonical-vocabulary reader every certidão uses; its own notes on
  `separacao_total` vs `separacao_obrigatoria` apply unchanged — a pacto
  never establishes the latter).
- `data_escritura`, `tabelionato`, `livro`, `folhas` — the escritura's.
- `registro` — `RegistroPacto(numero, livro, cartorio, data)`, shape 2 only.
- `data_casamento` — when the registro states the marriage date.
- `conjuges` — each contracting party: the name printed before its own
  check-digit-valid CPF (a CPF failing its check digits is never
  returned). A name with no valid CPF beside it is not returned either —
  a product matches spouses BY CPF first, and a guessed name is worse
  than none.

Nothing here is inferred: an absent fact stays `None`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol, runtime_checkable

from noctusai_lib.integrations.documents.civil_status import (
    _iter_datas,
    find_regime_bens,
    normalize,
)
from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_valido
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource


@dataclass(frozen=True)
class ConjugePacto:
    """One contracting party — `cpf` always passes its check digits."""

    nome: str
    cpf: str


@dataclass(frozen=True)
class RegistroPacto:
    """The registro of the escritura at a Registro de Imóveis (shape 2)."""

    numero: Optional[str] = None
    livro: Optional[str] = None
    cartorio: Optional[str] = None
    data: Optional[date] = None


@dataclass(frozen=True)
class PactoAntenupcialLido:
    regime_bens: Optional[str] = None
    regime_bens_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    data_escritura: Optional[date] = None
    tabelionato: Optional[str] = None
    livro: Optional[str] = None
    folhas: Optional[str] = None
    registro: Optional[RegistroPacto] = None
    data_casamento: Optional[date] = None
    conjuges: tuple[ConjugePacto, ...] = ()
    source: Optional[TextSource] = None
    error: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def achou_algo(self) -> bool:
        return bool(
            self.regime_bens or self.data_escritura or self.tabelionato
            or self.registro or self.conjuges
        )


# ─── pure parser ────────────────────────────────────────────────────────


def _dobrar(texto: str) -> str:
    """Upper-case, accent-stripped, LENGTH-PRESERVING — every offset in the
    result is the same offset in `texto`, so a match can be sliced back out
    of the original (accents and case intact)."""
    saida = []
    for c in texto:
        base = "".join(
            ch for ch in unicodedata.normalize("NFKD", c) if not unicodedata.combining(ch)
        )
        saida.append(base.upper() if len(base) == 1 else c.upper()[:1] or " ")
    return "".join(saida)


def _limpo(trecho: str) -> str:
    return re.sub(r"\s+", " ", trecho).strip(" ,.;:-–")


def _primeira_data(texto: str) -> Optional[date]:
    """The first date `civil_status._iter_datas` parses in `texto` — plus
    the escritura's own opening form "aos <dia> dias do mês de <mês> de
    <ano>", rewritten into the "<dia> de <mês> de <ano>" shape that reader
    already understands."""
    norm = normalize(texto)
    norm = re.sub(r"\bDIAS?\s+DO\s+MES\s+DE\b", "DE", norm)
    norm = re.sub(r"(\d)\s*[O°]\s+DE\b", r"\1 DE", norm)  # "1º de" → "1 de"
    datas = sorted(_iter_datas(norm), key=lambda par: par[0])
    return datas[0][1] if datas else None


_TABELIAO_RE = re.compile(
    r"(?:\b\d{1,3}\s*[O°]?\s*|\b[A-Z]+\s+(?:[A-Z]+\s+)?)?"
    r"(?:TABELIAO|TABELIONATO|OFICIO|CARTORIO)\s+DE\s+NOTAS"
    # The locality tail stays on the heading's own LINE (`[ \t]`, never
    # `\s`): a heading is routinely followed by "LIVRO ..." on the next.
    r"(?:[ \t]+(?:DESTA|NESTA|DA)[ \t]+(?:CAPITAL|CIDADE|COMARCA(?:[ \t]+DE[ \t]+[A-Z]+(?:[ \t]+[A-Z]+)?)?)"
    r"|[ \t]+(?:DE|DO[ \t]+MUNICIPIO[ \t]+DE)[ \t]+[A-Z]+(?:[ \t]+(?!LIVRO\b|FOLHAS?\b)[A-Z]+){0,2})?"
)
#: Ordinal-word prefixes a heading may print before "TABELIÃO" — only these
#: are kept as part of the office's name; any other word is prose.
_ORDINAIS = re.compile(
    r"^(?:PRIMEIRO|SEGUNDO|TERCEIRO|QUARTO|QUINTO|SEXTO|SETIMO|OITAVO|NONO|DECIMO"
    r"|VIGESIMO|TRIGESIMO)\b"
)
_LIVRO_RE = re.compile(r"\bLIVRO\s*(?:N[O°.]*\s*)?(\d[\d.]*)")
_FOLHAS_RE = re.compile(
    r"\b(?:FOLHAS?|FLS?\.?|PAGINAS?|PAGS?\.?)\s*(?:N[O°.]*\s*)?"
    r"(\d+\s*(?:V(?:ERSO)?\b)?(?:\s*(?:/|A|E|-|ATE)\s*\d+\s*(?:V(?:ERSO)?\b)?)?)"
)
_LAVRADA_RE = re.compile(r"\bLAVRAD[AO]\b")
_REGISTRO_AUXILIAR_RE = re.compile(r"\bLIVRO\s*(?:N[O°.]*\s*)?3\s*[-–]?\s*REGISTRO\s+AUXILIAR")
_REGISTRO_NUM_RE = re.compile(r"\bR\s*\.\s*(?:\d+\s*/\s*)?(\d{1,3}(?:\.\d{3})+|\d+)\b")
_REGISTRADO_SOB_RE = re.compile(
    r"\bREGISTRAD[AO]\s+SOB\s+(?:O\s+)?(?:N[O°.]*|NUMERO)\s*(\d{1,3}(?:\.\d{3})+|\d+)"
)
_OFICIAL_RI_RE = re.compile(
    r"(?:\b\d{1,3}\s*[O°]?\s*|\b[A-Z]+\s+(?:[A-Z]+\s+)?)?"
    r"(?:OFICIAL|CARTORIO|OFICIO|SERVENTIA)\s+DE?\s*(?:DO\s+)?REGISTROS?\s+DE\s+IMOVEIS"
    r"(?:[ \t]+(?:DA[ \t]+COMARCA[ \t]+)?DE[ \t]+[A-Z]+(?:[ \t]+(?!LIVRO\b)[A-Z]+)?)?"
)
#: "O casamento foi realizado ... em <data>" — the registro routinely
#: breaks this sentence across a page ("O casamento foi / (continua no
#: verso) / realizado por dito regime em ..."), so the verb is looked for
#: in a window after the opener, not contiguously.
_CASAMENTO_RE = re.compile(r"\bCASAMENTO\s+FOI\b|\bCASARAM-?SE\b|\bCONTRAIRAM\s+MATRIMONIO\b")
_REALIZADO_RE = re.compile(r"\bREALIZADO\b")
_CPF_RE = re.compile(r"\b(\d{3}\.?\d{3}\.?\d{3}\s*[-–.]?\s*\d{2})\b")
#: An all-caps person-name run (2..8 words) — the escritura prints the
#: contracting parties' names in capitals before their qualification.
_NOME_RE = re.compile(r"\b([A-Z]{2,}(?:\s+(?:D[AEO]S?|E)\s+|\s+)){1,7}[A-Z]{2,}\b")
_NAO_NOME = re.compile(
    r"\b(?:CPF|RG|SSP|CNPJ|LIVRO|REGISTRO|OFICIAL|TABELIAO|ESCRITURA|PACTO|ANTENUPCIAL"
    r"|CARTORIO|REPUBLICA|BRASIL|CAPITAL|SAO\s+PAULO|DE\s+BENS|SEPARACAO|COMUNHAO)\b"
)


_PALAVRAS_DE_CARTORIO = frozenset(
    {"TABELIAO", "TABELIONATO", "OFICIO", "CARTORIO", "OFICIAL", "SERVENTIA"}
)


def _cortar_ordinal(original: str, dobrado: str) -> str:
    """Drop leading words that are neither a number, an ordinal word, nor
    the office's own noun ("NO 14º Tabelião" → "14º Tabelião") — the
    optional word prefix in the office regexes exists for "DÉCIMO OITAVO
    OFICIAL ...", not for the prose before it."""
    while True:
        m = re.match(r"(\S+)\s+", dobrado)
        if m is None:
            return original
        palavra = m.group(1)
        if palavra[:1].isdigit() or _ORDINAIS.match(palavra) or palavra in _PALAVRAS_DE_CARTORIO:
            return original
        original, dobrado = original[m.end():], dobrado[m.end():]


def _office(texto: str, dobrado: str, padrao: re.Pattern[str], inicio: int = 0) -> Optional[str]:
    m = padrao.search(dobrado, inicio)
    if not m:
        return None
    return _limpo(_cortar_ordinal(texto[m.start():m.end()], dobrado[m.start():m.end()]))


def _conjuges(texto: str, dobrado: str) -> tuple[ConjugePacto, ...]:
    vistos: dict[str, ConjugePacto] = {}
    for m in _CPF_RE.finditer(dobrado):
        cpf = only_digits(m.group(1))
        if len(cpf) != 11 or not _cpf_valido(cpf) or cpf in vistos:
            continue
        janela_ini = max(0, m.start() - 260)
        janela = dobrado[janela_ini:m.start()]
        nome: Optional[str] = None
        for n in _NOME_RE.finditer(janela):
            candidato = n.group(0)
            if _NAO_NOME.search(candidato) or len(candidato.split()) < 2:
                continue
            nome = _limpo(texto[janela_ini + n.start():janela_ini + n.end()])
        if nome:
            vistos[cpf] = ConjugePacto(nome=nome, cpf=cpf)
    # A pacto names exactly two people; more than two distinct valid CPFs
    # means something else (witnesses, a procurador) is in the read —
    # ambiguous, so nobody is returned rather than the wrong pair.
    return tuple(vistos.values()) if len(vistos) <= 2 else ()


def parse_pacto_antenupcial(
    texto: str, source: Optional[TextSource] = None,
) -> PactoAntenupcialLido:
    """Read a pacto antenupcial (escritura or its registro) off its text."""
    if not (texto or "").strip():
        return PactoAntenupcialLido(source=source)
    dobrado = _dobrar(texto)

    regime, conf, _rotulo = find_regime_bens(texto)
    confianca = ExtractionConfidence(conf) if regime else ExtractionConfidence.NENHUMA
    if regime and source is not TextSource.TEXT_LAYER:
        confianca = ExtractionConfidence.MEDIA

    # The escritura's own facts: anchored on "lavrada" when the document
    # cites it (shape 2), else on the Tabelião heading (shape 1).
    lav = _LAVRADA_RE.search(dobrado)
    ancora = lav.start() if lav else 0
    trecho_esc = slice(ancora, ancora + 400) if lav else slice(0, len(dobrado))
    janela_esc = dobrado[trecho_esc]

    data_escritura = _primeira_data(texto[trecho_esc][:160]) if lav else None
    tabelionato = _office(texto, dobrado, _TABELIAO_RE, ancora)
    if tabelionato is None and lav:
        tabelionato = _office(texto, dobrado, _TABELIAO_RE)
    if data_escritura is None and not lav:
        m_aos = re.search(r"\bAOS\b", dobrado)
        if m_aos:
            data_escritura = _primeira_data(texto[m_aos.start():m_aos.start() + 160])

    registro_auxiliar = _REGISTRO_AUXILIAR_RE.search(dobrado)
    livro = folhas = None
    for m in _LIVRO_RE.finditer(janela_esc):
        abs_ini = (trecho_esc.start or 0) + m.start()
        if registro_auxiliar and _REGISTRO_AUXILIAR_RE.match(dobrado, abs_ini):
            continue
        livro = m.group(1).strip(".")
        resto = janela_esc[m.end():m.end() + 80]
        f = _FOLHAS_RE.search(resto)
        if f:
            folhas = _limpo(texto[(trecho_esc.start or 0) + m.end() + f.start(1):
                                  (trecho_esc.start or 0) + m.end() + f.end(1)])
        break
    if folhas is None:
        f = _FOLHAS_RE.search(janela_esc)
        if f:
            ini = (trecho_esc.start or 0) + f.start(1)
            folhas = _limpo(texto[ini:(trecho_esc.start or 0) + f.end(1)])

    registro: Optional[RegistroPacto] = None
    num = _REGISTRO_NUM_RE.search(dobrado) or _REGISTRADO_SOB_RE.search(dobrado)
    if registro_auxiliar or num:
        data_reg = None
        if num:
            depois = dobrado[num.end():num.end() + 60]
            if re.match(r"\s*(?:EM|DE)\b", depois):
                data_reg = _primeira_data(texto[num.end():num.end() + 60])
        registro = RegistroPacto(
            numero=num.group(1) if num else None,
            livro="3 - Registro Auxiliar" if registro_auxiliar else None,
            cartorio=_office(texto, dobrado, _OFICIAL_RI_RE),
            data=data_reg,
        )

    data_casamento = None
    cas = _CASAMENTO_RE.search(dobrado)
    if cas:
        fim = cas.end()
        if cas.group(0).startswith("CASAMENTO"):
            real = _REALIZADO_RE.search(dobrado, fim, fim + 300)
            fim = real.end() if real else None
        if fim is not None:
            data_casamento = _primeira_data(texto[fim:fim + 160])

    return PactoAntenupcialLido(
        regime_bens=regime,
        regime_bens_confianca=confianca,
        data_escritura=data_escritura,
        tabelionato=tabelionato,
        livro=livro,
        folhas=folhas,
        registro=registro,
        data_casamento=data_casamento,
        conjuges=_conjuges(texto, dobrado),
        source=source,
    )


# ─── Protocol + Fake + Real + factory ───────────────────────────────────


@runtime_checkable
class PactoAntenupcialExtractor(Protocol):
    """Bytes + mimetype → `PactoAntenupcialLido`. MUST NOT raise for an
    unreadable document — `error` is set instead (same contract as every
    sibling extractor: a raise into a background job is a lost job)."""

    async def extract(
        self, content: bytes, *, mimetype: Optional[str] = None, filename: Optional[str] = None,
    ) -> PactoAntenupcialLido:
        ...


#: Checksum-valid synthetic CPFs (the documentation CPF and the sibling
#: Fakes' own) — a Fake returning an invalid CPF would let a consumer test a
#: path the Real never takes.
_CPF_FAKE_1 = "12345678909"
_CPF_FAKE_2 = "41295423898"


class FakePactoAntenupcialExtractor:
    """Deterministic — the dev/test default. Pass `result=` to script one."""

    def __init__(self, result: Optional[PactoAntenupcialLido] = None) -> None:
        self._result = result

    async def extract(
        self, content: bytes, *, mimetype: Optional[str] = None, filename: Optional[str] = None,
    ) -> PactoAntenupcialLido:
        if self._result is not None:
            return self._result
        if not content:
            return PactoAntenupcialLido(error="empty_document", error_message="no bytes to read")
        return PactoAntenupcialLido(
            regime_bens="separacao_total",
            regime_bens_confianca=ExtractionConfidence.ALTA,
            data_escritura=date(2020, 1, 2),
            tabelionato="1º Tabelião de Notas FAKE",
            livro="1",
            folhas="1",
            conjuges=(
                ConjugePacto(nome="FULANO DE TAL FAKE", cpf=_CPF_FAKE_1),
                ConjugePacto(nome="BELTRANA DE TAL FAKE", cpf=_CPF_FAKE_2),
            ),
            source=TextSource.TEXT_LAYER,
        )


class LadderPactoAntenupcialExtractor:
    """Text layer first, vision second (the shared ladder), then the pure
    parser. Construct via `make_pacto_antenupcial_extractor(real=True)`."""

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        document_prompt: Optional[str] = None,
        resolver=None,
        max_pages: Optional[int] = None,
        provider: Optional[str] = None,
        ladder: Optional[DocumentTextLadder] = None,
    ) -> None:
        # `max_pages=None` — every page: the registro's own number and the
        # escritura citation may sit on any page (page 2 of 3 on deal 858).
        self._ladder = ladder or DocumentTextLadder(
            org_id=org_id,
            document_prompt=document_prompt,
            resolver=resolver,
            max_pages=max_pages,
            provider=provider,
        )

    async def extract(
        self, content: bytes, *, mimetype: Optional[str] = None, filename: Optional[str] = None,
    ) -> PactoAntenupcialLido:
        if not content:
            return PactoAntenupcialLido(error="empty_document", error_message="no bytes to read")
        texto, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return PactoAntenupcialLido(source=source, error=err[0], error_message=err[1])
        return parse_pacto_antenupcial(texto, source)


def make_pacto_antenupcial_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    document_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> PactoAntenupcialExtractor:
    """Fake-by-default, like every seed IO factory. `provider` = which
    vendor reads a scanned page (any `documents.providers.OCR_MODELS` key;
    `None` = the seed's canonical document provider)."""
    if not real:
        return FakePactoAntenupcialExtractor()
    return LadderPactoAntenupcialExtractor(
        org_id=org_id, document_prompt=document_prompt, provider=provider, max_pages=max_pages,
    )


__all__ = [
    "ConjugePacto",
    "FakePactoAntenupcialExtractor",
    "LadderPactoAntenupcialExtractor",
    "PactoAntenupcialExtractor",
    "PactoAntenupcialLido",
    "RegistroPacto",
    "make_pacto_antenupcial_extractor",
    "parse_pacto_antenupcial",
]
