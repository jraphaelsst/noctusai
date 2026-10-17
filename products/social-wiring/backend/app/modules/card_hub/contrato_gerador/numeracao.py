"""Numbering & cross-references — computed, never typed (spec §4).

The errors in contracts 01/03/04/06 are all typed numbers: a duplicated
DÉCIMA TERCEIRA, "Cláusula Sétima" pointing at the Oitava, ¶1 → ¶3, pendência
letters skipping c-). Here:

- clause numbers come from ONE registry filtered by the switches; a clause
  that is off is ABSENT from `cl`, so a template reference to it fails the
  render (StrictUndefined) instead of printing a wrong number;
- paragraph labels come from a per-clause counter whose totals are MEASURED
  by a first render pass (so "Único" is decided by what actually rendered,
  not by a second hand-kept declaration that could drift from the template);
- every `cl.<key>.ref` read is recorded, so the post-render lint can check
  each "Cláusula X" in the text names the clause the template meant.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Mapping, Optional

from noctusai_lib.domain.texto_ptbr import ordinal_por_extenso

ORDEM_CLAUSULAS: tuple[str, ...] = (
    "objeto",
    "preco",
    "confissao",
    "certidoes",
    "onus",
    "posse",
    "tributos",
    "irretratabilidade",
    "mora",
    "declaracao_partes",
    "vistoria",
    "assinatura_digital",
    "registro",
    "resolutiva",
    "intermediacao",
    "foro",
)

#: The conditional clauses and the switch that includes each (§0).
#: `assinatura_digital` (migration 157) is off for a FÍSICA contract — the
#: clauses after it re-number by construction.
CLAUSULA_CONDICIONAL: Mapping[str, str] = {
    "confissao": "tem_confissao",
    "declaracao_partes": "tem_declaracao_partes",
    "assinatura_digital": "tem_assinatura_digital",
    "intermediacao": "tem_intermediacao",
}

#: The heading text after "CLÁUSULA <ORD> – " each clause key must carry.
#: The lint uses it to prove a reference points at the right TOPIC, not just
#: at some existing number.
TITULO_CLAUSULA: Mapping[str, str] = {
    "objeto": "DO OBJETO DO CONTRATO",
    "preco": "DO PREÇO E CONDIÇÕES DE PAGAMENTO",
    "confissao": "DA CONFISSÃO DE DÍVIDA",
    "certidoes": "DAS CERTIDÕES E DOCUMENTOS",
    "onus": "DO ÔNUS SOBRE",
    "posse": "DA POSSE SOBRE",
    "tributos": "DO PAGAMENTO DOS TRIBUTOS",
    "irretratabilidade": "DA IRRETRATABILIDADE",
    "mora": "DA MORA E DO INADIMPLEMENTO",
    "declaracao_partes": "DECLARAÇÃO DAS PARTES",
    "vistoria": "DA VISTORIA PRÉVIA",
    "assinatura_digital": "DA ASSINATURA DIGITAL",
    "registro": "AUTORIZAÇÃO DE REGISTRO",
    "resolutiva": "CLÁUSULA RESOLUTIVA EXPRESSA",
    "intermediacao": "DA INTERMEDIAÇÃO",
    "foro": "DA ELEIÇÃO DO FORO",
}


def rotulo_clausula(chave: str) -> str:
    """The clause's heading as a label for the card UI / review items
    ("Do preço e condições de pagamento") — read off `TITULO_CLAUSULA`, never a
    second hand list. KeyError for a key that is not one of `ORDEM_CLAUSULAS`."""
    return TITULO_CLAUSULA[chave].capitalize()


class Clausula:
    def __init__(self, chave: str, n: int, registro: "RegistroClausulas") -> None:
        self.chave = chave
        self.n = n
        self._registro = registro

    @property
    def ORD(self) -> str:  # noqa: N802 — template token
        return ordinal_por_extenso(self.n, feminino=True).upper()

    @property
    def ref(self) -> str:
        self._registro.referencias[self.chave] += 1
        return f"Cláusula {ordinal_por_extenso(self.n, feminino=True).title()}"


#: Highest ordinal a citation is parsed up to — far above any contract here.
_MAX_ORDINAL = 60
_ORDINAL_CITADO = {ordinal_por_extenso(n, feminino=True): n for n in range(1, _MAX_ORDINAL)}
_RE_CITACAO = re.compile(r"[Cc]láusula ([A-Za-zÀ-ÿ]+)(?: ([A-Za-zÀ-ÿ]+))?")

#: A special condition (migration 207) cites another clause by its KEY —
#: "[cláusula:mora]" — never by number: the text is typed once, the numbering
#: moves with the switches. Resolved by `resolver_referencias` into a counted
#: `Clausula.ref`, so the post-render lint checks it like any template ref.
RE_REFERENCIA_POR_CHAVE = re.compile(r"\[\s*cl[áa]usula\s*:\s*([A-Za-z_]+)\s*\]", re.IGNORECASE)


def citacoes_de_clausula(texto: str) -> list[tuple[int, int, int]]:
    """Every "Cláusula <ordinal>" written out in `texto`, as (n, início, fim) —
    the ONE parser both the lint and the special-condition gate read."""
    achados: list[tuple[int, int, int]] = []
    for m in _RE_CITACAO.finditer(texto):
        if m.group(2):
            n = _ORDINAL_CITADO.get(f"{m.group(1)} {m.group(2)}".lower())
            if n is not None:
                achados.append((n, m.start(), m.end()))
                continue
        n = _ORDINAL_CITADO.get(m.group(1).lower())
        if n is not None:
            achados.append((n, m.start(), m.end(1)))
    return achados


def chaves_referidas(texto: str) -> list[str]:
    return [m.group(1).lower() for m in RE_REFERENCIA_POR_CHAVE.finditer(texto)]


def resolver_referencias(texto: str, cl: "RegistroClausulas") -> str:
    """Each "[cláusula:<chave>]" → that clause's counted `ref`. KeyError for a
    key `cl` lacks — `derivacao` blocks such a text before any render."""
    return RE_REFERENCIA_POR_CHAVE.sub(lambda m: cl[m.group(1).lower()].ref, texto)


class RegistroClausulas(dict):
    """`cl` in the template: key -> `Clausula`, only for included clauses."""

    def __init__(self) -> None:
        super().__init__()
        self.referencias: Counter[str] = Counter()


def numerar_clausulas(switches: Mapping[str, bool]) -> RegistroClausulas:
    registro = RegistroClausulas()
    n = 0
    for chave in ORDEM_CLAUSULAS:
        switch = CLAUSULA_CONDICIONAL.get(chave)
        if switch is not None and not switches.get(switch, False):
            continue
        n += 1
        registro[chave] = Clausula(chave, n, registro)
    return registro


#: Clauses whose paragraph is labelled "Parágrafo Primeiro" even when it is the
#: ONLY one rendered — a named exception to the "Único only alone" rule.
#: Owner decision 2026-10-05, backed by the corpus (signed contracts, lone
#: paragraph of the clause): `certidoes` -> "Primeiro" 76/78 (re-count over the
#: 102 extracted contract texts: 80/80). Every other clause keeps "Único"
#: (lone-paragraph counts: posse Único 64/64, objeto Único 56/56, preço Único
#: 44/44; intermediação is Primeiro 11/14 and ônus Primeiro 3/4 — NOT adopted:
#: below the certidões majority / too few — see the owner report).
PARAGRAFO_PRIMEIRO_MESMO_SOZINHO: frozenset[str] = frozenset({"certidoes"})


class ContadorParagrafos:
    """`par('<clausula>')` in the template.

    Pass 1 (`totais=None`) only counts calls per clause. Pass 2 receives those
    counts and labels: "Parágrafo Único:" when a clause rendered exactly one
    paragraph, "Parágrafo Primeiro:" … otherwise.
    """

    def __init__(self, totais: Optional[Mapping[str, int]] = None) -> None:
        self.totais = dict(totais) if totais is not None else None
        self.chamadas: Counter[str] = Counter()

    def __call__(self, chave: str) -> str:
        self.chamadas[chave] += 1
        if self.totais is None:
            return "Parágrafo:"
        total = self.totais.get(chave, 0)
        n = self.chamadas[chave]
        if n > total:
            raise RuntimeError(
                f"par('{chave}') chamado {n}× na segunda passagem, mas a "
                f"primeira contou {total} — o template não é determinístico"
            )
        if total == 1 and chave not in PARAGRAFO_PRIMEIRO_MESMO_SOZINHO:
            return "Parágrafo Único:"
        return f"Parágrafo {ordinal_por_extenso(n).title()}:"


def num2(n: int) -> str:
    return f"{n:02d}"


def letra(indice: int) -> str:
    """0 -> "a", 25 -> "z", 26 -> "aa"."""
    saida = ""
    i = indice
    while True:
        i, resto = divmod(i, 26)
        saida = chr(ord("a") + resto) + saida
        if i == 0:
            return saida
        i -= 1


def juntar(itens: list[str]) -> str:
    """["01"] -> "01"; ["01", "02"] -> "01 e 02"; ["01","02","03"] -> "01, 02 e 03"."""
    if not itens:
        return ""
    if len(itens) == 1:
        return itens[0]
    return ", ".join(itens[:-1]) + " e " + itens[-1]


__all__ = [
    "CLAUSULA_CONDICIONAL",
    "Clausula",
    "ContadorParagrafos",
    "ORDEM_CLAUSULAS",
    "PARAGRAFO_PRIMEIRO_MESMO_SOZINHO",
    "RE_REFERENCIA_POR_CHAVE",
    "RegistroClausulas",
    "TITULO_CLAUSULA",
    "chaves_referidas",
    "citacoes_de_clausula",
    "juntar",
    "letra",
    "num2",
    "numerar_clausulas",
    "resolver_referencias",
    "rotulo_clausula",
]
