"""What KIND of matrícula document is this, and when was it ISSUED?

Pure, deterministic, import-light — same family contract as `matricula.py`:
text in, plain values out, confidence as the strings `"alta"` / `"baixa"` /
`"nenhuma"`.

🔴 WHY THIS EXISTS (P5 audit, 2026-10)
-------------------------------------
On all ten audited deals the file uploaded as "the matrícula" was the
registry's **Visualização de Matrícula** — an online VIEW of the book,
printed to PDF, which carries no certification and has no emission date of
its own. The emission-date reader (a per-page LLM question, "data de emissão
impressa no documento") answered with the only dates such a printout has: the
registry ACTS' dates. The first act of a matrícula is often decades old, so
every deal then blocked on "certidão da matrícula vencida" — the wrong
problem, with the wrong remedy ("emit it again"), when the real one is "this
file is not a certidão at all; upload the Certidão de Matrícula".

So two questions are answered here, deterministically, before any date is
trusted:

1. **Kind.** `certidao` (inteiro teor / com ônus — it CERTIFIES: "certifico",
   "o referido é verdade", a selo, "certidão expedida/emitida") vs
   `visualizacao` (a view/printout: "visualização de matrícula", "não tem
   valor de certidão", "para simples consulta"). A visualização marker wins
   over a certidão marker — the disclaimer itself says "certidão" ("NÃO TEM
   VALOR DE CERTIDÃO"), and a printout is never upgraded by a stray word.
   Neither marker → `None` (unknown), never a guess.

2. **Emission date.** Read ONLY from the certification itself — a labelled
   emission ("certidão expedida às 10:22 do dia 01/03/2026", "data da
   emissão: …", "emitida em …") or the certificate's closing line
   ("o referido é verdade e dou fé. Cotia, 1º de março de 2026") — and
   NEVER from an act. Two structural guards make "an act date" impossible
   to return:

   - zones: the closing line is only looked for after the LAST
     certification marker (`CERTIFICO` / `O REFERIDO É VERDADE` / `CERTIDÃO
     EXPEDIDA`), and a labelled date only in that zone or the page head;
   - chronology: a certidão is issued AFTER the last act it reproduces, so
     any candidate earlier than the latest act's registration date
     (`data_ultimo_ato`, via the sibling act parser) is discarded. The same
     check is offered to a caller holding an EXTERNAL candidate (an LLM's
     answer) through `CertidaoMatriculaLida.aceita_data_externa`.

   A visualização never gets an emission date: `data_emissao=None` with
   `motivo="visualizacao_sem_valor_de_certidao"`, so a consumer can say
   "envie a Certidão de Matrícula (o arquivo é uma visualização)" instead of
   "vencida".

All fixtures in this module's tests are synthetic; no real document text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from noctusai_lib.integrations.documents.matricula import normalize

ALTA = "alta"
BAIXA = "baixa"
NENHUMA = "nenhuma"

#: `tipo_documento_matricula` vocabulary.
TIPO_CERTIDAO = "certidao"
TIPO_VISUALIZACAO = "visualizacao"
TIPOS_DOCUMENTO_MATRICULA: tuple[str, ...] = (TIPO_CERTIDAO, TIPO_VISUALIZACAO)

#: `motivo` vocabulary — why `data_emissao` is None.
MOTIVO_VISUALIZACAO = "visualizacao_sem_valor_de_certidao"
MOTIVO_NAO_ENCONTRADA = "emissao_nao_encontrada"
MOTIVO_DIVERGENTE = "emissao_divergente"
MOTIVO_ANTERIOR_AO_ULTIMO_ATO = "emissao_anterior_ao_ultimo_ato"
MOTIVOS_EMISSAO: tuple[str, ...] = (
    MOTIVO_VISUALIZACAO,
    MOTIVO_NAO_ENCONTRADA,
    MOTIVO_DIVERGENTE,
    MOTIVO_ANTERIOR_AO_ULTIMO_ATO,
)

# ─── kind ─────────────────────────────────────────────────────────────────

_VIS = r"VI[SZ]UALI[SZ]ACAO"

#: Phrases only a view/printout carries. Matched on `normalize`d text
#: (upper-case, accent-stripped, whitespace collapsed).
_MARCAS_VISUALIZACAO = re.compile(
    rf"{_VIS}\s+D[AE]\s+MATRICULA"
    rf"|{_VIS}\s+(?:GERADA|EMITIDA|IMPRESSA|REALIZADA)"
    rf"|MERA\s+{_VIS}"
    r"|(?:NAO|SEM)\s+(?:TEM|POSSUI|TENDO|POSSUINDO|CONSTITUI)?\s*(?:O\s+)?VALOR\s+DE\s+CERTIDAO"
    r"|NAO\s+(?:E|CONSTITUI|SUBSTITUI|VALE\s+COMO)\s+(?:A\s+|UMA\s+)?CERTIDAO"
    r"|PARA\s+(?:SIMPLES|MERA)\s+(?:CONSULTA|CONFERENCIA)"
)

#: Phrases only a certidão carries — it CERTIFIES. Bare "DOU FÉ" is NOT one:
#: act texts end with it too, so it would upgrade a printout whose
#: disclaimer the transcription lost.
_MARCAS_CERTIDAO = re.compile(
    r"(?<![A-Z])CERTIFICO(?![A-Z])"
    r"|O\s+REFERIDO\s+E\s+VERDADE"
    r"|CERTIDAO\s+(?:DIGITAL|ELETRONICA|DE\s+INTEIRO\s+TEOR|EM\s+INTEIRO\s+TEOR|DE\s+ONUS"
    r"|D[AE]\s+MATRICULA|ATUALIZADA|EXPEDIDA|EMITIDA)"
    r"|SELO\s+(?:DIGITAL|ELETRONICO|DE\s+FISCALIZACAO)"
)

# ─── emission date ────────────────────────────────────────────────────────

_MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}
_DATA = re.compile(
    r"(?<![\d/.])(?P<d>\d{1,2})\s*[/.\-]\s*(?P<m>\d{1,2})\s*[/.\-]\s*(?P<a>\d{4})(?![\d/])"
    r"|(?<!\d)(?P<de>\d{1,2})\s*(?:O|°)?\s+DE\s+(?P<me>" + "|".join(_MESES) + r")\s+DE\s+(?P<ae>\d{4})(?!\d)"
)

#: A label that ends right before the emission date. `AS 10:22:33 HORAS DO
#: DIA` / `EM` / `NO DIA` connectors tolerated.
_HORA = r"(?:AS\s+\d{1,2}\s*[:H]\s*\d{2}(?:\s*:\s*\d{2})?\s*(?:HORAS?|HS?|MIN\w*)?\s*(?:,\s*)?)?"
_CONECTOR = r"(?:(?:D[OE]\s+DIA|NO\s+DIA|EM|AOS|DE)\s+)?"
_ROTULO_EMISSAO = re.compile(
    r"(?:"
    r"(?:CERTIDAO\s+)?(?:EXPEDIDA|EMITIDA|GERADA|LAVRADA)\s+" + _HORA + _CONECTOR
    + r"|DATA\s+(?:DA|DE)\s+(?:EMISSAO|EXPEDICAO)\s*[:\-–—]?\s*" + _HORA
    + r"|(?<![A-Z])EMISSAO\s*[:\-–—]\s*" + _HORA
    + r"|EMITID[OA]\s+EM\s+" + _HORA
    + r")$"
)
#: The certificate's closing: `... dou fé. Cotia, 1º de março de 2026` —
#: a city followed by a comma, or the "dou fé / é verdade" formula itself.
_FECHO = re.compile(
    r"(?:[A-Z][A-Z' ]{1,40},\s*(?:SP\s*,\s*)?(?:EM\s+)?"
    r"|(?:DOU\s+FE|E\s+VERDADE)[^0-9]{0,80})$"
)
#: Where the certification starts. The LAST one is used: a "certifico" that
#: opens the document (preamble layout) is followed by the acts, so only
#: its LAST closing line is the certificate's.
_ZONA_CERTIFICACAO = re.compile(
    r"(?<![A-Z])CERTIFICO(?![A-Z])|O\s+REFERIDO\s+E\s+VERDADE|CERTIDAO\s+(?:EXPEDIDA|EMITIDA)"
)
#: The page head — some issuers print "Certidão emitida em …" on top.
_CABECA = 800
_JANELA_ROTULO = 60


@dataclass(frozen=True)
class CertidaoMatriculaLida:
    """The kind of a matrícula document and the certidão's own emission date.

    - `tipo_documento_matricula` — `"certidao"` / `"visualizacao"` / `None`
      (no marker either way). `tipo_rotulo` is the marker phrase, verbatim
      from the normalised text, for audit.
    - `data_emissao` — the CERTIDÃO's issuance date, never an act date; `None`
      for a visualização (always) and whenever it could not be read safely,
      with `motivo` saying why (`MOTIVOS_EMISSAO`).
    - `data_ultimo_ato` — the latest registration date among the acts, the
      chronology floor every emission candidate must clear.
    """

    tipo_documento_matricula: Optional[str] = None
    tipo_rotulo: Optional[str] = None
    data_emissao: Optional[date] = None
    data_emissao_confianca: str = NENHUMA
    data_emissao_rotulo: Optional[str] = None
    data_ultimo_ato: Optional[date] = None
    motivo: Optional[str] = None

    @property
    def visualizacao(self) -> bool:
        return self.tipo_documento_matricula == TIPO_VISUALIZACAO

    def aceita_data_externa(self, candidata: Optional[date]) -> bool:
        """May an emission date read ELSEWHERE (an LLM's answer) stand?

        Never for a visualização (it has no emission), and never when it
        predates the last act — a certidão reproduces every act, so it is
        issued after the latest of them; an earlier date IS an act date.
        """
        if candidata is None or self.visualizacao:
            return False
        if self.data_ultimo_ato is not None and candidata < self.data_ultimo_ato:
            return False
        return True


def _data(m: re.Match[str]) -> Optional[date]:
    try:
        if m.group("a"):
            return date(int(m.group("a")), int(m.group("m")), int(m.group("d")))
        return date(int(m.group("ae")), _MESES[m.group("me")], int(m.group("de")))
    except ValueError:
        return None


def classificar_documento_matricula(texto: str) -> tuple[Optional[str], Optional[str]]:
    """`(tipo_documento_matricula, marker)` — see module docstring. A
    visualização marker wins; neither marker → `(None, None)`."""
    norm = normalize(texto or "")
    vis = _MARCAS_VISUALIZACAO.search(norm)
    if vis:
        return TIPO_VISUALIZACAO, vis.group(0)
    cert = _MARCAS_CERTIDAO.search(norm)
    if cert:
        return TIPO_CERTIDAO, cert.group(0)
    return None, None


def data_ultimo_ato(texto: str) -> Optional[date]:
    """The latest registration date among the acts (`R-n` / `AV-n`) of a
    matrícula transcription, via the sibling act parser — `None` when no act
    carries one."""
    # Lazy: the act modules import `matricula.py`, as this one does; keeping
    # the import local avoids any cycle through the package `__init__`.
    from noctusai_lib.integrations.documents.matricula_ato_detalhes import (
        extrair_detalhes_ato,
    )
    from noctusai_lib.integrations.documents.matricula_atos import (
        segment_matricula_atos,
    )

    datas = []
    for ato in segment_matricula_atos(texto or ""):
        if ato.kind == "abertura":
            continue
        d = extrair_detalhes_ato(ato.quote(texto)).data_registro
        if d is not None:
            datas.append(d)
    return max(datas) if datas else None


def _candidatas(norm: str) -> tuple[list[tuple[date, str]], list[tuple[date, str]]]:
    """(labelled, closing) emission candidates, each `(date, label)`."""
    zonas = list(_ZONA_CERTIFICACAO.finditer(norm))
    inicio_zona = zonas[-1].start() if zonas else None

    rotuladas: list[tuple[date, str]] = []
    fechos: list[tuple[date, str]] = []
    for m in _DATA.finditer(norm):
        valor = _data(m)
        if valor is None:
            continue
        na_cabeca = m.start() < _CABECA
        na_zona = inicio_zona is not None and m.start() >= inicio_zona
        if not (na_cabeca or na_zona):
            continue
        prefixo = norm[max(0, m.start() - _JANELA_ROTULO) : m.start()]
        rotulo = _ROTULO_EMISSAO.search(prefixo)
        if rotulo:
            rotuladas.append((valor, rotulo.group(0).strip()))
        elif na_zona:
            fecho = _FECHO.search(norm[max(inicio_zona, m.start() - 120) : m.start()])
            if fecho:
                fechos.append((valor, fecho.group(0).strip()))
    return rotuladas, fechos[-1:]


def ler_certidao_matricula(texto: str) -> CertidaoMatriculaLida:
    """Classify a matrícula document and read the certidão's own emission
    date. Pure and deterministic; see module docstring."""
    tipo, tipo_rotulo = classificar_documento_matricula(texto)
    ultimo = data_ultimo_ato(texto)
    base = dict(
        tipo_documento_matricula=tipo, tipo_rotulo=tipo_rotulo, data_ultimo_ato=ultimo
    )
    if tipo == TIPO_VISUALIZACAO:
        return CertidaoMatriculaLida(**base, motivo=MOTIVO_VISUALIZACAO)

    norm = normalize(texto or "")
    rotuladas, fechos = _candidatas(norm)
    descartou = False
    for grupo, confianca in ((rotuladas, ALTA), (fechos, BAIXA)):
        validas = [(d, r) for d, r in grupo if ultimo is None or d >= ultimo]
        descartou = descartou or len(validas) < len(grupo)
        if not validas:
            continue
        distintas = {d for d, _ in validas}
        if len(distintas) > 1:
            # Disagreement is absence — same rule as the rest of the family.
            return CertidaoMatriculaLida(**base, motivo=MOTIVO_DIVERGENTE)
        valor, rotulo = validas[0]
        if confianca == BAIXA and tipo == TIPO_CERTIDAO:
            # The closing line of a document that certifies is the
            # certificate's own signature date.
            confianca = ALTA
        return CertidaoMatriculaLida(
            **base,
            data_emissao=valor,
            data_emissao_confianca=confianca,
            data_emissao_rotulo=rotulo,
        )
    motivo = MOTIVO_ANTERIOR_AO_ULTIMO_ATO if descartou else MOTIVO_NAO_ENCONTRADA
    return CertidaoMatriculaLida(**base, motivo=motivo)


__all__ = [
    "MOTIVOS_EMISSAO",
    "MOTIVO_ANTERIOR_AO_ULTIMO_ATO",
    "MOTIVO_DIVERGENTE",
    "MOTIVO_NAO_ENCONTRADA",
    "MOTIVO_VISUALIZACAO",
    "TIPOS_DOCUMENTO_MATRICULA",
    "TIPO_CERTIDAO",
    "TIPO_VISUALIZACAO",
    "CertidaoMatriculaLida",
    "classificar_documento_matricula",
    "data_ultimo_ato",
    "ler_certidao_matricula",
]
