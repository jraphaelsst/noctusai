# Vista CRM API — Authoritative Reference (NoctusAI)

> **Purpose.** This is NoctusAI's authoritative reference for the Vista Software /
> Loft CRM REST API. It folds three sources into one document so we never
> re-derive what we already know:
>
> 1. **Public docs** at `https://vistasoft.com.br/api/` (deep-documents
>    `/imoveis` + `/clientes` only; other families appear in the navigation but
>    have no spec).
> 2. **Live probe results** against the user's tenant
>    `oneconsu-rest.vistahost.com.br` — most recent re-probe 2026-05-03
>    captured in the §8 change log.
> 3. **Adapter behavior** as implemented in
>    `seed/lib/backend/noctusai_lib/integrations/vista/` (canonical platform
>    home, FORMALIZED 2026-05-03 — both the ERP showcase and the in-repo MCP
>    server consume from there).
>
> **Why this lives in KB.** Project folders (`projects/vista-api-mcp/`) are
> deleted when the project closes; this doc is durable. It is the single
> source of truth for: (a) any future agent walking into Vista work cold,
> (b) the in-repo Vista MCP server build, and (c) the portable repo-root
> `VISTA-API-MCP-GUIDE.md` (re-authored from this doc when the user
> needs to ship it to an external-environment agent).
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
`KB § CONTEXT/PATTERNS/backend/backend.md § FastAPI dependency factories with module-level
injection`). This keeps the router import-safe.

**Client wiring details** (`noctusai_lib/integrations/vista/client.py`):

- **`VistaClient(base_url, api_key, *, timeout_seconds=15.0, http_client=None)`**
  — `__init__` is lenient: it never raises, even on missing/empty config.
  Only `_request()` raises `VistaConfigError`. Callers can construct the
  client at module-import time without a Vista key in the env.
- **`client.configured: bool`** — read-only property. `True` iff both
  `base_url` and `api_key` are non-empty. The router uses this to render
  a "not_configured" tab status without making a Vista call.
- **`DEFAULT_TIMEOUT_SECONDS = 15.0`** — surfaces as HTTP 504 from the
  router (`VistaTimeout` → 504). Constructor takes a `timeout_seconds`
  override.
- **`http_client: Optional[httpx.AsyncClient]`** — injected for tests. If
  `None`, each request opens its own short-lived `httpx.AsyncClient`.

---

## 2. Query convention — the `pesquisa` parameter

Most endpoints take a single `pesquisa=<URL-encoded JSON>` query parameter
carrying a structured request:

```json
{
  "fields": ["Codigo", "Cidade", {"Corretor": ["Nome", "Email"]}],
  "filter": {"Bairro": "Centro", "ValorVenda": [250000, 500000]},
  "advFilter": {"Or": {"...": "..."}, "And": {"...": "..."}},
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

- `quantidade` max is **50** (server-side cap, confirmed live). The
  adapter enforces this client-side too: `listar_imoveis` clamps via
  `min(page_size, DEFAULT_PAGE_SIZE)` (`client.py:216`).
- Add `&showtotal=1` (top-level query, not inside `pesquisa`) to receive
  `total` and `paginas` in the response envelope. **The adapter only
  sends this on `/imoveis/listar`** (where `listar_imoveis` passes
  `showtotal=True`); `/usuarios/listar`, `/agencias/listar`, and
  `/imoveis/listarConteudo` are called without it. If you need pagination
  metadata for those, extend the helper.

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
  "CA2830": {"Codigo": "CA2830", "Cidade": "Cotia"},
  "TE0080": {"Codigo": "TE0080", "Cidade": "Cotia"},
  "total": 1784,
  "paginas": 595,
  "pagina": 1,
  "quantidade": 3
}
```

Normalizers must dict-iterate, **filtering out** the pagination keys
(`total`, `paginas`, `pagina`, `quantidade`). The adapter exposes the helper

```python
extract_items(payload: dict) -> tuple[list[dict], dict]
```

defined in `noctusai_lib/integrations/vista/client.py`. The pagination-key set is a
module constant `PAGINATION_KEYS = {"total", "paginas", "pagina", "quantidade"}`
— callers don't pass it. Behavior:

- **Non-dict payload** → returns `([], {})` defensively (never raises).
- **Items** → every dict-valued key whose name is NOT in `PAGINATION_KEYS`
  is appended to the items list, in insertion order.
- **Pagination** → every key in `PAGINATION_KEYS` becomes a key in the
  returned pagination dict; missing keys are simply absent (callers
  must `.get(key)` defensively, no `KeyError` guarantee).
- **The dict key is NOT the id.** Read the `Codigo` field from the payload
  itself — Vista uses alphanumeric ids for `/imoveis` (`"CA2830"`) and
  numeric-as-string for `/usuarios` / `/agencias` (`"16"`, `"1"`).

> **Public-doc claim mismatch.** Public docs print
> `{"results": [...], "total": ..., "pagina": ..., ...}`. The live tenant does
> NOT use `results: [...]` — items are top-level keys. Trust the live shape.

### Detail responses (`/imoveis/detalhes`)

Returns a flat object keyed by field, e.g.

```json
{
  "Codigo": "CA2830",
  "Cidade": "Cotia",
  "Caracteristicas": {"Piscina": "Sim"}
}
```

### Error responses

All non-200 responses use the **same envelope**: `{"message": ..., "status": <int>}`.
The shape of `message` varies — sometimes string, sometimes array, sometimes
embedded substring. Live probe results 2026-05-03:

| HTTP | Body shape (live) | Meaning |
|---|---|---|
| 200 | normal | OK |
| 400 | `{"message": ["Campo Estado não está disponível. Consulte a documentação para obter os campos disponíveis."], "status": 400}` — note `message` is an **array** in the field-rejection case | Field-level permission denied or unknown field |
| 401 | `{"message": "Permissão Negada: \"<key-hash>\" Método: <path>", "status": 401}` — `message` is a string with the masked key hash + path embedded | Endpoint exists; key lacks permission |
| 404 | `{"message": "No route found for \"GET http://<tenant>/<path>\": Method Not Allowed (Allow: ...)", "status": 404}` — Symfony-style routing message | Endpoint not exposed on this tenant |

The adapter's `_extract_unavailable_field` (`client.py:278-286`) does
substring search for `"Campo "` against the JSON-serialized body, which
works for both the string and array shapes — but if Vista changes the
phrase or moves the field name to a structured key, the field extraction
will degrade to `<unknown>`.

### Typed error hierarchy

The adapter typifies these in a 7-class hierarchy
(`noctusai_lib/integrations/vista/client.py:26-65`). **Inheritance matters for
`except` ordering** — every router and service catches the leaves before
the parent, otherwise the parent swallows them:

```
VistaError                                   # base — catch-all for all Vista failures
├── VistaConfigError                         # missing/empty VISTA_BASE_URL or VISTA_API_KEY
│                                            # raised at request time, NOT at __init__
├── VistaTimeout(endpoint)                   # httpx.TimeoutException wrapper
└── VistaUpstreamError(status, body, endpoint)
    ├── VistaPermissionDenied                # HTTP 401, "Permissão Negada"
    ├── VistaNotFound                        # HTTP 404, endpoint not exposed on tenant
    └── VistaFieldNotAvailable(field, ...)   # HTTP 400, "Campo X não está disponível"
                                             # `.field` is best-effort parsed from body
                                             # (returns `<unknown>` if parsing fails)
```

**Catch-order rule** (concrete example from
`app/routers/vista_showcase.py:111-118`):

```python
except VistaPermissionDenied: ...      # 401 → 403
except VistaNotFound: ...              # 404 → 404
except VistaFieldNotAvailable as e: ...# 400 → 422 — MUST come before VistaUpstreamError
except VistaTimeout: ...               # → 504
except VistaUpstreamError as e: ...    # everything else → 502
```

Reversing `VistaFieldNotAvailable` and `VistaUpstreamError` would silently
mask field-permission errors as generic 502s — exactly the symptom that
Phase 4.5 hardening was filed to prevent.

**Result carrier** — successful requests return a `VistaCallResult`
(`client.py:68-89`) with `data, status, latency_ms, endpoint, params_keys`.
Audit-logging downstream uses these fields directly so it never re-runs
the request.

---

## 4. Endpoint inventory

### 4.1 `/imoveis` (Properties)

| Op | Method | Path | ID param | This tenant | Public docs | Notes |
|---|---|---|---|---|---|---|
| List | GET | `/imoveis/listar` | — | ✅ | 📖 | ~1,783 properties on this tenant 2026-05-03 (count fluctuates as listings come and go). |
| Detail | GET | `/imoveis/detalhes` | `?imovel=` | ✅ | 📖 | `Foto` field NOT available on detalhes — use `FotoDestaque` from listar instead. |
| List enum content | GET | `/imoveis/listarConteudo` | — | ✅ | ❓ | Returns enum values for fields like `Status`, `Categoria`, `Cidade`, `Bairro`. Drives filter dropdowns. |
| Photos | GET | `/imoveis/fotos` | `?imovel=` | ❌ | 📖 | Re-probed 2026-05-03: live tenant returns 404 ("No route found"), NOT 401 — the endpoint isn't enabled for this subscription tier. Workaround: `FotoDestaque` field in `/imoveis/listar`. |
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

#### Confirmed `/imoveis/listar` field set (this tenant) — **calibrated 2026-05-02, re-verified 2026-05-03**

The earlier table listed several fields as available that this tenant's
key actually rejects with HTTP 400 (`Campo X não está disponível`). The
cause was Phase 1's smoke probe never tested the full field bundle in
one request. Live discovery on 2026-05-02 produced the corrected list
below; 2026-05-03 re-probe confirmed all fields still work.

✅ **Available** (request these):

```
Codigo            string   primary id (e.g. "CA2830", "ONE10006")
TituloSite        string   marketing title
Categoria         string   property type (e.g. "Casa", "Casa em Condomínio", "Terreno")
Status            string   listing status — values "Venda" / "Aluguel" / "Venda e Aluguel"
Finalidade        string   sometimes empty; "Residencial" when populated
Empreendimento    string   development name (nullable, in IMOVEL_DETAIL_FIELDS only)
Construtora       string   builder name (nullable, in IMOVEL_DETAIL_FIELDS only)
Cidade            string
Bairro            string
Endereco          string
Numero            string   (in IMOVEL_DETAIL_FIELDS only)
Complemento       string   (in IMOVEL_DETAIL_FIELDS only)
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
Caracteristicas   object   nested boolean/text features (only on /imoveis/detalhes; ~75 keys per property — Adega, Piscina, Lavabo, …)
DataCadastro      string   ISO-ish, space separator (in IMOVEL_DETAIL_FIELDS only)
DataAtualizacao   string
FotoDestaque      string   primary photo URL (the only photo field this tenant exposes — in IMOVEL_LIST_FIELDS only; NOT valid on /imoveis/detalhes)
Corretor          object   nested dict keyed-by-corretor-id: {"103": {"Codigo": "...", "Nome": "..."}}
                            — NOT a flat {"Nome": "..."} object on this tenant
```

🔒 **Rejected** by this tenant's API key (HTTP 400 if requested):
`Estado` (use `UF` instead), `Banheiros` (use `BanheiroSocial`),
`Foto` (use `FotoDestaque`), `FotoPrincipal`, `Slug`, `PalavrasChave`,
`CodigoImobiliaria`.

**Auto-included fields (Vista returns these unrequested — confirmed live
2026-05-03):**

- `CodigoImobiliaria`: returned as `null` on `oneconsu-rest`, even though
  requesting it explicitly returns 400. Don't filter, don't try to
  request — just accept it in the response payload.
- `Corretor_Codigo`: a flat string copy of the first corretor's id,
  returned alongside the nested `Corretor` dict. Useful as a faster
  ID-only check than walking the nested dict; the `_first_corretor_nome`
  normalizer ignores this and reads `Corretor[*].Nome` directly.

The reference adapter's `IMOVEL_LIST_FIELDS` constant carries the
calibrated set; future tenants may have different splits and need their
own probe pass — see §6 for the calibration gap.

#### `/imoveis/detalhes` quirks

- Accepts the same `pesquisa.fields` shape, but the **field set differs from
  `/imoveis/listar`** (see `IMOVEL_DETAIL_FIELDS` in
  `app/services/vista_showcase_service.py:70-81`):
  - **Adds:** `Numero`, `Complemento`, `DataCadastro`, `Caracteristicas`,
    `Empreendimento`, `Construtora`, plus `Fone` inside the nested
    `Corretor` object.
  - **Drops:** `FotoDestaque` (no photo field works on detalhes — see next
    bullet) and the listing-only `Status` filter.
- `Foto` / `FotoDestaque` are NOT valid fields here (return 400). The
  adapter works around this by **prefetching the matching listing row first**
  (see `fetch_imovel_detalhes` in `vista_showcase_service.py:234-273`):
  1. Calls `listar_imoveis(filter_={"Codigo": codigo}, page=1, page_size=1)`
     to grab the row's `FotoDestaque`. Audit-logs this with
     `extra={"phase": "detail-listing-prefetch"}`.
  2. **If the prefetch fails (any `VistaUpstreamError` family), the failure is
     non-fatal** — `fetch_imovel_detalhes` continues to call `/imoveis/detalhes`
     anyway. The detail view simply renders without a photo.
  3. Calls `detalhes_imovel(codigo, fields=IMOVEL_DETAIL_FIELDS)`.
  4. Merges the two payloads via
     `vista_imovel_detalhes_to_showcase(detalhes_payload, listing_payload=...)`
     (`normalizers.py:108-128`). **Merge strategy: `{**listing, **detalhes}`
     — detail fields win.** Plus a special override: if `listing.Foto` is
     truthy and `detalhes.Foto` is falsy, `Foto` is copied from listing.
- `imovel=<Codigo>` MUST be at the top level (`extra_params`), not inside
  `pesquisa`. The adapter handles this via `client.detalhes_imovel`
  (`client.py:224-229`).
- `Caracteristicas` is a free-form dict the seller fills in (e.g.
  `{"Piscina": "Sim", "Quintal": "Não"}`). Keys vary per property — the
  normalizer treats it as opaque and exposes it untransformed in
  `ShowcaseImovelDetalhes.caracteristicas`. Defensive: if Vista returns
  it as a non-dict, the normalizer substitutes `{}`. Live sample 2026-05-03
  shows ~75 boolean-flag keys per property (Adega, Banheiro Social, Piscina,
  Lavabo, Vista Mar, etc.).

#### `/imoveis/listarConteudo` quirks

- The adapter calls this with **`CONTEUDO_FIELDS = ["Status", "Categoria",
  "Cidade", "Bairro"]`** (`vista_showcase_service.py:85`) — the only
  combination probed live. Other field names may work but haven't been
  verified against this tenant.
- Returns a flat dict keyed by field name with the enum values for each.
  Used to populate filter dropdowns without scanning the full catalog.
- The `extract_items` envelope-splitter is **not** used here — the
  response isn't dict-keyed-by-id. The service just passes the raw dict
  through as a single-element items list (`fetch_imoveis_conteudo`,
  `vista_showcase_service.py:276-292`).

**Live enum content for `oneconsu-rest` 2026-05-03** (the response is a
flat dict keyed by the requested field names):

| Field | Values returned |
|---|---|
| `Status` | `["Aluguel", "Venda", "Venda e Aluguel"]` (3 — exhaustive on this tenant) |
| `Categoria` | 20+ values incl. `Apartamento`, `Casa`, `Casa em Condomínio`, `Chácara`, `Galpão`, `Salas/Conjuntos`, `Área`, `Casa comercial`, `Cobertura`, `Empreendimento`, `Galpão Industrial`, `Loft`, `Ponto Comercial`, `Prédio Comercial`, `Sítio`, `Sobrado`, `Terreno Comercial`, `Terreno de Rua`, `Terreno em Condomínio`, `Loja`, … |
| `Cidade` | 17 values: `Cotia`, `Carapicuíba`, `Vargem Grande Paulista`, `Embu das Artes`, `Barueri`, `Guarujá`, `Osasco`, `Santana de Parnaíba`, `São Paulo`, `Embu Das Artes` (note casing dup), `Itapecerica da Serra`, `Itapevi`, `Jandira`, `Ilhabela`, `São Roque`, `Ibiúna`, `Vinhedo` |
| `Bairro` | Long list (60+) including `Granja Viana`, `Alphaville Granja Viana`, `Portal da Granja - Km 22`, etc. |

**Casing duplicates.** Note the `Cidade` enum contains both `Embu das Artes`
and `Embu Das Artes` — Vista does NOT canonicalize. A filter using
exactly one form will miss properties listed under the other. Surface
this to the user / model when populating dropdowns.

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
| List | GET | `/usuarios/listar` | ✅ | 10 rows on this tenant 2026-05-03 |

#### Confirmed field set

```
Codigo   string
Nome     string
Email    string
Foto     string   URL
Setor    string   department/team (e.g. "Sócios")
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

> **Formalized 2026-05-03.** The Vista client + error hierarchy + normalizers
> + showcase DTOs live in **`seed/lib/backend/noctusai_lib/integrations/vista/`**
> — the canonical platform home consumed by both the ERP showcase AND the
> in-repo MCP server (`mcp/vista/`). See `KB § PATTERNS/common/accept-with-rationale.md
> § Vista CRM client + normalizers + showcase DTOs duplicated at N=2 — FORMALIZED 2026-05-03`
> for the historical entry.

```
seed/lib/backend/noctusai_lib/integrations/vista/   # canonical platform home
├── __init__.py              # public surface: VistaClient + error hierarchy
│                            #   + extract_items + 4 normalizers + 4 ShowcaseDTOs
├── client.py                # VistaClient + 7-class error hierarchy + extract_items
├── normalizers.py           # vista_*_to_showcase() — Vista payload → ShowcaseDTO
└── types.py                 # ShowcaseImovel/Usuario/Agencia/ImovelDetalhes Pydantic DTOs

ERP backend (consumer #1)
├── app/services/vista_showcase_service.py
│                            # imports from noctusai_lib.integrations.vista
│                            # Field-set constants + per-tab fetchers + audit path
│                            # + diagnose() probe runner + KNOWN_TABS catalog
├── app/services/vista_showcase_types.py
│                            # ERP-router-specific response wrappers
│                            # (ShowcasePagination, ShowcaseEnvelope, ShowcaseTabStatus,
│                            #  ShowcaseDiagnostic) — NOT Vista-protocol shapes
└── app/routers/vista_showcase.py
                             # imports from noctusai_lib.integrations.vista
                             # /api/vista-showcase/{tabs, imoveis, imoveis/{codigo},
                             #   imoveis-conteudo, usuarios, agencias, diagnostico}
                             # admin-only via require_admin

mcp/vista/ (consumer #2 — see mcp/vista/README.md)
├── settings.py              # VistaSettings — per-tenant config separate from platform .env
├── calibration.py           # per-tenant field-set probe-and-drop routine
├── types.py                 # MCP-tool-IO Pydantic schemas only
├── server.py                # stdio MCP entry point
└── tools/                   # vista.<service>.<action> tools — all import from noctusai_lib

ERP frontend
└── pages/VistaShowcase.tsx
                             # Admin-only page with seven sub-tabs:
                             # Imóveis, Detalhes, Usuários, Agência,
                             # Clientes 🔒, Corretores 🔒, Fotos ❌, Diagnóstico
```

### 5.1 Field-set constants

The adapter sends five distinct field sets, all hardcoded in
`app/services/vista_showcase_service.py:58-85`:

| Constant | Endpoint | Field count | Notes |
|---|---|---|---|
| `IMOVEL_LIST_FIELDS` | `/imoveis/listar` | 24 | Includes `FotoDestaque`, `BanheiroSocial`, `UF`, nested `{Corretor: [Nome, Email]}` |
| `IMOVEL_DETAIL_FIELDS` | `/imoveis/detalhes` | 27 | Adds `Numero`, `Complemento`, `Caracteristicas`, `Empreendimento`, `Construtora`, `DataCadastro`; nested Corretor adds `Fone`; **no photo field works** |
| `CONTEUDO_FIELDS` | `/imoveis/listarConteudo` | 4 | `Status`, `Categoria`, `Cidade`, `Bairro` — populates filter dropdowns |
| `USUARIO_FIELDS` | `/usuarios/listar` | 5 | `Codigo`, `Nome`, `Email`, `Foto`, `Setor` |
| `AGENCIA_FIELDS` | `/agencias/listar` | 6 | `Codigo`, `Nome`, `Endereco`, `Cidade`, `Bairro`, `Site` |

> **All sets are calibrated for `oneconsu-rest.vistahost.com.br` on 2026-05-02
> and re-verified 2026-05-03.** A different tenant key may need a different
> split — see §6 ("Per-tenant calibration — current state vs design intent")
> for the gap.

### 5.2 Normalizer field-mapping contract

`noctusai_lib/integrations/vista/normalizers.py` exposes four payload mappers plus
helpers. Every mapper preserves the original Vista payload in the DTO's
`raw` field for debug + future-migration use.

**Type-coercion helpers** (defensive against Vista's everything-is-a-string
payload):

| Helper | Behavior |
|---|---|
| `_to_float(value)` | `None`/`""` → `None`. `0`/`"0"` → `0.0` (kept distinct from "no data"). Comma decimal separator (`"250000,50"`) normalized to dot before parsing. |
| `_to_int(value)` | `None`/`""` → `None`. Else `int(float(str(value)))`. |
| `_str_or_none(value)` | `None`/`""` → `None`. Else `str(value)`. |
| `_first_corretor_nome(payload)` | Walks BOTH the flat shape (`Corretor.Nome`) and the nested-by-id shape (`Corretor["103"].Nome`), returning the first usable name. `None` if no Corretor. |

**Mappers:**

| Mapper | Vista key → ShowcaseDTO field (selected) |
|---|---|
| `vista_imovel_to_showcase` | Direct: `Codigo→codigo`, `TituloSite→titulo`, `Categoria→categoria`, `Finalidade→finalidade`, `Status→status`, `Cidade→cidade`, `Bairro→bairro`, `Endereco→endereco`, `CEP→cep`, `DataAtualizacao→data_atualizacao`. **Per-tenant fallbacks (try-first-then-second):** `UF` ‖ `Estado` `→estado`; `Banheiros` ‖ `BanheiroSocial` `→banheiros` (int); `Foto` ‖ `FotoDestaque` `→foto_url`. **Float coerced:** `ValorVenda`, `ValorLocacao`, `AreaTotal`, `AreaPrivativa`, `AreaConstruida`, `Latitude`, `Longitude`. **Int coerced:** `Dormitorios`, `Suites`, `Vagas`. **Special:** `Corretor` → `corretor_nome` via `_first_corretor_nome` (returns ONLY the first matched name, NOT a list). Always: `payload→raw`. |
| `vista_imovel_detalhes_to_showcase` | Merges `{**listing, **detalhes}` (detail fields win), then runs `vista_imovel_to_showcase` on the merged payload. Plus a `Foto` override: if `listing.Foto` truthy and `detalhes.Foto` falsy, listing's photo wins. Returns `ShowcaseImovelDetalhes(codigo, base=ShowcaseImovel(...), caracteristicas, raw=detalhes_payload)`. `caracteristicas` is opaque (passed through as-is); a non-dict response substitutes `{}`. |
| `vista_usuario_to_showcase` | `Codigo→codigo`, `Nome→nome`, `Email→email`, `Setor→setor`, `Foto→foto_url`, `payload→raw`. |
| `vista_agencia_to_showcase` | `Codigo→codigo`, `Nome→nome`, `Endereco→endereco`, `Cidade→cidade`, `Bairro→bairro`, `Site→site`, `payload→raw`. |

**Field-fallback rationale.** The `Estado`/`UF`, `Banheiros`/`BanheiroSocial`,
and `Foto`/`FotoDestaque` fallbacks exist because public docs advertise the
first form but `oneconsu-rest` only exposes the second. A tenant with
different permissions may have either or both. The normalizer trying both
shapes makes the adapter survive most tenant variations without code
changes — **but the `IMOVEL_LIST_FIELDS` constant must still match the
tenant** (see §6).

### 5.3 Diagnostic probe surface

`VistaClient.probe(endpoint)` (`client.py:247-270`) is a separate,
minimum-impact probe path distinct from per-tab fetchers:

- Sends `pesquisa={"fields": ["Codigo"]}` — the smallest viable probe.
- Catches every typed Vista error and returns a JSON-friendly status row
  instead of raising.
- Returns `{endpoint, status, http_status, latency_ms (only on "ok")}`.

Status values: `"ok" | "permission_denied" | "not_found" | "timeout" |
"not_configured" | "upstream_error"`.

`vista_showcase_service.diagnose(client)` (`service.py:356-383`) iterates
the canonical seven-endpoint list and collects results:

```python
PROBE_ENDPOINTS = [
    "/imoveis/listar",
    "/imoveis/listarConteudo",
    "/usuarios/listar",
    "/agencias/listar",
    "/clientes/listar",     # 401 expected on this tenant
    "/corretores/listar",   # 401 expected on this tenant
    "/imoveis/fotos",       # 404 expected on this tenant
]
```

Probes run **sequentially** (~1.4s wall-clock for seven endpoints).
Acceptable for an admin-only debug tool;
`vista_showcase_service.py:357-359` flags parallelization via
`asyncio.gather` as a future perf knob if the probe count grows.

The probe surface powers the Diagnóstico sub-tab. It is **NOT** the
field-set calibrator — see §6.

### 5.4 Audit-log contract

Every outbound Vista call writes one row to `erp.user_actions_log` via
`_audit()` (`vista_showcase_service.py:115-156`):

| Column | Value |
|---|---|
| `tipo_acao` | `'consulta_externa'` *(added by migration 023)* |
| `tipo_entidade` | `'integracao_vista'` *(added by migration 023)* |
| `entidade_id` | Vista record id (e.g. `"CA2830"`) on detail/per-record calls; `null` on listings and probes |
| `descricao` | `'OK GET /imoveis/listar'` on success; `'ERRO GET /imoveis/listar'` on failure |
| `detalhes` | JSON dict — schema below |

`detalhes` schema (every key optional unless flagged "always"):

```jsonc
{
  "endpoint": "/imoveis/listar",          // always
  "tenant_call": true,                    // always (marker for outbound calls)
  "status": 200,                          // success → 200; failure → error.status (when VistaUpstreamError)
  "latency_ms": 412,                      // present on success only
  "params_keys": ["key","pesquisa","showtotal"],  // sorted keys; NEVER values (LGPD)
  "error_class": "VistaPermissionDenied", // failure only
  "error": "Vista /clientes/listar returned 401: ...",  // failure only; truncated to 300 chars
  "phase": "detail-listing-prefetch",     // present when fetch_imovel_detalhes prefetches listar
  "probe_endpoints": ["..."],             // from diagnose()
  "probe_outcomes": ["ok","ok"]           // parallel to probe_endpoints
}
```

The Vista **response payload itself is never persisted** — `detalhes`
carries only metadata, not field values. This satisfies the LGPD
live-read constraint (Vista clientes payloads carry CPF / addresses /
phones — anything personal-data-shaped needs explicit consent gating,
audit-log per call, no payload persistence). A future migration phase
that caches Vista data (e.g. ingesting properties into `erp.ativos`)
would land in dedicated cache tables; `user_actions_log` stays
metadata-only.

**Audit-on-failure ordering.** Service fetchers call `_audit(...)` BEFORE
re-raising the typed error (`vista_showcase_service.py:213-215` and
parallel sites). Failed calls are auditable; the audit row exists even
when the request never returns 200 to the user. The `_deps.log_action`
call is itself wrapped in a `try/except` (`service.py:155-156`) so an
audit-write failure cannot mask a Vista call result — it logs a warning
and continues.

### 5.5 Router HTTP status mapping

Every router endpoint (`app/routers/vista_showcase.py`) maps Vista errors
to FastAPI `HTTPException` with a fixed status code:

| Vista error | HTTP | User-facing message (port. — copied verbatim) |
|---|---|---|
| `VistaConfigError` | 503 | "Vista não configurada (VISTA_BASE_URL / VISTA_API_KEY ausentes)." |
| `VistaPermissionDenied` | **403** | "Permissão pendente — solicite expansão de chave junto à Vista." |
| `VistaNotFound` | 404 | "Endpoint Vista não disponível neste tenant." / "Imóvel não encontrado em Vista." |
| `VistaFieldNotAvailable` | **422** | "Campo Vista 'X' indisponível para este tenant — atualize IMOVEL_LIST_FIELDS." |
| `VistaTimeout` | 504 | "Vista demorou mais que 15s para responder." |
| `VistaUpstreamError` (other) | 502 | "Vista respondeu erro {status}." |

**Why 422 (not 502) for `VistaFieldNotAvailable`.** Field-permission drift
is a known, semi-frequent failure mode — different tenant keys have
different per-field permissions. Surfacing it as 422 lets the frontend
distinguish "configuration drift — update the field-set constants" from
"real upstream outage" (502). This was the explicit fix from the Phase
4.5 hardening (see §8 changelog).

**Why 401 → 403 (not 401).** A Vista 401 is a *tenant key* permission
problem, not an *end-user* auth problem. Returning 401 to the browser
would trip the SPA's auth interceptor and log the user out — wrong
semantic. The user IS authenticated to ERP; ERP just lacks Vista
permission. 403 is the right surface.

### 5.6 Admin-gating

Every `/api/vista-showcase/*` endpoint depends on `require_admin`
(`vista_showcase.py:43-58`). Resolution order:

1. **SSO role** via `noctusai_lib.api.auth.resolve_sso_role(user)`. If
   `platform_admin` (or org-level admin/owner), allow.
2. **ERP-native role** via `user.user_metadata.erp_role` or
   `noctus_role`. Allowed set: `{"platform_admin", "admin", "owner"}`.
3. Otherwise → `HTTPException(403, "Admin privileges required for the
   Vista showcase")`.

This is the v1 LGPD mitigation — Vista carries personal data (CPFs,
phones, addresses on the `/clientes/*` family) and full read access
stays admin-only until proper consent gating lands.

---

## 6. Per-tenant calibration — current state vs design intent

> **Honesty section.** The Phase 4.5 failure (the deployed UI showed
> `[502] Vista respondeu erro 400` because the smoke probe never sent the
> full field bundle) established the **design intent** that any
> Vista-talking surface must run a probe routine and cache per-tenant safe
> field sets — different tenant keys have different per-field permissions,
> and hardcoding the public-doc field set is the wrong move.
>
> **Current adapter state — calibration is NOT runtime-probed.** The field
> sets `IMOVEL_LIST_FIELDS`, `IMOVEL_DETAIL_FIELDS`, `USUARIO_FIELDS`,
> `AGENCIA_FIELDS`, `CONTEUDO_FIELDS` (`vista_showcase_service.py:58-85`)
> are MODULE-LEVEL CONSTANTS calibrated once on 2026-05-02 against the
> `oneconsu-rest.vistahost.com.br` tenant. A different tenant key with
> different per-field permissions WILL hit `VistaFieldNotAvailable` on the
> first request. The router's 422 surface (§5.5) makes that recoverable
> but does NOT auto-correct the constants.
>
> **The `VistaClient.probe()` method exists** (`client.py:247-270`) but
> is used only by the Diagnóstico tab health check (§5.3) — it sends
> `["Codigo"]` only and learns nothing about which other fields work.
>
> **Status (2026-05-03):** Phase 1 of the in-repo Vista MCP server
> (`mcp/vista/`) ships the calibration routine described below. It runs
> lazily on first call to any imoveis/usuarios/agencias tool, caches per
> process, and is inspectable via `vista.diagnostics.show_calibrated_fields`.
> The showcase adapter still uses hardcoded constants — see §8 changelog
> 2026-05-03 for the architectural absorb-to-seed-lib path (gated on
> `mcp-server-expansion` substrate).
>
> **Implication for the MCP server.** Phase 0/1 of the in-repo Vista MCP
> server (NOW BUILT — see `mcp/vista/calibration.py`) ships the actual
> per-tenant calibration routine. Algorithm:
>
> 1. At first call (or boot), send a "discovery probe" per endpoint
>    family that requests the **public-doc full field set** plus a
>    safety bracket of NoctusAI-known fields.
> 2. On 400, parse the rejected field from the body, drop it, retry.
>    Repeat until the request succeeds (or the field count hits a
>    floor of `["Codigo"]`).
> 3. Cache the resulting safe field set per tenant key. TTL discussion
>    is open — recommend "until restart" for v1; tenant key rotation is
>    rare enough that explicit re-probe on key change is fine.
> 4. Surface the calibrated set as MCP-readable metadata so a host
>    operator can inspect what the server discovered.
>
> Until that lands, an MCP that imports the showcase adapter inherits
> its hardcoded constants — fine for `oneconsu-rest`, broken for any
> tenant with a different permission split.

---

## 6a. High-level adapter layer + real-estate domain (consume side)

> Added 2026-05-20 (the vista seed-lift; social-wiring is the first consumer). Composes on top of §5's low-level `VistaClient` to ship a thin product-facing surface the YouTube upload pipeline (and any future real-estate-shaped consumer) uses without re-implementing the Vista REST handshake.

### Adapter surface — `noctusai_lib.integrations.vista`

```python
from noctusai_lib.integrations.vista import (
    VistaCRMAdapter,        # Protocol — async get_property(code) -> PropertyData | None
    FakeVistaAdapter,       # in-memory; dev/test default
    VistaRESTAdapter,       # Real; wraps the Vista REST `/imoveis/detalhes` endpoint
    get_vista_adapter,      # factory: base_url/api_key/fake → adapter
    VistaError,             # transport / auth / 5xx
    VistaNotConfigured,     # aliased to VistaConfigError from §5 client.py
    PropertyData,           # re-exported from domain.real_estate for ergonomics
)
```

Factory contract:

```python
get_vista_adapter(
    *,
    base_url: str | None,
    api_key:  str | None,
    fake:     bool = False,
) -> VistaCRMAdapter
```

- `fake=True` → `FakeVistaAdapter` (constructor takes `dict[code, PropertyData]`).
- `base_url+api_key both set + fake=False` → `VistaRESTAdapter`.
- `base_url or api_key empty + fake=False` → raises `VistaNotConfigured`.

### Domain surface — `noctusai_lib.domain.real_estate`

Pure logic; no IO. The YT metadata shape is real-estate-specific (could come from any CRM, not just Vista) — sits in `domain/`, not `integrations/`.

```python
from noctusai_lib.domain.real_estate import (
    PropertyData,              # @dataclass(frozen=True) — title/address/price/bedrooms/area_sqm/description/…
    build_youtube_metadata,    # (prop, code) → {title, description, tags}
    validate_product_code,     # (code) -> bool — ONE\d+ pattern check
)
```

`build_youtube_metadata` output shape:

- `title`: `f"{product_code} — {prop.title}"[:100]` (YT title cap honored)
- `description`: multi-line with 📍/💰/🛏️/📐 emoji block + full property description, capped at 5000 chars
- `tags`: `[product_code, address, "imóvel", "real estate", "imobiliária"]`

### Consume recipe (social-wiring is the first consumer)

```python
# whatsapp_intake_service.py / routers/upload.py / any consumer
from noctusai_lib.integrations.vista import (
    VistaRESTAdapter as CRMService,           # alias keeps caller-side naming stable
    VistaError as CRMServiceError,
    VistaNotConfigured as CRMNotConfigured,
)
from noctusai_lib.domain.real_estate import (
    PropertyData,
    build_youtube_metadata,
    validate_product_code,
)

# Construct + call:
crm = CRMService(base_url=settings.crm_base_url, api_key=settings.crm_api_key)
prop = await crm.get_property("ONE10010")
if prop is not None:
    metadata = build_youtube_metadata(prop, "ONE10010")
    # → metadata["title"], metadata["description"], metadata["tags"]
```

### Composition vs §5 low-level client

The new adapter and §5's `VistaClient` co-exist. The adapter is consumer-facing; the client is endpoint-level. Today the adapter re-implements the `/imoveis/detalhes` HTTP call (byte-for-byte port of the original `products/social-wiring/.../crm_service.py`). **Triage:** [R] refactor — at N=2 (next consumer joins) the adapter should compose `VistaClient.detalhes_imovel(...)` + `vista_imovel_detalhes_to_showcase` + a small showcase→PropertyData mapper, eliminating the duplicated httpx code path. Tracked as a follow-up; not blocking.

### What's deliberately NOT here

- **MCP exposure** — §7 covers the future MCP server design; this adapter is library-only.
- **Per-tenant calibration** — §6 is the pre-existing gap; the adapter inherits the same constants.
- **Other CRMs / a `RealEstateCRMAdapter` superclass** — N=1 (Vista only). If a second CRM appears, refactor at that point per the recurrence rule.

---

## 7. Future MCP design notes

When an in-repo MCP server is built (or the external-environment one
ships):

1. **Tool surface.** One tool per row in §4 marked ✅ or 🔒 (the 🔒 ones still
   matter — different tenants have permission). Skip ❓ rows until probed.
2. **Auth as MCP secret.** The MCP server reads a per-tenant API key from its
   own config; do not propagate `VISTA_API_KEY` from this repo's `.env`.
3. **Re-use this document as the schema source.** The MCP can codegen tool
   schemas from §4 tables — every row's "ID param", method, path, and
   confirmed-field-set are sufficient to type the request/response.
4. **Error model.** Mirror the typed errors in §3 — the MCP host will see
   them as structured tool-error payloads, not raw 4xx text. Keep the
   catch-order rule (subclass before parent — see §3).
5. **Dict-keyed-by-id response shape** (§3) is unusual; the MCP wrapper
   should always normalize to `items: [...]` + `pagination: {...}` so the
   model never has to re-discover this.
6. **Live-probe gating.** Each MCP tool registers with a `probe_status`
   field — `live_probed | doc_only | referenced` — so a host operator can
   filter to only-known-good tools.
7. **Per-tenant calibration is mandatory at the MCP layer.** See §6 — the
   showcase adapter's hardcoded field sets are NOT a generic-tenant
   solution. The MCP must implement the discovery-probe routine before any
   production tool use.

---

## 8. Change log

### 2026-05-20 — High-level adapter layer + real-estate domain (vista-seed-lift)

Lifted the social-wiring product-local `app/services/crm_service.py` into two seed modules:

1. `noctusai_lib.integrations.vista` — added the adapter layer (`VistaCRMAdapter` Protocol + `FakeVistaAdapter` + `VistaRESTAdapter` + `get_vista_adapter` factory) alongside the pre-existing `VistaClient` low-level surface. See §6a for the consume recipe.
2. `noctusai_lib.domain.real_estate` — new module ships `PropertyData` + `build_youtube_metadata` + `validate_product_code` (pure functions; the YT metadata shape is real-estate-specific, not Vista-specific).

Product-local `crm_service.py` deleted (zero local copy). All callers consume from seed. Live-validated against ONE10010 (Casa em Alphaville).

Follow-up filed: refactor `VistaRESTAdapter` to compose `VistaClient.detalhes_imovel(...)` at N=2 (DRY).

### Older entries

| Date | Change | By |
|---|---|---|
| 2026-05-02 | Initial authoring inside `products/erp-imobiliario/projects/vista-crm-wiring/VISTA-API.md` (the showcase project, since closed and folder deleted). Folded Phase 1 live-probe results, public-doc imoveis/clientes specs, and adapter contract into a single MCP-ready reference. | Claude Opus 4.7 |
| 2026-05-02 | **Re-calibrated `/imoveis/listar` and `/imoveis/detalhes` field sets after live failure.** UI showed `[502] Vista respondeu erro 400` because Phase 1's smoke probe never sent the full field bundle in one request. New live discovery: this tenant rejects `Estado`, `Banheiros`, `Foto`, `FotoPrincipal`, `Slug`, `PalavrasChave`, `CodigoImobiliaria` with HTTP 400. Replacements: `UF` (for `Estado`), `BanheiroSocial` (for `Banheiros`), `FotoDestaque` (for `Foto`). Also discovered: `Corretor` is returned as a dict keyed by corretor id (`{"103": {"...": "..."}, "104": {"...": "..."}}`), not a flat `{"Nome": "..."}` object. Adapter constants and normalizer updated; `/imoveis` router now catches `VistaFieldNotAvailable` explicitly (422) so the next field-permission drift surfaces clearly instead of as a generic 502. Verified end-to-end against live tenant: 1,783 properties, 10 users, 1 agency. | Claude Opus 4.7 |
| 2026-05-02 | Doc relocated from the now-deleted `products/erp-imobiliario/projects/vista-crm-wiring/` showcase project into `projects/vista-api-mcp/VISTA-API.md` (project-internal scope) when the showcase project closed. | Claude Opus 4.7 |
| 2026-05-03 | **Live re-probe (8 endpoints + 1 negative test) against `oneconsu-rest`.** All previously-known statuses still hold: `/imoveis/listar` ✅ 200 (1,783 properties, 595 pages at 3/page), `/imoveis/detalhes` ✅ 200 with full DETAIL field bundle, `/imoveis/listarConteudo` ✅ 200, `/usuarios/listar` ✅ 200 (10 rows — was wrongly documented as "16+"), `/agencias/listar` ✅ 200 (1 row, "ONE CONSULTORIA IMOBILIARIA"), `/clientes/listar` 🔒 401, `/corretores/listar` 🔒 401, `/imoveis/fotos` ❌ 404. Negative test: requesting `Estado` still returns 400. **New findings folded in:** error response envelope is uniformly `{"message", "status"}` (doc previously claimed `{"mensagem"}` — wrong key); 400 `message` field is an **array** in field-rejection cases; 404 has Symfony "No route found" shape; 401 embeds the masked key hash + path; `/imoveis/listar` returns `Corretor_Codigo` (flat broker-id copy) and `CodigoImobiliaria` (`null` here) **unrequested**; `/imoveis/listarConteudo` Status enum is exhaustively `["Aluguel", "Venda", "Venda e Aluguel"]`; Cidade enum has a casing-dup quirk (`Embu das Artes` ‖ `Embu Das Artes` both appear). | Claude Opus 4.7 |
| 2026-05-03 | **Adapter-implementation refresh — closed the gap between the doc and the showcase code.** Driven by user "evolve the API" intent. Concretely: (a) §1 added client-wiring details (lenient `__init__`, `configured` property, `DEFAULT_TIMEOUT_SECONDS=15.0`, `http_client` injection seam). (b) §2 noted client-side `quantidade` clamp and the showtotal-per-endpoint asymmetry. (c) §3 fixed `extract_items()` signature (was wrongly documented as taking `pagination_keys=...`; real signature is `(payload: dict) -> tuple[list[dict], dict]`); added `VistaError` base + corrected the inheritance picture (`VistaPermissionDenied`/`NotFound`/`FieldNotAvailable` are subclasses of `VistaUpstreamError`); added the catch-order rule with the exact router example. (d) §4.1 expanded `/imoveis/detalhes` quirks with the listing-prefetch + `{**listing, **detalhes}` merge orchestration; expanded `listarConteudo` with the `CONTEUDO_FIELDS` constant and the live enum content. (e) §5 full rewrite: corrected layout, added §5.1 (5 field-set constants), §5.2 (full normalizer field-mapping contract incl. type-coercion helpers + per-tenant fallback chains), §5.3 (diagnostic probe surface), §5.4 (audit-log payload schema with the actual `detalhes` dict structure), §5.5 (router HTTP status mapping with 401→403 and 400→422 rationales), §5.6 (admin-gating resolution order). (f) NEW §6: explicit honesty about per-tenant calibration — the showcase adapter does NOT implement runtime calibration; field sets are constants frozen 2026-05-02. Sketched the calibration routine the in-repo MCP server should ship in Phase 0. | Claude Opus 4.7 |
| 2026-05-03 | **Vista MCP server Phase 1 shipped — `mcp/vista/`.** Per user directive 2026-05-03 ("implement the mcp phase"). Shipped: (a) ported VistaClient + 7-class error hierarchy + extract_items + VistaCallResult into `mcp/vista/client.py` (recommendation β from PROJECT.md §7 Q3 — port now, absorb to seed-lib later when `mcp-server-expansion` substrate lands). (b) Ported the 4 normalizers + helpers into `mcp/vista/normalizers.py`. (c) Pydantic In/Out per tool in `mcp/vista/types.py`. (d) **NEW: per-tenant calibration routine** at `mcp/vista/calibration.py` — addresses the §6 gap; lazy probe-and-drop loop per endpoint family, cached per process. (e) 8 tools across 6 services using the `vista.<service>.<action>` dotted naming convention from `KB § PATTERNS/architect/mcp-tool-conventions.md`. (f) Hierarchical registration via `tools/__init__.py`. (g) MCP stdio server entry at `mcp/vista/server.py`. (h) 12 smoke tests at `mcp/vista/tests/test_smoke.py` (all pass). (i) README at `mcp/vista/README.md` documenting Phase 1 scope, known limitations, and the calibration routine. **Bug surfaced AND fixed during live verification:** the showcase adapter's `VistaFieldNotAvailable` detector used `"não está disponível" in body_text`, which silently failed because Vista's wire body uses JSON unicode escapes (`não está disponível`) — meaning Phase 4.5's 422 surface NEVER fired. Fixed in BOTH `mcp/vista/client.py` AND `products/erp-imobiliario/backend/app/integrations/vista/client.py` (parse-message-then-search; handles array-shaped messages too). Recurrence rule: this fix lives in two places now → triage time when the seed-lib absorption ships, this becomes a single helper. **Live verification:** `vista.imoveis.list` returned 1,783 properties with valor_venda correctly coerced; calibration dropped exactly the 7 known-bad fields (Estado, Banheiros, Foto, FotoPrincipal, Slug, PalavrasChave, CodigoImobiliaria) ending at 25 valid fields. **Phase 1 deferred (Phase 2-5 work):** keeper detector for guide↔adapter drift; full integration tests against live tenant; nested-sub-field calibration; per-endpoint probe sentinels (`/imoveis/listarConteudo` rejects the generic `["Codigo"]` probe — UX nit, not a functional bug). | Claude Opus 4.7 |
| 2026-05-03 | **Doc relocated to `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` (durable home).** Project folders (`projects/vista-api-mcp/`) are deleted at project close — the doc would be lost there. KB is the single durable source of truth: (a) the in-repo Vista MCP server build will reference this doc; (b) the portable repo-root `VISTA-API-MCP-GUIDE.md` is re-authored from this doc; (c) any future agent walking into Vista work cold starts here. New folder `KB/CONTEXT/INTEGRATIONS/` established as the namespace for vendor-integration references; INDEX.md updated. PROJECT.md `Related docs` line updated to point here. | Claude Opus 4.7 |
