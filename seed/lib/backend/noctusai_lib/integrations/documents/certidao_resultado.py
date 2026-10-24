"""A certidão's VERDICT read from the issuer's own printed sentence.

Pure, deterministic, import-light: `(tipo, texto)` in, one of the result
vocabulary out — or `None`. Every issuer below certifies its result in a
fixed sentence ("…CERTIFICADO QUE NÃO CONSTAM DÉBITOS…", "…VERIFICOU NADA
CONSTAR COMO RÉU…"); that sentence IS the result, so no model is needed to
decide it.

🔴 WHY THIS EXISTS (P6 deterministic-extractors, 2026-10)
---------------------------------------------------------
Outside the few sources whose API returns a verdict, the result was decided
by an LLM (`resultado_origem='ia'` on ~95% of the rows in production). A
result is the one field a contract cannot get wrong: "positiva" sends the
deal to an esclarecimento, "negativa" lets it through.

Rules
-----
- One rule set per `tipo`, written from the issuers' real wording (audited
  over the 591 production certidões that carry text). An unknown `tipo` →
  `None`: the caller keeps its existing path.
- "Could not issue" wording wins first: a refusal page often QUOTES the
  other kinds by name ("o pedido de certidão positiva … deverá ser feito …").
- A "no" sentence and a "yes" sentence both present, with nothing printed to
  reconcile them → `None`, never a guess.
- TJSP's own homonym clause ("…VERIFICOU CONSTAR … NÃO QUALIFICADO(A) … QUE
  PODE(M) REFERIR-SE A HOMÔNIMO(S)") next to a "nada constar" for the
  qualified person is printed as such → `negativa_com_homonimos`. Whether a
  homonym is in fact the person stays a human's call (`positiva` is never
  downgraded here).

Serasa is not here: its report has its own parser (`serasa_crednet`).

All fixtures in this module's tests are synthetic; no real document text.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from noctusai_lib.integrations.documents.cpf import find_cpf
from noctusai_lib.integrations.documents.matricula import normalize
from noctusai_lib.integrations.documents.rg import find_rg

NEGATIVA = "negativa"
POSITIVA = "positiva"
POSITIVA_COM_EFEITO_DE_NEGATIVA = "positiva_com_efeito_de_negativa"
NEGATIVA_COM_HOMONIMOS = "negativa_com_homonimos"
NAO_EMITIDA = "nao_emitida"

_PCEN = re.compile(r"CERTIDAO\s+POSITIVA\s+COM\s+EFEITOS?\s+DE\s+NEGATIVA")


def _sim(padrao: str) -> re.Pattern[str]:
    """An affirmative sentence: the same words NOT preceded by "NÃO"/"NADA"."""
    return re.compile(r"(?<!NAO )(?<!NADA )" + padrao)


def _decidir(
    norm: str,
    *,
    nao_emitida: tuple[re.Pattern[str], ...] = (),
    pcen: tuple[re.Pattern[str], ...] = (),
    negativa: tuple[re.Pattern[str], ...] = (),
    positiva: tuple[re.Pattern[str], ...] = (),
) -> Optional[str]:
    if any(p.search(norm) for p in nao_emitida):
        return NAO_EMITIDA
    if any(p.search(norm) for p in pcen):
        return POSITIVA_COM_EFEITO_DE_NEGATIVA
    neg = any(p.search(norm) for p in negativa)
    pos = any(p.search(norm) for p in positiva)
    if neg and not pos:
        return NEGATIVA
    if pos and not neg:
        return POSITIVA
    return None


def _cnd_federal(n: str) -> Optional[str]:
    return _decidir(
        n,
        nao_emitida=(
            re.compile(r"SAO\s+INSUFICIENTES\s+PARA\s+EMITIR\s+A\s+CERTIDAO"),
            re.compile(r"EMISSAO\s+DE\s+CERTIDAO\s+NAO\s+PERMITIDA"),
        ),
        pcen=(_PCEN,),
        negativa=(re.compile(r"CERTIDAO\s+NEGATIVA\s+DE\s+DEBITOS\s+RELATIVOS"),),
        positiva=(re.compile(r"CERTIDAO\s+POSITIVA\s+DE\s+DEBITOS\s+RELATIVOS"),),
    )


def _cnd_fazenda_sp(n: str) -> Optional[str]:
    return _decidir(
        n,
        nao_emitida=(re.compile(r"NAO\s+FOI\s+POSSIVEL\s+EMITIR\s+A\s+CERTIDAO"),),
        pcen=(_PCEN,),
        negativa=(re.compile(r"CERTIFICADO\s+QUE\s+NAO\s+CONSTAM\s+DEBITOS"),),
        positiva=(_sim(r"CERTIFICADO\s+QUE\s+CONSTAM\s+DEBITOS"),),
    )


def _divida_ativa_sp(n: str) -> Optional[str]:
    return _decidir(
        n,
        nao_emitida=(re.compile(r"NAO\s+PERMITEM\s+A\s+EMISSAO\s+DA\s+CERTIDAO"),),
        pcen=(_PCEN,),
        negativa=(re.compile(r"NAO\s+CONSTAM\s+DEBITOS\s+INSCRITOS\s+EM\s+DIVIDA\s+ATIVA"),),
        positiva=(_sim(r"CONSTAM\s+DEBITOS\s+INSCRITOS\s+EM\s+DIVIDA\s+ATIVA"),),
    )


def _tst(n: str) -> Optional[str]:
    return _decidir(
        n,
        pcen=(re.compile(r"CERTIDAO\s+POSITIVA\s+COM\s+EFEITOS?\s+DE\s+NEGATIVA\s+DE\s+DEBITOS\s+TRABALHISTAS"),),
        negativa=(
            re.compile(r"CERTIDAO\s+NEGATIVA\s+DE\s+DEBITOS\s+TRABALHISTAS"),
            re.compile(r"NAO\s+CONSTA\s+COMO\s+INADIMPLENTE\s+NO\s+BANCO\s+NACIONAL"),
        ),
        positiva=(
            re.compile(r"CERTIDAO\s+POSITIVA\s+DE\s+DEBITOS\s+TRABALHISTAS\s+NOME"),
            _sim(r"CONSTA\s+DO\s+BANCO\s+NACIONAL\s+DE\s+DEVEDORES\s+TRABALHISTAS"),
        ),
    )


def _trf3(n: str) -> Optional[str]:
    return _decidir(
        n,
        negativa=(re.compile(r"NAO\s+CONSTAM\s*,\s*ATE\s+A\s+PRESENTE\s+DATA\s+E\s+HORA\s*,\s*PROCESSOS"),),
        positiva=(_sim(r"CONSTAM\s*,\s*ATE\s+A\s+PRESENTE\s+DATA\s+E\s+HORA\s*,\s*PROCESSOS"),),
    )


def _trt2_digital(n: str) -> Optional[str]:
    return _decidir(
        n,
        negativa=(re.compile(r"NAO\s+CONSTAM\s+ACOES\s+TRABALHISTAS"),),
        positiva=(_sim(r"CONSTAM\s+AS\s+SEGUINTES\s+ACOES\s+TRABALHISTAS"),),
    )


def _trt2_fisico(n: str) -> Optional[str]:
    return _decidir(
        n,
        negativa=(re.compile(r"NAO\s+CONSTA\s+ACAO\s+TRABALHISTA\s+EM\s+TRAMITACAO"),),
        positiva=(_sim(r"CONSTAM\s*,\s*ATE\s+[\d/]+\s*,\s*AS\s+ACOES\s+TRABALHISTAS\s+EM\s+TRAMITACAO"),),
    )


_TJSP_NADA = re.compile(r"VERIFICOU\s+NADA\s+CONSTAR\s+COMO\s+REU")
_TJSP_CONSTA_QUALIFICADO = re.compile(
    r"(?<!NADA )VERIFICOU\s+CONSTAR\s+COMO\s+REU/REQUERIDO/INTERESSADO\s+EM\s+NOME\s+DE\s*:"
)
_TJSP_HOMONIMOS = re.compile(r"NAO\s+QUALIFICAD\w*.{0,200}?REFERIR-SE\s+A\s+HOMONIMOS?")


def _tjsp_esaj(n: str) -> Optional[str]:
    nada = bool(_TJSP_NADA.search(n))
    consta = bool(_TJSP_CONSTA_QUALIFICADO.search(n))
    if consta and not nada:
        return POSITIVA
    if nada and not consta:
        return NEGATIVA_COM_HOMONIMOS if _TJSP_HOMONIMOS.search(n) else NEGATIVA
    return None


def _tjsp_eproc(n: str) -> Optional[str]:
    return _decidir(
        n,
        negativa=(re.compile(r"VERIFICAMOS\s+NADA\s+CONSTAR"),),
        positiva=(_sim(r"VERIFICAMOS\s+CONSTAR"),),
    )


def _cenprot(n: str) -> Optional[str]:
    return _decidir(
        n,
        negativa=(re.compile(r"NAO\s+CONSTAM\s+PROTESTOS"),),
        positiva=(re.compile(r"QUANTIDADE\s+DE\s+PROTESTOS\s*:\s*[1-9]"),),
    )


LEITORES: dict[str, Callable[[str], Optional[str]]] = {
    "cnd_federal": _cnd_federal,
    "cnd_fazenda_sp": _cnd_fazenda_sp,
    "divida_ativa_sp": _divida_ativa_sp,
    "cnd_trabalhista_tst": _tst,
    "trf3": _trf3,
    "trf3_sp": _trf3,
    "trt2_digital": _trt2_digital,
    "trt2_fisico": _trt2_fisico,
    "tjsp_esaj": _tjsp_esaj,
    "tjsp_eproc": _tjsp_eproc,
    "cenprot": _cenprot,
}


def ler_resultado_certidao(tipo: str, texto: Optional[str]) -> Optional[str]:
    """The verdict the issuer printed, or `None` (unknown tipo, no text, or
    nothing unambiguous printed)."""
    leitor = LEITORES.get(tipo)
    if leitor is None or not texto or not texto.strip():
        return None
    return leitor(normalize(texto))


#: Certidão tipos whose text PRINTS the searched person's RG beside the CPF
#: (the TJSP e-SAJ "Certidão de Distribuição Cível": `RG: 30.738.581-4`
#: `CPF: ...`). Unlike a CNH, that RG carries its check digit.
TIPOS_COM_RG_IMPRESSO = frozenset({"tjsp_esaj"})


def ler_identificacao_impressa(
    tipo: str, texto: Optional[str]
) -> Optional[tuple[str, str]]:
    """`(rg, cpf)` as printed on the certidão, or `None`.

    Reuses the identity readers (`rg.find_rg`, `cpf.find_cpf`) - no second RG
    regex. Only a LABELLED reading of both (`alta`) counts: a certidão that
    prints one of them loosely is not evidence about whose RG it is. The RG
    comes back verbatim as printed; the caller decides whether it belongs to
    a given party (CPF match) and whether it completes a stored RG.
    """
    if tipo not in TIPOS_COM_RG_IMPRESSO or not texto or not texto.strip():
        return None
    rg, rg_conf, _ = find_rg(texto)
    cpf, cpf_conf, _ = find_cpf(texto)
    if not rg or not cpf or rg_conf != "alta" or cpf_conf != "alta":
        return None
    return rg, cpf
