"""pt-BR legal-text helpers — número por extenso, ordinais, prazos, datas.

Pure, dependency-free, `Decimal`-exact. Built for contract generation
(`social_wiring`'s promessa de venda e compra, F5), where the digits and the
words of every amount are printed side by side — "R$ 1.234,56 (mil, duzentos
e trinta e quatro reais e cinquenta e seis centavos)" — and a hand-typed
mismatch between the two is exactly the error a signed contract must not
carry. Both halves come from ONE `Decimal` here, so they cannot disagree.

WHY NOT `num2words`
-------------------
It would be a new third-party dependency for ~150 lines of closed-vocabulary
logic, and its pt_BR output does not follow the notarial conventions this
module pins (the "de reais" after exact millions, the comma-vs-"e" rule
between thousand groups, "cem" vs "cento"). Owning the rule means a test
names each convention instead of inheriting a library's choice.

CONVENTIONS PINNED (each has a test)
------------------------------------
- "e" joins hundreds, tens and units inside a group ("duzentos e trinta e
  quatro"); "cem" alone, "cento e ..." otherwise.
- Between thousand groups: " e " before the LAST non-zero group when that
  group is < 100 or a round hundred ("mil e cem", "um milhão e quinhentos"),
  ", " otherwise ("mil, duzentos e trinta e quatro").
- "mil", never "um mil".
- Exact millions/billions take "de": "um milhão de reais", "dois milhões de
  reais e um centavo".
- Zero reais with centavos reads the centavos alone ("cinquenta centavos").

Lifted 2026-09-14 for contract automation F5 — see
`products/social-wiring/backend/app/modules/card_hub/contrato_gerador/`.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

CENTAVO = Decimal("0.01")

_UNIDADES = (
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito",
    "nove", "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis",
    "dezessete", "dezoito", "dezenove",
)
_DEZENAS = (
    "", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
    "oitenta", "noventa",
)
_CENTENAS = (
    "", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
    "seiscentos", "setecentos", "oitocentos", "novecentos",
)
#: (valor da escala, singular, plural) — "mil" is invariable and has no "um".
_ESCALAS = (
    (10**9, "bilhão", "bilhões"),
    (10**6, "milhão", "milhões"),
    (10**3, "mil", "mil"),
)

_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
)

_ORD_UNIDADES = (
    "", "primeir", "segund", "terceir", "quart", "quint", "sext", "sétim",
    "oitav", "non",
)
_ORD_DEZENAS = (
    "", "décim", "vigésim", "trigésim", "quadragésim", "quinquagésim",
    "sexagésim", "septuagésim", "octogésim", "nonagésim",
)
_ORD_CENTENAS = (
    "", "centésim", "ducentésim", "trecentésim", "quadringentésim",
    "quingentésim", "sexcentésim", "septingentésim", "octingentésim",
    "noningentésim",
)


def _feminizar(palavra: str) -> str:
    if palavra == "um":
        return "uma"
    if palavra == "dois":
        return "duas"
    if palavra.endswith("entos"):
        return palavra[: -len("os")] + "as"
    return palavra


def _ate_999(n: int, feminino: bool) -> str:
    if n == 100:
        return "cem"
    centena, resto = divmod(n, 100)
    partes: list[str] = []
    if centena:
        partes.append(_CENTENAS[centena])
    if resto:
        if resto < 20:
            partes.append(_UNIDADES[resto])
        else:
            dezena, unidade = divmod(resto, 10)
            partes.append(_DEZENAS[dezena])
            if unidade:
                partes.append(_UNIDADES[unidade])
    if feminino:
        partes = [_feminizar(p) for p in partes]
    return " e ".join(partes)


def inteiro_por_extenso(n: int, *, feminino: bool = False) -> str:
    """`1234` -> "mil, duzentos e trinta e quatro".

    `feminino=True` agrees the units and hundreds with a feminine noun
    ("duas parcelas", "duzentas e uma"); the scale words (milhão, bilhão) are
    nouns in their own right and stay masculine. Raises `ValueError` for a
    negative or non-integer input — a caller bug, never data to guess at.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"inteiro_por_extenso espera int, recebeu {n!r}")
    if n < 0:
        raise ValueError("inteiro_por_extenso não aceita negativos")
    if n == 0:
        return "zero"
    if n >= 10**12:
        raise ValueError("inteiro_por_extenso suporta valores abaixo de um trilhão")

    grupos: list[tuple[str, int]] = []  # (texto, valor do grupo sem escala)
    resto = n
    for escala, singular, plural in _ESCALAS:
        g, resto = divmod(resto, escala)
        if not g:
            continue
        if escala == 10**3:
            texto = "mil" if g == 1 else f"{_ate_999(g, feminino)} mil"
        else:
            texto = f"{_ate_999(g, False)} {singular if g == 1 else plural}"
        grupos.append((texto, g))
    if resto:
        grupos.append((_ate_999(resto, feminino), resto))

    saida = grupos[0][0]
    for i, (texto, valor) in enumerate(grupos[1:], start=1):
        ultimo = i == len(grupos) - 1
        conector = " e " if ultimo and (valor < 100 or valor % 100 == 0) else ", "
        saida += conector + texto
    return saida


def _exigir_centavos(valor: Decimal) -> Decimal:
    if not isinstance(valor, Decimal):
        raise ValueError(f"valor monetário deve ser Decimal, recebeu {type(valor).__name__}")
    if valor < 0:
        raise ValueError("valor monetário não pode ser negativo")
    quantizado = valor.quantize(CENTAVO)
    if quantizado != valor:
        raise ValueError(f"valor monetário com mais de 2 casas decimais: {valor}")
    return quantizado


def reais_por_extenso(valor: Decimal) -> str:
    """`Decimal("1234.56")` -> "mil, duzentos e trinta e quatro reais e
    cinquenta e seis centavos". Refuses (ValueError) a float, a negative, or
    a value with sub-centavo precision — rounding it silently would print an
    amount nobody agreed to."""
    q = _exigir_centavos(valor)
    inteiro = int(q)
    centavos = int((q - inteiro) * 100)

    partes: list[str] = []
    if inteiro:
        texto = inteiro_por_extenso(inteiro)
        if inteiro >= 10**6 and inteiro % 10**6 == 0:
            texto += " de"
        partes.append(f"{texto} {'real' if inteiro == 1 else 'reais'}")
    if centavos:
        partes.append(
            f"{inteiro_por_extenso(centavos)} {'centavo' if centavos == 1 else 'centavos'}"
        )
    if not partes:
        return "zero reais"
    return " e ".join(partes)


def formatar_inteiro_br(n: int) -> str:
    """`1234567` -> "1.234.567"."""
    return f"{n:,}".replace(",", ".")


def formatar_brl(valor: Decimal) -> str:
    """`Decimal("1234.5")` -> "R$ 1.234,50"."""
    q = _exigir_centavos(valor)
    inteiro = int(q)
    centavos = int((q - inteiro) * 100)
    return f"R$ {formatar_inteiro_br(inteiro)},{centavos:02d}"


def brl_por_extenso(valor: Decimal) -> str:
    """`Decimal("1234.56")` -> "R$ 1.234,56 (mil, duzentos e trinta e quatro
    reais e cinquenta e seis centavos)" — digits and words from one value."""
    return f"{formatar_brl(valor)} ({reais_por_extenso(valor)})"


_BRL_RE = re.compile(r"^\s*(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s*$")


def parse_brl(texto: str) -> Decimal:
    """`"R$ 1.234,56"` -> `Decimal("1234.56")`. The inverse of `formatar_brl`,
    used to round-trip a rendered document. Raises `ValueError` on anything
    that is not that exact shape."""
    m = _BRL_RE.match(texto or "")
    if not m:
        raise ValueError(f"valor em reais inválido: {texto!r}")
    try:
        return Decimal(f"{m.group(1).replace('.', '')}.{m.group(2)}")
    except InvalidOperation as exc:  # pragma: no cover - the regex already guarantees digits
        raise ValueError(f"valor em reais inválido: {texto!r}") from exc


def ordinal_por_extenso(n: int, *, feminino: bool = False) -> str:
    """`11` -> "décimo primeiro" (or "décima primeira"). Lowercase; the caller
    decides case ("CLÁUSULA DÉCIMA PRIMEIRA", "Parágrafo Décimo Primeiro")."""
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 999:
        raise ValueError(f"ordinal_por_extenso suporta 1..999, recebeu {n!r}")
    sufixo = "a" if feminino else "o"
    centena, resto = divmod(n, 100)
    dezena, unidade = divmod(resto, 10)
    radicais = [r for r in (_ORD_CENTENAS[centena], _ORD_DEZENAS[dezena], _ORD_UNIDADES[unidade]) if r]
    return " ".join(r + sufixo for r in radicais)


def numero_com_extenso(n: int, *, feminino: bool = False, largura: int = 0) -> str:
    """`2, feminino=True, largura=2` -> "02 (duas)"."""
    return f"{str(n).zfill(largura)} ({inteiro_por_extenso(n, feminino=feminino)})"


def dias_por_extenso(n: int, *, uteis: bool = False) -> str:
    """`90` -> "90 (noventa) dias corridos"; `5, uteis=True` -> "5 (cinco) dias
    úteis"; `1` -> "1 (um) dia corrido"."""
    if n == 1:
        return f"1 (um) dia {'útil' if uteis else 'corrido'}"
    return f"{n} ({inteiro_por_extenso(n)}) dias {'úteis' if uteis else 'corridos'}"


def data_por_extenso(d: date) -> str:
    """`date(2026, 9, 5)` -> "05 de setembro de 2026"."""
    return f"{d.day:02d} de {_MESES[d.month - 1]} de {d.year:04d}"


def formatar_data_br(d: date) -> str:
    """`date(2026, 9, 5)` -> "05/09/2026" — four-digit year, always."""
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"


def percentual_por_extenso(valor: Decimal) -> str:
    """`Decimal("1")` -> "1% (um por cento)"; `Decimal("1.25")` -> "1,25% (um
    vírgula vinte e cinco por cento)"."""
    if not isinstance(valor, Decimal) or valor < 0:
        raise ValueError(f"percentual deve ser Decimal não negativo, recebeu {valor!r}")
    normal = valor.normalize()
    sinal, digitos, expoente = normal.as_tuple()
    if expoente >= 0:
        inteiro = int(normal)
        return f"{inteiro}% ({inteiro_por_extenso(inteiro)} por cento)"
    casas = -expoente
    texto = f"{normal:.{casas}f}"
    parte_int, parte_dec = texto.split(".")
    extenso_dec = inteiro_por_extenso(int(parte_dec))
    zeros = len(parte_dec) - len(parte_dec.lstrip("0"))
    if zeros:
        extenso_dec = " ".join(["zero"] * zeros + [extenso_dec])
    return (
        f"{parte_int},{parte_dec}% ({inteiro_por_extenso(int(parte_int))} "
        f"vírgula {extenso_dec} por cento)"
    )


__all__ = [
    "CENTAVO",
    "brl_por_extenso",
    "data_por_extenso",
    "dias_por_extenso",
    "formatar_brl",
    "formatar_data_br",
    "formatar_inteiro_br",
    "inteiro_por_extenso",
    "numero_com_extenso",
    "ordinal_por_extenso",
    "parse_brl",
    "percentual_por_extenso",
    "reais_por_extenso",
]
