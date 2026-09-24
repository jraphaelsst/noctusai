"""Serasa Crednet (a web consulta printed to PDF) → typed fields.

Protocol + Fake + Real + factory, sibling of `matricula_extractor.py` and
sharing its ladder (`ladder.py`) and confidence vocabulary
(`types.ExtractionConfidence` / `types.TextSource`).

🔴 THE DOCUMENT IS A TABLE-SHAPED WEB PRINTOUT, NEVER A TEXT LAYER IN PRACTICE
-------------------------------------------------------------------------------
A Crednet consulta is a browser page saved as "Microsoft: Print To PDF" —
which, against the real corpus this module was built from, still rasterizes
to an image-only PDF (no selectable text layer survives the print). The
vision rung therefore always runs. The transcription prompt below asks the
model to render every table as pipe-delimited rows (`| col | col | ... |`),
because a table is exactly the shape this module's parser needs and prose
paraphrase would lose the column alignment the way `real.py`'s own header
comment describes for identity documents.

🔴 "SITUACAO DO CNPJ EM" IS NOT A CLOSING DATE (E2)
------------------------------------------------------
Each `Participação Societária` block prints a SECOND date — the date the
*company's own registration status* was last updated at Receita, as SEEN
FROM SERASA'S OWN CACHE. It is not the date used anywhere as a legal
"situação encerrada em" reference (the owner proved this date wrong on a
real case: 2026-09-24 tech-lead decision H4). It is parsed into
`ParticipacaoCrednet.situacao_em` and NOWHERE else — in particular it never
touches `CrednetFields.cpf_situacao_em`, which is the *person's* CPF
regularity date from a completely different section of the same document.

🔴 CHECK DIGITS ARE THE ANCHOR, A FAILED ONE IS NEVER CORRECTED
-------------------------------------------------------------------
Every CPF/CNPJ this module reads goes through `cpf.is_valid` / `cnpj.is_valid`
(KB `CONTEXT/PRODUCTS/social-wiring/CERTIDOES-LEVANTAMENTO-LEARNINGS.md` §1).
A failed check digit sets `*_valido=False`, forces that reading's confidence
to `baixa` and appends the matching token to `CrednetFields.aviso`
(`"cpf_digito_invalido"` / `"cnpj_digito_invalido"`, comma-joined when both
apply) — the raw value is kept verbatim, never silently "corrected" toward a
guess. Every identifier read off the OCR rung is additionally capped at
`baixa` regardless of the checksum outcome — see `_temper` below, the same
"not a text layer ⇒ not alta" rule `matricula_extractor._temper` states for
the same reason: nothing downstream of this module can tell a plausible
digit slip apart from a correct read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional, Protocol, runtime_checkable

from noctusai_lib.integrations.documents.cnpj import format_cnpj, is_valid as _cnpj_is_valid
from noctusai_lib.integrations.documents.cpf import format_cpf, is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.text import strip_accents_upper
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    TextSource,
)

# ─── transcription prompt (rung 2) ────────────────────────────────────────

#: Anti-helpful, verbatim-preserving, table-aware — the same posture
#: `real.py`'s identity prompt and `transcription.OCR_PROMPT` take, worded
#: for THIS layout: a Serasa Crednet consulta is dense with labelled tables
#: (Resumo, Ocorrências, Participação Societária), so the one instruction
#: that matters most is "render every table as pipe-delimited rows" — a
#: prose paraphrase of a table row is exactly what this module's parser
#: cannot read back.
DOCUMENT_PROMPT_CREDNET = (
    "Transcreva o texto EXATO desta página de consulta Serasa Crednet, sem "
    "corrigir, resumir ou traduzir nada. Preserve cada rótulo (como 'PROTOCOLO "
    "DA CONSULTA', 'Situação do CPF/CNPJ em') junto ao seu valor, na mesma "
    "linha. Represente TODA tabela como linhas separadas por barra vertical, "
    "uma linha por linha da tabela, incluindo o cabeçalho e cada linha de "
    "valor, no formato: | coluna1 | coluna2 | ... |. Na tabela 'Participação "
    "Societária', a linha 'SITUACAO DO CNPJ EM ...' que segue cada empresa "
    "não é uma tabela — transcreva-a como texto simples, na linha logo abaixo "
    "da linha da tabela correspondente."
)

# ─── shared confidence tempering ──────────────────────────────────────────


def _temper(confidence: ExtractionConfidence, source: TextSource) -> ExtractionConfidence:
    """`alta` is reachable only off a PDF's own text layer — see the module
    header. Own copy, not shared with `matricula_extractor._temper`: each
    extractor in this family states its own tempering, deliberately (see
    that module's docstring contrasting itself with `real._temper_name_confidence`)."""
    if confidence is ExtractionConfidence.ALTA and source is not TextSource.TEXT_LAYER:
        return ExtractionConfidence.BAIXA
    return confidence


def _tempered_map(
    confiancas: Mapping[str, ExtractionConfidence], source: TextSource
) -> dict[str, ExtractionConfidence]:
    return {campo: _temper(c, source) for campo, c in confiancas.items()}


# ─── small parsing helpers, local to this layout ──────────────────────────

_MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5,
    "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10,
    "NOVEMBRO": 11, "DEZEMBRO": 12,
}


def _data_br(txt: str) -> Optional[date]:
    """`DD/MM/AAAA` → `date`, or `None` when not shaped like one."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _decimal_brl(txt: str) -> Optional[Decimal]:
    """`R$ 1.234,56` → `Decimal("1234.56")`."""
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})", txt)
    if not m:
        return None
    inteiro = m.group(1).replace(".", "")
    try:
        return Decimal(f"{inteiro}.{m.group(2)}")
    except InvalidOperation:
        return None


def _decimal_pct(txt: str) -> Optional[Decimal]:
    """`100,0 %` → `Decimal("100.0")`."""
    m = re.search(r"(\d+(?:,\d+)?)", txt)
    if not m:
        return None
    try:
        return Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None


_CONSULTA_EM_RE = re.compile(
    r"(\d{1,2})\s+DE\s+(" + "|".join(_MESES) + r")\s+DE\s+(\d{4})\s+"
    r"(\d{2}):(\d{2}):(\d{2})"
)
_PROTOCOLO_RE = re.compile(r"PROTOCOLO\s+DA\s+CONSULTA\s*:?\s*(\d+)")

#: The `Resumo da consulta` VALUE row only — the header row's cells are text
#: labels, not a CPF/date, so it never matches this shape.
_RESUMO_RE = re.compile(
    r"^\|\s*(?P<cpf>\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})\s*\|\s*"
    r"(?P<nome>[^|]+?)\s*\|\s*(?P<mae>[^|]+?)\s*\|\s*"
    r"(?P<nasc>\d{2}/\d{2}/\d{4})\s*\|?\s*$",
    re.MULTILINE,
)

_SITUACAO_CPF_RE = re.compile(
    r"SITUACAO\s+DO\s+CPF/?CNPJ\s+EM\s+(?P<data>\d{2}/\d{2}/\d{4})\s*:\s*"
    r"(?P<situacao>[A-Z ]+?)(?:\n|$)"
)

_OCORRENCIA_ROTULOS: dict[str, str] = {
    "pendencias_internas": "PENDENCIAS INTERNAS",
    "pendencias_financeiras": "PENDENCIAS FINANCEIRAS",
    "protesto_estadual": "PROTESTO ESTADUAL",
    "cheques_sem_fundo": "CHEQUES SEM FUNDO BACEN",
}

#: The `Participação Societária` VALUE row: razão social, CNPJ, percentual,
#: UF. The CNPJ is matched loosely (punctuation + letters, per the
#: alphanumeric-CNPJ note in `cnpj.py`) — validity is `cnpj.is_valid`'s job,
#: not this regex's.
_PARTICIPACAO_ROW_RE = re.compile(
    r"^\|\s*(?P<empresa>[^|]+?)\s*\|\s*(?P<cnpj>[0-9A-Z./\-]{14,20})\s*\|\s*"
    r"(?P<pct>[\d,]+)\s*%?\s*\|\s*(?P<uf>[A-Z]{2})\s*\|?\s*$",
    re.MULTILINE,
)
#: The plain-text line right after a participação row — see the prompt's own
#: instruction to keep it OUT of the pipe-table shape.
_SITUACAO_CNPJ_RE = re.compile(
    r"SITUACAO\s+DO\s+CNPJ\s+EM\s+(?P<data>\d{2}/\d{2}/\d{4})\s*:\s*"
    r"(?P<situacao>[A-Z]+)(?:[^\n]*?DESDE\s*:\s*(?P<desde>[^|\n]+))?"
)
#: How far past a participação row to look for its situação line. Generous
#: for a wrapped OCR line; short enough never to reach the NEXT participação.
_JANELA_SITUACAO = 400


def _linha_com_rotulo(norm: str, rotulo: str) -> Optional[str]:
    """The rest of the pipe-table row whose first cell is `rotulo`, or
    `None` when that row was never found — the "unreadable" case."""
    m = re.search(rf"\|\s*{re.escape(rotulo)}\s*\|(?P<resto>[^\n]*)", norm)
    return m.group("resto") if m else None


def _ocorrencia(norm: str, rotulo: str) -> "OcorrenciaCrednet":
    resto = _linha_com_rotulo(norm, rotulo)
    if resto is None:
        # The row itself was never found — a legible document that still
        # did not carry this section reads as unreadable, not "none",
        # because a genuinely clean report always prints the row.
        return OcorrenciaCrednet()
    if "NAO CONSTAM" in resto:
        return OcorrenciaCrednet(constam=False)
    partes = [p.strip() for p in resto.split("|") if p.strip()]
    quantidade: Optional[int] = None
    valor: Optional[Decimal] = None
    ultimo: Optional[date] = None
    for p in partes:
        if quantidade is None and re.fullmatch(r"\d+", p):
            quantidade = int(p)
            continue
        if valor is None and "R$" in p:
            valor = _decimal_brl(p)
            continue
        if ultimo is None:
            d = _data_br(p)
            if d is not None:
                ultimo = d
    if quantidade is None and valor is None and ultimo is None:
        # The row matched but nothing inside it parsed — garbled, not clean.
        return OcorrenciaCrednet()
    return OcorrenciaCrednet(
        constam=True, quantidade=quantidade, valor=valor, ultimo_registro=ultimo
    )


def _participacoes(norm: str, source: TextSource) -> tuple["ParticipacaoCrednet", ...]:
    saida: list[ParticipacaoCrednet] = []
    for m in _PARTICIPACAO_ROW_RE.finditer(norm):
        cnpj_bruto = m.group("cnpj")
        valido = _cnpj_is_valid(cnpj_bruto)
        cnpj_formatado = format_cnpj(cnpj_bruto) or cnpj_bruto
        confianca = _temper(
            ExtractionConfidence.ALTA if valido else ExtractionConfidence.BAIXA,
            source,
        )

        situacao_texto: Optional[str] = None
        situacao_em: Optional[date] = None
        desde: Optional[str] = None
        janela = norm[m.end() : m.end() + _JANELA_SITUACAO]
        sm = _SITUACAO_CNPJ_RE.search(janela)
        if sm:
            situacao_texto = sm.group("situacao").strip()
            situacao_em = _data_br(sm.group("data"))
            if sm.group("desde"):
                desde = sm.group("desde").strip()

        saida.append(
            ParticipacaoCrednet(
                razao_social=m.group("empresa").strip() or None,
                cnpj=cnpj_formatado,
                cnpj_valido=valido,
                participacao_pct=_decimal_pct(m.group("pct")),
                uf=m.group("uf"),
                situacao_texto=situacao_texto,
                situacao_em=situacao_em,
                desde=desde,
                confianca=confianca,
            )
        )
    return tuple(saida)


# ─── public value objects ──────────────────────────────────────────────────


@dataclass(frozen=True)
class OcorrenciaCrednet:
    """One row of the `Ocorrências` table — 'NAO CONSTAM OCORRENCIAS', a
    count, or unreadable. `constam=None` means the row itself could not be
    found/parsed, which is deliberately distinct from `False` (the row WAS
    found and it says clean)."""

    constam: Optional[bool] = None
    quantidade: Optional[int] = None
    valor: Optional[Decimal] = None
    ultimo_registro: Optional[date] = None


@dataclass(frozen=True)
class ParticipacaoCrednet:
    """One company in `Participação Societária`. `situacao_em` is the
    Crednet-cached Receita update date — see the module header's E2 note:
    it is never a closing date for anything outside this object."""

    razao_social: Optional[str] = None
    cnpj: Optional[str] = None
    cnpj_valido: bool = False
    participacao_pct: Optional[Decimal] = None
    uf: Optional[str] = None
    situacao_texto: Optional[str] = None
    #: Crednet's "SITUACAO DO CNPJ EM" — NOT a closing date (E2).
    situacao_em: Optional[date] = None
    desde: Optional[str] = None
    confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA


@dataclass(frozen=True)
class CrednetFields:
    """What one Serasa Crednet consulta yielded.

    `confiancas`/`rotulos` are keyed by this dataclass's own scalar field
    names (`"protocolo"`, `"cpf"`, `"nome"`, `"nome_mae"`, `"data_nascimento"`,
    `"consulta_em"`, `"cpf_situacao"`) — a per-field dict rather than the
    per-field `<campo>_confianca`/`<campo>_rotulo` attribute pairs
    `IdentityFields` uses, because this document's own table structure
    already gives each field an unambiguous column; the dict keeps the
    dataclass from growing fourteen near-duplicate attributes for seven
    scalar facts.
    """

    consulta_em: Optional[datetime] = None
    protocolo: Optional[str] = None
    cpf: Optional[str] = None
    cpf_valido: bool = False
    nome: Optional[str] = None
    nome_mae: Optional[str] = None
    data_nascimento: Optional[date] = None
    cpf_situacao: Optional[str] = None
    cpf_situacao_em: Optional[date] = None
    pendencias_internas: OcorrenciaCrednet = field(default_factory=OcorrenciaCrednet)
    pendencias_financeiras: OcorrenciaCrednet = field(default_factory=OcorrenciaCrednet)
    protesto_estadual: OcorrenciaCrednet = field(default_factory=OcorrenciaCrednet)
    cheques_sem_fundo: OcorrenciaCrednet = field(default_factory=OcorrenciaCrednet)
    participacoes: tuple[ParticipacaoCrednet, ...] = ()
    confiancas: Mapping[str, ExtractionConfidence] = field(default_factory=dict)
    rotulos: Mapping[str, Optional[str]] = field(default_factory=dict)
    source: TextSource = TextSource.NENHUMA
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None

    def ocorrencias_constam(self) -> Optional[bool]:
        """`True` when any of the four ocorrências rows confirms a hit,
        `False` only when all four cleanly say "não constam", `None` when
        none confirm a hit but at least one row could not be read — an
        unreadable row must never be reported as a clean negative."""
        ocorrencias = (
            self.pendencias_internas,
            self.pendencias_financeiras,
            self.protesto_estadual,
            self.cheques_sem_fundo,
        )
        if any(o.constam is True for o in ocorrencias):
            return True
        if any(o.constam is None for o in ocorrencias):
            return None
        return False


# ─── pure parser ────────────────────────────────────────────────────────


def parse_crednet(text: str, source: TextSource) -> CrednetFields:
    """Text (already ladder-read) → `CrednetFields`. Pure, never raises."""
    norm = strip_accents_upper(text or "")

    confiancas: dict[str, ExtractionConfidence] = {
        campo: ExtractionConfidence.NENHUMA
        for campo in (
            "protocolo", "consulta_em", "cpf", "nome", "nome_mae",
            "data_nascimento", "cpf_situacao",
        )
    }
    rotulos: dict[str, Optional[str]] = {campo: None for campo in confiancas}

    protocolo: Optional[str] = None
    m = _PROTOCOLO_RE.search(norm)
    if m:
        protocolo = m.group(1)
        confiancas["protocolo"] = ExtractionConfidence.ALTA
        rotulos["protocolo"] = "PROTOCOLO DA CONSULTA"

    consulta_em: Optional[datetime] = None
    m = _CONSULTA_EM_RE.search(norm)
    if m:
        dia, mes_nome, ano, hh, mm, ss = m.groups()
        try:
            consulta_em = datetime(
                int(ano), _MESES[mes_nome], int(dia), int(hh), int(mm), int(ss)
            )
            confiancas["consulta_em"] = ExtractionConfidence.ALTA
        except ValueError:
            consulta_em = None

    cpf_valor: Optional[str] = None
    cpf_valido = False
    nome: Optional[str] = None
    nome_mae: Optional[str] = None
    data_nascimento: Optional[date] = None
    m = _RESUMO_RE.search(norm)
    if m:
        cpf_bruto = m.group("cpf")
        cpf_valido = _cpf_is_valid(cpf_bruto)
        cpf_valor = format_cpf(cpf_bruto) or cpf_bruto
        confiancas["cpf"] = ExtractionConfidence.ALTA if cpf_valido else ExtractionConfidence.BAIXA
        rotulos["cpf"] = "CPF"

        nome = m.group("nome").strip() or None
        if nome:
            confiancas["nome"] = ExtractionConfidence.ALTA
            rotulos["nome"] = "NOME"

        nome_mae = m.group("mae").strip() or None
        if nome_mae:
            confiancas["nome_mae"] = ExtractionConfidence.ALTA
            rotulos["nome_mae"] = "NOME DA MAE"

        data_nascimento = _data_br(m.group("nasc"))
        if data_nascimento is not None:
            confiancas["data_nascimento"] = ExtractionConfidence.ALTA
            rotulos["data_nascimento"] = "DATA NASCIMENTO"

    cpf_situacao: Optional[str] = None
    cpf_situacao_em: Optional[date] = None
    m = _SITUACAO_CPF_RE.search(norm)
    if m:
        cpf_situacao = m.group("situacao").strip() or None
        cpf_situacao_em = _data_br(m.group("data"))
        if cpf_situacao is not None:
            confiancas["cpf_situacao"] = ExtractionConfidence.ALTA
            rotulos["cpf_situacao"] = "SITUACAO DO CPF/CNPJ EM"

    pendencias_internas = _ocorrencia(norm, _OCORRENCIA_ROTULOS["pendencias_internas"])
    pendencias_financeiras = _ocorrencia(norm, _OCORRENCIA_ROTULOS["pendencias_financeiras"])
    protesto_estadual = _ocorrencia(norm, _OCORRENCIA_ROTULOS["protesto_estadual"])
    cheques_sem_fundo = _ocorrencia(norm, _OCORRENCIA_ROTULOS["cheques_sem_fundo"])

    participacoes = _participacoes(norm, source)

    avisos: list[str] = []
    if cpf_valor is not None and not cpf_valido:
        avisos.append("cpf_digito_invalido")
    if any(p.cnpj is not None and not p.cnpj_valido for p in participacoes):
        avisos.append("cnpj_digito_invalido")

    return CrednetFields(
        consulta_em=consulta_em,
        protocolo=protocolo,
        cpf=cpf_valor,
        cpf_valido=cpf_valido,
        nome=nome,
        nome_mae=nome_mae,
        data_nascimento=data_nascimento,
        cpf_situacao=cpf_situacao,
        cpf_situacao_em=cpf_situacao_em,
        pendencias_internas=pendencias_internas,
        pendencias_financeiras=pendencias_financeiras,
        protesto_estadual=protesto_estadual,
        cheques_sem_fundo=cheques_sem_fundo,
        participacoes=participacoes,
        confiancas=_tempered_map(confiancas, source),
        rotulos=rotulos,
        source=source,
        aviso=",".join(avisos) if avisos else None,
    )


# ─── Protocol + Fake + Real + factory ──────────────────────────────────────


@runtime_checkable
class CrednetExtractor(Protocol):
    """Bytes + mimetype → a Serasa Crednet consulta's typed fields.

    Implementations MUST NOT raise for an unreadable/corrupt document — they
    return `CrednetFields` with `error` set."""

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CrednetFields:
        ...


class FakeCrednetExtractor:
    """Deterministic extractor — the dev/test default.

    Uses the SAME real, checksum-valid CPF/CNPJ `fake.FakeIdentityExtractor`
    does (`412.954.238-98` / `11.222.333/0001-81`) — a Fake that returned an
    arithmetically invalid identifier would let a consumer's tests pass
    against a code path the Real adapter never exhibits (`cpf_valido=False`
    is its OWN, separately-tested branch, not the happy path)."""

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CrednetFields:
        if not content:
            return CrednetFields(error="empty_document", error_message="no bytes to read")
        return CrednetFields(
            consulta_em=datetime(2026, 1, 1, 12, 0, 0),
            protocolo="000001",
            cpf="412.954.238-98",
            cpf_valido=True,
            nome="FULANO DE TAL SILVA",
            nome_mae="CICLANA DE TAL SILVA",
            data_nascimento=date(1980, 1, 1),
            cpf_situacao="REGULAR",
            cpf_situacao_em=date(2026, 1, 1),
            pendencias_internas=OcorrenciaCrednet(constam=False),
            pendencias_financeiras=OcorrenciaCrednet(constam=False),
            protesto_estadual=OcorrenciaCrednet(constam=False),
            cheques_sem_fundo=OcorrenciaCrednet(constam=False),
            participacoes=(
                ParticipacaoCrednet(
                    razao_social="EMPRESA FAKE SINTETICA LTDA",
                    cnpj="11.222.333/0001-81",
                    cnpj_valido=True,
                    participacao_pct=Decimal("100.0"),
                    uf="SP",
                    situacao_texto="ATIVA",
                    confianca=ExtractionConfidence.ALTA,
                ),
            ),
            confiancas={
                campo: ExtractionConfidence.ALTA
                for campo in (
                    "protocolo", "consulta_em", "cpf", "nome", "nome_mae",
                    "data_nascimento", "cpf_situacao",
                )
            },
            rotulos={
                "protocolo": "PROTOCOLO DA CONSULTA",
                "consulta_em": None,
                "cpf": "CPF",
                "nome": "NOME",
                "nome_mae": "NOME DA MAE",
                "data_nascimento": "DATA NASCIMENTO",
                "cpf_situacao": "SITUACAO DO CPF/CNPJ EM",
            },
            source=TextSource.TEXT_LAYER,
        )


class LadderCrednetExtractor:
    """Text-layer-first, vision-second Crednet reader.

    Construct via `make_crednet_extractor(real=True)`."""

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        resolver=None,
        provider: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> None:
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=DOCUMENT_PROMPT_CREDNET,
            resolver=resolver,
            provider=provider,
            max_pages=max_pages,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CrednetFields:
        if not content:
            return CrednetFields(error="empty_document", error_message="no bytes to read")

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return CrednetFields(source=source, error=err[0], error_message=err[1])
        if not text.strip():
            return CrednetFields(source=source)

        return parse_crednet(text, source)


def make_crednet_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> CrednetExtractor:
    """Return a Serasa Crednet extractor. Fake-by-default.

    Args:
        max_pages: `None` (the default) reads EVERY page — a
            `Participação Societária` block routinely sits on page 2, and
            capping the page count here would silently drop it.
        provider: Which vendor reads the scanned page — any key of
            `documents.providers.OCR_MODELS`. `None` = the resolver's own
            canonical default.
    """
    if not real:
        return FakeCrednetExtractor()
    return LadderCrednetExtractor(org_id=org_id, provider=provider, max_pages=max_pages)


__all__ = [
    "CrednetExtractor",
    "CrednetFields",
    "DOCUMENT_PROMPT_CREDNET",
    "FakeCrednetExtractor",
    "LadderCrednetExtractor",
    "OcorrenciaCrednet",
    "ParticipacaoCrednet",
    "make_crednet_extractor",
    "parse_crednet",
]
