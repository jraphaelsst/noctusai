"""Pydantic schemas — MCP tool I/O only.

Showcase DTOs (`ShowcaseImovel`, `ShowcaseUsuario`, `ShowcaseAgencia`,
`ShowcaseImovelDetalhes`) live in `noctusai_lib.integrations.vista`
(formalized 2026-05-03). This module keeps only the MCP-tool-specific
input/output schemas — one pair per tool descriptor. `Field(description=...)`
on every property so MCP introspection surfaces help text automatically
(per `KB § PATTERNS/mcp-tool-conventions.md` § 2).

Output models start minimal (`items: list[dict]`) per the convention doc;
tighten as call sites stabilize.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ─── Tool I/O schemas ────────────────────────────────────────────────────


class ListImoveisInput(BaseModel):
    page: int = Field(1, ge=1, description="Page number (Vista paginates at quantidade=50 max).")
    page_size: int = Field(50, ge=1, le=50, description="Page size (Vista server-side cap is 50).")
    status: Optional[str] = Field(None, description="Vista Status filter (e.g. 'Venda', 'Aluguel', 'Venda e Aluguel'). Use vista.imoveis.list_filters to discover live values.")
    categoria: Optional[str] = Field(None, description="Vista Categoria filter (e.g. 'Casa', 'Apartamento', 'Terreno').")
    cidade: Optional[str] = Field(None, description="Vista Cidade filter. Note: tenant has casing duplicates (vista.md § 4.1).")
    bairro: Optional[str] = Field(None, description="Vista Bairro filter.")
    finalidade: Optional[str] = Field(None, description="Vista Finalidade filter (e.g. 'Residencial').")


class ListImoveisOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="ShowcaseImovel-shaped objects.")
    pagination: dict = Field(default_factory=dict, description="{total, paginas, pagina, quantidade}.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class GetImovelInput(BaseModel):
    codigo: str = Field(..., description="Vista primary id, e.g. 'CA2830'.")


class GetImovelOutput(BaseModel):
    item: Optional[dict] = Field(None, description="ShowcaseImovelDetalhes-shaped object, or null if not found.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListImoveisFiltersOutput(BaseModel):
    filters: dict[str, list[str]] = Field(default_factory=dict, description="Enum values per field ({Status, Categoria, Cidade, Bairro}).")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListUsuariosOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="ShowcaseUsuario-shaped objects.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


class ListAgenciasOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="ShowcaseAgencia-shaped objects.")
    probe_status: str = Field("live_probed", description="One of live_probed | doc_only | referenced.")


# ─── 🔒 Gated families (vista.md § 4.2 / § 4.5) ──────────────────────────
#
# Same I/O shape as the ungated tools above — deliberately. These were stubs
# until 2026-08-19: the input model declared `page`/`page_size` that the
# handler never forwarded, and the outputs carried no field descriptions and
# no pagination envelope. Keeping the two halves the same shape is what stops
# the gated half from quietly rotting while it waits for a grant.


class ListClientesInput(BaseModel):
    page: int = Field(1, ge=1, description="Page number (Vista paginates at quantidade=50 max).")
    page_size: int = Field(50, ge=1, le=50, description="Page size (Vista server-side cap is 50).")


class GetClienteInput(BaseModel):
    codigo: str = Field(..., description="Vista client id, sent as the top-level `cliente=` param (NOT inside `pesquisa`).")


class ListCorretoresInput(BaseModel):
    page: int = Field(1, ge=1, description="Page number (Vista paginates at quantidade=50 max).")
    page_size: int = Field(50, ge=1, le=50, description="Page size (Vista server-side cap is 50).")


class ListClientesOutput(BaseModel):
    """Permission-gated. Returns empty items + a typed_error when the tenant lacks permission."""
    items: list[dict] = Field(default_factory=list, description="Raw Vista cliente rows. NOT normalized to a Showcase DTO — no 200 has ever been observed on this tenant, so there is no live payload to write a normalizer against (vista.md § 4.2).")
    pagination: dict = Field(default_factory=dict, description="{total, paginas, pagina, quantidade} — empty while the family is 401-gated.")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} when the tenant key lacks the grant. `message` is key-redacted at the client boundary (vista.md § 3).")
    probe_status: str = Field("permission_gated", description="One of live_probed | permission_gated | write_only | absent. Flips to live_probed on the first 200.")


class GetClienteOutput(BaseModel):
    """Permission-gated per-client detail. LGPD: carries CPF / address / phones on a 200."""
    item: Optional[dict] = Field(None, description="Raw Vista cliente detail row, or null when gated/not found.")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} when the tenant key lacks the grant.")
    probe_status: str = Field("permission_gated", description="One of live_probed | permission_gated | write_only | absent.")


class ListCorretoresOutput(BaseModel):
    """Broker roster — same list shape as every other family."""
    items: list[dict] = Field(default_factory=list, description="Raw Vista corretor rows. Since the 2026-10-26 grant Vista returns ONLY {Codigo, Nome} here regardless of `fields`; richer broker data lives in `vista.usuarios.list` (Setor='Corretores').")
    pagination: dict = Field(default_factory=dict, description="{total, paginas, pagina, quantidade} — mapped from Vista's new `meta` {totalItems, totalPages, currentPage, itemsPerPage}.")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} on failure. A VistaPermissionDenied (401) now means the 2026-10-26 grant was ROLLED BACK.")
    probe_status: str = Field("live_probed", description="One of live_probed | permission_gated | write_only | absent.")


# ─── Families opened by the 2026-10-26 grant (raw rows, LGPD-minimal) ─────

_PAGE = Field(1, ge=1, description="Page number.")
_PAGE_SIZE = Field(50, ge=1, le=50, description="Page size (Vista rejects quantidade > 50 with a 400).")


class RawListOutput(BaseModel):
    """Generic list result: raw Vista rows + the shared pagination vocabulary."""
    items: list[dict] = Field(default_factory=list, description="Raw Vista rows, projected to the requested (or minimal default) fields.")
    pagination: dict = Field(default_factory=dict, description="{total, paginas, pagina, quantidade} when Vista reports them; empty for routes that do not page.")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} on failure — key-redacted at the client boundary. ValueError = the request was refused before any call.")
    probe_status: str = Field("live_probed", description="One of live_probed | permission_gated | write_only | absent.")


class RawGetOutput(BaseModel):
    """Generic single-record result."""
    item: Optional[dict] = Field(None, description="The raw Vista record, or null on failure / not found.")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} on failure.")
    probe_status: str = Field("live_probed", description="One of live_probed | permission_gated | write_only | absent.")


class ListNegociosOutput(RawListOutput):
    valor_total: Optional[str] = Field(None, description="Vista's `valorTotal` sibling — the sum of ValorNegocio over the WHOLE scoped result (not just this page).")


class ListNegociosInput(BaseModel):
    codigo_pipe: Optional[str] = Field(None, description="Pipeline code (e.g. '1', '2'). Exactly ONE of codigo_pipe / codigo_cliente is required — Vista answers an empty body when both are sent.")
    codigo_cliente: Optional[str] = Field(None, description="Client code — list that client's deals. Exactly ONE of codigo_pipe / codigo_cliente.")
    fields: Optional[list[str]] = Field(None, description="Deal fields to return. Default is a minimal set WITHOUT the client's name/photo (NomeCliente, FotoCliente are opt-in — personal data). Unknown names → 400.")
    order: Optional[dict[str, str]] = Field(None, description="Vista order, e.g. {\"Codigo\": \"desc\"}.")
    page: int = _PAGE
    page_size: int = _PAGE_SIZE


class GetNegocioInput(BaseModel):
    codigo: str = Field(..., description="Deal code, sent as the top-level `codigo_negocio=` param.")
    fields: Optional[list[str]] = Field(None, description="Fields to return; default = the minimal deal projection.")


class ListPipesInput(BaseModel):
    empresa: str = Field("1", description="Agency (Empresa) code — mandatory for Vista; `1` on oneconsu-rest (see vista.agencias.list).")


class ListAgendaInput(BaseModel):
    fields: Optional[list[str]] = Field(None, description="Activity fields (catalog: vista.diagnostics.list_fields family='agenda'). Default omits NomeCliente / Texto / Local — opt in explicitly (personal data / free text).")
    filter: Optional[dict[str, Any]] = Field(None, description="Vista filter, e.g. {\"DataHora\": [\">=\", \"2026-10-01\"]} (proven live 2026-10-27).")
    order: Optional[dict[str, str]] = Field(None, description="Vista order, e.g. {\"DataHora\": \"desc\"}.")
    page: int = _PAGE
    page_size: int = _PAGE_SIZE


class GetAgendaInput(BaseModel):
    codigo: str = Field(..., description="Activity code, sent as the top-level `codigo=` param.")
    fields: Optional[list[str]] = Field(None, description="Fields to return; default = the minimal agenda projection. NB: `TipoAtividade` is a 500 on this route.")


class ListProprietariosInput(BaseModel):
    fields: Optional[list[str]] = Field(None, description="🔴 LGPD: default is ONLY {Codigo, Nome}. Owner rows carry CPFCNPJ, RG, bank account, income and spouse data — request such a field ONLY by naming it here, and only when the task needs it. Catalog: vista.diagnostics.list_fields family='imoveis' → `proprietarios` relation.")
    page: int = _PAGE
    page_size: int = _PAGE_SIZE


class GetProprietarioInput(BaseModel):
    codigo: str = Field(..., description="Owner code, sent as the top-level `codigo=` param.")
    fields: Optional[list[str]] = Field(None, description="🔴 LGPD: default is ONLY {Codigo, Nome}; any identity/bank field must be named explicitly.")


class ListContratosInput(BaseModel):
    fields: Optional[list[str]] = Field(None, description="Keys to keep (UPPERCASE, e.g. CODIGO, IMOVEL, VLR_VENDA). Vista ignores projections on this route, so this is applied CLIENT-SIDE. Default drops OBS and the relation objects Clientes / Proprietarios / Corretores / Agencias / Anexos (personal data) — name them to include.")


class ListDestaquesInput(BaseModel):
    fields: Optional[list[str]] = Field(None, description="Listing fields, e.g. ['Codigo', 'TituloSite']. Default ['Codigo']; `CodigoImovel` always comes back (and is a 400 if requested).")
    page: int = _PAGE
    page_size: int = _PAGE_SIZE


class FinalidadesOutput(BaseModel):
    finalidades: list[str] = Field(default_factory=list, description="Live finalidade values, e.g. ['Venda', 'Aluguel'].")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} on failure.")
    probe_status: str = Field("live_probed", description="One of live_probed | permission_gated | write_only | absent.")


class HistoryInput(BaseModel):
    codigo: str = Field(..., description="Imóvel code (vista.imoveis.history) or client code (vista.clientes.history).")
    fields: Optional[list[str]] = Field(None, description="History-entry sub-fields (catalog: the `prontuarios` / `historicos` relation in vista.diagnostics.list_fields). Default omits `Texto` and client/offer details — opt in explicitly. `Codigo` is NOT a valid sub-field.")
    offset: int = Field(0, ge=0, description="Client-side window start — Vista returns the WHOLE history at once (hundreds of entries).")
    limit: int = Field(50, ge=1, le=500, description="Client-side window size.")


class HistoryOutput(BaseModel):
    items: list[dict] = Field(default_factory=list, description="History entries in Vista's order, windowed by offset/limit.")
    total: int = Field(0, description="Total entries Vista returned before windowing.")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} on failure.")
    probe_status: str = Field("live_probed", description="One of live_probed | permission_gated | write_only | absent.")


class ListClienteFiltersInput(BaseModel):
    fields: list[str] = Field(default_factory=lambda: ["Status", "Interesse", "VeiculoCaptacao"], min_length=1, description="Client fields to enumerate distinct values for (`Codigo` is a 400).")


class ListFieldsInput(BaseModel):
    family: Literal["imoveis", "clientes", "usuarios", "agencias", "agenda"] = Field(..., description="Family whose `/<family>/listarcampos` catalog to read. Owner fields are the `proprietarios` relation of 'imoveis'; there is no catalog route for negocios / contratos / corretores / proprietarios / pipes.")


class ListFieldsOutput(BaseModel):
    family: str = Field("", description="The family queried.")
    fields: dict[str, list[str]] = Field(default_factory=dict, description="{\"<family>\": [field...], \"<Relation>\": [sub-field...]} — the tenant's REAL field names; use them for any `fields` argument and for relation sub-fields.")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status} on failure.")
    probe_status: str = Field("live_probed", description="One of live_probed | permission_gated | write_only | absent.")


# ─── ✍️ Writes (vista.md § 4.7) ─────────────────────────────────────────────


class AddImovelFotosInput(BaseModel):
    codigo: str = Field(..., description="Vista imóvel code, e.g. 'CA2830'. Sent as the top-level `imovel=` param.")
    fotos: dict[str, str] = Field(..., min_length=1, description="Keyed map of distinct labels → PUBLIC http(s) image URLs, e.g. {\"foto1\": \"https://…/a.jpg\"}. Vista downloads each URL itself; no bytes, no base64, no arrays.")


class SubmitLeadInput(BaseModel):
    nome: str = Field(..., min_length=1, description="Lead's name.")
    mensagem: str = Field(..., min_length=1, description="The lead's message / what they asked.")
    veiculo: str = Field(..., min_length=1, description="Lead source shown to the agency (site, portal, campaign name).")
    email: Optional[str] = Field(None, description="Lead e-mail. `email` or `fone` is required.")
    fone: Optional[str] = Field(None, description="Lead phone. `email` or `fone` is required. Vista de-duplicates existing clients on it.")
    anuncio: Optional[str] = Field(None, description="Imóvel code the lead is about. NOT validated by Vista — pass a real code.")
    interesse: Optional[str] = Field(None, description="Interest, e.g. 'Venda' or 'Locação'.")


class WriteOutput(BaseModel):
    """Result of a CRM write. Exactly one of `result` / `typed_error` is set."""
    result: Optional[dict] = Field(None, description="Vista's response body. For photos, read `Fotos.<key>` per photo — a 207 means some keys failed and created nothing.")
    http_status: Optional[int] = Field(None, description="200 = all ok; 207 = partial (photos).")
    typed_error: Optional[dict] = Field(None, description="{error_class, message, status}. VistaPermissionDenied = the key lacks the method grant (ask Vista, do not retry); WritesDisabled = VISTA_MCP_ALLOW_WRITES is off; ValueError = the payload was rejected before any request.")


class WritePermissionsOutput(BaseModel):
    probes: list[dict] = Field(default_factory=list, description="One row per write route: {endpoint, verdict, http_status, expected_verdict, as_expected, note}. verdict ∈ permitted | denied | absent | unknown | not_configured.")
    configured: bool = Field(False, description="True iff base_url + api_key are set.")
    unexpected: list[str] = Field(default_factory=list, description="Routes whose verdict differs from the recorded baseline — e.g. `/imoveis/fotos` flipping to permitted means Vista's grant has landed.")
    writes_enabled: bool = Field(False, description="Whether this MCP process allows the write tools (VISTA_MCP_ALLOW_WRITES).")


class ProbeOutput(BaseModel):
    probes: list[dict] = Field(default_factory=list, description="One row per PROBE_ENDPOINTS entry: {endpoint, status, http_status, latency_ms, expected_http_status, as_expected, note}. Read `as_expected` — NOT `status` — to decide whether a row needs attention: several endpoints answer a bare GET with 400/401/405 by design.")
    tenant_base_url: str = Field("", description="The base URL the probe was issued against.")
    configured: bool = Field(False, description="True iff VistaClient saw both base_url + api_key.")
    unexpected: list[str] = Field(default_factory=list, description="Endpoints whose http_status differed from the documented baseline — the only rows an operator must act on. Empty means the tenant matches vista.md § 4.")


class CalibratedFieldsOutput(BaseModel):
    """Reports the per-tenant field-set the calibration routine discovered.

    Phase 1 ships this as a passthrough of the hardcoded constants — the
    real calibration routine in `calibration.py` runs lazily on first
    real call and updates these on the fly.
    """
    imoveis_list: list[Any] = Field(default_factory=list)
    imoveis_detail: list[Any] = Field(default_factory=list)
    imoveis_conteudo: list[str] = Field(default_factory=list)
    usuarios: list[str] = Field(default_factory=list)
    agencias: list[str] = Field(default_factory=list)
    clientes: list[str] = Field(default_factory=list, description="🔒 Gated — stays empty while the tenant answers 401 (a permission denial is deliberately not cached).")
    corretores: list[str] = Field(default_factory=list, description="Not calibrated since 2026-10-27 — `/corretores/listar` ignores `fields` and always returns Codigo + Nome. Stays empty.")
    rejected: dict[str, list[str]] = Field(default_factory=dict, description="Per-endpoint list of fields probed and rejected during calibration.")
    calibrated_at: Optional[str] = Field(None, description="ISO timestamp of last calibration run; null if no probe has run.")


__all__ = [
    "ListImoveisInput",
    "ListImoveisOutput",
    "GetImovelInput",
    "GetImovelOutput",
    "ListImoveisFiltersOutput",
    "ListUsuariosOutput",
    "ListAgenciasOutput",
    "ListClientesInput",
    "ListClientesOutput",
    "GetClienteInput",
    "GetClienteOutput",
    "ListCorretoresInput",
    "ListCorretoresOutput",
    "RawListOutput",
    "RawGetOutput",
    "ListNegociosInput",
    "ListNegociosOutput",
    "GetNegocioInput",
    "ListPipesInput",
    "ListAgendaInput",
    "GetAgendaInput",
    "ListProprietariosInput",
    "GetProprietarioInput",
    "ListContratosInput",
    "ListDestaquesInput",
    "FinalidadesOutput",
    "HistoryInput",
    "HistoryOutput",
    "ListClienteFiltersInput",
    "ListFieldsInput",
    "ListFieldsOutput",
    "AddImovelFotosInput",
    "SubmitLeadInput",
    "WriteOutput",
    "WritePermissionsOutput",
    "ProbeOutput",
    "CalibratedFieldsOutput",
]
