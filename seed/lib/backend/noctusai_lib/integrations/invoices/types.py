"""Provider-agnostic invoice vocabulary — the ONE place the enums and DTOs live.

Money is integer cents (`*_cents`), never float; the Focus adapter converts to
reais at the wire boundary only. Dates are `datetime.date` / ISO strings.

Secret-bearing fields (`ProviderCompany.company_token`) are `repr=False` so a
stray `logger.info("%r", company)` can never print them.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class InvoiceKind(str, Enum):
    NFE = "nfe"
    NFSE = "nfse"


class InvoiceStatus(str, Enum):
    PROCESSING = "processing"
    AUTHORIZED = "authorized"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ERROR = "error"


class NfseMode(str, Enum):
    """Which NFS-e channel a company issues through (mutually exclusive)."""

    NACIONAL = "nacional"
    MUNICIPAL = "municipal"


class InvoiceEnvironment(str, Enum):
    HOMOLOGACAO = "homologacao"
    PRODUCAO = "producao"


@dataclass(frozen=True)
class Address:
    street: str = ""
    number: str = ""
    complement: str = ""
    district: str = ""
    city: str = ""
    city_ibge: str = ""
    state: str = ""
    zip_code: str = ""


@dataclass(frozen=True)
class CompanyRequest:
    cnpj: str
    legal_name: str
    trade_name: str = ""
    inscricao_municipal: str = ""
    inscricao_estadual: str = ""
    #: `mei` | `simples` | `simples_excess` | `normal` -> Focus `regime_tributario` 4/1/2/3.
    tax_regime: str = "simples"
    address: Address = field(default_factory=Address)
    email: str = ""
    nfse_mode: NfseMode = NfseMode.NACIONAL
    enable_nfe: bool = False
    #: Provider id of an already-registered company (PUT instead of POST).
    #: ADDITIVE to the contract: Focus has no documented lookup-by-CNPJ, so the
    #: caller (which persisted `ProviderCompany.ref`) passes it back.
    company_ref: Optional[str] = None


@dataclass(frozen=True)
class ProviderCompany:
    ref: str
    cnpj: str
    nfse_mode: NfseMode
    nfe_enabled: bool
    nfse_enabled: bool
    # NO token field, deliberately: a dataclass field is reachable by asdict /
    # pydantic / FastAPI serialization whatever its repr. The provider hands the
    # per-company token straight to the injected `token_sink`
    # (`CompanyTokenStore.sink_for(org_id)`), so it never rides a returned object.


@dataclass(frozen=True)
class CertificateInfo:
    valid_until: datetime.datetime
    #: 14 digits read from the ICP-Brasil e-CNPJ; `None` when the certificate
    #: carries none (e.g. an e-CPF) - the caller treats that as a mismatch.
    subject_cnpj: Optional[str] = None


@dataclass(frozen=True)
class InvoiceTaker:
    name: str
    doc: str  # CPF (11 digits) or CNPJ (14 digits), digits only
    email: str = ""
    address: Address = field(default_factory=Address)


@dataclass(frozen=True)
class InvoiceItem:
    description: str
    quantity: float
    unit_cents: int
    total_cents: int
    service_code: str = ""      # NFS-e: item_lista_servico / national tax code
    nbs_code: str = ""          # NFS-e (RT): codigo_nbs
    cfop: str = ""              # NF-e
    ncm: str = ""               # NF-e
    c_class_trib: str = ""      # NFS-e (RT): IBS/CBS classificacao tributaria


@dataclass(frozen=True)
class InvoiceRequest:
    ref: str
    kind: InvoiceKind
    company_ref: str
    issued_on: datetime.datetime
    competence: datetime.date
    taker: InvoiceTaker
    items: list[InvoiceItem]
    total_cents: int
    iss_rate_bps: int = 0
    iss_retained: bool = False
    #: Reforma Tributaria IBS/CBS block, passed through with provider key names.
    ibs_cbs: Optional[dict[str, Any]] = None
    additional_info: str = ""


@dataclass(frozen=True)
class InvoiceResult:
    ref: str
    kind: InvoiceKind
    status: InvoiceStatus
    number: Optional[str] = None
    series: Optional[str] = None
    access_key: Optional[str] = None
    verification_code: Optional[str] = None
    pdf_url: Optional[str] = None
    xml_url: Optional[str] = None
    rejection_reasons: list[str] = field(default_factory=list)
    #: Provider body with every token-looking value scrubbed.
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class InvoiceEvent:
    ref: str
    kind: Optional[InvoiceKind]
    #: A HINT only (contract 2.6): the handler re-reads via `get()`.
    status_hint: Optional[InvoiceStatus]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
