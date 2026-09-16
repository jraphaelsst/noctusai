"""The generator's pure input — every value a contract can print, already read.

`carregador.carregar` fills this from the existing card_hub / matrículas /
certidões / imóvel / settings services; everything downstream (`derivacao`,
`contexto`, rendering, lint) is pure over it. That split is what lets the
6 variants of spec §1.3 be tested with synthetic fixtures and no database.

WHERE EACH VALUE LIVES, AND WHY THERE
-------------------------------------
Spec §6.1 listed 28 fields the contracts USE and the system did not HOLD. Six
backend slices (migrations 114-118) gave every one of them real storage, so
each now lives on the ENTITY IT DESCRIBES rather than in a side-car:

- `Termos`              <- `atendimento_negociacao_termos` (114): the per-deal
  clauses (posse, itens/ad corpus, ônus, confissão, corretagem).
- `Parcela.dispara_corretagem` / `.permuta_ativo_ids` <- the parcela row (114).
- `Intermediario.*` qualification <- `atendimento_intermediarios` (114).
- `Imovel.titulo_aquisitivo_texto` / `.onus_credor` <- `imovel_dados` (115),
  the operator's CONFIRMED wording (never the recomputed suggestion).
- `Imovel.ultima_transferencia_em` / `.ultima_transferencia_transmitentes`
  <- the matrícula's last compra e venda (115).
- `PermutaImovel`       <- the `tipo='permuta'` parcela's `permuta_ativos`
  (114) + each ativo's own imóvel + that ativo's matrícula quote (115).
- `Certidao.consulta_situacao_cadastral` / `.consulta_data_situacao`
  <- `certidao_consultas` (116).
- `Pessoa.certidoes`    <- reachable for EVERY party incl. the titular (116).
- `Pessoa.data_casamento` / `.certidao_estado_civil_emitida_em` <- 117.
- `Imobiliaria` office settings <- `org_dados_cadastrais` (117).
- `Imovel.certidoes`    <- `GET /api/imoveis/{codigo}/certidoes` (118).
- `DadosContrato.prazo_pendencias_dias` <- the contract row (114).

Every field still defaults to None/empty = UNKNOWN, so a partially-filled card
builds a `DadosContrato`; the gate then NAMES what is missing (`faltando`)
with a machine-usable `destino`. Nothing here is ever invented.

WHAT REMAINS WITHOUT A HOME (spec §6.1, named refusals — see `derivacao`)
------------------------------------------------------------------------
- #20 procurador / inventariante qualification wording (`PAPEIS_SEM_REDACAO`):
  no sample contract has it, so there is no wording to generate.
- `Termos.onus_quitacao='ja_quitado'` (#11's "already paid, has termo" state)
  and `Termos.obrigacoes_vendedor` / `.permuta_obrigacoes_entrega`: stored by
  114, but the sample contracts carry no clause for them — the gate refuses by
  name rather than printing a clause the office never wrote.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from noctusai_lib.integrations.documents.formatting import FormatRange


@dataclass
class Endereco:
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    cep: Optional[str] = None


@dataclass
class Certidao:
    tipo: str
    resultado: Optional[str]
    numero: Optional[str]
    emitida_em: Optional[date]
    validade_ate: Optional[date]
    #: The consulta this result belongs to: 'cpf' (the person) or 'cnpj'
    #: (a company linked to the person).
    consulta_tipo_documento: str = "cpf"
    consulta_nome: Optional[str] = None
    consulta_documento: Optional[str] = None
    #: [Q9] Receita situação cadastral of the CNPJ consulta — 'ativa' |
    #: 'baixada' | 'inapta' | 'suspensa' | 'nula'; None = unknown. Decides
    #: whether the company's certidão group is required (cnpj only).
    consulta_situacao_cadastral: Optional[str] = None
    #: [Q9] Date of that situação (for 'baixada': when it was closed).
    consulta_data_situacao: Optional[date] = None


@dataclass
class CertidaoImovel:
    """One row of `GET /api/imoveis/{codigo}/certidoes` (migration 118) — the
    contract's imóvel certidão group. Subject to the same [Q10] 30-day rule as
    a party's certidões."""

    tipo: str  # "cnd_iptu" | "cnd_condominio" | "matricula"
    numero: Optional[str] = None
    emitida_em: Optional[date] = None
    validade_ate: Optional[date] = None
    resultado: Optional[str] = None
    inscricao_imobiliaria: Optional[str] = None
    confirmado: bool = False


@dataclass
class Pessoa:
    cliente_id: str
    lado: str  # "vendedor" | "comprador"
    papel: str
    #: `atendimento_partes.id`; None for the titular (`atendimentos.cliente_id`).
    parte_id: Optional[str]
    nome: Optional[str] = None  # clientes.nome_oficial
    nacionalidade: Optional[str] = None
    genero: Optional[str] = None
    estado_civil: Optional[str] = None
    regime_bens: Optional[str] = None
    profissao: Optional[str] = None
    cpf: Optional[str] = None
    rg: Optional[str] = None
    rg_orgao: Optional[str] = None
    email: Optional[str] = None
    endereco: Endereco = field(default_factory=Endereco)
    conjuge_cliente_id: Optional[str] = None
    #: [Q2] Marriage date — picks "na vigência" / "anterior à vigência da Lei
    #: 6.515/77" for a casado. None = unknown (faltando for a casado).
    data_casamento: Optional[date] = None
    #: [Q11] Emission date of the estado-civil certidão (nascimento/casamento
    #: with averbações); must be < 90 days old at the assinatura.
    certidao_estado_civil_emitida_em: Optional[date] = None
    #: Keys from `documento_checklist_service.completude_contratual`.
    faltando_qualificacao: list[str] = field(default_factory=list)
    #: Migration 116 closed spec §6.1 #18: certidões are reachable for EVERY
    #: party, the titular included (`certidoes_por_cliente`). An empty list is
    #: therefore "none issued yet" — a real, nameable gap — never "unreachable".
    certidoes: list[Certidao] = field(default_factory=list)


@dataclass
class Parcela:
    id: str
    tipo: str
    valor: Optional[Decimal]
    vencimento: Optional[date]
    evento: Optional[str]
    forma_pagamento: Optional[str]
    favorecido_id: Optional[str]
    confissao_divida: bool
    ordem: int
    #: [§6.1 #23] Receiving THIS parcela is what triggers the corretagem
    #: payment — the marco is a fact about the parcela, not a typed number.
    dispara_corretagem: bool = False
    #: [§6.1 #1, #2] The `permuta_ativos` this `tipo='permuta'` parcela is paid
    #: with. More than one is normal (contract 01 swaps two matrículas).
    permuta_ativo_ids: tuple[str, ...] = ()


@dataclass
class Favorecido:
    id: str
    nome: str
    cpf_cnpj: Optional[str] = None
    banco: Optional[str] = None
    agencia: Optional[str] = None
    conta: Optional[str] = None
    pix: Optional[str] = None


@dataclass
class Intermediario:
    id: str
    corretor_id: Optional[str]
    nome: str
    creci: Optional[str]
    tipo: str  # "percentual" | "valor_fixo"
    valor: Optional[Decimal]
    #: [§6.1 #22] Which favorecido receives this intermediário's corretagem.
    favorecido_id: Optional[str] = None
    #: [§6.1 #21] Qualification of an EXTERNAL intermediário (no `corretor_id`):
    #: the office's own intermediação is qualified from `Imobiliaria` instead.
    pessoa_tipo: Optional[str] = None  # "pf" | "pj"
    documento: Optional[str] = None  # CPF (11) or CNPJ (14)
    email: Optional[str] = None
    endereco: Endereco = field(default_factory=Endereco)
    representante_nome: Optional[str] = None
    representante_cpf: Optional[str] = None


@dataclass
class AtoCitado:
    kind: str  # "abertura" | "R" | "AV"
    numero: Optional[int]


@dataclass
class Imovel:
    codigo: str
    titulo: Optional[str] = None
    empreendimento: Optional[str] = None
    endereco: Endereco = field(default_factory=Endereco)
    numero_matricula: Optional[str] = None
    numero_registro_imoveis: Optional[str] = None
    inscricao_municipal: Optional[str] = None
    situacao_onus: Optional[str] = None
    onus_certidao_em: Optional[date] = None
    onus_fonte_atos: list[AtoCitado] = field(default_factory=list)
    titulo_aquisitivo_confirmado: bool = False
    #: [§6.1 #8] The operator's CONFIRMED título-aquisitivo wording
    #: (`imovel_dados.titulo_aquisitivo_texto`, migration 115) — never the
    #: recomputed suggestion, which may differ from what was confirmed.
    titulo_aquisitivo_texto: Optional[str] = None
    #: [§6.1 #11] The confirmed creditor of the ônus (`imovel_dados.onus_credor`).
    onus_credor: Optional[str] = None
    #: [Q9] Registration date of the LAST compra e venda on the matrícula.
    #: < 5 years before the assinatura → the previous owner(s) must present
    #: certidões. None = unknown (faltando).
    ultima_transferencia_em: Optional[date] = None
    #: Who sold in that last transfer — so the "add the antigo proprietário"
    #: refusal can NAME them instead of leaving the operator to find them.
    ultima_transferencia_transmitentes: tuple[str, ...] = ()
    #: [§6.1 #14] The imóvel's own certidões (migration 118).
    certidoes: tuple[CertidaoImovel, ...] = ()


@dataclass
class Matricula:
    """The contract's selected acts (`estrutura_service.obter_selecao`)."""

    codigo: Optional[str] = None
    texto: str = ""
    num_atos: int = 0
    #: Bold/underline offsets into `texto` — already re-based by
    #: `obter_selecao` from the extraction's document-level `formatacao`
    #: onto this selection's own concatenated text (contract §5). Empty
    #: for a selection made before the source was (re-)transcribed with
    #: formatting — the quote still renders, just unformatted.
    formatacao: tuple[FormatRange, ...] = ()


@dataclass
class PermutaImovel:
    """[§6.1 #2, #3] One property given in permuta: the `permuta_ativos` row,
    the imóvel behind it, and THAT imóvel's own matrícula quote
    (`obter_selecao()['permutas']`, `papel='permuta'` — migration 115).

    Every printable field is Optional so a half-linked ativo is NAMED by the
    gate rather than rendered with a blank.
    """

    permuta_ativo_id: str
    descricao_matricula: Optional[str] = None
    #: The catalog imóvel's address when the ativo points at one, otherwise the
    #: ativo's OWN address snapshot — a property brought as swap currency is
    #: often not a catalog listing at all (migration 101's `permuta_ativos`
    #: carries its own profile for exactly that case). `contexto` derives the
    #: printed short form; the loader never formats.
    endereco: Endereco = field(default_factory=Endereco)
    inscricao_municipal: Optional[str] = None
    matricula_numero: Optional[str] = None
    cartorio: Optional[str] = None
    #: How many acts this imóvel's quote is built from — 0 = no quote selected.
    num_atos: int = 0


@dataclass
class Financiamento:
    existe: bool = False
    situacao: str = "pendente"
    fgts: bool = False


@dataclass
class Imobiliaria:
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    cnpj: Optional[str] = None
    creci_pj: Optional[str] = None
    responsavel_nome: Optional[str] = None
    responsavel_creci: Optional[str] = None
    email: Optional[str] = None
    endereco: Endereco = field(default_factory=Endereco)
    #: [Q12] The office's posse multa diária (R$ per day of delay), used in
    #: every contract, permuta included. None = not configured (faltando).
    posse_multa_diaria: Optional[Decimal] = None
    #: Digital signing platform named in the assinatura_digital clause
    #: (spec §6.1 #26). None = not configured (faltando).
    plataforma_assinatura_nome: Optional[str] = None
    plataforma_assinatura_url: Optional[str] = None
    #: [Q11] The office's default pendências prazo (days); None → 10.
    prazo_pendencias_padrao_dias: Optional[int] = None


@dataclass
class Testemunha:
    nome: Optional[str]
    rg: Optional[str]
    #: [Q14] Printed under the witness's name and required by the gate.
    cpf: Optional[str] = None


@dataclass
class Termos:
    """`atendimento_negociacao_termos` (migration 114) — the per-deal clauses
    the instrument prints. One row per atendimento; every field nullable,
    because terms are drafted over several sittings.

    🔴 `posse_marco` / `permuta_posse_marco` use the STORAGE vocabulary
    ('assinatura' | 'parcela' | 'protocolo_registro'), and `parcela` NAMES its
    parcela via `*_marco_parcela_id`. The generator prints that parcela's
    computed NUMBER — it never assumes which parcela the marco is.
    """

    posse_prazo_dias: Optional[int] = None
    posse_marco: Optional[str] = None
    posse_marco_parcela_id: Optional[str] = None
    permuta_posse_prazo_dias: Optional[int] = None
    permuta_posse_marco: Optional[str] = None
    permuta_posse_marco_parcela_id: Optional[str] = None
    #: Stored by 114; no sample contract has a clause for it (see module doc).
    permuta_obrigacoes_entrega: Optional[str] = None
    itens_integrantes: Optional[str] = None
    ad_corpus: Optional[bool] = None
    #: Stored by 114; no sample contract has a clause for it (see module doc).
    obrigacoes_vendedor: Optional[str] = None
    #: 'compradores_prazo' | 'interveniente_quitante' | 'parcela' | 'ja_quitado'
    onus_quitacao: Optional[str] = None
    onus_prazo_dias: Optional[int] = None
    confissao_juros_am: Optional[Decimal] = None
    confissao_garantia: Optional[str] = None
    #: 'vendedores' | 'compradores' | 'partes'
    corretagem_contratantes: Optional[str] = None
    corretagem_num_parcelas: Optional[int] = None


@dataclass
class DadosContrato:
    contrato_id: str
    #: The card's titular (`atendimentos.cliente_id`) — what every `faltando`
    #: item's `destino.ids` navigates by. Optional so a synthetic fixture can
    #: omit it; a destino then simply carries no `cliente_id`.
    cliente_id: Optional[str]
    modelo: str
    vendedores: list[Pessoa]
    compradores: list[Pessoa]
    imovel: Optional[Imovel]
    matricula: Matricula
    valor_negociado: Optional[Decimal]
    pct_comissao: Optional[Decimal]
    parcelas: list[Parcela]
    favorecidos: list[Favorecido]
    intermediarios: list[Intermediario]
    financiamento: Financiamento
    imobiliaria: Imobiliaria
    testemunhas: list[Testemunha]
    termos: Termos = field(default_factory=Termos)
    #: The imóveis the `tipo='permuta'` parcela is paid with, in link order.
    #: 🔴 Permuta is driven by that PARCELA (114), not by the legacy
    #: `atendimento_negociacao.permuta_ativo_id` that service marks superseded.
    permuta_imoveis: list[PermutaImovel] = field(default_factory=list)
    #: [Q11] Per-contract pendências prazo (days), overriding the office's
    #: `Imobiliaria.prazo_pendencias_padrao_dias`; None = use that default.
    prazo_pendencias_dias: Optional[int] = None
    #: The signing date STORED on the contract (`atendimento_contratos.
    #: assinatura_data`, migration 114). It wins over "today"; today in
    #: São Paulo stays the fallback (`service.hoje`). An explicit
    #: `assinatura_data` in the POST body still wins over both — that is an
    #: operator asking for a specific date at generation time.
    assinatura_data: Optional[date] = None


#: Papéis that sign the instrument. `fiador`/`outro` are parties to the deal
#: but not to this contract's qualification.
PAPEIS_SIGNATARIOS: frozenset[str] = frozenset(
    {"proprietario", "comprador", "conjuge", "procurador", "inventariante"}
)
#: Papéis whose qualification wording/data does not exist (spec §6.1 #20) —
#: no sample contract carries it, so there is nothing to generate.
PAPEIS_SEM_REDACAO: frozenset[str] = frozenset({"procurador", "inventariante"})


def signatarios(pessoas: list[Pessoa]) -> list[Pessoa]:
    return [p for p in pessoas if p.papel in PAPEIS_SIGNATARIOS]


def parcela_permuta(d: DadosContrato) -> Optional[Parcela]:
    """The deal's permuta parcela (spec §2.3 `tipo == 'permuta'`), or None.

    One per deal: `derivacao` blocks a second one rather than guessing which
    of them the permuta clauses are about.
    """
    permutas = [p for p in d.parcelas if p.tipo == "permuta"]
    return permutas[0] if permutas else None


__all__ = [
    "AtoCitado",
    "Certidao",
    "CertidaoImovel",
    "DadosContrato",
    "Endereco",
    "Favorecido",
    "Financiamento",
    "Imobiliaria",
    "Imovel",
    "Intermediario",
    "Matricula",
    "PAPEIS_SEM_REDACAO",
    "PAPEIS_SIGNATARIOS",
    "Parcela",
    "PermutaImovel",
    "Pessoa",
    "Termos",
    "Testemunha",
    "parcela_permuta",
    "signatarios",
]
