"""The imóvel's own certidões — CND de IPTU and the condomínio's declaração —
read from their PRINTED text, deterministically.

Pure, deterministic, import-light: text in, plain values out. Same family
contract as `matricula_certidao`. A field is returned only when the document
prints it; anything ambiguous comes back `None`, never a guess — the caller
may still ask a model, but the printed reading wins wherever it exists.

🔴 WHY THIS EXISTS (P6 deterministic-extractors, 2026-10)
---------------------------------------------------------
These fields were LLM-only. Auditing the 26 real CNDs held in production
showed the failure mode that matters most for a contract: a condomínio
declaração saying the unit is paid up ("cotas condominiais quitadas", "em dia
com o pagamento", "quite com todas as suas taxas") came back `positiva` — the
model read a reassuring document as a "positive" one, while `positiva` in a
certidão means THERE ARE DEBTS. Readiness then reported a debt that does not
exist. Every field below is printed in a fixed form, so nothing here needs a
model.

Fields
------
- `resultado` — `negativa` | `positiva` | `positiva_com_efeito_de_negativa`.
  Read from the issuer's own wording (title and certifying sentence). Both a
  "no debts" and a "debts" phrase, with no "efeito de negativa" to reconcile
  them → `None`.
- `numero` — the certidão's own number, right after its title label
  (`CERTIDÃO NEGATIVA Nº. 197477/2026`, `CERTIDÃO IMOBILIÁRIA Nº: … 29556/2026`).
- `emitida_em` — a labelled emission (`certidão emitida … do dia 03/09/2026`)
  or the issuer's dated closing (`Prefeitura do Município de Cotia, 11 de
  agosto de 2026.`). A date that follows `DE` (a law: `Lei 2.968, de 28 de
  dezembro de 2009`) is never a closing.
- `validade_ate` — printed outright (`válida até …`), or `emitida_em` plus the
  printed term (`válida por 60 dias`): the document's own rule, applied to its
  own date. `validade_dias` carries the term so a caller can show it.
- `inscricao` — the inscrição imobiliária/cadastral as printed. The
  município's mask is the caller's check (`primitives.identificador`).

All fixtures in this module's tests are synthetic; no real document text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from noctusai_lib.integrations.documents.datas_ptbr import (
    DATA_EXTENSO,
    datas_no_texto,
)
from noctusai_lib.integrations.documents.matricula import normalize

NEGATIVA = "negativa"
POSITIVA = "positiva"
POSITIVA_COM_EFEITO_DE_NEGATIVA = "positiva_com_efeito_de_negativa"


@dataclass(frozen=True)
class CndImovelLida:
    numero: Optional[str] = None
    emitida_em: Optional[date] = None
    validade_ate: Optional[date] = None
    validade_dias: Optional[int] = None
    resultado: Optional[str] = None
    inscricao: Optional[str] = None

    def campos(self) -> dict[str, object]:
        """The non-empty fields under the imóvel row's column names."""
        out: dict[str, object] = {
            "numero": self.numero,
            "emitida_em": self.emitida_em.isoformat() if self.emitida_em else None,
            "validade_ate": self.validade_ate.isoformat() if self.validade_ate else None,
            "resultado": self.resultado,
            "inscricao_imobiliaria": self.inscricao,
        }
        return {k: v for k, v in out.items() if v is not None}


# ─── resultado ─────────────────────────────────────────────────────────────

_EFEITO_NEGATIVA = re.compile(r"POSITIVA\s+COM\s+EFEITOS?\s+DE\s+NEGATIVA")

#: "No debts" wording — the issuer's title or its certifying sentence.
_SEM_DEBITO = re.compile(
    r"CERTIDAO\s+NEGATIVA"
    r"|NAO\s+(?:CONSTA[M]?|EXISTE[M]?|HA)\s+(?:QUAISQUER\s+)?(?:DEBITOS?|PENDENCIAS?)"
    r"|NAO\s+ENCONTRAMOS\s+PENDENCIAS?"
    r"|NADA\s+CONSTA"
    r"|QUITAD[OA]S?(?![A-Z])"
    r"|(?<![A-Z])QUITE\s+COM"
    r"|EM\s+DIA\s+COM"
    r"|INEXISTEN\w*\s+DE\s+DEBITOS?"
)
#: "Debts" wording. `CONSTA(M) DÉBITOS` only when not negated (checked below).
_COM_DEBITO = re.compile(
    r"CERTIDAO\s+POSITIVA"
    r"|(?<![A-Z])EM\s+DEBITO"
    r"|(?<![A-Z])CONSTA[M]?\s+(?:OS\s+SEGUINTES\s+)?DEBITOS?"
    r"|(?<![A-Z])POSSUI\s+DEBITOS?"
    r"|EM\s+ATRASO"
    r"|EM\s+ABERTO"
    r"|INADIMPLEN\w*"
)


def _com_debito(norm: str) -> bool:
    for m in _COM_DEBITO.finditer(norm):
        antes = norm[max(0, m.start() - 6) : m.start()]
        if re.search(r"NAO\s*$", antes):
            continue  # "NÃO CONSTAM DÉBITOS"
        return True
    return False


def ler_resultado(norm: str) -> Optional[str]:
    if _EFEITO_NEGATIVA.search(norm):
        return POSITIVA_COM_EFEITO_DE_NEGATIVA
    sem = bool(_SEM_DEBITO.search(norm))
    com = _com_debito(norm)
    if sem and not com:
        return NEGATIVA
    if com and not sem:
        return POSITIVA
    return None


# ─── número ────────────────────────────────────────────────────────────────

_ROTULO_NUMERO = re.compile(
    r"CERTIDAO(?:\s+(?:NEGATIVA|POSITIVA|IMOBILIARIA))?\s+(?:NUMERO|N\s*[O°]?)(?![A-Z])\s*[.:]?"
)
_NUMERO = re.compile(r"(?<![\d/])(\d{3,})\s*/\s*(\d{4})(?![\d/])")
#: How far a scrambled layout may push the value from its label
#: ("CERTIDÃO IMOBILIÁRIA Nº: / INTERESSADO(A): / 29556/2026").
_JANELA_NUMERO = 60


def ler_numero(norm: str) -> Optional[str]:
    for rot in _ROTULO_NUMERO.finditer(norm):
        m = _NUMERO.search(norm, rot.end(), rot.end() + _JANELA_NUMERO)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


# ─── emissão ───────────────────────────────────────────────────────────────

_ROTULO_EMISSAO = re.compile(
    r"(?:EMITIDA|EXPEDIDA|GERADA)\s+(?:EM|AS\s+[\d:H ]+(?:HORAS?)?\s+DO\s+DIA|NO\s+DIA)\s*$"
    r"|DATA\s+(?:DA|DE)\s+EMISSAO\s*[:\-]?\s*$"
)
#: The issuer's dated closing: `<LUGAR> , <data por extenso>` — a place name
#: then a comma right before the date. A law's `, DE 28 DE …` never matches:
#: the date must follow the comma directly.
_FECHO = re.compile(r"[A-Z][A-Z' ]{1,60}\s*,\s*(?:EM\s+)?$")


def ler_emissao(norm: str) -> Optional[date]:
    rotuladas: list[date] = []
    fechos: list[date] = []
    for inicio, _fim, valor in datas_no_texto(norm):
        prefixo = norm[max(0, inicio - 60) : inicio]
        if _ROTULO_EMISSAO.search(prefixo):
            rotuladas.append(valor)
        elif _FECHO.search(prefixo) and DATA_EXTENSO.match(norm, inicio):
            fechos.append(valor)
    for grupo in (rotuladas, fechos):
        if len(set(grupo)) == 1:
            return grupo[0]
    return None


# ─── validade ──────────────────────────────────────────────────────────────

_VALIDA_POR = re.compile(r"VALIDA\s+POR\s+(\d{1,3})(?:\s*\([A-Z ]+\))?\s+DIAS")
_VALIDA_ATE = re.compile(r"VALIDA\s+ATE\s*[:\-]?\s*")


def ler_validade(norm: str, emitida_em: Optional[date]) -> tuple[Optional[date], Optional[int]]:
    for m in _VALIDA_ATE.finditer(norm):
        datas = datas_no_texto(norm, m.end(), m.end() + 30)
        if datas and datas[0][0] == m.end():
            return datas[0][2], None
    m = _VALIDA_POR.search(norm)
    if not m:
        return None, None
    dias = int(m.group(1))
    return (emitida_em + timedelta(days=dias) if emitida_em else None), dias


# ─── inscrição ─────────────────────────────────────────────────────────────

#: A dotted cadastral number (`23252.53.55.0304.00.000`): at least four
#: groups, so a date or a CEP never qualifies.
_INSCRICAO = re.compile(r"(?<![\d.])\d{2,6}(?:\.\d{1,5}){3,6}(?![\d.])")
_ROTULO_INSCRICAO = re.compile(r"INSCRICAO\s+(?:IMOBILIARIA|CADASTRAL)")


def ler_inscricao(norm: str) -> Optional[str]:
    """The ONE distinct dotted cadastral number on a page that labels an
    inscrição. Two different ones → `None` (which is the imóvel's is not
    something to guess)."""
    if not _ROTULO_INSCRICAO.search(norm):
        return None
    achados = {m.group(0) for m in _INSCRICAO.finditer(norm)}
    return achados.pop() if len(achados) == 1 else None


# ─── entry points ──────────────────────────────────────────────────────────


def ler_cnd_iptu(texto: str) -> CndImovelLida:
    norm = normalize(texto or "")
    emitida = ler_emissao(norm)
    validade, dias = ler_validade(norm, emitida)
    return CndImovelLida(
        numero=ler_numero(norm),
        emitida_em=emitida,
        validade_ate=validade,
        validade_dias=dias,
        resultado=ler_resultado(norm),
        inscricao=ler_inscricao(norm),
    )


def ler_declaracao_condominio(texto: str) -> CndImovelLida:
    """The condomínio's/associação's declaração: only its date and whether
    the unit owes anything are contract facts; it has no número/inscrição."""
    norm = normalize(texto or "")
    return CndImovelLida(emitida_em=ler_emissao(norm), resultado=ler_resultado(norm))


LEITORES_POR_TIPO = {
    "cnd_iptu": ler_cnd_iptu,
    "cnd_condominio": ler_declaracao_condominio,
}
