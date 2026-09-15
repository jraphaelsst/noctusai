"""The generator's pure input — every value a contract can print, already read.

`carregador.carregar` fills this from the existing card_hub / matrículas /
certidões / settings services; everything downstream (`derivacao`,
`contexto`, rendering, lint) is pure over it. That split is what lets the
6 variants of spec §1.3 be tested with synthetic fixtures and no database.

`Complementos` is the honest name for spec §6.1: fields the contracts USE and
the system does not HOLD. Production passes an empty `Complementos()` (see
`deps.get_complementos_contrato`), so every switch that needs one of them
reports it as `faltando` — never a blank, never an invented value.
NOC-REMEDIATE[contrato-f6-campos-missing]: each field below moves to real
storage (the F6 data-model slice); the provider then reads it — 2026-09-14

The fields the office's policy answers added (spec §6.2, answered 2026-09-15)
live on the entity they describe — `Pessoa.data_casamento` /
`certidao_estado_civil_emitida_em`, `Certidao.consulta_situacao_cadastral` /
`consulta_data_situacao`, `Imovel.ultima_transferencia_em`, the
`Imobiliaria` office settings and `DadosContrato.prazo_pendencias_dias`. Each
defaults to None = UNKNOWN, so a loader that does not read it yet still builds
a `DadosContrato`; the gate then names it as `faltando`.
NOC-REMEDIATE[contrato-f6-campos-missing]: `carregador` fills these (the F6
wiring slice) — 2026-09-15
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Mapping, Optional

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
    #: None = unreachable, not "none issued": the titular has no parte row,
    #: and certidões are linked by parte (spec §6.1 #18).
    certidoes: Optional[list[Certidao]] = None


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
    #: [Q9] Registration date of the LAST compra e venda on the matrícula.
    #: < 5 years before the assinatura → the previous owner(s) must present
    #: certidões. None = unknown (faltando).
    ultima_transferencia_em: Optional[date] = None


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
class PermutaImovel:
    descricao_matricula: str
    cidade: str
    inscricao_municipal: str
    matricula_numero: str
    cartorio: str
    endereco_curto: str


@dataclass
class Complementos:
    """Spec §6.1 — used by the contracts, not held by the system (see module doc)."""

    titulo_aquisitivo_texto: Optional[str] = None  # §6.1 #8
    itens_integrantes: Optional[str] = None  # §6.1 #9
    ad_corpus: Optional[bool] = None  # §6.1 #10
    onus_credor: Optional[str] = None  # §6.1 #11
    onus_quitacao: Optional[str] = None  # §6.1 #11 compradores_prazo|interveniente_quitante|parcela
    onus_prazo_dias: Optional[int] = None  # §6.1 #11
    posse_prazo_dias: Optional[int] = None  # §6.1 #12
    posse_marco: Optional[str] = None  # §6.1 #12 assinatura|parcela_financiamento|protocolo_registro
    permuta_parcela_valor: Optional[Decimal] = None  # §6.1 #1
    permuta_imoveis: tuple[PermutaImovel, ...] = ()  # §6.1 #2, #3
    permuta_posse_prazo_dias: Optional[int] = None  # §6.1 #12
    permuta_posse_marco: Optional[str] = None  # §6.1 #12
    juros_am_confissao: Optional[Decimal] = None  # §6.1 #6
    garantia_confissao: Optional[str] = None  # §6.1 #6
    corretagem_contratantes: Optional[str] = None  # §6.1 #23 vendedores|partes
    corretagem_parcelas_marco: tuple[int, ...] = ()  # §6.1 #23
    corretagem_num_parcelas: Optional[int] = None  # §6.1 #23
    corretagem_favorecidos: Mapping[str, str] = field(default_factory=dict)  # §6.1 #22
    intermediarios_qualificacao: Mapping[str, str] = field(default_factory=dict)  # §6.1 #21


@dataclass
class DadosContrato:
    contrato_id: str
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
    permuta_ativo_id: Optional[str]
    financiamento: Financiamento
    imobiliaria: Imobiliaria
    testemunhas: list[Testemunha]
    complementos: Complementos = field(default_factory=Complementos)
    #: [Q11] Per-contract pendências prazo (days), overriding the office's
    #: `Imobiliaria.prazo_pendencias_padrao_dias`; None = use that default.
    prazo_pendencias_dias: Optional[int] = None


#: Papéis that sign the instrument. `fiador`/`outro` are parties to the deal
#: but not to this contract's qualification.
PAPEIS_SIGNATARIOS: frozenset[str] = frozenset(
    {"proprietario", "comprador", "conjuge", "procurador", "inventariante"}
)
#: Papéis whose qualification wording/data does not exist (spec §6.1 #20).
PAPEIS_SEM_REDACAO: frozenset[str] = frozenset({"procurador", "inventariante"})


def signatarios(pessoas: list[Pessoa]) -> list[Pessoa]:
    return [p for p in pessoas if p.papel in PAPEIS_SIGNATARIOS]


__all__ = [
    "AtoCitado",
    "Certidao",
    "Complementos",
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
    "Testemunha",
    "signatarios",
]
