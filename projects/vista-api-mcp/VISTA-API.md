# Vista CRM API — Authoritative Reference (NoctusAI)

> **Purpose.** This is NoctusAI's authoritative reference for the Vista Software /
> Loft CRM REST API. It folds three sources into one document so we never
> re-derive what we already know:
>
> 1. **Public docs** at `https://vistasoft.com.br/api/` (deep-documents
>    `/imoveis` + `/clientes` only; other families appear in the navigation but
>    have no spec).
> 2. **Live probe results** against the user's tenant
>    `oneconsu-rest.vistahost.com.br` captured in
>    `PROJECT.md § Discovery results` (2026-05-01).
> 3. **Adapter behavior** as implemented in
>    `products/erp-imobiliario/backend/app/integrations/vista/`.
>
> **Future MCP intent.** The user's directive (2026-05-02) is to spin off this
> document into a dedicated MCP branch that exposes Vista as a typed tool.
> Keep the structure normalized: every endpoint row is a tuple `(method, path,
> id-param, fields-witnessed, status-on-this-tenant, status-on-public-docs,
> caveats)`. An MCP author can map this 1:1 to tool definitions without
> re-reading the public docs.
>
> **Status legend** — used per endpoint and per field:
>
> - ✅ **live-200** — confirmed reachable on this tenant; fields verified.
> - 🔒 **live-401** — endpoint exists but this tenant's key is unauthorized.
>   The MCP target tenant may have permission.
> - ❌ **live-404** — endpoint not exposed on this tenant. Public docs may
>   advertise it; a different subscription tier may expose it.
> - 📖 **doc-only** — appears in public docs (vistasoft.com.br/api) but never
>   live-probed because we don't need it yet.
> - ❓ **referenced** — mentioned in public-doc nav with no spec body. We have
>   not probed it. An MCP that targets a tenant with permission MUST verify
>   the shape before relying on it.

---

## 1. Authentication

| Item | Value |
|---|---|
| Auth method | Single API key per tenant, sent as `?key=<API_KEY>` query param on every request |
| Required header | `Accept: application/json` |
| Bearer / OAuth / cookie | **Not used** |
| Tenant URL shape | `https://<tenant-slug>-rest.vistahost.com.br` (this tenant: `oneconsu-rest.vistahost.com.br`) |

Where the key lives in NoctusAI:

- Backend `.env` (root, gitignored): `VISTA_BASE_URL`, `VISTA_API_KEY`.
- Read into Python at startup via `ERPSettings.vista_base_url` / `vista_api_key`.
- **Never** prefixed with `VITE_` — the browser must never see the key. The
  frontend calls `/api/vista-showcase/*` and the ERP backend proxies upstream.

If the key is missing the adapter raises a typed error at request time (not at
import time, per the FastAPI dep-factory pattern in
`KB § PATTERNS/backend.md § FastAPI dependency factories with module-level
injection`). This keeps the router import-safe.

---

## 2. Query convention — the `pesquisa` parameter

Most endpoints take a single `pesquisa=<URL-encoded JSON>` query parameter
carrying a structured request:

```json
{
  "fields": ["Codigo", "Cidade", {"Corretor": ["Nome", "Email"]}],
  "filter": {"Bairro": "Centro", "ValorVenda": [250000, 500000]},
  "advFilter": {"Or": {...}, "And": {...}},
  "order": {"DataAtualizacao": "desc"},
  "paginacao": {"pagina": 1, "quantidade": 50}
}
```

### `fields`

Array of strings (column names) plus optional nested-relation objects of the
shape `{"<RelationName>": ["SubField1", "SubField2"]}`. Documented nested
relations:

- `Corretor` → `Nome`, `Fone`, `Email`, `Creci`
- `Agencia` → `Nome`, `Fone`, `Endereco`, `Numero`, `Complemento`, `Bairro`, `Cidade`
- `fotos` (on `/imoveis/listar`) → `Foto`, `FotoPequena`, `Destaque`, `Tipo`, `Descricao`

> **Public-doc warning.** "Caso você não informe os campos que quer utilizar, a
> API retornará apenas o código." — without explicit `fields`, only the primary
> id comes back. Always pass `fields` explicitly.

> **Per-field permissions.** A field absent from `fields` is silently skipped.
> A field that the tenant's key cannot read returns `400 "Campo X não está
> disponível"` — see Phase 1 results for `/usuarios` and `/agencias`. The MCP
> tool must surface this as a typed `VistaFieldNotAvailable` error.

### `filter` operators

| Operator | Shape | Meaning |
|---|---|---|
| equality | `{"Bairro": "Centro"}` | exact match |
| range | `{"ValorVenda": [250000, 500000]}` | between (inclusive of bounds, per public-doc examples) |
| comparison | `{"ValorVenda": [">", 250000]}` | `>`, `<`, `>=`, `<=`, `like`, `!=` |
| list | `{"Status": ["ATIVO", "DISPONIVEL"]}` | IN — semantics confirmed empirically; tested against `/imoveis/listar` |

### `paginacao`

```json
{"pagina": 1, "quantidade": 50}
```

- `quantidade` max is **50** (server-side cap, confirmed live).
- Add `&showtotal=1` (top-level query, not inside `pesquisa`) to receive
  `total` and `paginas` in the response envelope.

### `order`

```json
{"DataAtualizacao": "desc"}
```

Object whose keys are field names and whose values are `"asc"` / `"desc"`.

### `advFilter`

Nested boolean composition with `And` / `Or`. Public docs are thin on this;
treat as power-user. Our adapter does not expose it in v1.

### Top-level (NOT inside `pesquisa`) parameters

Some endpoints require ID parameters at the top level, **not** inside
`pesquisa`. Confirmed live:

| Endpoint | Top-level param | Example |
|---|---|---|
| `/imoveis/detalhes` | `imovel=<Codigo>` | `?imovel=CA2830&pesquisa=...&key=...` |
| `/clientes/detalhes` 🔒 | `cliente=<Codigo>` | (per public docs; not live-verified) |
| `/imoveis/fotos` 🔒 | `imovel=<Codigo>` | (per public docs; not live-verified) |
| `/imoveis/anexos` ❓ | `imovel=<Codigo>` | (per public docs) |
| `/imoveis/historicos` ❓ | `imovel=<Codigo>` | (per public docs) |

Always URL-encode values containing whitespace (e.g. `"Porto Alegre"` →
`Porto+Alegre` or `Porto%20Alegre`).

---

## 3. Response envelope

### Collection responses (`/imoveis/listar`, `/usuarios/listar`, etc.)

The response is **a top-level dict keyed by primary id**, with pagination
metadata as **sibling keys**, NOT a JSON array:

```json
{
  "CA2830": {"Codigo": "CA2830", "Cidade": "Cotia", ...},
  "TE0080": {"Codigo": "TE0080", "Cidade": "Cotia", ...},
  "total": 1784,
  "paginas": 595,
  "pagina": 1,
  "quantidade": 3
}
```

Normalizers must dict-iterate, **filtering out** the pagination keys
(`total`, `paginas`, `pagina`, `quantidade`). The adapter exposes a helper
`extract_items(response, pagination_keys=...)` that returns
`(items: list[dict], pagination: PaginationMeta)`.

> **Public-doc claim mismatch.** Public docs print
> `{"results": [...], "total": ..., "pagina": ..., ...}`. The live tenant does
> NOT use `results: [...]` — items are top-level keys. Trust the live shape.

### Detail responses (`/imoveis/detalhes`)

Returns a flat object keyed by field, e.g.

```json
{
  "Codigo": "CA2830",
  "Cidade": "Cotia",
  "Caracteristicas": {"Piscina": "Sim", ...},
  ...
}
```

### Error responses

| HTTP | Body shape | Meaning |
|---|---|---|
| 200 | normal | OK |
| 400 | `{"campo": "X não está disponível"}` (variant phrasings) | Field-level permission denied or unknown field |
| 401 | `{"mensagem": "Permissão Negada"}` | Endpoint exists; key lacks permission |
| 404 | typically empty / Vista 404 page | Endpoint not exposed on this tenant |

The adapter typifies these as:

- `VistaConfigError` — missing/empty base URL or API key (raised at request time)
- `VistaUpstreamError(status: int, body: str)` — generic 5xx + 4xx wrapper
- `VistaFieldNotAvailable(field: str, endpoint: str)` — 400 with the
  "não está disponível" pattern
- `VistaPermissionDenied(endpoint: str)` — 401 with "Permissão Negada"
- `VistaNotFound(endpoint: str)` — 404
- `VistaTimeout(endpoint: str)` — `httpx.TimeoutException`

---

## 4. Endpoint inventory

### 4.1 `/imoveis` (Properties)

| Op | Method | Path | ID param | This tenant | Public docs | Notes |
|---|---|---|---|---|---|---|
| List | GET | `/imoveis/listar` | — | ✅ | 📖 | 1,784 properties on this tenant. |
| Detail | GET | `/imoveis/detalhes` | `?imovel=` | ✅ | 📖 | `Foto` field NOT available on detalhes — use `Foto` from listar instead. |
| List enum content | GET | `/imoveis/listarConteudo` | — | ✅ | ❓ | Returns enum values for fields like `Status`, `Categoria`, `Cidade`, `Bairro`. Drives filter dropdowns. |
| Photos | GET | `/imoveis/fotos` | `?imovel=` | ❌ | 📖 | Re-probed 2026-05-02: live tenant returns 404 ("No route found"), NOT 401 — the endpoint isn't enabled for this subscription tier. Workaround: `Foto` field in `/imoveis/listar`. |
| Documents | GET | `/imoveis/anexos` | `?imovel=` | ❓ | 📖 | Not probed. |
| History | GET | `/imoveis/historicos` | `?imovel=` | ❓ | 📖 | Public-doc spelling is `historicos`; we also tried `historico` → 404. |
| Available fields | GET | `/imoveis/campos` | — | ❓ | 📖 | Returns field-name reference. Not probed. |
| Create | POST | `/imoveis/cadastrar` | — | ❓ | 📖 | Out of scope (read-only v1). |
| Update | PUT | `/imoveis/alterar` | `?imovel=` | ❓ | 📖 | Out of scope. |
| Add photo | POST | `/imoveis/cadfoto` | `?imovel=` | ❓ | 📖 | Out of scope. |
| Add doc | POST | `/imoveis/caddoc` | `?imovel=` | ❓ | 📖 | Out of scope. |
| Add history | POST | `/imoveis/cadhis` | `?imovel=` | ❓ | 📖 | Out of scope. |
| Register owner | POST | `/imoveis/cadprop` | `?imovel=` | ❓ | 📖 | Out of scope. |
| Assign broker | POST | `/imoveis/cadcor` | `?imovel=` | ❓ | 📖 | Out of scope. |
| Search variants | GET | `/imoveis/buscar`, `/imoveis/pesquisar`, `/imoveis/proximos`, `/imoveis/destaque` | — | ❌ | — | Not on this tenant; not in public docs. |

#### Confirmed `/imoveis/listar` field set (this tenant) — **RE-CALIBRATED 2026-05-02**

The earlier table listed several fields as available that this tenant's
key actually rejects with HTTP 400 (`Campo X não está disponível`). The
cause was Phase 1's smoke probe never tested the full field bundle in
one request. Live discovery on 2026-05-02 produced the corrected list
below.

✅ **Available** (29 fields, request these):

```
Codigo            string   primary id (e.g. "CA2830", "ONE10006")
TituloSite        string   marketing title
Categoria         string   property type (e.g. "Casa", "Casa em Condomínio", "Terreno")
Status            string   listing status — values "Venda" / "Aluguel" / "Venda e Aluguel"
Finalidade        string   sometimes empty; "Residencial" when populated
Empreendimento    string   development name (nullable)
Construtora       string   builder name (nullable)
Cidade            string
Bairro            string
Endereco          string
Numero            string
Complemento       string
CEP               string
UF                string   two-letter state ("SP")
Latitude          string   decimal as string
Longitude         string   decimal as string
ValorVenda        string   decimal as string ("2350000")
ValorLocacao      string   decimal as string
AreaTotal         string   m² as string
AreaPrivativa     string
AreaConstruida    string
Dormitorios       string   integer as string
Suites            string
Vagas             string
BanheiroSocial    string   "Sim" / "Nao" — NOT a count; aggregate `Banheiros` is denied
Caracteristicas   object   nested boolean/text features (returned in detalhes, not always in listar)
DataCadastro      string   ISO-ish, space separator
DataAtualizacao   string
FotoDestaque      string   primary photo URL (the only photo field this tenant exposes)
Corretor          object   nested dict keyed-by-corretor-id: {"103": {"Codigo": "...", "Nome": "..."}}
                            — NOT a flat {"Nome": "..."} object on this tenant
```

🔒 **Rejected** by this tenant's API key (HTTP 400 if requested):
`Estado` (use `UF` instead), `Banheiros` (use `BanheiroSocial`),
`Foto` (use `FotoDestaque`), `FotoPrincipal`, `Slug`, `PalavrasChave`,
`CodigoImobiliaria`. Note: `CodigoImobiliaria` is sometimes returned in
the response body even when not requested — but cannot be requested
explicitly.

The reference adapter's `IMOVEL_LIST_FIELDS` constant carries the
calibrated set; future tenants may have different splits and need their
own probe pass.

#### `/imoveis/detalhes` quirks

- Accepts the same `pesquisa.fields` array.
- `Foto` is NOT a valid field here (returns 400). Pull the photo URL from
  `/imoveis/listar` and pass it through.
- `imovel=<Codigo>` MUST be at the top level, not inside `pesquisa`.

#### `/imoveis/listarConteudo` quirks

- `pesquisa.fields=["Status","Categoria","Cidade","Bairro"]` returns enum
  values (one per requested field).
- Useful for populating filter dropdowns without scanning the full catalog.

### 4.2 `/clientes` (Clients) — 🔒 not authorized on this tenant

Documented in public docs, blocked on this tenant's key.

| Op | Method | Path | ID param | This tenant | Public docs |
|---|---|---|---|---|---|
| Search | GET | `/clientes/pesquisar` | — | 🔒 | 📖 |
| List | GET | `/clientes/listar` | — | 🔒 | ❓ |
| By broker | GET | `/clientes/porcorretor` | — | ❓ | 📖 |
| By agency | GET | `/clientes/poragencia` | — | ❓ | 📖 |
| Detail | GET | `/clientes/detalhes` | `?cliente=` | 🔒 | 📖 |
| History | GET | `/clientes/historicos` | `?cliente=` | ❓ | 📖 |
| Favorites | GET | `/clientes/favoritos` | `?cliente=` | ❓ | 📖 |
| Available fields | GET | `/clientes/campos` | — | ❓ | 📖 |
| Create | POST | `/clientes/cadastrar` | — | ❓ | 📖 |
| Update | PUT | `/clientes/alterar` | `?cliente=` | ❓ | 📖 |
| Add history | POST | `/clientes/cadhis` | `?cliente=` | ❓ | 📖 |
| Assign broker | POST | `/clientes/cadcor` | `?cliente=` | ❓ | 📖 |
| Submit lead | POST | `/clientes/lead` | — | ❓ | 📖 |

UI behavior on this tenant: render a "Permissão pendente — solicite expansão
junto à Vista" placeholder and surface the 401 status code. The MCP tool
should surface the same as a typed `VistaPermissionDenied`.

### 4.3 `/usuarios` (internal Vista users) — ✅

| Op | Method | Path | This tenant | Notes |
|---|---|---|---|---|
| List | GET | `/usuarios/listar` | ✅ | 16+ rows on this tenant |

#### Confirmed field set

```
Codigo   string
Nome     string
Email    string
Foto     string   URL
Setor    string   department/team
```

Fields that returned `400 "Campo X não está disponível"` on this tenant:
`Apelido`, `Login`, `FotoPequena`, `DataCadastro`, `CodigoImobiliaria`. Do not
request these unless the tenant key changes.

### 4.4 `/agencias` (agency metadata) — ✅

| Op | Method | Path | This tenant | Notes |
|---|---|---|---|---|
| List | GET | `/agencias/listar` | ✅ | Single row on this tenant: "ONE CONSULTORIA IMOBILIARIA" |

#### Confirmed field set

```
Codigo   string
Nome     string
Endereco string
Cidade   string
Bairro   string
Site     string
```

Fields that returned 400 on this tenant: `Estado`, `UF`, `CEP`, `Telefone`,
`Email`, `Foto`, `Logo`, `Status`, `DataCadastro`. Avoid.

### 4.5 `/corretores` (brokers) — 🔒

Endpoint exists; this tenant's key has no permission. UI placeholder.

### 4.6 Endpoint families NOT exposed on this tenant — ❌

These return 404 here. They are referenced in the public-doc nav, but the
public docs provide no spec. Treat as ❓ for an MCP targeting other tenants:

```
/leads/*                  ❓ (public-doc nav only; doc body empty)
/atendimentos/*           ❓
/agendamentos/*           ❓
/negociacoes/*            ❓
/propostas/*              ❓
/vendas/*                 ❓
/condominios/*            ❓
/empreendimentos/*        ❓
/bairros/*                ❓
/cidades/*                ❓
/categorias/*             ❓
/tabelas/*                ❓
/portais/*                ❓
/ancillary-revenue/*      ❓ (referenced explicitly via the user-supplied
                              link `#fotos_ancillary-revenue`; no body)
/buscas/*                 ❓
/campanhas/*              ❓
/tarefas/*                ❓
/reservas/*               ❓
```

If/when an MCP targets a tenant that exposes any of these, the adapter must
re-probe and add a row above with verified shape.

---

## 5. Adapter contract — what the NoctusAI ERP code does with this

```
ERP backend
├── app/integrations/vista/
│   ├── client.py          # VistaClient(...).list_imoveis(...) etc — typed
│   ├── types.py           # VistaListImovelDTO, VistaUsuarioDTO, …
│   └── normalizers.py     # vista_imovel_to_showcase(payload) → ShowcaseDTO
├── app/services/vista_showcase_service.py
│   # Coordinates per-tab fetch + audit-log write per outbound call
└── app/routers/vista_showcase.py
    # /api/vista-showcase/{tab}, admin-only

ERP frontend
└── pages/VistaShowcase.tsx
    # Single admin-only page with seven sub-tabs (Imóveis, Detalhes,
    # Usuários, Agência, Clientes 🔒, Corretores 🔒, Fotos 🔒,
    # Diagnóstico)
```

### Audit-log contract

Every outbound Vista call writes one row to `erp.user_actions_log`:

```
tipo_acao      = 'consulta_externa'           # added by migration 023
tipo_entidade  = 'integracao_vista'           # added by migration 023
entidade_id    = <Vista record id, e.g. "CA2830", or null on listings>
descricao      = 'GET /imoveis/listar' (or similar)
detalhes       = {tenant, path, params_keys, status, latency_ms}
```

The Vista **response payload itself is never persisted** — `detalhes` carries
only metadata, not field values. This satisfies the LGPD live-read constraint
in `PROJECT.md § Confirmed constraints`.

---

## 6. Future MCP design notes

When this folder spins off into an MCP branch:

1. **Tool surface.** One tool per row in §4 marked ✅ or 🔒 (the 🔒 ones still
   matter — different tenants have permission). Skip ❓ rows until probed.
2. **Auth as MCP secret.** The MCP server reads a per-tenant API key from its
   own config; do not propagate `VISTA_API_KEY` from this repo's `.env`.
3. **Re-use this document as the schema source.** The MCP can codegen tool
   schemas from §4 tables — every row's "ID param", method, path, and
   confirmed-field-set are sufficient to type the request/response.
4. **Error model.** Mirror the typed errors in §3 — the MCP host will see
   them as structured tool-error payloads, not raw 4xx text.
5. **Dict-keyed-by-id response shape** (§3) is unusual; the MCP wrapper
   should always normalize to `items: [...]` + `pagination: {...}` so the
   model never has to re-discover this.
6. **Live-probe gating.** Each MCP tool registers with a `probe_status`
   field — `live_probed | doc_only | referenced` — so a host operator can
   filter to only-known-good tools.

---

## 7. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | Initial authoring. Folded Phase 1 live-probe results, public-doc imoveis/clientes specs, and adapter contract into a single MCP-ready reference. | Claude Opus 4.7 |
| 2026-05-02 | **Re-calibrated `/imoveis/listar` and `/imoveis/detalhes` field sets after live failure.** UI showed `[502] Vista respondeu erro 400` because Phase 1's smoke probe never sent the full field bundle in one request. New live discovery: this tenant rejects `Estado`, `Banheiros`, `Foto`, `FotoPrincipal`, `Slug`, `PalavrasChave`, `CodigoImobiliaria` with HTTP 400. Replacements: `UF` (for `Estado`), `BanheiroSocial` (for `Banheiros`), `FotoDestaque` (for `Foto`). Also discovered: `Corretor` is returned as a dict keyed by corretor id (`{"103": {...}, "104": {...}}`), not a flat `{"Nome": "..."}` object. Adapter constants and normalizer updated; `/imoveis` router now catches `VistaFieldNotAvailable` explicitly (422) so the next field-permission drift surfaces clearly instead of as a generic 502. Verified end-to-end against live tenant: 1,783 properties, 10 users, 1 agency. | Claude Opus 4.7 |
