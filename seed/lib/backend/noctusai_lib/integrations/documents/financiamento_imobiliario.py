"""Financing contract + bank proposta → typed fields, ONE module, TWO
readers sharing ONE Quadro Resumo vocabulary.

Protocol + Fake + Real + factory, sibling of `guia_itbi.py`/`cartao_cnpj.py`
— same confidence vocabulary, same "not a text layer ⇒ not alta" tempering
for ordinary fields, and the SAME money-field tempering `guia_itbi.py`
introduces (never `alta` off vision; `media` only via a deterministic
check — here EITHER the extenso cross-check `money.ler_valor` already
does, OR this module's own Quadro-sum arithmetic).

🔴 WHY ONE MODULE, TWO READERS
--------------------------------
`contrato_financiamento` (a 25-page, image-only bank contract) and
`proposta_financiamento` (a single JPG/photo of a bank's proposal) print
the SAME "Quadro Resumo" fact set — valor de compra e venda, valor
financiado, FGTS, prazo, taxas, sistema de amortização — under the SAME
label vocabulary, because both come from the same bank's own template
family. `parse_financiamento_imobiliario` is that ONE shared vocabulary
and parser; `LadderContratoFinanciamentoExtractor` and
`LadderPropostaFinanciamentoExtractor` differ only in HOW they get text in
front of it — one paginates a long document, the other reads one image.

🔴 PAGE TARGETING: EVERY PAGE, PAGE BY PAGE (owner mandate 2026-09-28)
-------------------------------------------------------------------
`LadderContratoFinanciamentoExtractor` reads the WHOLE contract in one
`documents.transcription.DocumentTranscriber.transcribe(paginas=None)`
call — `LadderDocumentTranscriber` already makes one vision call per page
needing it, so this is page-by-page, not a batch — then locates the Quadro
Resumo wherever it printed it. Capped only by the transcriber's own
`MAX_VISION_PAGES` (40) safety ceiling, which fails LOUDLY
(`too_many_vision_pages`) rather than truncating silently.

🔴 SUPERSEDED (through 2026-09-27): a deterministic two-pass 4-page window
(`1..4`, then `5..8`, never more than 8 vision pages total) that returned
`error='quadro_resumo_nao_encontrado'` for a Quadro sitting on page 9+ of a
longer contract — and never read those later pages at all, Quadro or not.
Replaced once the owner's "every page, no cost cap" mandate made the
cost/coverage trade-off that window existed for the wrong call.

🔴 THE DPS TRIPWIRE — THIS MODULE NEVER PERSISTS THAT TEXT
----------------------------------------------------------------
A signed "Declaração Pessoal de Saúde" (a health questionnaire, LGPD art.
11 sensitive data) can end up misfiled into a financing-document slot. If
the read text carries a DPS marker, `parse_financiamento_imobiliario`
returns IMMEDIATELY with `error='documento_sensivel_dps'` and NO other
fields — no partial reading, no text retained anywhere in the returned
value. Both readers share this because both share the parser.

🔴 EVIDENCE IS ONE BANK (ITAÚ)
--------------------------------
The label vocabulary and `_BANCOS` code table below are bank-AGNOSTIC by
construction (a synonym table, same shape as `guia_itbi._ROTULOS`), but
only Itaú (código 341) has been measured against a real document. Every
other bank's entry here is FEBRABAN's own published code, not a
calibrated layout — extending coverage for a bank whose real layout has
been seen is adding synonyms to its field, same as `guia_itbi.py`.

🔴 `conta_credito_vendedor` IS PARSED, NOT LEFT AS RAW TEXT (owner H5)
---------------------------------------------------------------------------
The Quadro's own "conta de crédito do vendedor" box is read as STRUCTURED
fields (bank name/code, agência, conta, titular CPF) — the owner approved
using it to fill a favorecido (matched to a vendedor by CPF) and to
auto-create an `agentes_financeiros` row (H7), both of which need the bank
CODE, not a free-text box.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.integrations.documents.caixa_rotulada import (
    campo as _caixa_campo,
    data_br as _caixa_data_br,
    cpfs_em,
    limpar_nome,
    parear_nomes_cpfs,
    percentual as _caixa_percentual,
    pessoas_com_cpf,
    separar_nomes,
    temperar_alta_por_fonte,
)
from noctusai_lib.integrations.documents.cpf import format_cpf, is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.money import ValorLido, ler_valor
from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper
from noctusai_lib.integrations.documents.transcription import (
    DocumentTranscriber,
    Transcription,
    make_document_transcriber,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

# ─── transcription prompt (rung 2), shared by both readers ───────────────

DOCUMENT_PROMPT_FINANCIAMENTO = (
    "Transcreva o texto EXATO deste documento de financiamento imobiliário "
    "(contrato de financiamento bancário ou proposta de financiamento), sem "
    "corrigir, resumir ou traduzir o CONTEÚDO de nenhum campo. O documento "
    "imprime cada campo como um RÓTULO seguido de um valor — junte cada "
    "rótulo ao seu valor em UMA ÚNICA LINHA no formato RÓTULO: valor, o "
    "rótulo exatamente como impresso, seguido de dois pontos (mesmo que o "
    "documento não os imprima) e o valor impresso naquele campo. Uma linha "
    "por campo. Preste atenção especial ao 'QUADRO RESUMO' (ou 'RESUMO DO "
    "FINANCIAMENTO'), transcrevendo TODOS os seus campos. Para compradores "
    "e vendedores, liste cada pessoa como 'Nome do titular - CPF: "
    "000.000.000-00', separando duas ou mais pessoas do MESMO campo com "
    "ponto e vírgula (;), na mesma linha do rótulo. Se o campo estiver "
    "ilegível, escreva [ILEGÍVEL]; se estiver em branco, escreva [EM "
    "BRANCO]. Transcreva também qualquer valor por extenso impresso entre "
    "parênteses logo após um valor monetário. Em tabelas, as linhas "
    "verticais das bordas NÃO são texto: nunca as transcreva como o dígito 1 "
    "nem como a letra I (um código de banco '| 033' é '033')."
)

_ILEGIVEL = "[ILEGÍVEL]"
_EM_BRANCO = "[EM BRANCO]"

#: A Declaração Pessoal de Saúde reaching this module's text is refused
#: outright — see the module header. Two tiers, both a REFUSAL gate (never a
#: field read):
#: - a FORM TITLE (`_DPS_TITULOS_FORMULARIO`) is enough on its own;
#: - the phrase "DECLARAÇÃO PESSOAL DE SAÚDE" needs QUESTIONNAIRE STRUCTURE
#:   beside it (≥ `_DPS_MIN_SINAIS` of `_DPS_SINAIS_QUESTIONARIO`). A real
#:   bank financing contract NAMES the DPS in its insurance (MIP) clauses —
#:   measured live on deal 883 (Itaú, 2026-09-25): a bare-mention tripwire
#:   refused the whole contract, forever (a re-upload can't help), so no
#:   financing fact could ever be read. A mention carries no health data; the
#:   questionnaire (weight/height, illness, treatment, surgery, SIM/NÃO boxes)
#:   is what LGPD art. 11 protects.
_DPS_TITULOS_FORMULARIO: tuple[str, ...] = (
    "DECLARACAO DE SAUDE DO PROPONENTE",
    "QUESTIONARIO DE SAUDE",
)
_DPS_MENCAO = "DECLARACAO PESSOAL DE SAUDE"
_DPS_SINAIS_QUESTIONARIO: tuple[str, ...] = (
    "PESO", "ALTURA", "DOENCA", "TRATAMENTO", "CIRURGIA", "INTERNA",
    "MEDICAMENTO", "SIM ( )", "NAO ( )", "( ) SIM", "( ) NAO",
)
_DPS_MIN_SINAIS = 2


def _e_dps(normalizado: str) -> bool:
    """The tripwire predicate for ONE page's text — see
    `_DPS_TITULOS_FORMULARIO` and `_algum_dps`."""
    if any(t in normalizado for t in _DPS_TITULOS_FORMULARIO):
        return True
    if _DPS_MENCAO not in normalizado:
        return False
    sinais = sum(1 for s in _DPS_SINAIS_QUESTIONARIO if s in normalizado)
    return sinais >= _DPS_MIN_SINAIS


def _algum_dps(text: str, paginas: Optional[Sequence[str]]) -> bool:
    """The tripwire, judged PAGE BY PAGE when the caller has pages. A mention
    and its questionnaire signals must sit on the SAME page — measured live on
    deal 883 (Itaú, 2026-09-26): page 7 names the DPS in the MIP clause and
    page 8's insurance text says "doença"/"tratamento", so a joined 5–8
    window tripped a questionnaire that exists on no page. A real DPS prints
    its questions on its own form page. `paginas=None` (a single image, the
    proposta) judges the whole text as its one page."""
    textos = paginas if paginas is not None else (text,)
    return any(_e_dps(strip_accents_upper(t or "")) for t in textos)


def _temper(confidence: ExtractionConfidence, source: TextSource) -> ExtractionConfidence:
    """`alta` is reachable only off a PDF's own text layer — shared with
    `cartao_cnpj`/`guia_itbi` via `caixa_rotulada.temperar_alta_por_fonte`
    (identical semantics in all three). Applies to every field EXCEPT the
    money ones — see `_confianca_valor`."""
    return temperar_alta_por_fonte(confidence, source)


def _confianca_valor(
    lido: ValorLido, source: TextSource, *, soma_confere: bool = False
) -> ExtractionConfidence:
    """Money-field confidence — never `alta` off vision. `media` off vision
    when EITHER `money.ler_valor`'s own extenso cross-check agrees, OR the
    Quadro Resumo's own arithmetic sums correctly (`soma_confere`) — the
    contract's two named deterministic checks, either one sufficient. See
    the module header and `guia_itbi._confianca_valor` (the same rule,
    minus the second check, which only a multi-field Quadro affords)."""
    if lido.valor is None:
        return ExtractionConfidence.NENHUMA
    if source is TextSource.TEXT_LAYER and lido.extenso_confere is not False:
        return ExtractionConfidence.ALTA
    if lido.extenso_confere or soma_confere:
        return ExtractionConfidence.MEDIA
    return ExtractionConfidence.BAIXA


# ─── bank code table (data) — see the module header ───────────────────────

#: `synonym (accent/case-normalised) -> (nome canônico, código FEBRABAN)`.
#: Itaú is the one entry measured against a real document (883); the rest
#: are FEBRABAN's own published codes, offered so the synonym table is
#: bank-agnostic by CONSTRUCTION, not a claim that their real layouts have
#: been seen. Extending this for a bank whose real contract has been
#: measured is adding synonyms here, never a new parser.
_BANCOS: dict[str, tuple[str, str]] = {
    "ITAU": ("Itaú Unibanco S.A.", "341"),
    "ITAU UNIBANCO": ("Itaú Unibanco S.A.", "341"),
    "BANCO ITAU": ("Itaú Unibanco S.A.", "341"),
    "CAIXA ECONOMICA FEDERAL": ("Caixa Econômica Federal", "104"),
    "CAIXA": ("Caixa Econômica Federal", "104"),
    "BRADESCO": ("Banco Bradesco S.A.", "237"),
    "BANCO BRADESCO": ("Banco Bradesco S.A.", "237"),
    "SANTANDER": ("Banco Santander (Brasil) S.A.", "033"),
    "BANCO SANTANDER": ("Banco Santander (Brasil) S.A.", "033"),
    "BANCO DO BRASIL": ("Banco do Brasil S.A.", "001"),
    "BB": ("Banco do Brasil S.A.", "001"),
}


def _banco_por_codigo(codigo: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """`(nome canônico, código)` for a printed FEBRABAN code ("0341", "341")
    — only codes `_BANCOS` already carries; anything else is `(None, None)`."""
    digitos = re.sub(r"\D", "", codigo or "")
    if not digitos:
        return (None, None)
    for canonico, cod in _BANCOS.values():
        if int(cod) == int(digitos):
            return (canonico, cod)
    return (None, None)


def _banco_por_nome(nome: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """`(nome canônico, código)` for the FIRST `_BANCOS` synonym found
    anywhere inside `nome` — never a guess: an unrecognised bank name
    returns `(None, None)`, and the raw printed text still survives at
    `rotulos`/the field itself, whichever field called this."""
    if not nome:
        return (None, None)
    norm = strip_accents_upper(nome)
    for sinonimo, (canonico, codigo) in _BANCOS.items():
        if sinonimo in norm:
            return (canonico, codigo)
    return (None, None)


# ─── label synonym table (as data) — the shared Quadro Resumo vocabulary ──

_ROTULOS: dict[str, tuple[str, ...]] = {
    #: Itaú prints "CREDOR: ITAÚ UNIBANCO S.A." — a bare "BANCO" sitting
    #: INSIDE "UNIBANCO" is a word-boundary match failure, not an ordering
    #: one; `caixa_rotulada.campo` word-boundary-matches every synonym (so
    #: "BANCO" never fires there) AND tries synonyms longest-first
    #: regardless of this tuple's own declared order (883, measured).
    "banco_nome": ("CREDOR", "BANCO", "INSTITUICAO FINANCEIRA", "AGENTE FINANCEIRO"),
    "numero_contrato": ("NUMERO DO CONTRATO", "CONTRATO NO", "N DO CONTRATO"),
    "numero_proposta": ("NUMERO DA PROPOSTA", "PROPOSTA NO", "N DA PROPOSTA"),
    #: Specific-first for a human reading this table — `caixa_rotulada.campo`
    #: tries synonyms longest-first regardless, so the bare "DATA" can no
    #: longer shadow the specific ones the way it silently did before this
    #: field moved onto the shared matcher (this tuple's own declared order
    #: is no longer load-bearing, unlike before).
    "data_documento": ("DATA DE EMISSAO", "DATA DO CONTRATO", "DATA"),
    "valor_compra_venda": (
        "VALOR DE COMPRA E VENDA",
        "VALOR DA COMPRA E VENDA",
        "VALOR DO IMOVEL",
        "PRECO DE VENDA DO IMOVEL",  # Itaú item 1 (883, measured)
    ),
    #: Itaú item 13 — "VALOR DA AVALIAÇÃO REALIZADA E ATRIBUÍDA PARA FINS DE
    #: VENDA EM LEILÃO PÚBLICO" (Lei 9.514 art. 24 VI: the appraisal value).
    "valor_avaliacao": ("VALOR DE AVALIACAO", "VALOR AVALIADO", "VALOR DA AVALIACAO"),
    #: Itaú items 1C / 3A (883, measured == the contract's financiamento
    #: parcela). NOT "VALOR TOTAL DO FINANCIAMENTO (SALDO DEVEDOR)": that one
    #: adds financed despesas the seller never receives.
    "valor_financiado": (
        "VALOR FINANCIADO",
        "VALOR DO FINANCIAMENTO",
        "RECURSOS DO FINANCIAMENTO",
        "VALOR DO CREDITO",  # Itaú proposta, app message (883, measured)
        "VALOR DESTINADO AO PAGAMENTO DO PRECO DE VENDA DO IMOVEL",
    ),
    #: Bare "FGTS" last — `caixa_rotulada.campo` tries synonyms
    #: longest-first regardless of this tuple's own declared order, so a
    #: bare "FGTS" can never grab a "RECURSOS DO FGTS: [EM BRANCO]"-style
    #: line ahead of the more specific synonym that's actually printed
    #: there; kept declared specific-first anyway for a human reading this
    #: table. Other banks' Quadros print the vinculada-account phrasing
    #: rather than Itaú's "RECURSOS DO FGTS" (not yet measured against a
    #: real document from a bank other than Itaú — see the module header).
    "valor_fgts": (
        "RECURSOS DO FGTS",
        "VALOR DO FGTS",
        "RECURSOS FGTS",
        "RECURSOS DA CONTA VINCULADA DO FGTS",
        "VALOR DA CONTA VINCULADA",
        "FGTS",
    ),
    "valor_recursos_proprios": (
        "RECURSOS PROPRIOS",
        "VALOR DE RECURSOS PROPRIOS",
        "ENTRADA",
    ),
    #: Specific first — the bare "PRAZO" also matches Itaú's "PRAZO DE
    #: CARÊNCIA PARA EXPEDIÇÃO DE INTIMAÇÃO: 30 dias".
    "prazo_meses": ("PRAZO DE AMORTIZACAO", "PRAZO EM MESES", "PRAZO"),
    "taxa_nominal_aa": ("TAXA NOMINAL", "TAXA NOMINAL AA", "TAXA DE JUROS NOMINAL"),
    "taxa_efetiva_aa": ("TAXA EFETIVA", "TAXA EFETIVA AA", "TAXA DE JUROS EFETIVA"),
    "sistema_amortizacao": ("SISTEMA DE AMORTIZACAO", "SISTEMA"),
    "compradores": ("COMPRADOR", "COMPRADORES", "MUTUARIO", "MUTUARIOS"),
    "vendedores": ("VENDEDOR", "VENDEDORES"),
    "conta_credito_vendedor": (
        "CONTA DE CREDITO DO VENDEDOR",
        "DADOS BANCARIOS DO VENDEDOR",
        "CONTA PARA CREDITO AO VENDEDOR",
        #: Itaú item 8 — the amount on the label line, the account on the
        #: NEXT line as `|`-separated sub-fields (883, measured). See
        #: `_bloco_conta`.
        "VALOR A SER LIBERADO AO VENDEDOR",
    ),
}

#: The Quadro Resumo's own anchor line — see `_quadro_encontrado`.
#: Itaú prints no "QUADRO RESUMO" title — its summary is numbered items
#: headed "CONDIÇÕES DO FINANCIAMENTO" (883, measured); the ≥3-fields rule in
#: `_quadro_encontrado` still has to hold beside it.
_QUADRO_ANCHOR: tuple[str, ...] = (
    "QUADRO RESUMO",
    "RESUMO DO FINANCIAMENTO",
    "CONDICOES DO FINANCIAMENTO",
)

_CAMPOS_MONETARIOS: tuple[str, ...] = (
    "valor_compra_venda", "valor_avaliacao", "valor_financiado", "valor_fgts",
    "valor_recursos_proprios",
)


def _todos_rotulos() -> tuple[str, ...]:
    return tuple(r for sinonimos in _ROTULOS.values() for r in sinonimos)


def _campo(
    linhas: list[str], sinonimos: Sequence[str], *, todos_rotulos: Sequence[str]
) -> tuple[Optional[str], Optional[str], bool]:
    """`(valor, rótulo encontrado, mascarado)` for the FIRST admissible
    synonym in `sinonimos` that matches a box in `linhas` — via the shared
    `caixa_rotulada.campo`, common to `cartao_cnpj`/`guia_itbi` now (the
    other-field-longer-label guard this field's own "PRECO DE VENDA DO
    IMOVEL" (compra e venda) / "VALOR DESTINADO AO PAGAMENTO DO PRECO DE
    VENDA DO IMOVEL" (financiado) pair needs, every-occurrence-per-line
    scanning, longest-synonym-first ordering, and word-boundary matching
    all live there now — see that module's header for the full drift
    history this fixes)."""
    return _caixa_campo(
        linhas, sinonimos, todos_rotulos=todos_rotulos, valores_mascarados=(_ILEGIVEL, _EM_BRANCO)
    )


def _data_br(txt: Optional[str]) -> Optional[date]:
    """Shared with `cartao_cnpj`/`guia_itbi` — identical semantics — via
    `caixa_rotulada.data_br`."""
    return _caixa_data_br(txt)


_INTEIRO_RE = re.compile(r"(\d+)")


_MESES_RE = re.compile(r"(\d+)\s*(?:MESES|MES|PRESTACOES|PARCELAS)\b")
_ANOS_RE = re.compile(r"(\d+)\s*ANOS?\b")


def _prazo_meses(txt: Optional[str]) -> Optional[int]:
    """The term in MONTHS. Itaú's proposta prints "30 anos (360 meses)" —
    the first integer is the years (883, measured). An explicit month count
    wins; a bare year count converts; a bare number is taken as months (the
    Quadro's "Prazo de amortização: 400 meses" / "360")."""
    if not txt:
        return None
    norm = strip_accents_upper(txt)
    m = _MESES_RE.search(norm)
    if m:
        return int(m.group(1))
    a = _ANOS_RE.search(norm)
    if a:
        return int(a.group(1)) * 12
    return _inteiro(txt)


def _inteiro(txt: Optional[str]) -> Optional[int]:
    if not txt:
        return None
    m = _INTEIRO_RE.search(txt)
    return int(m.group(1)) if m else None


def _percentual(txt: Optional[str]) -> Optional[Decimal]:
    """Shared with `guia_itbi` — identical semantics — via
    `caixa_rotulada.percentual`."""
    return _caixa_percentual(txt)


@dataclass(frozen=True)
class PessoaFinanciamento:
    """One comprador/vendedor named on the document — CPF check-digit
    verified, never corrected (see `cpf.is_valid`'s own contract)."""

    nome: Optional[str] = None
    cpf: Optional[str] = None
    cpf_valido: bool = False


def _pessoas(valor: Optional[str]) -> tuple[PessoaFinanciamento, ...]:
    """Shared parsing with `guia_itbi._pessoas` via
    `caixa_rotulada.pessoas_com_cpf` — this module's own
    `PessoaFinanciamento` type is unchanged, only the `;`-separated "Nome -
    CPF: ..." parsing itself is shared."""
    return pessoas_com_cpf(valor, PessoaFinanciamento)


# ─── the proponente(s) a bank PROPOSTA names (2026-10-03, measured) ──────
# A proposta is a LETTER, not a Quadro Resumo: it names its proponente(s)
# in prose or in a label pair, never in the "Nome - CPF: ..." box the
# contract prints. Measured on 11 real proposals (vision):
# - 10/11 (Itaú "Carta de Crédito"): "Oi, <Nome>. Sua proposta foi
#   aprovada ..." — the name only, NO CPF anywhere on the letter;
# - 1/11: "Nome do(s) Comprador(es): <nome>" and, on its OWN line,
#   "CPF(s): <cpf>" — the pair the "Nome - CPF" parser never sees.
# Before this, `compradores` read empty on every proposal, so SW's
# belongs-to-this-deal check had no evidence at all (5/5 live uploads
# 'pertencimento_nao_verificado').

_SAUDACAO_RE = re.compile(
    r"\b(?:OI|OLA),\s+(.+?)[.,!]?\s+SUA PROPOSTA (?:FOI )?APROVADA"
)
_NOMES_ROTULO_RE = re.compile(
    r"\bNOMES?\s+DOS?\s*(?:\(\s*S\s*\))?\s*"
    r"(?:COMPRADOR|PROPONENTE|MUTUARIO|CLIENTE)\s*(?:\(\s*E?S\s*\)|ES|S)?\s*:\s*(.+)$"
)
_CPFS_ROTULO_RE = re.compile(r"\bCPF\s*(?:\(\s*S\s*\)|S)?\s*:\s*(.+)$")


def _proponentes(
    linhas: list[str],
) -> tuple[tuple[PessoaFinanciamento, ...], tuple[str, ...]]:
    """`(pessoas pareadas com CPF, todos os nomes lidos)` for a proposta's
    proponente(s) — see the block comment above. Pairing and name
    splitting are `caixa_rotulada`'s shared rule (`separar_nomes` /
    `parear_nomes_cpfs`: equal counts only; a masked CPF is no CPF); a
    name is never invented, never fuzzily completed — the caller matches
    it strictly."""
    nomes: list[str] = []
    texto_rotulado: Optional[str] = None
    cpfs: list[str] = []
    for linha in linhas:
        m = _SAUDACAO_RE.search(linha)
        if m and (nome := limpar_nome(m.group(1))):
            nomes.append(nome)
            continue
        m = _NOMES_ROTULO_RE.search(linha)
        if m:
            texto_rotulado = m.group(1) if texto_rotulado is None else f"{texto_rotulado};{m.group(1)}"
            continue
        m = _CPFS_ROTULO_RE.search(linha)
        if m and not cpfs:
            cpfs = cpfs_em(m.group(1))
    rotulados = separar_nomes(texto_rotulado, len(cpfs))
    pareadas = parear_nomes_cpfs(rotulados, cpfs, PessoaFinanciamento)
    todos = tuple(dict.fromkeys([*nomes, *rotulados]))
    return pareadas, todos


#: The account-detail fields inside the `conta_credito_vendedor` box — its
#: OWN mini label vocabulary, read from the SAME box's raw value text (see
#: `_conta_credito`) rather than as separate top-level `_ROTULOS` entries:
#: the bank/agência/conta/titular only mean anything AS a group, printed
#: together inside one Quadro box.
_CONTA_ROTULOS: dict[str, tuple[str, ...]] = {
    #: Itaú prints the CODE ("CÓD. BANCO: 0341") — see `_banco_por_codigo`.
    "banco": ("COD. BANCO", "COD BANCO", "BANCO"),
    "agencia": ("AGENCIA", "AG"),
    "conta": ("CONTA", "CONTA CORRENTE", "C/C"),
    "titular_cpf": ("CPF DO TITULAR", "CPF TITULAR", "CPF / CNPJ", "CPF/CNPJ", "CPF"),
}

#: A numbered Quadro item ("9 - VALOR A SER LIBERADO AO COMPRADOR") ends the
#: account block `_bloco_conta` gathers.
#: A box never runs longer than this — a missing item number must not let the
#: block swallow the rest of the contract. Itaú's table flattens to one
#: `Rótulo: valor` line per column (Nome, CPF/CNPJ, Cód. Banco, Agência,
#: Conta, Percentual) in most transcriptions (883, 3 of 3 runs measured).
_BLOCO_CONTA_MAX_LINHAS = 8

#: A continuation line of the box is `RÓTULO: valor` shaped — anything else
#: (a clause, a heading) ends it.
_LINHA_ROTULADA_RE = re.compile(r"^[^:]{1,30}:")
_ITEM_NUMERADO_RE = re.compile(r"^\d+(\.\d+)?\s*[-–.]\s")


def _bloco_conta(linhas: list[str], rotulo: Optional[str], valor: Optional[str]) -> Optional[str]:
    """The account box's text when the label line itself carries no account
    sub-field (Itaú: "VALOR A SER LIBERADO AO VENDEDOR: R$ …" with the
    account on the NEXT line) — the label line's value plus the lines after
    it while they stay `RÓTULO: valor` shaped, up to the next numbered item.
    Otherwise `valor` as is."""
    if valor is None or rotulo is None:
        return valor
    sub = tuple(s for sins in _CONTA_ROTULOS.values() for s in sins)
    if any(s in strip_accents_upper(valor) for s in sub):
        return valor
    for i, linha in enumerate(linhas):
        if rotulo not in linha:
            continue
        seguintes: list[str] = []
        for prox in linhas[i + 1 : i + 1 + _BLOCO_CONTA_MAX_LINHAS]:
            if (
                not prox.strip()
                or _ITEM_NUMERADO_RE.match(prox)
                or not _LINHA_ROTULADA_RE.match(prox)
            ):
                break
            seguintes.append(prox)
        return "\n".join([valor, *seguintes]) if seguintes else valor
    return valor


@dataclass(frozen=True)
class ContaCreditoVendedor:
    """The seller's own credit account, printed inside the Quadro Resumo —
    read as STRUCTURED fields per owner decision H5 (§B of the
    negociação/financiamento extraction contract): the bank CODE is what
    lets S2 auto-create an `agentes_financeiros` row (H7), and the CPF is
    what lets S2 match this account to a vendedor before offering it as a
    favorecido. Reading-only from THIS module's point of view — whether it
    fills a favorecido is a decision the SW wiring layer makes."""

    banco_nome: Optional[str] = None
    banco_codigo: Optional[str] = None
    agencia: Optional[str] = None
    conta: Optional[str] = None
    titular_cpf: Optional[str] = None
    titular_cpf_valido: bool = False
    #: The bank text/code exactly as printed, kept when it maps to no known
    #: bank so the reviewer sees WHAT was read (never a guessed bank).
    banco_impresso: Optional[str] = None


def _conta_credito(valor: Optional[str]) -> Optional[ContaCreditoVendedor]:
    """The `conta_credito_vendedor` box's own raw value text (which itself
    carries `RÓTULO: valor` sub-fields, semicolon- or newline-separated,
    per this module's own transcription prompt) → its structured fields.
    `None` when the box itself was not found/was masked — distinct from a
    `ContaCreditoVendedor` whose sub-fields are individually `None`."""
    if not valor:
        return None
    partes = re.split(r"[;\n|]", valor)
    norm_partes = [strip_accents_upper(p) for p in partes]
    achados: dict[str, str] = {}
    for campo, sinonimos in _CONTA_ROTULOS.items():
        for sinonimo in sinonimos:
            encontrado = False
            for bruta, norm in zip(partes, norm_partes):
                idx = norm.find(sinonimo)
                if idx < 0:
                    continue
                resto = bruta[idx + len(sinonimo) :].lstrip(" .:").strip()
                if resto and resto not in (_ILEGIVEL, _EM_BRANCO):
                    achados[campo] = resto
                    encontrado = True
                break
            if encontrado:
                break

    banco_nome, banco_codigo = _banco_por_nome(achados.get("banco"))
    if banco_nome is None:
        banco_nome, banco_codigo = _banco_por_codigo(achados.get("banco"))
    agencia = achados.get("agencia")
    if agencia:
        agencia = agencia.rstrip("-– ") or None
    titular_cpf_bruto = achados.get("titular_cpf")
    titular_cpf = format_cpf(titular_cpf_bruto) if titular_cpf_bruto else None
    titular_cpf_valido = bool(titular_cpf_bruto) and _cpf_is_valid(titular_cpf_bruto)

    return ContaCreditoVendedor(
        banco_nome=banco_nome,
        banco_codigo=banco_codigo,
        agencia=agencia,
        conta=achados.get("conta"),
        titular_cpf=titular_cpf,
        titular_cpf_valido=titular_cpf_valido,
        banco_impresso=achados.get("banco") if banco_codigo is None else None,
    )


# ─── public value object ───────────────────────────────────────────────────


@dataclass(frozen=True)
class FinanciamentoImobiliarioFields:
    """What one financing contract or bank proposta yielded. Every field is
    READING-ONLY from this module's own point of view — which, if any,
    feeds a DB column is a decision the SW wiring layer makes (see the
    negociação/financiamento extraction contract §B)."""

    documento: Literal["contrato", "proposta"] = "contrato"
    banco_nome: Optional[str] = None
    banco_codigo: Optional[str] = None
    numero_contrato: Optional[str] = None
    numero_proposta: Optional[str] = None
    data_documento: Optional[date] = None
    valor_compra_venda: Optional[Decimal] = None
    valor_avaliacao: Optional[Decimal] = None
    valor_financiado: Optional[Decimal] = None
    valor_fgts: Optional[Decimal] = None
    valor_recursos_proprios: Optional[Decimal] = None
    prazo_meses: Optional[int] = None
    taxa_nominal_aa: Optional[Decimal] = None
    taxa_efetiva_aa: Optional[Decimal] = None
    sistema_amortizacao: Optional[str] = None
    compradores: tuple[PessoaFinanciamento, ...] = ()
    vendedores: tuple[PessoaFinanciamento, ...] = ()
    #: Every comprador/proponente NAME the document printed outside the "Nome - CPF"
    #: box — a proposta letter's greeting / "Nome do(s) Comprador(es)"
    #: label (see `_proponentes`), with or without a CPF beside it. The
    #: evidence a belongs-to-this-deal check matches STRICTLY by name when
    #: the letter carries no verifiable CPF.
    nomes_compradores: tuple[str, ...] = ()
    #: Pages the WINNING (or, if neither pass found the Quadro, every
    #: attempted) read actually covered — set by the extractor, not the
    #: pure parser below, which has no page concept of its own. `()` for
    #: `proposta` (a single image, no window to record).
    paginas_lidas: tuple[int, ...] = ()
    quadro_encontrado: bool = False
    conta_credito_vendedor: Optional[ContaCreditoVendedor] = None
    confiancas: Mapping[str, ExtractionConfidence] = field(default_factory=dict)
    rotulos: Mapping[str, Optional[str]] = field(default_factory=dict)
    source: TextSource = TextSource.NENHUMA
    aviso: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None


# ─── pure parser, shared by both readers ───────────────────────────────────


def _quadro_encontrado(
    anchor_presente: bool,
    valor_compra_venda: Optional[Decimal],
    valor_financiado: Optional[Decimal],
    valor_fgts: Optional[Decimal],
    valor_recursos_proprios: Optional[Decimal],
    prazo_meses: Optional[int],
) -> bool:
    """The anchor plus AT LEAST 3 of {compra e venda, financiado,
    FGTS-or-recursos-próprios, prazo} carrying a value — see the module
    header and the negociação/financiamento extraction contract §D.4."""
    if not anchor_presente:
        return False
    presentes = sum(
        (
            valor_compra_venda is not None,
            valor_financiado is not None,
            valor_fgts is not None or valor_recursos_proprios is not None,
            prazo_meses is not None,
        )
    )
    return presentes >= 3


def parse_financiamento_imobiliario(
    text: str,
    source: TextSource,
    documento: Literal["contrato", "proposta"],
    *,
    paginas: Optional[Sequence[str]] = None,
) -> FinanciamentoImobiliarioFields:
    """Text (already ladder/transcriber-read) → `FinanciamentoImobiliarioFields`.
    Pure, never raises. Shared by both readers — see the module header.
    `paginas` — the same text's pages, one string each, so the DPS tripwire
    judges each page on its own (`_algum_dps`); `None` ⇒ one page.
    """
    if _algum_dps(text, paginas):
        # The DPS tripwire — no other field, no text, whichever reader
        # called this. See the module header.
        return FinanciamentoImobiliarioFields(
            documento=documento, source=source, error="documento_sensivel_dps"
        )

    todos = _todos_rotulos()
    linhas = normalize_lines(text or "")
    todos_norm = tuple(strip_accents_upper(r) for r in todos)

    confiancas: dict[str, ExtractionConfidence] = {c: ExtractionConfidence.NENHUMA for c in _ROTULOS}
    rotulos: dict[str, Optional[str]] = {c: None for c in _ROTULOS}
    brutos: dict[str, Optional[str]] = {}

    #: `conta_credito_vendedor`'s own VALUE legitimately re-uses a top-level
    #: label ("BANCO") for its nested sub-field — see `_CONTA_ROTULOS` and
    #: `_conta_credito`. The generic "trim at the next KNOWN label" cutoff
    #: `_campo` applies must not treat that nested "BANCO:" as the start of
    #: a NEW top-level box, or the whole account block truncates to nothing
    #: the moment its own bank name is reached.
    _conta_sub_norm = frozenset(
        strip_accents_upper(s) for sins in _CONTA_ROTULOS.values() for s in sins
    )
    for campo, sinonimos in _ROTULOS.items():
        sinonimos_norm = tuple(strip_accents_upper(s) for s in sinonimos)
        todos_para_campo = (
            tuple(r for r in todos_norm if r not in _conta_sub_norm)
            if campo == "conta_credito_vendedor"
            else todos_norm
        )
        valor, achado, _mascarado = _campo(linhas, sinonimos_norm, todos_rotulos=todos_para_campo)
        brutos[campo] = valor
        rotulos[campo] = achado
        if valor is not None:
            confiancas[campo] = ExtractionConfidence.ALTA

    anchor_presente = any(
        strip_accents_upper(a) in strip_accents_upper(text or "") for a in _QUADRO_ANCHOR
    )

    lidos: dict[str, ValorLido] = {campo: ler_valor(brutos[campo] or "") for campo in _CAMPOS_MONETARIOS}

    avisos: list[str] = []

    valor_compra_venda = lidos["valor_compra_venda"].valor
    valor_avaliacao = lidos["valor_avaliacao"].valor
    valor_financiado = lidos["valor_financiado"].valor
    valor_fgts = lidos["valor_fgts"].valor
    valor_recursos_proprios = lidos["valor_recursos_proprios"].valor

    # 🔴 Invariants that NULL the offending field + aviso (contract §D.5) —
    # `valor_financiado` is the dependent one in both: a bank never finances
    # more than the deal's own price, nor more than its own appraisal.
    if valor_financiado is not None and valor_compra_venda is not None:
        if valor_financiado > valor_compra_venda:
            avisos.append("valor_financiado_maior_que_compra_venda")
            valor_financiado = None
    if (
        valor_financiado is not None
        and valor_avaliacao is not None
        and valor_financiado > valor_avaliacao
    ):
        avisos.append("valor_financiado_maior_que_avaliacao")
        valor_financiado = None

    # The Quadro sum — a SEPARATE, softer rule: a mismatch never nulls a
    # field, it caps every money field's confidence at `baixa` (contract
    # §D.5's `quadro_resumo_soma_divergente`).
    soma_confere = False
    if (
        valor_financiado is not None
        and valor_fgts is not None
        and valor_recursos_proprios is not None
        and valor_compra_venda is not None
    ):
        soma = valor_financiado + valor_fgts + valor_recursos_proprios
        soma_confere = soma == valor_compra_venda
        if not soma_confere:
            avisos.append("quadro_resumo_soma_divergente")
    elif (
        valor_compra_venda is not None
        and valor_financiado is not None
        and valor_recursos_proprios is not None
        and valor_fgts is None
        and (valor_financiado + valor_recursos_proprios) != valor_compra_venda
    ):
        # FGTS itself was never read (box not found/unreadable), so the
        # FULL sum check above never ran at all — a softer, partial-legs
        # aviso: financiado + recursos próprios alone already don't add up
        # to compra e venda, which is exactly what a genuinely-unread FGTS
        # leg would explain. Never nulls a field (same posture as the
        # full-sum check); a human reads the aviso and checks the box.
        avisos.append("quadro_resumo_fgts_ausente")

    prazo_meses = _prazo_meses(brutos["prazo_meses"])
    if brutos["prazo_meses"] and prazo_meses is None:
        confiancas["prazo_meses"] = ExtractionConfidence.NENHUMA
    elif prazo_meses is not None:
        confiancas["prazo_meses"] = _temper(ExtractionConfidence.ALTA, source)

    taxa_nominal_aa = _percentual(brutos["taxa_nominal_aa"])
    if brutos["taxa_nominal_aa"] and taxa_nominal_aa is None:
        confiancas["taxa_nominal_aa"] = ExtractionConfidence.NENHUMA
    elif taxa_nominal_aa is not None:
        confiancas["taxa_nominal_aa"] = _temper(ExtractionConfidence.ALTA, source)

    taxa_efetiva_aa = _percentual(brutos["taxa_efetiva_aa"])
    if brutos["taxa_efetiva_aa"] and taxa_efetiva_aa is None:
        confiancas["taxa_efetiva_aa"] = ExtractionConfidence.NENHUMA
    elif taxa_efetiva_aa is not None:
        confiancas["taxa_efetiva_aa"] = _temper(ExtractionConfidence.ALTA, source)

    data_documento = _data_br(brutos["data_documento"])
    if brutos["data_documento"] and data_documento is None:
        confiancas["data_documento"] = ExtractionConfidence.NENHUMA
    elif data_documento is not None:
        confiancas["data_documento"] = _temper(ExtractionConfidence.ALTA, source)

    banco_nome, banco_codigo = _banco_por_nome(brutos["banco_nome"])
    if brutos["banco_nome"] and banco_nome is None:
        # A bank name was printed but is not (yet) in `_BANCOS` — never a
        # guess, so this reads as unreadable rather than silently keeping
        # the label matched with no canonical value.
        confiancas["banco_nome"] = ExtractionConfidence.NENHUMA
    elif banco_nome is not None:
        confiancas["banco_nome"] = _temper(ExtractionConfidence.ALTA, source)

    compradores = _pessoas(brutos["compradores"])
    vendedores = _pessoas(brutos["vendedores"])
    pareadas, nomes_compradores = _proponentes(linhas)
    if not compradores and pareadas:
        compradores = pareadas
    for campo, pessoas in (("compradores", compradores), ("vendedores", vendedores)):
        if not pessoas:
            confiancas[campo] = ExtractionConfidence.NENHUMA
        elif all(p.cpf_valido for p in pessoas):
            confiancas[campo] = _temper(ExtractionConfidence.ALTA, source)
        else:
            confiancas[campo] = ExtractionConfidence.BAIXA
            avisos.append(f"{campo}_cpf_digito_invalido")

    for campo in ("numero_contrato", "numero_proposta", "sistema_amortizacao"):
        if brutos[campo] is not None:
            confiancas[campo] = _temper(ExtractionConfidence.ALTA, source)

    conta_credito_vendedor = _conta_credito(
        _bloco_conta(linhas, rotulos["conta_credito_vendedor"], brutos["conta_credito_vendedor"])
    )
    if conta_credito_vendedor is None:
        confiancas["conta_credito_vendedor"] = ExtractionConfidence.NENHUMA
    elif conta_credito_vendedor.titular_cpf and not conta_credito_vendedor.titular_cpf_valido:
        confiancas["conta_credito_vendedor"] = ExtractionConfidence.BAIXA
        avisos.append("conta_credito_vendedor_cpf_digito_invalido")
    else:
        confiancas["conta_credito_vendedor"] = _temper(ExtractionConfidence.ALTA, source)
    if conta_credito_vendedor is not None and conta_credito_vendedor.banco_impresso:
        # A bank WAS printed but maps to no known one (883: Haiku read the
        # table border before "033" as a digit) — surfaced, never guessed.
        avisos.append("conta_credito_vendedor_banco_nao_reconhecido")

    valores_finais = {
        "valor_compra_venda": valor_compra_venda,
        "valor_avaliacao": valor_avaliacao,
        "valor_financiado": valor_financiado,
        "valor_fgts": valor_fgts,
        "valor_recursos_proprios": valor_recursos_proprios,
    }
    for campo in _CAMPOS_MONETARIOS:
        lido = lidos[campo]
        valor_final = valores_finais[campo]
        if valor_final is None:
            confiancas[campo] = ExtractionConfidence.NENHUMA
        else:
            confiancas[campo] = _confianca_valor(lido, source, soma_confere=soma_confere)

    quadro = _quadro_encontrado(
        anchor_presente,
        valor_compra_venda,
        valor_financiado,
        valor_fgts,
        valor_recursos_proprios,
        prazo_meses,
    )

    return FinanciamentoImobiliarioFields(
        documento=documento,
        banco_nome=banco_nome,
        banco_codigo=banco_codigo,
        numero_contrato=brutos["numero_contrato"],
        numero_proposta=brutos["numero_proposta"],
        data_documento=data_documento,
        valor_compra_venda=valor_compra_venda,
        valor_avaliacao=valor_avaliacao,
        valor_financiado=valor_financiado,
        valor_fgts=valor_fgts,
        valor_recursos_proprios=valor_recursos_proprios,
        prazo_meses=prazo_meses,
        taxa_nominal_aa=taxa_nominal_aa,
        taxa_efetiva_aa=taxa_efetiva_aa,
        sistema_amortizacao=brutos["sistema_amortizacao"],
        compradores=compradores,
        vendedores=vendedores,
        nomes_compradores=nomes_compradores,
        quadro_encontrado=quadro,
        conta_credito_vendedor=conta_credito_vendedor,
        confiancas=confiancas,
        rotulos=rotulos,
        source=source,
        aviso=",".join(avisos) if avisos else None,
    )


# ─── Protocol + Fake + Real + factory ──────────────────────────────────────


@runtime_checkable
class FinanciamentoImobiliarioExtractor(Protocol):
    """Bytes + mimetype → a financing document's typed fields.

    Implementations MUST NOT raise for an unreadable/corrupt document — they
    return `FinanciamentoImobiliarioFields` with `error` set."""

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FinanciamentoImobiliarioFields:
        ...


def _fake_pessoas() -> tuple[PessoaFinanciamento, ...]:
    return (PessoaFinanciamento(nome="COMPRADOR FAKE SINTETICO", cpf="412.954.238-98", cpf_valido=True),)


class FakeContratoFinanciamentoExtractor:
    """Deterministic contrato reader — the dev/test default. Pass `result=`
    to script a specific outcome, same convention as `FakeCartaoCnpjExtractor`."""

    def __init__(self, result: Optional[FinanciamentoImobiliarioFields] = None) -> None:
        self._result = result

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FinanciamentoImobiliarioFields:
        if self._result is not None:
            return self._result
        if not content:
            return FinanciamentoImobiliarioFields(
                documento="contrato", error="empty_document", error_message="no bytes to read"
            )
        campos = tuple(_ROTULOS)
        return FinanciamentoImobiliarioFields(
            documento="contrato",
            banco_nome="Itaú Unibanco S.A.",
            banco_codigo="341",
            numero_contrato="CONTRATO-FAKE-001",
            numero_proposta=None,
            data_documento=date(2026, 1, 1),
            valor_compra_venda=Decimal("500000.00"),
            valor_avaliacao=Decimal("520000.00"),
            valor_financiado=Decimal("400000.00"),
            valor_fgts=Decimal("20000.00"),
            valor_recursos_proprios=Decimal("80000.00"),
            prazo_meses=360,
            taxa_nominal_aa=Decimal("9.5"),
            taxa_efetiva_aa=Decimal("9.9"),
            sistema_amortizacao="SAC",
            compradores=_fake_pessoas(),
            vendedores=_fake_pessoas(),
            paginas_lidas=(1, 2, 3, 4),
            quadro_encontrado=True,
            conta_credito_vendedor=ContaCreditoVendedor(
                banco_nome="Itaú Unibanco S.A.",
                banco_codigo="341",
                agencia="0001",
                conta="99999-9",
                titular_cpf="412.954.238-98",
                titular_cpf_valido=True,
            ),
            confiancas={campo: ExtractionConfidence.ALTA for campo in campos},
            rotulos={campo: _ROTULOS[campo][0] for campo in campos},
            source=TextSource.TEXT_LAYER,
        )


class FakePropostaFinanciamentoExtractor:
    """Deterministic proposta reader — the dev/test default."""

    def __init__(self, result: Optional[FinanciamentoImobiliarioFields] = None) -> None:
        self._result = result

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FinanciamentoImobiliarioFields:
        if self._result is not None:
            return self._result
        if not content:
            return FinanciamentoImobiliarioFields(
                documento="proposta", error="empty_document", error_message="no bytes to read"
            )
        campos = tuple(_ROTULOS)
        return FinanciamentoImobiliarioFields(
            documento="proposta",
            banco_nome="Itaú Unibanco S.A.",
            banco_codigo="341",
            numero_proposta="PROPOSTA-FAKE-001",
            data_documento=date(2026, 1, 1),
            valor_compra_venda=Decimal("500000.00"),
            valor_financiado=Decimal("400000.00"),
            prazo_meses=360,
            compradores=_fake_pessoas(),
            quadro_encontrado=True,
            confiancas={campo: ExtractionConfidence.ALTA for campo in campos},
            rotulos={campo: _ROTULOS[campo][0] for campo in campos},
            source=TextSource.TEXT_LAYER,
        )


def _fonte_da_transcricao(transcricao: Transcription) -> TextSource:
    """Which `TextSource` best labels a whole (possibly page-mixed)
    `Transcription` — the same "any vision page caps the blend" rule
    `ladder.DocumentTextLadder.to_text`'s own `paginas=` bypass path uses."""
    if transcricao.paginas_por_visao:
        return TextSource.OCR
    if transcricao.text.strip():
        return TextSource.TEXT_LAYER
    return TextSource.NENHUMA


class LadderContratoFinanciamentoExtractor:
    """The financing contract — page-by-page, whole-document read over
    `documents.transcription.DocumentTranscriber`, then the Quadro Resumo is
    located wherever it sits. See the module header.

    🔴 OWNER MANDATE (2026-09-28): every uploaded document is read
    "correctamente e precisamente, página por página, nunca em lotes" — no
    cost cap. Before this, the contract was read in at most two 4-page
    windows (`1..4`, then `5..8`) and gave up beyond page 8 entirely —
    `error='quadro_resumo_nao_encontrado'` for a Quadro that happened to sit
    on page 10, and pages 9+ of a longer contract NEVER read at all, whether
    or not the Quadro was on them. A single `transcribe()` call with
    `paginas=None` reads every page — one vision call per page needing it,
    exactly as `LadderDocumentTranscriber._transcribe` already does — capped
    only by the transcriber's own `MAX_VISION_PAGES` (40) safety ceiling,
    which still fails LOUDLY (`too_many_vision_pages`) rather than silently
    truncating.

    Construct via `make_contrato_financiamento_extractor(real=True)`.
    """

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        provider: Optional[str] = None,
        transcriber: Optional[DocumentTranscriber] = None,
    ) -> None:
        self._transcriber = transcriber or make_document_transcriber(
            real=True,
            org_id=org_id,
            provider=provider,
            ocr_prompt=DOCUMENT_PROMPT_FINANCIAMENTO,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FinanciamentoImobiliarioFields:
        if not content:
            return FinanciamentoImobiliarioFields(
                documento="contrato", error="empty_document", error_message="no bytes to read"
            )

        t = await self._transcriber.transcribe(
            content, mimetype=mimetype, filename=filename
        )
        if not t.ok:
            return FinanciamentoImobiliarioFields(
                documento="contrato", error=t.error, error_message=t.error_message
            )

        campos = parse_financiamento_imobiliario(
            t.text, _fonte_da_transcricao(t), "contrato", paginas=[p.text for p in t.pages]
        )
        if campos.error == "documento_sensivel_dps":
            return campos

        pages = tuple(sorted(p.number for p in t.pages))
        if campos.quadro_encontrado:
            return dataclasses.replace(campos, paginas_lidas=pages)

        return dataclasses.replace(
            campos,
            paginas_lidas=pages,
            error="quadro_resumo_nao_encontrado",
            error_message=f"Quadro Resumo not found in pages {pages or '()'}",
        )


class LadderPropostaFinanciamentoExtractor:
    """The single-image bank proposta reader — no page window (a photo has
    no page concept), same shared parser as the contrato reader.

    Construct via `make_proposta_financiamento_extractor(real=True)`.
    """

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        resolver=None,
        provider: Optional[str] = None,
    ) -> None:
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=DOCUMENT_PROMPT_FINANCIAMENTO,
            resolver=resolver,
            provider=provider,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> FinanciamentoImobiliarioFields:
        if not content:
            return FinanciamentoImobiliarioFields(
                documento="proposta", error="empty_document", error_message="no bytes to read"
            )

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return FinanciamentoImobiliarioFields(documento="proposta", source=source, error=err[0], error_message=err[1])
        if not text.strip():
            return FinanciamentoImobiliarioFields(documento="proposta", source=source)

        return parse_financiamento_imobiliario(text, source, "proposta")


def make_contrato_financiamento_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> FinanciamentoImobiliarioExtractor:
    """Return a financing CONTRACT extractor. Fake-by-default.

    Reads every page of the contract, page by page, then locates the Quadro
    Resumo wherever it sits — see `LadderContratoFinanciamentoExtractor`'s
    own docstring for the two-pass-window design this replaced.
    """
    if not real:
        return FakeContratoFinanciamentoExtractor()
    return LadderContratoFinanciamentoExtractor(org_id=org_id, provider=provider)


def make_proposta_financiamento_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> FinanciamentoImobiliarioExtractor:
    """Return a bank PROPOSTA extractor. Fake-by-default."""
    if not real:
        return FakePropostaFinanciamentoExtractor()
    return LadderPropostaFinanciamentoExtractor(org_id=org_id, provider=provider)


__all__ = [
    "ContaCreditoVendedor",
    "DOCUMENT_PROMPT_FINANCIAMENTO",
    "FakeContratoFinanciamentoExtractor",
    "FakePropostaFinanciamentoExtractor",
    "FinanciamentoImobiliarioExtractor",
    "FinanciamentoImobiliarioFields",
    "LadderContratoFinanciamentoExtractor",
    "LadderPropostaFinanciamentoExtractor",
    "PessoaFinanciamento",
    "make_contrato_financiamento_extractor",
    "make_proposta_financiamento_extractor",
    "parse_financiamento_imobiliario",
]
