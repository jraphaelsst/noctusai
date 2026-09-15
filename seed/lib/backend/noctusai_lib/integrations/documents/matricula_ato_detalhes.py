"""Read ONE act of a matrícula into typed details — pure, deterministic.

`segment_matricula_atos` (sibling module) splits a transcription into acts as
offsets. This module answers the next question a contract asks about an act:
WHAT happened (natureza), WHEN it was registered, for HOW MUCH, BETWEEN WHOM,
in favour of WHICH creditor, by WHICH instrument, and WHICH earlier acts it
refers to. No IO, no LLM: text in, `AtoDetalhes` out.

🔴 VALUES ARE READ, NEVER COMPOSED
----------------------------------
Every text value (a party's `nome`, the `credor`, the instrument's `tipo`,
`tabelionato`, `livro`, `folhas`, `cidade`) is a SUBSTRING of the literal act
text, only trimmed at its edges. The matching runs on a normalised copy
(upper-case, accent-stripped — `matricula_atos.normalized_with_offsets`) and
every hit is mapped back to the original characters. Only three kinds of
value are normalised on the way out, because their canonical form carries no
reading of its own:

- dates -> `datetime.date` (`10 de março de 2001` and `10/03/2001` are one date);
- CPF / CNPJ -> `123.456.789-09` / `11.222.333/0001-81`;
- `valor` -> `Decimal` (only amounts in REAIS — a `Cr$` amount is a different
  currency, and storing it as a bare number would be a guess about its value).

🔴 UNKNOWN IS `None`, NEVER A GUESS
-----------------------------------
Each field carries its own confidence, as the plain strings `"alta"` /
`"baixa"` / `"nenhuma"` (the values of `types.ExtractionConfidence`, same
convention as `cpf.py`):

- `alta`  — the value sat next to its own label (`Transmitente:`, `Em <data>`
  right after the header, `lavrada em`), and nothing in the act contradicts it.
- `baixa` — something plausible was found, but narratively (`em favor do …`),
  or with a competing reading nearby, or with a CPF whose check digits fail.
  A suggestion for the operator, not a fact.
- `nenhuma` — nothing usable. The value is `None` (or an empty tuple).

Two readings that DISAGREE (two different registration dates, both labelled)
are absence, not a vote — the same rule `cpf.py` and `birthdate.py` follow.

Scope: the act text as `MatriculaAto.quote` returns it, header included. The
abertura carries no act, so callers do not run this on it.

All fixture names, numbers and banks in this module's tests are invented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Optional

from noctusai_lib.integrations.documents.cpf import format_cpf
from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_valido
from noctusai_lib.integrations.documents.matricula import normalize
from noctusai_lib.integrations.documents.matricula_atos import normalized_with_offsets

ALTA = "alta"
BAIXA = "baixa"
NENHUMA = "nenhuma"

NaturezaAto = Literal[
    "compra_e_venda",
    "doacao",
    "permuta",
    "partilha",
    "dacao",
    "arrematacao",
    "hipoteca",
    "alienacao_fiduciaria",
    "cancelamento",
    "penhora",
    "usufruto",
    "indisponibilidade",
    "construcao",
    "outro",
]

#: The vocabulary, in a stable order — mirrored by migration 115's CHECK.
NATUREZAS_ATO: tuple[str, ...] = (
    "compra_e_venda",
    "doacao",
    "permuta",
    "partilha",
    "dacao",
    "arrematacao",
    "hipoteca",
    "alienacao_fiduciaria",
    "cancelamento",
    "penhora",
    "usufruto",
    "indisponibilidade",
    "construcao",
    "outro",
)

#: Natures that move ownership to someone else.
NATUREZAS_TRANSFERENCIA: frozenset[str] = frozenset(
    {"compra_e_venda", "doacao", "permuta", "partilha", "dacao", "arrematacao"}
)

#: Natures that have a creditor — the only ones `credor` is read for.
NATUREZAS_COM_CREDOR: frozenset[str] = frozenset({"hipoteca", "alienacao_fiduciaria"})

CONFIANCAS: tuple[str, ...] = (ALTA, BAIXA, NENHUMA)


# ─── value objects ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Parte:
    """A party to an act. `nome` is a literal substring; `cpf_cnpj` is the
    formatted document number, or None when the act does not print one."""

    nome: str
    cpf_cnpj: Optional[str] = None

    def to_json(self) -> dict:
        return {"nome": self.nome, "cpf_cnpj": self.cpf_cnpj}

    @classmethod
    def from_json(cls, data: dict) -> "Parte":
        return cls(nome=str(data["nome"]), cpf_cnpj=data.get("cpf_cnpj"))


@dataclass(frozen=True)
class Instrumento:
    """The document the act registers (`Escritura Pública de Venda e Compra`,
    `Instrumento particular`, `Formal de Partilha`, ...). Every field but
    `data` is a literal substring."""

    tipo: Optional[str] = None
    data: Optional[date] = None
    tabelionato: Optional[str] = None
    livro: Optional[str] = None
    folhas: Optional[str] = None
    cidade: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "tipo": self.tipo,
            "data": self.data.isoformat() if self.data else None,
            "tabelionato": self.tabelionato,
            "livro": self.livro,
            "folhas": self.folhas,
            "cidade": self.cidade,
        }

    @classmethod
    def from_json(cls, data: Optional[dict]) -> Optional["Instrumento"]:
        if not data:
            return None
        bruto = data.get("data")
        return cls(
            tipo=data.get("tipo"),
            data=date.fromisoformat(bruto) if isinstance(bruto, str) and bruto else bruto,
            tabelionato=data.get("tabelionato"),
            livro=data.get("livro"),
            folhas=data.get("folhas"),
            cidade=data.get("cidade"),
        )


@dataclass(frozen=True)
class AtoReferido:
    """An earlier act this act cites (`cancelamento do R-3`)."""

    kind: Literal["R", "AV"]
    numero: int

    def to_json(self) -> dict:
        return {"kind": self.kind, "numero": self.numero}


@dataclass(frozen=True)
class AtoDetalhes:
    """Typed details of one act. See the module docstring for the contract."""

    natureza: Optional[str] = None
    natureza_confianca: str = NENHUMA
    data_registro: Optional[date] = None
    data_registro_confianca: str = NENHUMA
    valor: Optional[Decimal] = None
    valor_confianca: str = NENHUMA
    transmitentes: tuple[Parte, ...] = ()
    transmitentes_confianca: str = NENHUMA
    adquirentes: tuple[Parte, ...] = ()
    adquirentes_confianca: str = NENHUMA
    credor: Optional[str] = None
    credor_confianca: str = NENHUMA
    instrumento: Optional[Instrumento] = None
    instrumento_confianca: str = NENHUMA
    atos_referidos: tuple[AtoReferido, ...] = ()
    atos_referidos_confianca: str = NENHUMA

    def to_json(self) -> dict:
        """JSON-safe dict (dates ISO, `valor` as a decimal string)."""
        return {
            "natureza": self.natureza,
            "natureza_confianca": self.natureza_confianca,
            "data_registro": self.data_registro.isoformat() if self.data_registro else None,
            "data_registro_confianca": self.data_registro_confianca,
            "valor": str(self.valor) if self.valor is not None else None,
            "valor_confianca": self.valor_confianca,
            "transmitentes": [p.to_json() for p in self.transmitentes],
            "transmitentes_confianca": self.transmitentes_confianca,
            "adquirentes": [p.to_json() for p in self.adquirentes],
            "adquirentes_confianca": self.adquirentes_confianca,
            "credor": self.credor,
            "credor_confianca": self.credor_confianca,
            "instrumento": self.instrumento.to_json() if self.instrumento else None,
            "instrumento_confianca": self.instrumento_confianca,
            "atos_referidos": [a.to_json() for a in self.atos_referidos],
            "atos_referidos_confianca": self.atos_referidos_confianca,
        }


# ─── text with an offset map ──────────────────────────────────────────────

_BORDA = " \t\r\n,;:-–—"


class _Texto:
    """The act text, its normalised twin (line breaks flattened 1:1 to spaces
    so a pattern survives an OCR line wrap), and the offset map back."""

    def __init__(self, texto: str) -> None:
        self.original = texto
        norm, self.origem = normalized_with_offsets(texto)
        self.norm = "".join(" " if c.isspace() else c for c in norm)

    def span(self, a: int, b: int) -> tuple[int, int]:
        return self.origem[a], self.origem[b - 1] + 1

    def literal(self, a: int, b: int) -> Optional[str]:
        """The original slice behind normalised `[a, b)`, edge-trimmed."""
        if b <= a:
            return None
        ini, fim = self.span(a, b)
        valor = self.original[ini:fim].strip(_BORDA)
        return valor or None

    def nome(self, a: int, b: int) -> Optional[str]:
        """`literal`, keeping the final dot of a dotted abbreviation
        (`Banco Exemplo S.A.`) that the name terminator stopped short of."""
        if b <= a:
            return None
        ini, fim = self.span(a, b)
        bruto = self.original[ini:fim]
        inicio = ini + (len(bruto) - len(bruto.lstrip(_BORDA)))
        valor = bruto.strip(_BORDA).rstrip(".").rstrip()
        if not valor:
            return None
        termino = inicio + len(valor)
        if re.search(r"\.[A-Za-z]$", valor) and self.original[termino : termino + 1] == ".":
            termino += 1
        return self.original[inicio:termino]


def _rx(corpo: str) -> re.Pattern[str]:
    """A whole-word alternation over normalised text."""
    return re.compile(rf"(?<![A-Z])(?:{corpo})(?![A-Z])")


# ─── header ───────────────────────────────────────────────────────────────

_HEADER = re.compile(
    r"^\s*(?P<kind>AV|R)\s*[-.–—]?\s*(?P<num>\d{1,4})(?!\d)(?!,\d)"
    r"(?P<suf>\s*/\s*(?:M\s*[.-]?\s*)?\d+(?:\.\d+)*"
    r"|-(?:M\.?)?(?:\d{1,3}(?:\.\d{3})+|\d{4,}))?"
)


def _digitos(valor: Optional[str]) -> str:
    return re.sub(r"\D", "", valor or "")


# ─── natureza ─────────────────────────────────────────────────────────────

_NATUREZAS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "cancelamento",
        _rx(
            r"CANCELAMENTO|CANCELA-SE|CANCELAD[OA]S?|BAIXA\s+D[AOE]S?"
            r"|LEVANTAMENTO\s+D[AOE]S?\s+(?:PENHORA|INDISPONIBILIDADE|ARRESTO|SEQUESTRO)"
            r"|EXTINCAO\s+D[OAE]S?|EXTINT[OA]|RENUNCIA\s+(?:A|AO|DO|DA)\s+USUFRUTO"
            r"|DESCONSTITUICAO"
        ),
    ),
    ("alienacao_fiduciaria", _rx(r"ALIENACAO\s+FIDUCIARIA|ALIENAD[OA]\s+FIDUCIARIAMENTE|PROPRIEDADE\s+FIDUCIARIA")),
    ("hipoteca", _rx(r"HIPOTECA|HIPOTECAD[OA]|HIPOTECARI[OA]")),
    ("penhora", _rx(r"PENHORA|PENHORAD[OA]")),
    ("indisponibilidade", _rx(r"INDISPONIBILIDADE|INDISPONIVEL")),
    ("usufruto", _rx(r"USUFRUTO|USUFRUTUARI[OA]S?")),
    (
        "compra_e_venda",
        _rx(r"COMPRA\s+E\s+VENDA|VENDA\s+E\s+COMPRA|VENDA|VENDEU|VENDERAM|VENDID[OA]S?"),
    ),
    ("doacao", _rx(r"DOACAO|DOOU|DOARAM|DOAD[OA]S?")),
    ("permuta", _rx(r"PERMUTA|PERMUTAD[OA]S?|PERMUTARAM")),
    (
        "partilha",
        _rx(r"PARTILHA|SOBREPARTILHA|INVENTARIO|ARROLAMENTO|TRANSMISSAO\s+CAUSA\s+MORTIS"),
    ),
    ("dacao", _rx(r"DACAO(?:\s+EM\s+PAGAMENTO)?")),
    ("arrematacao", _rx(r"ARREMATACAO|ARREMATAD[OA]")),
    (
        "construcao",
        _rx(
            r"CONSTRUCAO|EDIFICACAO|HABITE-SE|AUTO\s+DE\s+CONCLUSAO"
            r"|AMPLIACAO\s+D[AE]\s+AREA\s+CONSTRUIDA"
        ),
    ),
    (
        "outro",
        _rx(
            r"PROMESSA\s+DE\s+(?:COMPRA\s+E\s+)?VENDA|COMPROMISSO\s+DE\s+(?:COMPRA\s+E\s+)?VENDA"
            r"|ADJUDICACAO|INTEGRALIZACAO|USUCAPIAO|CONSOLIDACAO\s+DA\s+PROPRIEDADE"
            r"|CASAMENTO|DIVORCIO|SEPARACAO\s+JUDICIAL|OBITO|RETIFICACAO|DEMOLICAO"
            r"|DESMEMBRAMENTO|UNIFICACAO|FUSAO|INCORPORACAO|INSTITUICAO\s+DE\s+CONDOMINIO"
            r"|CONVENCAO\s+DE\s+CONDOMINIO|CESSAO|NUMERO\s+DE\s+CONTRIBUINTE"
            r"|CADASTRO\s+MUNICIPAL|INSCRICAO\s+MUNICIPAL|ALTERACAO\s+D[AE]\s+DENOMINACAO"
            r"|TOMBAMENTO|SERVIDAO|LOCACAO|ARRESTO|SEQUESTRO|CAUCAO|ANTICRESE"
            r"|BEM\s+DE\s+FAMILIA"
        ),
    ),
)

#: How far into the body (after the header) a nature may start and still be
#: the act's TITLE rather than something the act mentions in passing.
_JANELA_TITULO = 120

_FIM_FRASE = re.compile(r"\.(?=\s|$)|;")


def _natureza(t: _Texto, corpo: int) -> tuple[Optional[str], str]:
    achados: list[tuple[int, int, str]] = []
    for natureza, rx in _NATUREZAS:
        for m in rx.finditer(t.norm, corpo):
            achados.append((m.start(), m.end(), natureza))
    # `VENDA` inside `PROMESSA DE VENDA` is the promise, not a sale.
    achados = [
        a
        for a in achados
        if not any(
            b is not a and b[0] <= a[0] and a[1] <= b[1] and (b[1] - b[0]) > (a[1] - a[0])
            for b in achados
        )
    ]
    if not achados:
        return None, NENHUMA
    achados.sort(key=lambda a: (a[0], -(a[1] - a[0])))
    inicio, fim, natureza = achados[0]
    fim_frase_m = _FIM_FRASE.search(t.norm, fim)
    fim_frase = fim_frase_m.start() if fim_frase_m else len(t.norm)
    conflitos = {n for (i, _f, n) in achados[1:] if i < fim_frase and n != natureza}
    if natureza == "cancelamento":
        # What follows a cancellation in its own sentence is its OBJECT
        # (`CANCELAMENTO da hipoteca`), not a competing reading.
        conflitos = set()
    if inicio - corpo <= _JANELA_TITULO and not conflitos:
        return natureza, ALTA
    return natureza, BAIXA


# ─── dates ────────────────────────────────────────────────────────────────

_MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

_DATA_NUM = re.compile(r"(?<![\d/.])(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?![\d/])")
_DATA_EXT = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:O|°)?\s+DE\s+(" + "|".join(_MESES) + r")\s+DE\s+(\d{4})(?!\d)"
)


def _datas(norm: str, desde: int = 0, ate: Optional[int] = None) -> list[tuple[int, int, date]]:
    ate = len(norm) if ate is None else ate
    saida: list[tuple[int, int, date]] = []
    for m in _DATA_NUM.finditer(norm, desde, ate):
        dia, mes, ano = (int(g) for g in m.groups())
        try:
            saida.append((m.start(), m.end(), date(ano, mes, dia)))
        except ValueError:
            continue
    for m in _DATA_EXT.finditer(norm, desde, ate):
        try:
            saida.append((m.start(), m.end(), date(int(m.group(3)), _MESES[m.group(2)], int(m.group(1)))))
        except ValueError:
            continue
    saida.sort()
    return saida


#: The date sits right after the header: `R-1/45.678 - Em 10 de março de 2001`.
_ANCORA_INICIO = re.compile(r"^[\s\-–—.:,]*(?:EM\s+|DATA\s*[:\-–—]?\s*)?$")

#: A registration label ends right before the date.
_ROTULO_REGISTRO = re.compile(
    r"(?:(?<![A-Z])(?:REGISTRAD[OA]|AVERBAD[OA])\s+(?:EM|NO\s+DIA)"
    r"|(?<![A-Z])DATA\s+D[OA]\s+(?:REGISTRO|AVERBACAO|ATO)\s*[:\-–—]?"
    r"|(?<![A-Z])DATA\s*[:\-–—]"
    r"|(?:^|[.;]\s*)EM)\s*$"
)

#: The closing `Cotia, 12 de março de 2020.` — weaker: it is the signing line.
_CIDADE_VIRGULA = re.compile(r"(?:^|[.;]\s*)[A-Z][A-Z' ]{1,40},\s*(?:EM\s+)?$")

_JANELA_FECHO = 160


def _data_registro(t: _Texto, corpo: int) -> tuple[Optional[date], str]:
    fortes: list[date] = []
    fracas: list[date] = []
    for inicio, _fim, valor in _datas(t.norm, corpo):
        prefixo = t.norm[corpo:inicio]
        if _ANCORA_INICIO.match(prefixo) or _ROTULO_REGISTRO.search(prefixo):
            fortes.append(valor)
        elif inicio >= len(t.norm) - _JANELA_FECHO and _CIDADE_VIRGULA.search(prefixo):
            fracas.append(valor)
    if fortes:
        return (fortes[0], ALTA) if len(set(fortes)) == 1 else (None, NENHUMA)
    if len(set(fracas)) == 1:
        return fracas[0], BAIXA
    return None, NENHUMA


# ─── valor ────────────────────────────────────────────────────────────────

_MOEDA = re.compile(
    r"(?P<moeda>R\$|CR\$|NCZ\$|CZ\$|US\$)\s*"
    # `(?!\d|[.,]\d)`, not `(?![\d,])`: `R$ 300.000,00, sendo` is followed by a
    # comma, and refusing that comma made the pattern backtrack to `300`.
    r"(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+(?:,\d{2})?)(?!\d|[.,]\d)"
)
_VALOR_ROTULO = _rx(r"VALOR|PRECO|QUANTIA|IMPORTANCIA|MONTANTE")
_VALOR_ISCA = _rx(
    r"VENAL|AVALIACAO|AVALIAD[OA]|ITBI|FISCA(?:L|IS)|REFERENCIA|IMPOSTO|EMOLUMENTOS"
    r"|CUSTAS|PARCELAS?|PRESTAC(?:AO|OES)|RECURSOS\s+PROPRIOS|FGTS|SINAL|ENTRADA"
    r"|SUBSIDIO|DESCONTO|TAXA|SELO|JUROS|MENSA(?:L|IS)|CAPITAL\s+SOCIAL|LANCE\s+MINIMO"
)
_JANELA_VALOR = 50


def _valor(t: _Texto, corpo: int) -> tuple[Optional[Decimal], str]:
    rotulados: list[Decimal] = []
    soltos: list[Decimal] = []
    for m in _MOEDA.finditer(t.norm, corpo):
        if m.group("moeda") != "R$":
            continue
        try:
            quantia = Decimal(m.group("num").replace(".", "").replace(",", "."))
        except InvalidOperation:  # pragma: no cover - the regex guarantees digits
            continue
        janela_ini = max(corpo, m.start() - _JANELA_VALOR)
        janela = t.norm[janela_ini : m.start()]
        rotulos = list(_VALOR_ROTULO.finditer(janela))
        iscas = list(_VALOR_ISCA.finditer(janela))
        if rotulos:
            ultimo_rotulo = rotulos[-1].start()
            if any(i.start() >= ultimo_rotulo for i in iscas):
                continue  # `valor venal de R$ ...`
            rotulados.append(quantia)
        elif not iscas:
            soltos.append(quantia)
    if rotulados:
        return rotulados[0], (ALTA if len(set(rotulados)) == 1 else BAIXA)
    if len(set(soltos)) == 1:
        return soltos[0], BAIXA
    return None, NENHUMA


# ─── documents (CPF / CNPJ) ───────────────────────────────────────────────

#: The trailing lookahead refuses a longer number (`-`, `/`, a digit, or a
#: dot followed by a digit) but NOT a sentence-ending dot: `CPF 123.456.789-09.`
#: is the last thing in a clause far more often than not.
_CNPJ = re.compile(r"(?<![\d./-])(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?![\d/-]|\.\d)")
_CPF = re.compile(r"(?<![\d./-])(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?![\d/-]|\.\d)")


def _cnpj_valido(digitos: str) -> bool:
    if len(digitos) != 14 or digitos == digitos[0] * 14:
        return False
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for tamanho, p in ((12, pesos), (13, [6] + pesos)):
        resto = sum(int(d) * w for d, w in zip(digitos[:tamanho], p)) % 11
        if (0 if resto < 2 else 11 - resto) != int(digitos[tamanho]):
            return False
    return True


def formatar_cpf_cnpj(valor: str) -> Optional[str]:
    """`12345678909` -> `123.456.789-09`; 14 digits -> `11.222.333/0001-81`.
    None for any other digit count."""
    d = _digitos(valor)
    if len(d) == 11:
        return format_cpf(d)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return None


def cpf_cnpj_valido(valor: str) -> bool:
    """Do the check digits of this CPF (11 digits) or CNPJ (14) verify?"""
    d = _digitos(valor)
    return _cpf_valido(d) if len(d) == 11 else _cnpj_valido(d)


def _documento(norm: str, a: int, b: int) -> tuple[Optional[str], bool]:
    """The first CPF/CNPJ in `[a, b)`: (formatted, check digits verify)."""
    melhores = []
    for rx in (_CNPJ, _CPF):
        m = rx.search(norm, a, b)
        if m:
            melhores.append(m)
    if not melhores:
        return None, False
    m = min(melhores, key=lambda x: x.start())
    return formatar_cpf_cnpj(m.group(1)), cpf_cnpj_valido(m.group(1))


# ─── names ────────────────────────────────────────────────────────────────

_W = r"(?:ES|AS|OS|A|O|S)?(?:\s*\((?:S|ES|A|AS|OS)\))?"

_ROT_TRANSMITENTE = (
    rf"OUTORGANTE{_W}(?:\s+(?:VENDEDOR|DOADOR|TRANSMITENTE|ALIENANTE|CEDENTE){_W})?"
    rf"|(?:TRANSMITENTE|VENDEDOR|DOADOR|ALIENANTE|CEDENTE){_W}"
)
_ROT_ADQUIRENTE = (
    rf"OUTORGAD{_W}(?:\s+(?:COMPRADOR|DONATARI|ADQUIRENTE|CESSIONARI){_W})?"
    rf"|(?:ADQUIRENTE|COMPRADOR|DONATARI|CESSIONARI|ARREMATANTE|ADJUDICATARI){_W}"
    rf"|HERDEIR{_W}(?:\s+E\s+MEEIR{_W})?|MEEIR{_W}"
)
_ROT_CREDOR = rf"CREDOR{_W}(?:\s+(?:FIDUCIARI|HIPOTECARI){_W})?"
_ROT_OUTROS = (
    rf"DEVEDOR{_W}(?:\s+(?:FIDUCIANTE|HIPOTECANTE){_W})?|FIDUCIANTE{_W}|EMITENTE{_W}"
    rf"|INTERVENIENTE{_W}(?:\s+(?:ANUENTE|GARANTIDOR|HIPOTECANTE|QUITANTE){_W})?"
    rf"|ANUENTE{_W}|FIADOR{_W}|AVALISTA{_W}|PROPRIETARI{_W}|USUFRUTUARI{_W}"
    rf"|NU-?PROPRIETARI{_W}|EXEQUENTE{_W}|EXECUTAD{_W}|REQUERENTE{_W}|INVENTARIANTE{_W}"
    r"|VALOR|PRECO|TITULO|FORMA\s+DO\s+TITULO|CONDICOES|PRAZO|IMOVEL|OBJETO|PROTOCOLO"
    r"|PRENOTACAO|EMOLUMENTOS|SELO|ITBI|JUROS|TAXA\s+DE\s+JUROS|DATA|REGISTRO\s+ANTERIOR"
)

_ROTULO_PARTE = re.compile(
    rf"(?<![A-Z])(?:(?P<t>{_ROT_TRANSMITENTE})|(?P<a>{_ROT_ADQUIRENTE})"
    rf"|(?P<c>{_ROT_CREDOR})|(?P<x>{_ROT_OUTROS}))\s*[:\-–—]\s*"
)

#: A label-less end to a party block: the sentence that starts the next clause.
_FIM_BLOCO = re.compile(
    r"\.\s+(?=(?:VALOR|PRECO|O\s+OFICIAL|OFICIAL|DOU\s+FE|ESCREVENTE|EMOLUMENTOS|SELO"
    r"|PROTOCOLO|PRENOTACAO|CONDICOES|TITULO|FORMA\s+DO\s+TITULO|REGISTRAD|AVERBAD"
    r"|DATA|PELO|PELA|CONFORME|NOS\s+TERMOS|ITBI|R\$|CANCELAMENTO|HIPOTECA|ALIENACAO"
    r"|FICA|AVERBA|REGISTRA|EM\s+\d)(?![A-Z]))"
)

_SEPARA_PESSOA = re.compile(
    r";|\s+E\s+(?:SUA|SEU)\s+(?:MULHER|MARIDO|ESPOSA|ESPOSO|COMPANHEIR[OA]|CONJUGE)(?![A-Z])\s*,?"
    r"|(?:^|\s)\(?\d{1,2}\)\s+"
)

#: Leading noise before a name — including the `(1)` of a numbered list that
#: sits at the very start of a block, where no separator precedes it.
#: 🔴 No `^`: this is applied with `.match(norm, pos)`, and Python's `^` never
#: matches at a `pos` that is not the real start of the string — with it, the
#: prefix silently never stripped anything.
_PREFIXO_NOME = re.compile(
    r"[\s:\-–—,.]*(?:\(?\d{1,2}\)\s*)?(?:E\s+)?(?:(?:O|A|OS|AS)\s+)?(?:(?:SR|SRA|DR|DRA)\.?\s+)?"
)

_FIM_NOME = re.compile(
    r",|;|\(|:|\s[-–—]\s|\.(?=\s|$)|\d|R\$"
    r"|\s(?:POR|MEDIANTE|PORTADOR[A]?|INSCRIT[OA]S?|CPF|C\.P\.F|CNPJ|C\.N\.P\.J|RG|R\.G|CEDULA\s+DE\s+IDENTIDADE"
    r"|BRASILEIR[OA]S?|ESTRANGEIR[OA]S?|NASCID[OA]|SOLTEIR[OA]S?|CASAD[OA]S?|VIUV[OA]"
    r"|DIVORCIAD[OA]S?|SEPARAD[OA]S?|MAIOR(?:ES)?|MENOR|EMPRESARI[OA]|COM\s+SEDE|SEDIAD[OA]"
    r"|RESIDENTES?|DOMICILIAD[OA]S?|NESTE\s+ATO|REPRESENTAD[OA]|JA\s+QUALIFICAD[OA]S?"
    r"|ACIMA\s+QUALIFICAD[OA]S?|QUALIFICAD[OA]S?|PESSOA\s+JURIDICA|INSTITUICAO\s+FINANCEIRA"
    r"|EMPRESA\s+PUBLICA|PELO\s+VALOR|NO\s+VALOR|PARA\s+GARANTIA|EM\s+GARANTIA|NOS\s+TERMOS"
    r"|CONFORME|PELA\s+QUANTIA|PARA\s+PAGAMENTO|OBJETO)(?![A-Z])"
)

_NOME_CHARS = re.compile(r"^[A-Z' /&.\-]+$")

#: A "name" that starts like this is prose or a document, not a party.
_NAO_NOME = frozenset(
    {
        "NAO", "CONSTA", "MESMO", "MESMA", "MESMOS", "MESMAS", "SUPRA", "REFERIDO", "REFERIDA",
        "ESCRITURA", "INSTRUMENTO", "CONTRATO", "COMPRA", "VENDA", "DOACAO", "TITULO",
        "DIVIDA", "PAGAMENTO", "FINANCIAMENTO", "EMPRESTIMO", "OBRIGACOES", "OBRIGACAO",
        "CREDITO", "IMOVEL", "PRESENTE", "CEDULA", "VALOR", "QUANTIA", "FORMAL", "FAVOR",
    }
)


def _nome_valido(nome_norm: str, *, minimo_palavras: int = 2) -> bool:
    valor = " ".join(nome_norm.split())
    if not (3 <= len(valor) <= 150) or not _NOME_CHARS.match(valor):
        return False
    palavras = valor.split()
    if not (1 <= len(palavras) <= 12) or palavras[0] in _NAO_NOME:
        return False
    letras = [p for p in palavras if re.search(r"[A-Z]{2}", p)]
    if len(palavras) < minimo_palavras and not (letras and len(letras[0]) >= 4):
        return False
    return bool(letras)


def _fim_nome(norm: str, a: int, b: int) -> int:
    m = _FIM_NOME.search(norm, a, b)
    return m.start() if m else b


def _pessoas(t: _Texto, a: int, b: int) -> list[tuple[Parte, bool]]:
    """Parties in the block `[a, b)`: (Parte, its document verifies)."""
    fronteiras = [a]
    for m in _SEPARA_PESSOA.finditer(t.norm, a, b):
        fronteiras.extend([m.start(), m.end()])
    fronteiras.append(b)
    segmentos = [
        (fronteiras[i], fronteiras[i + 1]) for i in range(0, len(fronteiras) - 1, 2)
    ]
    saida: list[tuple[Parte, bool]] = []
    for s_ini, s_fim in segmentos:
        p = _PREFIXO_NOME.match(t.norm, s_ini, s_fim)
        n_ini = p.end() if p else s_ini
        n_fim = _fim_nome(t.norm, n_ini, s_fim)
        if n_fim <= n_ini:
            continue
        # `FULANO DE TAL E BELTRANA DE TAL, brasileiros` — two names, one
        # qualification. Split only when BOTH halves are names by themselves
        # (`FULANO E SILVA` is one name with a particle).
        partes_nome = [(n_ini, n_fim)]
        for m in re.finditer(r"\s+E\s+", t.norm[n_ini:n_fim]):
            esq = (n_ini, n_ini + m.start())
            dir_ = (n_ini + m.end(), n_fim)
            if _nome_valido(t.norm[esq[0] : esq[1]]) and _nome_valido(t.norm[dir_[0] : dir_[1]]):
                partes_nome = [esq, dir_]
                break
        documento, valido = _documento(t.norm, s_ini, s_fim)
        if len(partes_nome) > 1:
            documento, valido = None, False  # one qualification, two people: whose CPF?
        for x, y in partes_nome:
            if not _nome_valido(t.norm[x:y]):
                continue
            nome = t.nome(x, y)
            if nome:
                saida.append((Parte(nome=nome, cpf_cnpj=documento), valido))
    return saida


def _blocos_rotulados(t: _Texto, corpo: int) -> list[tuple[str, int, int]]:
    """(side, value start, value end) for every `Label:` block in the act."""
    marcas = [
        (next(k for k in ("t", "a", "c", "x") if m.group(k)), m.start(), m.end())
        for m in _ROTULO_PARTE.finditer(t.norm, corpo)
    ]
    blocos: list[tuple[str, int, int]] = []
    for i, (lado, _ini, fim) in enumerate(marcas):
        if lado == "x":
            continue
        limite = marcas[i + 1][1] if i + 1 < len(marcas) else len(t.norm)
        corte = _FIM_BLOCO.search(t.norm, fim, limite)
        blocos.append((lado, fim, corte.start() if corte else limite))
    return blocos


def _confianca_partes(achados: list[tuple[Parte, bool]], rotulado: bool) -> str:
    if not achados:
        return NENHUMA
    if rotulado and all(ok for _p, ok in achados):
        return ALTA
    return BAIXA


_NARRATIVA_ADQUIRENTE = _rx(
    r"(?:VENDID[OA]S?|VENDA|VENDEU|VENDERAM|DOAD[OA]S?|DOACAO|TRANSMITID[OA]S?)"
    r"\s+(?:(?:DO|O)\s+IMOVEL\s+)?(?:A|AO|AOS|AS|PARA)"
)


def _partes(t: _Texto, corpo: int, blocos: list[tuple[str, int, int]]):
    trans = [x for lado, a, b in blocos if lado == "t" for x in _pessoas(t, a, b)]
    adq = [x for lado, a, b in blocos if lado == "a" for x in _pessoas(t, a, b)]
    adq_rotulado = bool(adq)
    if not adq:
        for m in _NARRATIVA_ADQUIRENTE.finditer(t.norm, corpo):
            corte = _FIM_FRASE.search(t.norm, m.end())
            fim = corte.start() if corte else len(t.norm)
            achados = _pessoas(t, m.end(), fim)
            if achados:
                adq = achados[:1]
                break
    return (
        tuple(p for p, _ in trans),
        _confianca_partes(trans, True),
        tuple(p for p, _ in adq),
        _confianca_partes(adq, adq_rotulado),
    )


# ─── credor ───────────────────────────────────────────────────────────────

#: Longest phrasing first: `em garantia a favor do BANCO` must consume the whole
#: lead-in, or `EM GARANTIA A` wins and the "name" becomes `favor do BANCO`.
_CREDOR_NARRATIVA = _rx(
    r"(?:EM\s+GARANTIA\s+)?(?:EM|A)\s+FAVOR\s+D(?:O|A|E|OS|AS)"
    r"|EM\s+GARANTIA\s+(?:A|AO|AOS|DA|DO|DE)"
    r"|TENDO\s+COMO\s+CREDOR(?:A)?|AO\s+CREDOR(?:A)?|A\s+CREDORA"
)


def _credor(
    t: _Texto, corpo: int, natureza: Optional[str], blocos: list[tuple[str, int, int]]
) -> tuple[Optional[str], str]:
    if natureza not in NATUREZAS_COM_CREDOR:
        return None, NENHUMA
    for lado, a, b in blocos:
        if lado != "c":
            continue
        achados = _pessoas(t, a, b)
        if achados:
            parte, ok = achados[0]
            return parte.nome, (ALTA if ok else BAIXA)
    for m in _CREDOR_NARRATIVA.finditer(t.norm, corpo):
        inicio = m.end()
        while inicio < len(t.norm) and t.norm[inicio] == " ":
            inicio += 1
        fim = _fim_nome(t.norm, inicio, len(t.norm))
        if not _nome_valido(t.norm[inicio:fim], minimo_palavras=1):
            continue
        nome = t.nome(inicio, fim)
        if not nome:
            continue
        corte = _FIM_FRASE.search(t.norm, fim)
        _doc, ok = _documento(t.norm, fim, corte.start() if corte else len(t.norm))
        return nome, (ALTA if ok else BAIXA)
    return None, NENHUMA


# ─── instrumento ──────────────────────────────────────────────────────────

_INSTRUMENTO = _rx(
    r"ESCRITURA(?:\s+PUBLICA)?|INSTRUMENTO\s+PARTICULAR|ESCRITO\s+PARTICULAR"
    r"|CONTRATO(?!\s+SOCIAL)(?:\s+PARTICULAR)?|FORMAL\s+DE\s+PARTILHA"
    r"|CARTA\s+DE\s+(?:ARREMATACAO|ADJUDICACAO|SENTENCA)|CEDULA\s+DE\s+CREDITO|MANDADO"
    r"|CERTIDAO\s+DE\s+(?:PENHORA|INTEIRO\s+TEOR)|REQUERIMENTO|TERMO"
)
_TITULO_ROTULO = _rx(r"TITULO|FORMA\s+DO\s+TITULO")

_FIM_TIPO = re.compile(
    r",|;|\(|:|\s[-–—]\s|\.(?=\s|$)"
    r"|\s+(?:LAVRAD|DATAD|EXPEDID|EMITID|FIRMAD|CELEBRAD|PASSAD|OUTORGAD|ASSINAD|REGISTRAD"
    r"|PERANTE|NAS\s+NOTAS|NO\s+LIVRO|LIVRO|FLS?(?![A-Z])|FOLHAS?(?![A-Z])|COM\s+FORCA"
    r"|NOS\s+TERMOS|NA\s+FORMA|PEL[OA](?![A-Z])|N[OA]\s+\d|D[OA]\s+\d"
    r"|N[OA]\s+(?:CARTORIO|TABELI|OFICIO|SERVICO)|D[OA]\s+(?:CARTORIO|TABELI|OFICIO|SERVICO|JUIZO)"
    r"|EM\s+\d|AOS\s+\d|DE\s+\d|DE\s+DATA|NO?\.?\s*\d|NUMERO|SOB\s+O|EXTRAID|ENTRE(?![A-Z])"
    r"|EM\s+QUE|QUE(?![A-Z])|ONDE|FIGURA|EM\s+FAVOR|A\s+FAVOR|TENDO|FOI|FORAM|FICA"
    r"|NO\s+VALOR|PELO\s+VALOR)"
)
_CONTEXTO_INSTRUMENTO = _rx(
    r"LAVRAD[OA]|DATAD[OA]|EXPEDID[OA]|EMITID[OA]|FIRMAD[OA]|CELEBRAD[OA]|TABELI\w*|NOTAS"
)
_VERBO_DATA = re.compile(
    r"(?<![A-Z])(?:LAVRAD[OA]|DATAD[OA]|EXPEDID[OA]|EMITID[OA]|FIRMAD[OA]|CELEBRAD[OA]"
    r"|PASSAD[OA]|ASSINAD[OA]|OUTORGAD[OA])\s+(?:(?:EM|AOS|NO\s+DIA|DE)\s+)?$"
)
_DATA_COLADA = re.compile(r"^\s*,?\s*(?:DE|EM|AOS|DATAD[OA]\s+DE|DE\s+DATA\s+DE)\s+$")
_TABELIONATO = re.compile(
    r"(?<![A-Z0-9])(?:\d{1,3}\s*(?:O|A|°)?\.?\s*)?"
    r"(?:(?:TABELIONATO|TABELIAO|TABELIA)(?:\s+DE\s+NOTAS)?"
    r"(?:\s+E\s+(?:DE\s+)?PROTESTOS?(?:\s+DE\s+LETRAS\s+E\s+TITULOS)?)?"
    r"|(?:OFICIO|CARTORIO|SERVICO\s+NOTARIAL)(?:\s+D[OE]\s+\d{1,3}\s*(?:O|A|°)?\.?\s*OFICIO)?"
    r"\s+(?:DE\s+NOTAS|NOTARIAL))(?![A-Z])"
)
_CIDADE = re.compile(
    r"\s+D[AEO]S?\s+(?:(?:COMARCA|MUNICIPIO|CIDADE|DISTRITO)\s+D[AEO]\s+)?"
    r"(?P<c>[A-Z][A-Z']*(?:\s+(?:D[AEO]S?\s+)?[A-Z][A-Z']*){0,4}?)"
    r"(?=\s*(?:/|,|;|\.|\(|:|-\s*[A-Z]{2}(?![A-Z])|\s[-–—]\s|$)"
    r"|\s+(?:LIVRO|NO\s+LIVRO|FLS?|FOLHAS?|SOB|EM|AOS|E\s+REGISTRAD|REGISTRAD|PAGINAS?)(?![A-Z]))"
)
_NAO_CIDADE = frozenset({"DESTA", "NESTA", "DESSA", "NESSA", "CAPITAL", "COMARCA", "CIDADE"})
_LIVRO = re.compile(r"(?<![A-Z])LIVRO\s*(?:N[O°]?\.?\s*)?(?P<v>\d[\d.]*(?:-?[A-Z](?![A-Z]))?)")
_FOLHAS = re.compile(
    r"(?<![A-Z])(?:FLS?|FOLHAS?|PAGINAS?|PAGS?|PGS?)\.?\s*(?:N[O°]?\.?\s*)?"
    r"(?P<v>\d+(?:\s*V(?:ERSO)?(?![A-Z]))?(?:\s*(?:/|-|A|AO|E)\s*\d+(?:\s*V(?:ERSO)?(?![A-Z]))?)?)"
)
_FIM_CLAUSULA = re.compile(r"\.\s+(?=[A-Z]{2})")
_JANELA_CLAUSULA = 320


def _instrumento(
    t: _Texto, corpo: int, blocos: list[tuple[str, int, int]]
) -> tuple[Optional[Instrumento], str]:
    candidatos = list(_INSTRUMENTO.finditer(t.norm, corpo))
    if not candidatos:
        return None, NENHUMA
    escolhido = None
    rotulo = _TITULO_ROTULO.search(t.norm, corpo)
    if rotulo:
        escolhido = next((m for m in candidatos if 0 <= m.start() - rotulo.end() <= 12), None)
    if escolhido is None:
        for m in candidatos:
            janela = t.norm[m.end() : m.end() + 160]
            if _datas(janela) or _CONTEXTO_INSTRUMENTO.search(janela):
                escolhido = m
                break
    if escolhido is None:
        return None, NENHUMA

    fim_tipo_m = _FIM_TIPO.search(t.norm, escolhido.end(), min(len(t.norm), escolhido.start() + 90))
    fim_tipo = fim_tipo_m.start() if fim_tipo_m else min(len(t.norm), escolhido.start() + 90)
    tipo = t.literal(escolhido.start(), fim_tipo)

    limite = min(len(t.norm), escolhido.start() + _JANELA_CLAUSULA)
    for _lado, a, _b in blocos:
        if a > escolhido.start():
            limite = min(limite, a)
    corte = _FIM_CLAUSULA.search(t.norm, fim_tipo, limite)
    if corte:
        limite = corte.start()

    data_inst = None
    for inicio, _fim, valor in _datas(t.norm, fim_tipo, limite):
        antes = t.norm[max(fim_tipo, inicio - 30) : inicio]
        if _VERBO_DATA.search(antes) or _DATA_COLADA.match(t.norm[fim_tipo:inicio]):
            data_inst = valor
            break

    tabelionato = cidade = None
    tab = _TABELIONATO.search(t.norm, fim_tipo, limite)
    if tab:
        tabelionato = t.literal(tab.start(), tab.end())
        c = _CIDADE.match(t.norm, tab.end())
        if c and c.group("c").split()[0] not in _NAO_CIDADE:
            cidade = t.literal(c.start("c"), c.end("c"))

    livro_m = _LIVRO.search(t.norm, fim_tipo, limite)
    folhas_m = _FOLHAS.search(t.norm, fim_tipo, limite)
    instrumento = Instrumento(
        tipo=tipo,
        data=data_inst,
        tabelionato=tabelionato,
        livro=t.literal(livro_m.start("v"), livro_m.end("v")) if livro_m else None,
        folhas=t.literal(folhas_m.start("v"), folhas_m.end("v")) if folhas_m else None,
        cidade=cidade,
    )
    notarial = normalize(tipo or "").startswith("ESCRITURA")
    completo = tipo and data_inst and (tabelionato or not notarial)
    return instrumento, (ALTA if completo else BAIXA)


# ─── atos referidos ───────────────────────────────────────────────────────

_CITACAO = re.compile(
    r"(?<![A-Z0-9$])(?P<k>AV|R)(?:\s*[-.–—]\s*|\s+)(?P<n>\d{1,4})(?![\d])(?!,\d)(?!\.\d)"
    r"(?P<suf>\s*/\s*(?:M\s*[.-]?\s*)?\d+(?:\.\d+)*)?"
)
_CITACAO_VERBAL = re.compile(
    r"(?<![A-Z])(?P<k>REGISTRO|AVERBACAO)\s+(?:N[O°]?\.?|NUMERO)\s*(?P<n>\d{1,4})(?![\d,/]|\.\d)"
)
_CITACAO_ISCA_ANTES = re.compile(
    r"(?:QUADRA|LOTE|RUA|AVENIDA|UNIDADE|APARTAMENTO|APTO|BLOCO|TORRE|FICHA|LIVRO|FOLHA"
    r"|ZONA|SETOR|REGISTRO\s+ANTERIOR|TRANSCRICAO)\s*[:.]?\s*$"
)
_CITACAO_ISCA_DEPOIS = re.compile(r"^\s+DE\s+[A-Z]")


def _atos_referidos(
    t: _Texto, corpo: int, proprio: Optional[tuple[str, int]], sufixo_proprio: str
) -> tuple[tuple[AtoReferido, ...], str]:
    vistos: list[AtoReferido] = []
    verbal = False
    for m in _CITACAO.finditer(t.norm, corpo):
        antes = t.norm[max(corpo, m.start() - 24) : m.start()]
        if _CITACAO_ISCA_ANTES.search(antes) or _CITACAO_ISCA_DEPOIS.match(t.norm[m.end() :]):
            continue
        sufixo = _digitos(m.group("suf"))
        if sufixo and sufixo_proprio and sufixo != sufixo_proprio:
            continue  # an act of ANOTHER matrícula
        ref = AtoReferido(kind=m.group("k"), numero=int(m.group("n")))  # type: ignore[arg-type]
        if (ref.kind, ref.numero) != proprio and ref not in vistos:
            vistos.append(ref)
    for m in _CITACAO_VERBAL.finditer(t.norm, corpo):
        antes = t.norm[max(corpo, m.start() - 24) : m.start()]
        if _CITACAO_ISCA_ANTES.search(antes):
            continue
        kind = "R" if m.group("k") == "REGISTRO" else "AV"
        ref = AtoReferido(kind=kind, numero=int(m.group("n")))  # type: ignore[arg-type]
        if (ref.kind, ref.numero) != proprio and ref not in vistos:
            vistos.append(ref)
            verbal = True
    if not vistos:
        return (), NENHUMA
    return tuple(vistos), (BAIXA if verbal else ALTA)


# ─── public API ───────────────────────────────────────────────────────────


def extrair_detalhes_ato(texto_ato: str) -> AtoDetalhes:
    """Read one act's details. Pure and deterministic; see module docstring."""
    if not texto_ato or not texto_ato.strip():
        return AtoDetalhes()
    t = _Texto(texto_ato)
    cabecalho = _HEADER.match(t.norm)
    corpo = cabecalho.end() if cabecalho else 0
    proprio = (cabecalho.group("kind"), int(cabecalho.group("num"))) if cabecalho else None
    sufixo_proprio = _digitos(cabecalho.group("suf")) if cabecalho else ""

    natureza, natureza_conf = _natureza(t, corpo)
    data_registro, data_conf = _data_registro(t, corpo)
    valor, valor_conf = _valor(t, corpo)
    blocos = _blocos_rotulados(t, corpo)
    transmitentes, trans_conf, adquirentes, adq_conf = _partes(t, corpo, blocos)
    credor, credor_conf = _credor(t, corpo, natureza, blocos)
    instrumento, inst_conf = _instrumento(t, corpo, blocos)
    referidos, ref_conf = _atos_referidos(t, corpo, proprio, sufixo_proprio)

    return AtoDetalhes(
        natureza=natureza,
        natureza_confianca=natureza_conf,
        data_registro=data_registro,
        data_registro_confianca=data_conf,
        valor=valor,
        valor_confianca=valor_conf,
        transmitentes=transmitentes,
        transmitentes_confianca=trans_conf,
        adquirentes=adquirentes,
        adquirentes_confianca=adq_conf,
        credor=credor,
        credor_confianca=credor_conf,
        instrumento=instrumento,
        instrumento_confianca=inst_conf,
        atos_referidos=referidos,
        atos_referidos_confianca=ref_conf,
    )


_FEMININOS = frozenset({"ESCRITURA", "CARTA", "CEDULA", "CERTIDAO"})
_VERBOS_DATA = {
    "ESCRITURA": "lavrada em",
    "FORMAL": "expedido em",
    "CARTA": "expedida em",
    "MANDADO": "expedido em",
    "CERTIDAO": "expedida em",
    "CEDULA": "emitida em",
}


def frase_titulo_aquisitivo(
    instrumento: Optional[Instrumento], *, kind: str, numero: int
) -> Optional[str]:
    """The paraphrased título aquisitivo a contract states, built ONLY from
    what the act says (e.g. `adquirido por Escritura Pública de Venda e
    Compra lavrada em 12/03/2020 no 2º Tabelionato de Notas de Cotia, Livro
    100, fls. 20, registrada sob o R-3`). Missing pieces are omitted, never
    invented; None when there is no instrument type to name.
    """
    if kind not in ("R", "AV"):
        raise ValueError(f"kind deve ser 'R' ou 'AV', recebeu {kind!r}")
    if instrumento is None or not (instrumento.tipo or "").strip():
        return None
    tipo = instrumento.tipo.strip()
    primeira = normalize(tipo).split()[0]
    sufixo = "a" if primeira in _FEMININOS else "o"
    verbo = _VERBOS_DATA.get(primeira, f"datad{sufixo} de")

    cabeca = f"adquirido por {tipo}"
    if instrumento.data:
        cabeca += f" {verbo} {instrumento.data:%d/%m/%Y}"
    if instrumento.tabelionato:
        cabeca += f" no {instrumento.tabelionato.strip()}"
        if instrumento.cidade:
            cabeca += f" de {instrumento.cidade.strip()}"
    partes = [cabeca]
    if not instrumento.tabelionato and instrumento.cidade:
        partes.append(f"em {instrumento.cidade.strip()}")
    if instrumento.livro:
        partes.append(f"Livro {instrumento.livro.strip()}")
    if instrumento.folhas:
        partes.append(f"fls. {instrumento.folhas.strip()}")
    if kind == "R":
        partes.append(f"registrad{sufixo} sob o R-{numero}")
    else:
        partes.append(f"averbad{sufixo} sob a AV-{numero}")
    return ", ".join(partes)


def parse_detalhes_json(data: dict[str, Any]) -> AtoDetalhes:
    """Inverse of `AtoDetalhes.to_json` — for a caller holding stored rows."""
    bruto_data = data.get("data_registro")
    bruto_valor = data.get("valor")
    return AtoDetalhes(
        natureza=data.get("natureza"),
        natureza_confianca=data.get("natureza_confianca") or NENHUMA,
        data_registro=date.fromisoformat(bruto_data) if isinstance(bruto_data, str) and bruto_data else bruto_data,
        data_registro_confianca=data.get("data_registro_confianca") or NENHUMA,
        valor=Decimal(str(bruto_valor)) if bruto_valor is not None else None,
        valor_confianca=data.get("valor_confianca") or NENHUMA,
        transmitentes=tuple(Parte.from_json(p) for p in data.get("transmitentes") or ()),
        transmitentes_confianca=data.get("transmitentes_confianca") or NENHUMA,
        adquirentes=tuple(Parte.from_json(p) for p in data.get("adquirentes") or ()),
        adquirentes_confianca=data.get("adquirentes_confianca") or NENHUMA,
        credor=data.get("credor"),
        credor_confianca=data.get("credor_confianca") or NENHUMA,
        instrumento=Instrumento.from_json(data.get("instrumento")),
        instrumento_confianca=data.get("instrumento_confianca") or NENHUMA,
        atos_referidos=tuple(
            AtoReferido(kind=a["kind"], numero=int(a["numero"]))
            for a in data.get("atos_referidos") or ()
        ),
        atos_referidos_confianca=data.get("atos_referidos_confianca") or NENHUMA,
    )


__all__ = [
    "ALTA",
    "BAIXA",
    "CONFIANCAS",
    "NATUREZAS_ATO",
    "NATUREZAS_COM_CREDOR",
    "NATUREZAS_TRANSFERENCIA",
    "NENHUMA",
    "AtoDetalhes",
    "AtoReferido",
    "Instrumento",
    "NaturezaAto",
    "Parte",
    "cpf_cnpj_valido",
    "extrair_detalhes_ato",
    "formatar_cpf_cnpj",
    "frase_titulo_aquisitivo",
    "parse_detalhes_json",
]
