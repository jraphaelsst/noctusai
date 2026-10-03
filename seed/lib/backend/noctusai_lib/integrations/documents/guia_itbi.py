"""Guia de ITBI (Imposto de Transmissão de Bens Imóveis) → typed fields.

Protocol + Fake + Real + factory, sibling of `cartao_cnpj.py` — same ladder
(`ladder.py`), same confidence vocabulary, same "not a text layer ⇒ not
alta" tempering. Usually a 1-page municipal scan.

🔴 THE LAYOUT VARIES BY MUNICÍPIO — LABELS ARE A SYNONYM TABLE, NEVER A
POSITION
-------------------------------------------------------------------------
Every município issues its own guia, and the label wording for the SAME
fact differs between them ("VALOR DA TRANSAÇÃO" / "VALOR DECLARADO" /
"VALOR DE TRANSMISSÃO" for the same field). So `_ROTULOS` below maps each
canonical field name to a TUPLE of synonym spellings — extending coverage
for a new município is adding one string to one tuple, never a new parser.
`_campo` tries every synonym in order and stops at the first match.

🔴 THIS IS A CROSS-CHECK DOCUMENT, NOT AN AUTHORITATIVE ONE (owner H2)
-------------------------------------------------------------------------
`valor_transacao` here is one of THREE documents `campo_conflitos` compares
against `atendimento_negociacao.valor_negociado` — the fill-empty/conflict
DECISION lives in the SW wiring layer, not here. This module only reads.

🔴 `valor_venal` / `base_calculo` / `valor_financiado_sfh` ARE NEVER MAPPED
INTO `atendimento_negociacao.valor_negociado`
-----------------------------------------------------------------------------
Three distinct, easily-confused money boxes on the SAME guia — the SW field
map (§B of the negociação/financiamento extraction contract) calls this out
explicitly as a documented trap. This module keeps them as three separate
typed fields; nothing here decides which one, if any, feeds a DB column.
The one composition: on a guide that prints NO transaction value, only
its two parts ("à vista" + financiado), `valor_transacao` is their SUM —
see `_derivar_valor_transacao`. `valor_financiado_sfh` alone still never
stands in for the price.

🔴 `[ILEGÍVEL]` / `[EM BRANCO]` ARE `None`, NEVER THE LITERAL TOKEN
----------------------------------------------------------------------
Same convention as `cartao_cnpj.py`'s masked-box handling: the prompt asks
the model to say so explicitly rather than invent a plausible value, and the
parser folds either token to `None` while the box's own label still lands
in `rotulos` so a human can see the field WAS present and unreadable, not
silently missing from the layout.

🔴 MONEY FIELDS NEVER REACH `alta` HERE, EVEN OFF A REAL TEXT LAYER
----------------------------------------------------------------------
Unlike this module's OTHER fields (which follow `_temper`'s usual
"alta only off TEXT_LAYER" rule), every money field goes through
`_confianca_valor` instead: capped at `baixa` off vision REGARDLESS of
source, raised to `media` only when `money.ler_valor`'s own extenso
cross-check agrees. See the negociação/financiamento extraction contract
§D.5: "Money precision comes from deterministic checks... never from a
model's self-reported confidence" — `alta` on a money field would be
exactly that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.integrations.documents.caixa_rotulada import (
    campo as _caixa_campo,
    data_br as _caixa_data_br,
    linhas_unidas,
    localizar,
    percentual as _caixa_percentual,
    pessoas_com_cpf,
    temperar_alta_por_fonte,
    valor_em_coluna,
)
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.money import ValorLido, ler_valor
from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

# ─── transcription prompt (rung 2) ────────────────────────────────────────

DOCUMENT_PROMPT_GUIA_ITBI = (
    "Transcreva o texto EXATO desta Guia de ITBI (Imposto de Transmissão de "
    "Bens Imóveis), sem corrigir, resumir ou traduzir o CONTEÚDO de nenhum "
    "campo. O documento imprime cada campo como um RÓTULO seguido de um "
    "valor — junte cada rótulo ao seu valor em UMA ÚNICA LINHA no formato "
    "RÓTULO: valor, o rótulo exatamente como impresso, seguido de dois "
    "pontos (mesmo que o documento não os imprima) e o valor impresso "
    "naquele campo. Uma linha por campo. Para compradores e vendedores, "
    "liste cada pessoa como 'Nome do titular - CPF: 000.000.000-00', "
    "separando duas ou mais pessoas do MESMO campo com ponto e vírgula "
    "(;), na mesma linha do rótulo (COMPRADOR ou VENDEDOR). Se o campo "
    "estiver ilegível, escreva [ILEGÍVEL]; se estiver em branco, escreva "
    "[EM BRANCO]. Transcreva também qualquer valor por extenso impresso "
    "entre parênteses logo após um valor monetário."
)

_ILEGIVEL = "[ILEGÍVEL]"
_EM_BRANCO = "[EM BRANCO]"


def _temper(confidence: ExtractionConfidence, source: TextSource) -> ExtractionConfidence:
    """`alta` is reachable only off a PDF's own text layer — shared with
    `cartao_cnpj`/`financiamento_imobiliario` via
    `caixa_rotulada.temperar_alta_por_fonte` (identical semantics in all
    three). Applies to every field EXCEPT the money ones — see
    `_confianca_valor`."""
    return temperar_alta_por_fonte(confidence, source)


def _confianca_valor(lido: ValorLido, source: TextSource) -> ExtractionConfidence:
    """Money-field confidence — never `alta`, `media` only via the
    extenso cross-check. See the module header's money-fields note."""
    if lido.valor is None:
        return ExtractionConfidence.NENHUMA
    if source is TextSource.TEXT_LAYER and lido.extenso_confere is not False:
        # An exact digit read off the PDF's own text layer is trustworthy
        # on its own; a DISAGREEING extenso on the SAME text layer is a
        # document-authoring inconsistency worth a human's eyes, so that
        # one case still caps at `lido.confianca` (baixa) rather than
        # promoting past it.
        return ExtractionConfidence.ALTA
    return (
        ExtractionConfidence.MEDIA
        if lido.extenso_confere
        else ExtractionConfidence.BAIXA
    )


# ─── label synonym table (as data — see the module header) ────────────────

#: `campo name -> (synonym label, ...)`, each already accent-stripped/upper
#: (matches `text.strip_accents_upper`'s output, same convention
#: `cartao_cnpj._ROTULOS` uses). Extend for a new município by adding one
#: string to the field's own tuple — never a new code path.
_ROTULOS: dict[str, tuple[str, ...]] = {
    "valor_transacao": (
        # Cotia's guide (measured on 5 real guides, 2026-10-03): the deed's
        # declared price, printed under the "instrumento" label with the
        # market-value gloss — NOT Carapicuíba's "(à vista)" cash part.
        "VALOR DO INSTRUMENTO (VALOR VENAL DE MERCADO)",
        "VALOR DA TRANSACAO",
        "VALOR DECLARADO",
        "VALOR DE TRANSMISSAO",
        "VALOR DO NEGOCIO",
    ),
    "valor_venal": ("VALOR VENAL", "VALOR VENAL DE REFERENCIA"),
    # "BASE CALCULO" (no "DE"): measured on a real guide, deal 883 (2026-09-25).
    "base_calculo": ("BASE DE CALCULO", "BASE DE CALCULO DO ITBI", "BASE CALCULO"),
    "valor_financiado_sfh": (
        "VALOR FINANCIADO SFH",
        "VALOR FINANCIADO PELO SFH",
        "PARCELA FINANCIADA SFH",
        # Bare "Valor Financiado" (883 guide): equals the contract's
        # financiamento parcela exactly — measured, not assumed.
        "VALOR FINANCIADO",
    ),
    # The cash (non-financed) part of the price. Carapicuíba's guide (883,
    # 2026-09-28) prints "Valor do Instrumento (à vista)" + "Valor
    # Financiado" and NO transaction-value box at all — see
    # `_derivar_valor_transacao`.
    "valor_a_vista": (
        "VALOR DO INSTRUMENTO (A VISTA)",
        "VALOR DO INSTRUMENTO",
        "VALOR A VISTA",
    ),
    "aliquota_pct": ("ALIQUOTA", "ALIQUOTA APLICADA"),
    # "(=)Vr. Imposto R$" on the 883 guide; "VL." is the other common abbrev.
    "valor_itbi": ("VALOR DO ITBI", "VALOR DO IMPOSTO", "TOTAL A PAGAR",
                   "VR. IMPOSTO", "VL. IMPOSTO"),
    "vencimento": ("DATA DE VENCIMENTO", "VENCIMENTO"),
    "inscricao_imobiliaria": (
        "INSCRICAO IMOBILIARIA",
        "INSCRICAO CADASTRAL",
        "CADASTRO IMOBILIARIO",
    ),
    "numero_matricula": ("MATRICULA", "NUMERO DA MATRICULA", "MATRICULA DO IMOVEL"),
    "compradores": ("COMPRADOR", "COMPRADORES", "ADQUIRENTE", "ADQUIRENTES"),
    "vendedores": ("VENDEDOR", "VENDEDORES", "TRANSMITENTE", "TRANSMITENTES"),
    "municipio": ("MUNICIPIO", "MUNICIPIO DO IMOVEL"),
}

#: The field names that hold a money value — routed through `money.ler_valor`
#: and `_confianca_valor` rather than the plain string/date parsers below.
_CAMPOS_MONETARIOS: tuple[str, ...] = (
    "valor_transacao", "valor_venal", "base_calculo", "valor_financiado_sfh",
    "valor_a_vista", "valor_itbi",
)


def _derivar_valor_transacao(
    a_vista: Optional[Decimal],
    financiado: Optional[Decimal],
    base_calculo: Optional[Decimal],
) -> tuple[Optional[Decimal], ExtractionConfidence]:
    """The transaction value of a guide that prints only its two PARTS.

    Some municípios (Carapicuíba, measured on deal 883) print the price
    split into "à vista" + "financiado" and no transaction-value box. The
    price is then their sum — measured on 883: the sum equals the signed
    contract's price, and the guide's own base de cálculo. Derived, never
    read, so never above `media`: `media` when the base de cálculo
    corroborates the sum, `baixa` otherwise (the base may legitimately be a
    higher valor venal). Both parts are required — one alone is not a price.
    """
    if a_vista is None or financiado is None:
        return None, ExtractionConfidence.NENHUMA
    soma = a_vista + financiado
    if base_calculo is not None and base_calculo == soma:
        return soma, ExtractionConfidence.MEDIA
    return soma, ExtractionConfidence.BAIXA


def _todos_rotulos() -> tuple[str, ...]:
    return tuple(r for sinonimos in _ROTULOS.values() for r in sinonimos)


def _campo(
    linhas: list[str], sinonimos: Sequence[str], *, todos_rotulos: Sequence[str]
) -> tuple[Optional[str], Optional[str], bool]:
    """`(valor, rótulo encontrado, mascarado)` for the FIRST admissible
    synonym in `sinonimos` that matches a box in `linhas` — via the shared
    `caixa_rotulada.campo`, common to `cartao_cnpj`/
    `financiamento_imobiliario` now (the other-field-longer-label guard
    this module never had, every-occurrence-per-line scanning,
    longest-synonym-first ordering, and word-boundary matching all live
    there — see that module's header for the full drift history this
    fixes). `mascarado` is `True` only when the box's own value was
    `[ILEGÍVEL]`/`[EM BRANCO]` (see the module header) — distinct from
    "never found"."""
    return _caixa_campo(
        linhas, sinonimos, todos_rotulos=todos_rotulos, valores_mascarados=(_ILEGIVEL, _EM_BRANCO)
    )


def _eh_rotulo_monetario(linha: str) -> bool:
    """A money box's label line, as printed: "VALOR ..." or any money
    synonym of `_ROTULOS` — the label side of `valor_em_coluna`."""
    if linha.startswith("VALOR"):
        return True
    return any(
        r in linha for c in _CAMPOS_MONETARIOS for r in _ROTULOS[c]
    )


def _eh_valor_monetario(linha: str) -> bool:
    """An `R$` amount `ler_valor` reads — the value side of
    `valor_em_coluna`. The `R$` is required: a columnar dump also carries
    areas/fractions ("123,45") that `ler_valor` would read as money."""
    return "R$" in linha and ler_valor(linha).valor is not None


def _valor_monetario_por_layout(
    linhas: list[str],
    unidas: list[str],
    sinonimos: Sequence[str],
    todos: Sequence[str],
    valor: Optional[str],
    achado: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """A money box's value when the text layer's LAYOUT defeats the
    line-by-line box reader. Two shapes, both measured on real guides
    (2026-10-03 — every text-layer guide in the corpus read 'sem_dados'
    before this):

    - COLUMNAR (Cotia): the row "Valor Venal IPTU | Valor do Instrumento"
      is dumped as a label column followed by a value column, so the line
      after a label is ANOTHER box's value (an area, "123,45", which
      `ler_valor` happily reads as money). The columnar pairing
      (`caixa_rotulada.valor_em_coluna`, money labels ↔ `R$` amounts, equal
      counts only) takes precedence over the next-line fallback; a dump it
      cannot pair reads `None` (never the first column's value).
    - WRAPPED PROSE (Embu das Artes): "... E VALOR DA" / "TRANSAÇÃO: R$
      ..." — the label straddles a line break, so no line carries it; the
      joined-pairs pass (`caixa_rotulada.linhas_unidas`) finds it. Only
      tried when the line-by-line pass never located the label at all."""
    loc = localizar(linhas, sinonimos, todos_rotulos=todos)
    if loc is not None:
        valor_coluna, em_coluna = valor_em_coluna(
            linhas,
            loc[0],
            eh_rotulo_do_tipo=_eh_rotulo_monetario,
            eh_valor_do_tipo=_eh_valor_monetario,
        )
        if valor_coluna is not None:
            return valor_coluna, loc[2]
        if em_coluna:
            # A columnar dump that could not be paired unambiguously: the
            # next-line read would hand back the FIRST column's value.
            return None, loc[2]
        return valor, achado
    valor_unido, achado_unido, _ = _campo(unidas, sinonimos, todos_rotulos=todos)
    if achado_unido is not None:
        return valor_unido, achado_unido
    return valor, achado


def _data_br(txt: Optional[str]) -> Optional[date]:
    """Shared with `cartao_cnpj`/`financiamento_imobiliario` — identical
    semantics — via `caixa_rotulada.data_br`."""
    return _caixa_data_br(txt)


def _percentual(txt: Optional[str]) -> Optional[Decimal]:
    """Shared with `financiamento_imobiliario` — identical semantics — via
    `caixa_rotulada.percentual`."""
    return _caixa_percentual(txt)


@dataclass(frozen=True)
class PessoaItbi:
    """One comprador/vendedor named on the guia — CPF check-digit verified,
    never corrected (see `cpf.is_valid`'s own contract)."""

    nome: Optional[str] = None
    cpf: Optional[str] = None
    cpf_valido: bool = False


def _pessoas(valor: Optional[str]) -> tuple[PessoaItbi, ...]:
    """Shared parsing with `financiamento_imobiliario._pessoas` via
    `caixa_rotulada.pessoas_com_cpf` — this module's own `PessoaItbi` type
    is unchanged, only the `;`-separated "Nome - CPF: ..." parsing itself
    is shared."""
    return pessoas_com_cpf(valor, PessoaItbi)


#: Cotia's contribuinte block, text layer: three label lines then their
#: three values in the same order (name, address, CPF) — measured on 5
#: real guides, 2026-10-03. The contribuinte IS the comprador there
#: ("1 - Contribuinte(Comprador)").
_BLOCO_CONTRIBUINTE: tuple[str, ...] = ("NOME:", "ENDERECO:", "CGC/CPF:")
_CPF_LINHA_RE = re.compile(r"^(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})$")


def _contribuinte_colunar(linhas: list[str]) -> tuple[PessoaItbi, ...]:
    """The comprador of a guide whose text layer dumps its contribuinte
    block as a column (see `_BLOCO_CONTRIBUINTE`). Only when the block is
    headed as the COMPRADOR's and the third value is CPF-shaped — never a
    guess at which line is which."""
    n = len(_BLOCO_CONTRIBUINTE)
    for i in range(len(linhas) - 2 * n + 1):
        if tuple(linhas[i : i + n]) != _BLOCO_CONTRIBUINTE:
            continue
        if not any("COMPRADOR" in linha for linha in linhas[max(0, i - 2) : i]):
            continue
        nome, cpf_linha = linhas[i + n], linhas[i + n + 2]
        if not _CPF_LINHA_RE.match(cpf_linha):
            continue
        return _pessoas(f"{nome} - CPF: {cpf_linha}")
    return ()


def _pessoas_por_layout(
    linhas: list[str],
    unidas: list[str],
    campo: str,
    todos: Sequence[str],
    brutos: Mapping[str, Optional[str]],
) -> tuple[PessoaItbi, ...]:
    """A people field, robust to the same text-layer layouts the money
    fields meet (see `_valor_monetario_por_layout`): the box read as-is;
    the joined-pairs read (a text layer wraps "FULANO - CPF: ... E" /
    "BELTRANA - CPF: ..." mid-list, Embu das Artes) — whichever names MORE
    people; and, for the comprador only, Cotia's columnar contribuinte
    block when neither found anyone.

    NOC-REMEDIATE[guia-itbi-pessoas-vision]: the 3 vision-read guides of
    the corpus name their people in shapes none of these read — a
    "CONTRIBUINTE: A e B" line paired with a separate "CPF/CNPJ: x / y"
    line, or "ADQUIRENTE: nome - CPF/CNPJ: [EM BRANCO]" (name only) — so
    SW's belongs-check stays `pertencimento_nao_verificado` for them (a
    pending conflict, never a wrong fill); the label-pair reader
    `financiamento_imobiliario._proponentes` already does for the proposta
    is the shape to share here. — 2026-10-03"""
    sinonimos = tuple(strip_accents_upper(s) for s in _ROTULOS[campo])
    pessoas = _pessoas(brutos[campo])
    loc = localizar(linhas, sinonimos, todos_rotulos=todos)
    if loc is not None and loc[0] < len(unidas):
        # The pair STARTING at the label's own line — `unidas[i]` is
        # `linhas[i] + " " + linhas[i + 1]`, i.e. the label's line plus its
        # continuation (the pair ending at it would repeat the label's
        # line and still cut the list).
        valor_unido, _, _ = _campo([unidas[loc[0]]], sinonimos, todos_rotulos=todos)
        pessoas_unidas = _pessoas(valor_unido)
        if len(pessoas_unidas) > len(pessoas):
            pessoas = pessoas_unidas
    if not pessoas and campo == "compradores":
        pessoas = _contribuinte_colunar(linhas)
    return pessoas


# ─── public value object ───────────────────────────────────────────────────


@dataclass(frozen=True)
class GuiaItbiFields:
    """What one Guia de ITBI yielded. Every field is READING-ONLY from this
    module's own point of view — which, if any, feeds a DB column is a
    decision the SW wiring layer makes (see the module header)."""

    valor_transacao: Optional[Decimal] = None
    valor_venal: Optional[Decimal] = None
    base_calculo: Optional[Decimal] = None
    valor_financiado_sfh: Optional[Decimal] = None
    valor_a_vista: Optional[Decimal] = None
    aliquota_pct: Optional[Decimal] = None
    valor_itbi: Optional[Decimal] = None
    vencimento: Optional[date] = None
    inscricao_imobiliaria: Optional[str] = None
    numero_matricula: Optional[str] = None
    compradores: tuple[PessoaItbi, ...] = ()
    vendedores: tuple[PessoaItbi, ...] = ()
    municipio: Optional[str] = None
    confiancas: Mapping[str, ExtractionConfidence] = field(default_factory=dict)
    rotulos: Mapping[str, Optional[str]] = field(default_factory=dict)
    source: TextSource = TextSource.NENHUMA
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None


# ─── pure parser ────────────────────────────────────────────────────────


def parse_guia_itbi(text: str, source: TextSource) -> GuiaItbiFields:
    """Text (already ladder-read) → `GuiaItbiFields`. Pure, never raises."""
    todos = _todos_rotulos()
    linhas = normalize_lines(text or "")
    todos_norm = tuple(strip_accents_upper(r) for r in todos)

    confiancas: dict[str, ExtractionConfidence] = {c: ExtractionConfidence.NENHUMA for c in _ROTULOS}
    rotulos: dict[str, Optional[str]] = {c: None for c in _ROTULOS}
    brutos: dict[str, Optional[str]] = {}

    unidas = linhas_unidas(linhas)
    for campo, sinonimos in _ROTULOS.items():
        sinonimos_norm = tuple(strip_accents_upper(s) for s in sinonimos)
        valor, achado, _mascarado = _campo(linhas, sinonimos_norm, todos_rotulos=todos_norm)
        if campo in _CAMPOS_MONETARIOS:
            valor, achado = _valor_monetario_por_layout(
                linhas, unidas, sinonimos_norm, todos_norm, valor, achado
            )
        brutos[campo] = valor
        rotulos[campo] = achado
        if valor is not None:
            confiancas[campo] = ExtractionConfidence.ALTA

    lidos: dict[str, ValorLido] = {}
    for campo in _CAMPOS_MONETARIOS:
        lidos[campo] = ler_valor(brutos[campo] or "")

    avisos: list[str] = []

    aliquota_pct = _percentual(brutos["aliquota_pct"])
    if brutos["aliquota_pct"] and aliquota_pct is None:
        confiancas["aliquota_pct"] = ExtractionConfidence.NENHUMA
    elif aliquota_pct is not None and not (Decimal("0") < aliquota_pct <= Decimal("10")):
        avisos.append("aliquota_fora_da_faixa")
        aliquota_pct = None
        confiancas["aliquota_pct"] = ExtractionConfidence.NENHUMA
    elif aliquota_pct is not None:
        confiancas["aliquota_pct"] = _temper(ExtractionConfidence.ALTA, source)

    valor_itbi = lidos["valor_itbi"].valor
    base_calculo = lidos["base_calculo"].valor
    if (
        valor_itbi is not None
        and base_calculo is not None
        and aliquota_pct is not None
    ):
        esperado = (base_calculo * aliquota_pct / Decimal("100")).quantize(Decimal("0.01"))
        if abs(valor_itbi - esperado) > Decimal("1.00"):
            avisos.append("itbi_soma_divergente")
            valor_itbi = None

    vencimento = _data_br(brutos["vencimento"])
    if brutos["vencimento"] and vencimento is None:
        confiancas["vencimento"] = ExtractionConfidence.NENHUMA
    elif vencimento is not None:
        confiancas["vencimento"] = _temper(ExtractionConfidence.ALTA, source)

    compradores = _pessoas_por_layout(linhas, unidas, "compradores", todos_norm, brutos)
    vendedores = _pessoas_por_layout(linhas, unidas, "vendedores", todos_norm, brutos)
    for campo, pessoas in (("compradores", compradores), ("vendedores", vendedores)):
        if not pessoas:
            confiancas[campo] = ExtractionConfidence.NENHUMA
        elif all(p.cpf_valido for p in pessoas):
            confiancas[campo] = _temper(ExtractionConfidence.ALTA, source)
        else:
            confiancas[campo] = ExtractionConfidence.BAIXA
            avisos.append(f"{campo}_cpf_digito_invalido")

    for campo in ("inscricao_imobiliaria", "numero_matricula", "municipio"):
        if brutos[campo] is not None:
            confiancas[campo] = _temper(ExtractionConfidence.ALTA, source)

    for campo in _CAMPOS_MONETARIOS:
        lido = lidos[campo]
        # `valor_itbi` may have been nulled above by the arithmetic
        # invariant — its confidence must follow the FINAL value, not
        # `ler_valor`'s own (pre-nulling) reading, or a nulled field would
        # still report a non-`nenhuma` confidence.
        valor_final = valor_itbi if campo == "valor_itbi" else lido.valor
        confiancas[campo] = (
            ExtractionConfidence.NENHUMA
            if valor_final is None
            else _confianca_valor(lido, source)
        )

    valor_transacao = lidos["valor_transacao"].valor
    if valor_transacao is None:
        valor_transacao, conf_derivada = _derivar_valor_transacao(
            lidos["valor_a_vista"].valor, lidos["valor_financiado_sfh"].valor, base_calculo,
        )
        if valor_transacao is not None:
            confiancas["valor_transacao"] = conf_derivada
            rotulos["valor_transacao"] = (
                f"{rotulos['valor_a_vista']} + {rotulos['valor_financiado_sfh']}"
            )
            avisos.append("valor_transacao_derivado")

    return GuiaItbiFields(
        valor_transacao=valor_transacao,
        valor_venal=lidos["valor_venal"].valor,
        base_calculo=base_calculo,
        valor_financiado_sfh=lidos["valor_financiado_sfh"].valor,
        valor_a_vista=lidos["valor_a_vista"].valor,
        aliquota_pct=aliquota_pct,
        valor_itbi=valor_itbi,
        vencimento=vencimento,
        inscricao_imobiliaria=brutos["inscricao_imobiliaria"],
        numero_matricula=brutos["numero_matricula"],
        compradores=compradores,
        vendedores=vendedores,
        municipio=brutos["municipio"],
        confiancas=confiancas,
        rotulos=rotulos,
        source=source,
        aviso=",".join(avisos) if avisos else None,
    )


# ─── Protocol + Fake + Real + factory ──────────────────────────────────────


@runtime_checkable
class GuiaItbiExtractor(Protocol):
    """Bytes + mimetype → a Guia de ITBI's typed fields.

    Implementations MUST NOT raise for an unreadable/corrupt document — they
    return `GuiaItbiFields` with `error` set."""

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> GuiaItbiFields:
        ...


class FakeGuiaItbiExtractor:
    """Deterministic extractor — the dev/test default.

    Pass `result=` to script a specific outcome (a divergent ITBI sum, an
    invalid CPF, a failure) — same convention as `FakeCartaoCnpjExtractor`.
    """

    def __init__(self, result: Optional[GuiaItbiFields] = None) -> None:
        self._result = result

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> GuiaItbiFields:
        if self._result is not None:
            return self._result
        if not content:
            return GuiaItbiFields(error="empty_document", error_message="no bytes to read")
        campos = tuple(_ROTULOS)
        compradores = (PessoaItbi(nome="COMPRADOR FAKE SINTETICO", cpf="412.954.238-98", cpf_valido=True),)
        vendedores = (PessoaItbi(nome="VENDEDOR FAKE SINTETICO", cpf="412.954.238-98", cpf_valido=True),)
        return GuiaItbiFields(
            valor_transacao=Decimal("350000.00"),
            valor_venal=Decimal("300000.00"),
            base_calculo=Decimal("350000.00"),
            valor_financiado_sfh=None,
            aliquota_pct=Decimal("2"),
            valor_itbi=Decimal("7000.00"),
            vencimento=date(2026, 12, 31),
            inscricao_imobiliaria="99.999.999-9",
            numero_matricula="99.999",
            compradores=compradores,
            vendedores=vendedores,
            municipio="SAO PAULO FAKE",
            confiancas={campo: ExtractionConfidence.ALTA for campo in campos},
            rotulos={campo: _ROTULOS[campo][0] for campo in campos},
            source=TextSource.TEXT_LAYER,
        )


class LadderGuiaItbiExtractor:
    """Text-layer-first, vision-second Guia de ITBI reader.

    Construct via `make_guia_itbi_extractor(real=True)`."""

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        resolver=None,
        provider: Optional[str] = None,
    ) -> None:
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=DOCUMENT_PROMPT_GUIA_ITBI,
            resolver=resolver,
            provider=provider,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> GuiaItbiFields:
        if not content:
            return GuiaItbiFields(error="empty_document", error_message="no bytes to read")

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return GuiaItbiFields(source=source, error=err[0], error_message=err[1])
        if not text.strip():
            return GuiaItbiFields(source=source)

        return parse_guia_itbi(text, source)


def make_guia_itbi_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> GuiaItbiExtractor:
    """Return a Guia de ITBI extractor. Fake-by-default."""
    if not real:
        return FakeGuiaItbiExtractor()
    return LadderGuiaItbiExtractor(org_id=org_id, provider=provider)


__all__ = [
    "DOCUMENT_PROMPT_GUIA_ITBI",
    "FakeGuiaItbiExtractor",
    "GuiaItbiExtractor",
    "GuiaItbiFields",
    "LadderGuiaItbiExtractor",
    "PessoaItbi",
    "make_guia_itbi_extractor",
    "parse_guia_itbi",
]
