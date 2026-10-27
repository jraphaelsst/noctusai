"""Default field projections for the Vista families opened on 2026-10-26.

**Why this module exists.** Vista's "full access" grant on key `…644c`
(live-probed 2026-10-26/27) opened families that carry identity-grade
personal data — owners (`proprietarios`: CPF/CNPJ, RG, bank account,
income, spouse), the broker record attached to a client (`CorretorCliente`:
CPF, RG, CNH), deal/visit rows naming the client, and contract rows whose
relation objects embed buyer and owner identities. The grant is a vendor
permission, not a legal basis (`KB § PATTERNS/security/lgpd.md`).

**The rule these constants encode — minimal by default, PII by explicit
ask.** Every consumer (the MCP tools in `mcp/vista/`, any product sync)
starts from the projection below; wider field sets are reachable only by
passing `fields` explicitly, so reading a CPF is always a visible decision at
the call site, never an inherited default. The names are the tenant's REAL
field names from `/<family>/listarcampos` — not the public-doc guesses that
made an earlier note claim "no CPF on this tenant" (the field is `CPFCNPJ`,
not `CPF`).

Kept as module-level tuples (immutable) and shared by Real + Fake consumers.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

#: `/proprietarios/listar` + `/detalhes` — 🔴 identity PII family (149 fields).
DEFAULT_PROPRIETARIO_FIELDS: tuple[str, ...] = ("Codigo", "Nome")

#: `/negocios/listar` — every key is a valid `fields` name (live 2026-10-27).
#: `NomeCliente` / `FotoCliente` (the client's name + photo) are deliberately
#: left out; `CodigoCliente` links to `vista.clientes.get` when needed.
DEFAULT_NEGOCIO_FIELDS: tuple[str, ...] = (
    "Codigo", "NomeNegocio", "Status", "CodigoPipe", "EtapaAtual", "NomeEtapa",
    "DataInicial", "DataFinal", "PrevisaoFechamento", "ValorNegocio",
    "CodigoCliente", "CodigoImovel", "VeiculoCaptacao", "MotivoPerda",
)

#: `/agenda/listar` + `/detalhes` — names from `/agenda/listarcampos` (29).
#: `NomeCliente`, `Texto` and `Local` (free text / third-party names) are
#: opt-in; `Cliente` is the client code. `TipoAtividade` is left out on
#: purpose: `/agenda/listar` accepts it but `/agenda/detalhes` answers a 500
#: for it (live 2026-10-27), and one default must serve both.
DEFAULT_AGENDA_FIELDS: tuple[str, ...] = (
    "Codigo", "Tipo", "Assunto", "Status", "Concluido",
    "DataHora", "DataHoraInicio", "DataHoraFinal", "DiaInteiro",
    "Corretor", "Cliente", "Imovel", "Negocio",
)

#: `prontuarios` relation sub-fields (property history). `Texto`, `Cliente`
#: and `PROPOSTA` are opt-in (free text / client identity / offer terms).
DEFAULT_PRONTUARIO_FIELDS: tuple[str, ...] = (
    "Data", "Hora", "Assunto", "Pendente", "Status", "CodigoCorretor",
)

#: `historicos` relation sub-fields (client history). `Texto` and
#: `ValorProposta` are opt-in. NB: Vista silently omits `Data` here.
DEFAULT_HISTORICO_CLIENTE_FIELDS: tuple[str, ...] = (
    "Data", "Hora", "Assunto", "Pendente", "Codigoimovel", "VeiculodeCaptacao",
)

#: `/contratos/listar` — the server IGNORES `fields`, so this projection is
#: applied client-side by `project_contrato`. Excluded by default: the
#: relation objects `Clientes`, `Proprietarios`, `Corretores`, `Agencias`,
#: `Anexos` (identities) and `OBS` (free text).
DEFAULT_CONTRATO_FIELDS: tuple[str, ...] = (
    "CODIGO", "NUMERO_CONTRATO", "SEQUENCIA_VENDA", "ANO", "DATA_CONTRATO",
    "STATUS", "TIPO", "IMOVEL", "CORRETOR",
    "VLR_VENDA", "VLR_ENTRADA", "VLR_COMISSAO", "VLR_COMISSAO_CORRETOR",
    "TOTAL_COMISSAO", "PERC_COMISSAO", "PERC_IMOB", "PERC_CORRETOR",
    "NUM_PARC", "VLR_TOTAL_PARC", "VLR_PARC_IMOB", "VLR_PARC_CORRET",
)

#: Identity-grade PII names the `clientes` catalog exposes on `oneconsu-rest`
#: (`/clientes/listarcampos`, 2026-10-26). None may ever enter
#: `CANDIDATE_CLIENTE_FIELDS` — that list is both the calibration superset AND
#: the default projection of `vista.clientes.*`; pinned by a test.
CLIENTE_IDENTITY_PII_FIELDS: tuple[str, ...] = (
    "CPFCNPJ", "RG", "RGEmissor", "RGDataExpedicao", "CNH",
    "Banco", "Agencia", "Conta",
    "EmailResidencial", "EmailComercial", "EnderecoResidencial", "EnderecoComercial",
    "CEPResidencial", "FoneResidencial", "FoneComercial",
    "NomeConjuge", "CPFConjuge", "RGConjuge",
)


def resolve_fields(
    explicit: Optional[Iterable[Any]], default: Iterable[Any]
) -> list[Any]:
    """`explicit` when the caller asked for fields, else the minimal default."""
    return list(explicit) if explicit else list(default)


def project_contrato(
    row: dict, fields: Optional[Iterable[str]] = None
) -> dict:
    """Client-side projection of one `/contratos/listar` row.

    Vista ignores `fields` on this route, so minimisation can only happen
    here. Unknown names are skipped (not invented as null).
    """
    keep = list(fields) if fields else list(DEFAULT_CONTRATO_FIELDS)
    return {k: row[k] for k in keep if k in row}


__all__ = [
    "DEFAULT_PROPRIETARIO_FIELDS",
    "DEFAULT_NEGOCIO_FIELDS",
    "DEFAULT_AGENDA_FIELDS",
    "DEFAULT_PRONTUARIO_FIELDS",
    "DEFAULT_HISTORICO_CLIENTE_FIELDS",
    "DEFAULT_CONTRATO_FIELDS",
    "CLIENTE_IDENTITY_PII_FIELDS",
    "resolve_fields",
    "project_contrato",
]
