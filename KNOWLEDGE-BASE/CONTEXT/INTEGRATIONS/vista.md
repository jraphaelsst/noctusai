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

#### ✅ Delta sync — SOLVED, and it needs nothing from Vista

Long carried as an open Tier-4 ask ("existe filtro de alterados desde
`DataAtualizacao`?"). It exists and it works — `filter` already does it, in
both shapes, **confirmed live 2026-08-21** against `/imoveis/listar`:

```jsonc
{"filter": {"DataAtualizacao": [">=", "2026-08-01"]}}   // 826 of 1,943
{"filter": {"DataAtualizacao": ["2026-08-01", "2026-08-31"]}}  // 826 — range form
{"order":  {"DataAtualizacao": "desc"}}                  // newest-first cursor
```

So a `/imoveis` refresh does **not** need the 39-request full crawl the
support request assumed; it needs one filtered page-walk over what actually
changed. The adapter still full-crawls — an open improvement, not a
blocker.

**This does NOT extend to `/clientes`**, which exposes no `DataAtualizacao`
at all (§ 4.2) — 42,960 rows, full crawl only. Check for the field before
assuming delta sync on any family.

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
| 401 | `{"message": "Permissão Negada: \"<API KEY VERBATIM>\" Método: <path>", "status": 401}` — a string embedding **the raw API key** + the method path | Endpoint exists; key lacks permission |
| 404 | `{"message": "No route found for \"GET http://<tenant>/<path>\"", "status": 404}` — Symfony-style routing message. Method-specific: a route that exists but rejects GET answers **405**, not 404 | Endpoint not exposed on this tenant |

#### ⚠️ Credential echo — Vista returns our API key in error text

> **Corrected 2026-08-05.** This table previously called the 401 token a
> "masked key hash". It is **not masked** — it is the tenant API key
> verbatim, confirmed by string-matching the live 401 body against
> `VISTA_API_KEY`. That mistaken belief is why the leak sat unnoticed.

Two paths carry the credential out of the HTTP layer:

1. **4xx bodies** — the 401 `message` embeds the key (above).
2. **Transport errors** — httpx renders the full request URL, and the key
   is a *query parameter* (`?key=…`, § 1), so any `httpx.HTTPError` /
   timeout string contains it too.

Both used to reach `VistaUpstreamError.body` and `str(exc)`, and from there
the MCP's `typed_error.message` — which is read straight into an AI agent's
context window. **Contract: redact at the client boundary.**
`noctusai_lib.integrations.vista.redact_api_key(text, api_key)` replaces the
key with `KEY_REDACTION_PLACEHOLDER`; `VistaClient._redact` applies it to
every body and transport-error string before they enter the error/log model,
and `VistaRESTAdapter` (`real.py`, a second independent HTTP path) applies it
to its own two error strings.

Guarded by `test_401_body_reaches_the_caller_redacted` +
`test_transport_error_url_reaches_the_caller_redacted`
(`seed/lib/backend/tests/test_vista_integration.py`) — both verified to go
red when the redaction is removed.

**If you add a third Vista HTTP path, it redacts too.** The rotation
question is separate and open: the key has been exposed in agent contexts
and any log built from `str(exc)` prior to 2026-08-05.

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

### 4.2 `/clientes` (Clients) — ✅ two routes GRANTED 2026-08-21, the rest ❌ absent

**Re-probed live 2026-08-21 — the § 9 Tier-1 grant LANDED.** The critical
distinction this table carries: **🔒 401 ≠ ❌ 404**. Only 🔒 is unlocked by a
Vista support request — a 404 route does not exist on this tenant's REST
deployment, so asking them to "grant permission" on it is a category error.
That split is exactly what played out: the two 🔒 rows opened, and every ❌
row is still 404 after the same grant.

> **✅ 2026-08-21 — the grant is in effect on key `…644c`.** Vista replied
> that they had re-applied the permissions and cleared their system cache.
> Verified — not taken on their word (§ 7.0): `vista.diagnostics.probe`
> **and** raw HTTP in a fresh process both show `/clientes/listar` → **200**
> (42,960 clients) and `/clientes/detalhes?cliente=<id>` → **200**. The
> 2026-08-19 "grant not landed" finding was accurate when written; what
> changed was on Vista's side, and their cache flush is the most likely
> reason the first attempt appeared to do nothing.
>
> **`/corretores/listar` was in the SAME request and did NOT open** — it
> still returns 401 (§ 4.5). Record this ask as *partially* satisfied; two of
> three methods.

| Op | Method | Path | ID param | This tenant (2026-08-21) | Public docs | MCP tool |
|---|---|---|---|---|---|---|
| List | GET | `/clientes/listar` | — | ✅ 200 | 📖 | `vista.clientes.list` |
| Detail | GET | `/clientes/detalhes` | `?cliente=` | ✅ 200 | 📖 | `vista.clientes.get` |
| By broker | GET | `/clientes/porcorretor` | — | ❌ 404 | 📖 |
| By agency | GET | `/clientes/poragencia` | — | ❌ 404 | 📖 |
| History | GET | `/clientes/historico` | `?cliente=` | ❌ 404 | 📖 |
| Favorites | GET | `/clientes/favoritos` | `?cliente=` | ❌ 404 | 📖 |
| Available fields | GET | `/clientes/campos` | — | ❌ 404 | 📖 |
| Create | POST | `/clientes/cadastrar` | — | ❌ 404 | 📖 |
| Update | PUT | `/clientes/update` | `?cliente=` | ❌ 404 | 📖 |
| Add history | POST | `/clientes/cadhis` | `?cliente=` | ❌ 404 | 📖 |
| Assign broker | POST | `/clientes/cadcor` | `?cliente=` | ❌ 404 | 📖 |
| Submit lead | POST | `/clientes/lead` | — | ❌ 404 | 📖 |

> **🔴 Two route names in the pre-2026-08-21 table were OUR typos, not
> Vista's routes.** `/clientes/pesquisar` is not a documented Vista method at
> all (it was invented here and then "confirmed absent" — a 404 for a route
> nobody publishes proves nothing), and history is documented singular,
> `/clientes/historico`, where we had probed `historicos`. Both are corrected
> above and both were re-probed under the published name: still 404. The
> lesson generalises — **probe the vendor's published method names, and treat
> a 404 on a name you cannot cite in their docs as untested, not absent.**
>
> **Earlier corrections vs the 2026-05-03 snapshot** (always-doc-the-trim):
> the ❓ rows (`porcorretor`, `poragencia`, `historico`, `favoritos`,
> `campos`, and the four write ops) are confirmed ❌ — they had simply never
> been probed.

**How the write rows were probed without issuing a write.** Vista's router
returns **405** for a route that exists but rejects the method, and **404**
when there is no route at all — verified by `/imoveis/fotos`, which answers
GET with 405. So a *read-only* GET distinguishes "exists, needs POST" from
"absent" with no risk to a live CRM. Every write row above answered 404, so
they are genuinely absent, not merely method-mismatched.

**What a permission grant would and would not buy.** Granting
`clientes/listar` + `clientes/detalhes` yields the client roster and
per-client detail. It does **not** yield history (`historicos`),
broker↔client assignment (`porcorretor`/`cadcor`), favourites, or lead
submission (`lead`) — those routes are absent regardless of permission.
Notably there is therefore **no API path to write a captured lead back into
Vista** on this tenant; an inbound-lead flow terminates in our own database.

#### Field set — ✅ CONFIRMED live 2026-08-21 (11 of 32 candidates), on BOTH routes

The eleven below were confirmed on `/clientes/listar` on 2026-08-21 and on
`/clientes/detalhes` on 2026-08-23 (bogus-code probe, below). The second check
was not ceremony: `CLIENTE_DETAIL_FIELDS` had been shipped on the assumption
that both routes share an accepted set, and a single rejection there would
have turned every detail-dialog open into a 422 in production.

Established **without reading a single client record**: Vista's 400 names
every field it rejects, so `accepted = requested − rejected` is derivable
from error messages alone. Use that technique whenever a field set must be
mapped ahead of an LGPD intake.

```
✅ ACCEPTED   Codigo  Nome  Celular  DataCadastro  DataNascimento
              Corretor  Status  Profissao  EstadoCivil  Sexo  Interesse

❌ REJECTED   Email  Fone  FoneCelular  Telefone  CPF  Observacao
              Bairro  Cidade  Estado  UF  CEP  Endereco  Numero  Complemento
              Tipo  Origem  Categoria  Finalidade  ValorMaximo  ValorMinimo
              DataAtualizacao
```

**🔴 The old guess was wrong in BOTH directions, and each direction bites
differently.** It listed `Email`/`Fone`/`Endereco`/`CEP`/`Cidade` — all
rejected here — and it *omitted* seven fields this tenant does expose
(`DataNascimento`, `Corretor`, `Status`, `Profissao`, `EstadoCivil`, `Sexo`,
`Interesse`). The false positives are harmless: calibration drops them. The
omissions are not — **calibration narrows and can never widen**, so a field
missing from `calibration.CANDIDATE_CLIENTE_FIELDS` is invisible to every
consumer forever, regardless of what the tenant offers. Keep those lists as
generous supersets. Guarded by
`test_candidate_cliente_fields_cover_the_live_tenant_set`.

**⚠️ LGPD — the intake was re-done against this list.** The pre-grant note
claimed "CPF, addresses and phones". The truth is *neither* worse nor milder,
but different: **no CPF, no address, no email**, yet `DataNascimento`, `Sexo`,
`EstadoCivil`, `Profissao` and `Celular` are all returned. That is a
demographic profile, and a data-category intake written against the old
assumption would have classified the wrong categories entirely.

#### The bogus-code probe — verify a DETAIL field set with zero data exposure

`/clientes/detalhes` validates `fields` **before** it resolves the record. That
ordering is the whole trick, and it was established on 2026-08-23 rather than
assumed:

```
cliente=__NOC_FIELD_PROBE__  fields=[…the 11…]  → 400 "O cliente solicitado não foi encontrado."
cliente=__NOC_FIELD_PROBE__  fields=[Codigo, CPF]       → 400 "Campo CPF não está disponível."
cliente=__NOC_FIELD_PROBE__  fields=[Codigo, Endereco]  → 400 "Campo Endereco não está disponível."
cliente=__NOC_FIELD_PROBE__  fields=[Codigo, NoctusNaoExiste] → 400 "Campo NoctusNaoExiste não está disponível."
```

The three known-bad runs are the discriminator: they prove field validation
wins the race, so the clean run's *record*-not-found means the eleven fields
were all accepted. **Send a code that cannot exist and neither branch returns
anyone's data** — a rejection names the field, a pass names nothing.

Do this before wiring any detail endpoint over a personal-data family. It is
the same lever as the `accepted = requested − rejected` derivation on
`/clientes/listar` (above), applied to the one endpoint shape where you cannot
simply ask for one row without getting one person.

> ⚠️ **Still unverified, deliberately:** the *shape* of a populated
> `/clientes/detalhes` response. Only a real record reveals whether it is the
> flat dict `/imoveis/detalhes` returns, and reading one to find out is the
> thing this whole section avoids. `vista_cliente_detalhes_to_showcase` reads
> a flat dict and the ERP service degrades a non-dict to `{}`, so the failure
> mode is a detail dialog of em-dashes, not a crash. First real open by an
> admin settles it.

**✅ Consumed since 2026-08-22 — under a two-tier minimisation split.** The ERP
Clientes tab reads this family live. Seven fields in the list, the four
demographic ones only on opening one named client, nothing persisted, admin
only, every call audited. The design and its enforcement points are in § 5.1;
the residual controller decisions (legal basis, the Vista DPA, audit-log
retention) are recorded in `LGPD-WARNINGS.md` — they are the user's to make and
do not block a read-only, non-persisting surface.

**🔴 No `DataAtualizacao` ⇒ `clientes` cannot be delta-synced.** Unlike
`/imoveis` (§ 2 `filter`), there is no modification timestamp to filter on,
so the only way to refresh 42,960 clients is a full crawl — **860 requests**
at the 50-row cap. Ask Vista for the field before designing any sync loop
over this family (§ 9 Tier 4).

#### `/clientes/listarConteudo` — the PHP crash is FIXED, still unwrapped

Probed 2026-08-19 it returned **404 with a raw PHP error** on a well-formed
`pesquisa` (`in_array(): Argument #2 ($haystack) must be of type array, null
given`) — an unhandled server-side crash. **Re-probed 2026-08-21 it answers
a normal `400 "Campo X não está disponível"`**, i.e. it now behaves like
every other endpoint and validates fields properly. Most likely repaired by
the same maintenance that applied the grant.

It is still **not wrapped by a tool** and its useful field set is unmapped
(`Cidade` — the obvious analogue of `/imoveis/listarConteudo` — is rejected).
If a `clientes` filter-enum UI is ever needed, map it then; do not assume
parity with the `/imoveis` version.

**UI behavior now that the grant landed:** render real client data. Keep the
"Permissão pendente — solicite expansão junto à Vista" placeholder wired to
the typed `VistaPermissionDenied` path — it is the correct rendering if the
grant is ever rolled back, and for any tenant that lacks it. The MCP tool
still surfaces 401 as a typed error with the key redacted (§ 3).

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

### 4.5 `/corretores` (brokers) — 🔒 one route gated, two ❌ absent

**Re-probed live 2026-08-21 — still gated, and now notably so.** Vista
granted `clientes/listar` + `clientes/detalhes` on the same key the same
day (§ 4.2) and `corretores/listar` did **not** open — the three were asked
for together in one request (§ 9 Tier 1). So this is not "the grant hasn't
propagated": it is a per-method decision that came back partial. When
re-asking, quote this method name alone, plus the live 401, and note that
the sibling methods in the same ticket did land.

| Op | Method | Path | This tenant (2026-08-21) | MCP tool |
|---|---|---|---|---|
| List | GET | `/corretores/listar` | 🔒 401 | `vista.corretores.list` |
| Detail | GET | `/corretores/detalhes` | ❌ 404 | — |
| Content | GET | `/corretores/listarConteudo` | ❌ 404 | — |

> The two ❌ rows are **new evidence from 2026-08-19** — they had never been
> probed. They matter for scoping the ask: even a granted `corretores/listar`
> buys the roster only, with no per-broker detail route behind it.

#### Candidate field set — ⚠️ UNPROVEN (same caveat as § 4.2)

```
Codigo  Nome  Email  Fone  Celular  Creci
Setor  Foto  Status  DataCadastro
```

Lives in `calibration.CANDIDATE_CORRETOR_FIELDS`. Never confirmed against a
200 — see § 4.2's field-set caveat, which applies verbatim.

#### ✅ The ungated substitute — prefer it

`/usuarios/listar` (§ 4.3, ✅) **already returns the broker roster** with
`Setor: "Corretores"`, and `/imoveis/listar` embeds the listing broker's
name + email per property. So the *practical* gap `/corretores` leaves is
small. This is codified in the tool surface, not just here: the
`vista.corretores.list` MCP descriptor names `vista.usuarios.list` as the
substitute, so a host LLM that hits the 401 is routed to the working call
instead of reporting itself blocked. Weigh that before spending a support
request on this family.

### 4.6 Endpoint families NOT exposed on this tenant — ❌

**Re-probed live 2026-08-05** (`<family>/listar`, GET): every one below
returned **404 "No route found"** — not 401. They are referenced in the
public-doc nav with no spec body.

```
/leads/*                  ❌ 404   (public-doc nav only; doc body empty)
/atendimentos/*           ❌ 404
/agendamentos/*           ❌ 404
/negociacoes/*            ❌ 404
/propostas/*              ❌ 404
/vendas/*                 ❌ 404
/condominios/*            ❌ 404
/empreendimentos/*        ❌ 404
/portais/*                ❌ 404
/buscas/*                 ❌ 404
/campanhas/*              ❌ 404
/tarefas/*                ❌ 404
/reservas/*               ❌ 404
/bairros/*                ❓       (not re-probed; enum values already come
/cidades/*                ❓        from /imoveis/listarConteudo, so there is
/categorias/*             ❓        no consumer need — probe before relying)
/tabelas/*                ❓
/ancillary-revenue/*      ❓       (referenced via the user-supplied link
                                    `#fotos_ancillary-revenue`; no body)
```

**A 404 cannot distinguish** "not provisioned for this tenant" from "not
built in this Vista REST version" — only Vista can answer that. That
question is the Tier-2 ask in the support request (§ 9).

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

The adapter sends seven distinct field sets, all hardcoded in
`app/services/vista_showcase_service.py`:

| Constant | Endpoint | Field count | Notes |
|---|---|---|---|
| `IMOVEL_LIST_FIELDS` | `/imoveis/listar` | 24 | Includes `FotoDestaque`, `BanheiroSocial`, `UF`, nested `{Corretor: [Nome, Email]}` |
| `IMOVEL_DETAIL_FIELDS` | `/imoveis/detalhes` | 27 | Adds `Numero`, `Complemento`, `Caracteristicas`, `Empreendimento`, `Construtora`, `DataCadastro`; nested Corretor adds `Fone`; **no photo field works** |
| `CONTEUDO_FIELDS` | `/imoveis/listarConteudo` | 4 | `Status`, `Categoria`, `Cidade`, `Bairro` — populates filter dropdowns |
| `CLIENTE_LIST_FIELDS` | `/clientes/listar` | 7 | 🔴 **Deliberately 7 of the 11 the tenant accepts** — see the minimisation note below |
| `CLIENTE_DETAIL_FIELDS` | `/clientes/detalhes` | 11 | The list set + `DataNascimento`, `Sexo`, `EstadoCivil`, `Profissao` |
| `USUARIO_FIELDS` | `/usuarios/listar` | 5 | `Codigo`, `Nome`, `Email`, `Foto`, `Setor` |
| `AGENCIA_FIELDS` | `/agencias/listar` | 6 | `Codigo`, `Nome`, `Endereco`, `Cidade`, `Bairro`, `Site` |

> **All sets are calibrated for `oneconsu-rest.vistahost.com.br` on 2026-05-02
> and re-verified 2026-05-03** (the two `CLIENTE_*` sets: 2026-08-21). A
> different tenant key may need a different split — see §6 ("Per-tenant
> calibration — current state vs design intent") for the gap.

#### 🔴 The clientes split is a privacy decision, not a performance one

`CLIENTE_LIST_FIELDS` withholds four fields the tenant *would* return —
`DataNascimento`, `Sexo`, `EstadoCivil`, `Profissao`. A 42,960-row family
rendered 50 at a time is the worst place to carry a demographic profile: every
page view would pull fifty of them to display a name and a phone number. The
detail endpoint asks for them instead — once, for one named `codigo`, with its
own audit row carrying `projection: "detail"`, so the log can distinguish
"listed fifty names" from "opened one person's profile".

The constants are the *policy*; the enforcement is structural. `ShowcaseCliente`
has no field to hold a birth date and no `raw` passthrough, so the list
endpoint cannot leak one even if a tenant over-answers. Widening the list
therefore takes a type change — which is exactly the moment the decision
should be re-made rather than drifted into. Guarded by
`test_cliente_list_projection_cannot_carry_a_demographic_field` (seed) and
`test_the_list_never_ASKS_vista_for_a_demographic_field` (ERP router — the
wire-level half, since a projection that requests fields and then drops them
has already transmitted them).

### 5.2 Normalizer field-mapping contract

`noctusai_lib/integrations/vista/normalizers.py` exposes six payload mappers plus
helpers. Every mapper preserves the original Vista payload in the DTO's
`raw` field for debug + future-migration use — **except the two cliente
mappers**, which do not, because `ShowcaseCliente` has no `raw` field. There is
no clientes migration to hold a payload for, and an unstructured copy of
personal data would re-admit through the back door precisely what the field
selection excludes through the front. The ERP envelope reports
`raw_available: false` for that family, and the Clientes tab consequently
offers no "mostrar payload bruto" button.

`vista_cliente_to_showcase` reuses `_first_corretor_nome`: Vista returns
`Corretor` dict-keyed-by-id on clientes exactly as on imóveis, so the quirk has
one reader and cannot be re-solved differently twice.

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

**The endpoint list is seed-canonical** — `VISTA_ENDPOINT_BASELINE` in
`noctusai_lib.integrations.vista`. Both consumers import it: the MCP's
`vista.diagnostics.probe` and `vista_showcase_service.diagnose()`.

> **Lifted to the seed 2026-08-05 at N=2 (always-doc-the-trim).** The
> identical list had been hand-copied into `mcp/vista/tools/diagnostics.py`
> *and* `vista_showcase_service.py`, and **both carried the same two stale
> labels** — a hand-maintained list in two places drifts in two places.
> Do not re-inline it; a re-probe must update exactly one tuple.

```python
# (path, expected bare-GET status, probe_status, note)
VISTA_ENDPOINT_BASELINE = (
    ("/imoveis/listar",        200, "live_probed",      "reachable"),
    ("/imoveis/listarConteudo",400, "live_probed",      "bare GET needs `pesquisa`"),
    ("/usuarios/listar",       200, "live_probed",      "reachable"),
    ("/agencias/listar",       200, "live_probed",      "reachable"),
    ("/clientes/listar",       401, "permission_gated", "§ 4.2"),
    ("/clientes/detalhes",     401, "permission_gated", "§ 4.2; 401 precedes the missing-param 400"),
    ("/corretores/listar",     401, "permission_gated", "§ 4.5"),
    ("/imoveis/fotos",         405, "write_only",       "GET not allowed"),
)
```

> **`/clientes/detalhes` joined the baseline 2026-08-19.** It is the second
> Tier-1 method, and the probe is how we find out the grant landed — leaving
> it out meant the only signal for half the ask was a manual re-probe. Note
> its expected status is **401, not 400**: Vista runs the permission check
> *before* parameter validation, so a bare GET with no `cliente=` still reads
> as denied. A future agent who "fixes" this row to 400 will have broken the
> grant detector.

**`expected` encodes that a non-200 is not automatically a fault.** Two
labels were corrected 2026-08-05:

- `/imoveis/listarConteudo` — needs a `pesquisa` param, so the bare probe
  GET is *always* 400. The old probe reported `upstream_error` on an
  endpoint whose own tool works fine: a permanent false alarm that trains
  an operator to ignore the report.
- `/imoveis/fotos` — answers GET with **405**, not 404, and was labelled
  `tier_gated`. It is a *write-only* (POST upload) route that exists. The
  405-vs-404 distinction is what makes read-only write-surface probing
  possible at all (§ 4.2).

`probe` therefore returns `{…, expected_http_status, as_expected, note}` per
row plus a top-level `unexpected: [...]` — **read `unexpected`, not
`status`**, to decide whether a tenant has actually drifted.

Probes run **sequentially** (~1.4s wall-clock for the eight baseline rows).
The MCP tool descriptor states this count too — **derived** via
`len(VISTA_ENDPOINT_BASELINE)`, never typed, since the hand-written "7" went
stale the day `/clientes/detalhes` joined the baseline and told a host LLM to
expect one fewer row than the probe returns, on precisely the row that detects
the Tier-1 grant landing. Guarded by
`test_probe_descriptor_endpoint_count_matches_the_baseline`.
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

### 2026-08-21 — ✅ The Tier-1 grant LANDED (2 of 3) + live field map + delta sync solved

Vista replied that they had re-applied the endpoint permissions on key
`…644c` and cleared their system cache. Verified by probe, not by their word
(§ 7.0 of the project doc), in a fresh process as well as through the MCP:

- **`/clientes/listar` 401 → 200** (42,960 clients) and
  **`/clientes/detalhes` 401 → 200**. The § 4.2 gate is open.
- **`/corretores/listar` is still 401** — same key, same ticket, did not
  open. The ask is *partially* satisfied; § 4.5 carries the re-ask.
- **`/clientes/listarConteudo`'s raw-PHP crash is fixed** — it now returns a
  normal field-validation 400 (§ 4.2).
- **Live `clientes` field set mapped** — 11 of 32 candidates accepted,
  established from 400 error messages **without reading any client record**.
  The old guess was wrong in both directions; the seven omissions were the
  dangerous half, because calibration narrows and never widens (§ 4.2).
- **LGPD categories corrected** — no CPF/address/email on this tenant, but
  `DataNascimento`/`Sexo`/`EstadoCivil`/`Profissao`/`Celular` are returned.
  The intake must be re-done against the real list.
- **Delta sync solved for `/imoveis`** (§ 2) — `filter` on `DataAtualizacao`
  works in both operator and range form; no Vista request needed. It does
  **not** work for `/clientes`, which has no such field.
- **Two route names in § 4.2 were our own typos** — `/clientes/pesquisar`
  (never a documented Vista method) and `historicos` (published singular,
  `historico`). Re-probed under the published names: still 404. Generalised
  rule now in § 4.2: a 404 on a name you cannot cite in the vendor's docs is
  *untested*, not absent.
- **Code:** the endpoint baseline re-graded (`/clientes/*` → `live_probed`,
  so a future 401 reads as a ROLLBACK); `VistaFieldNotAvailable` now carries
  `.fields` and calibration drops the whole rejected set per pass —
  **13 HTTP round-trips → 2**, measured live, since Vista names every
  rejected field in one 400 and we only ever read the first; `.field` kept
  for the ERP router. Public-doc surface re-swept into
  `diagnostics._UNPROBED_KNOWN`.

### 2026-08-19 (later) — Third re-probe from a restarted session; probe count derived

The earlier entry's verdict was re-tested under the one condition it had not
yet been: a **restarted MCP session**, so nothing about the answer could be
blamed on a long-lived process holding old state. Same answer —
`clientes/listar`, `clientes/detalhes`, `corretores/listar` all 401 on key
`…644c`, and `imoveis/listar` + `usuarios/listar` still 200 in the same pass
(so the key itself is live; it is the per-method grant that is missing). The
401 body still echoes the API key verbatim, confirming the § 9 Tier-4 upstream
defect is unfixed on their side. **Tier 1 remains open.**

One drift found and fixed on contact: `vista.diagnostics.probe`'s tool
**description** still advertised "7 endpoints" while the seed-canonical
baseline had grown to 8. A hand-typed count against a derived source — the
same failure shape as `PROBE_ENDPOINTS` forking at N=2 (2026-08-05 entry), one
layer up. It mattered specifically because the 8th row **is** the grant
detector: a host LLM was told to expect a probe that does not include the row
it most needs. The count is now `len(VISTA_ENDPOINT_BASELINE)`, guarded by
`test_probe_descriptor_endpoint_count_matches_the_baseline` (verified red
against the pre-fix string).

### 2026-08-19 — Grant NOT landed (re-verified) + gated-surface refined to parity

**The status answer first.** Vista reportedly granted the § 9 Tier-1 ask. It
is **not in effect**: `clientes/listar`, `clientes/detalhes` and
`corretores/listar` all still return 401, confirmed twice — via
`vista.diagnostics.probe` and via raw HTTP in a fresh process using
well-formed `pesquisa` payloads (ruling out both the MCP module cache and a
malformed-request false negative). The full § 2.3 404 surface was re-swept
in the same pass: **nothing moved** — 13 families and 11 `clientes`
sub-routes still 404. Recorded per § 7.0: *verify by probe, not by their
word.*

**Two new pieces of endpoint evidence.** `/corretores/detalhes` and
`/corretores/listarConteudo` are ❌ 404 (never probed before) — so even a
granted `corretores/listar` buys the roster alone. And
`/clientes/listarConteudo` is the odd one out: it neither 401s nor 404s on a
bare GET, but answers a well-formed request with a raw PHP `in_array()`
crash. Documented in § 4.2 so its 400 is not misread as a partial grant.

**The gated half had rotted while waiting.** `clientes`/`corretores` were
stubs diverging from the ✅ families in ways that each lied to a caller, and
were fixed to parity:

| Defect | Consequence |
|---|---|
| `ListClientesInput` declared `page`/`page_size`; `listar_clientes` accepted neither | A host asking for page 2 silently got page 1 — a wrong answer delivered confidently. Both client helpers are now paginated + `showtotal`, clamped to the server's 50 cap. |
| `CLIENTE_CANDIDATE_FIELDS` declared, never referenced; call hardcoded `["Codigo","Nome"]` | Dead constant masquerading as configuration. Replaced by real `CANDIDATE_CLIENTE_FIELDS`/`CANDIDATE_CORRETOR_FIELDS` driven through the calibrator. |
| **A 401 cached the full un-narrowed candidate set as "safe fields"** | `VistaPermissionDenied` subclasses `VistaUpstreamError`, so the generic handler swallowed it and cached every candidate for the process lifetime. The day the grant lands, the first live call would ship that superset and 400 on the first unexposed field — recoverable only by restart. `_calibrate` now returns the floor **without caching** a denial, so the grant self-heals on the next call. |
| `/clientes/detalhes` had no tool despite being 🔒 401 (unlockable), not ❌ 404 | Half the Tier-1 ask was unreachable even if granted. Added `vista.clientes.get`; also added to the probe baseline so the grant is *detected*, not discovered by hand. |
| `FakeVistaClient` claimed signature parity with `VistaClient` in a docstring, enforced by nothing | The Fake kept the old signatures; a consumer passing `page=` would work live and `TypeError` in tests. Fake updated **and** a mechanical parity test added over all 8 client helpers. |

Tool surface 10 → 11. Gated tools now return `probe_status:
"permission_gated"` so a host LLM reads "ask Vista", not "retry". Regression
tests were each verified to go **red** against the pre-fix code.

### 2026-08-05 — Live re-probe (24 routes) + credential-echo fix + baseline seed-lift

Triggered by a capability audit ("what can we actually reach, and what would
we have to ask Vista for?"). Three findings, all fixed same-commit:

1. **🔴 Credential echo (§ 3).** Vista returns the API key **verbatim** in
   401 bodies, and httpx renders the `?key=` URL in transport errors. Both
   reached `VistaUpstreamError.body` / `str(exc)` and the MCP's
   `typed_error.message` — i.e. into agent context. This doc had called the
   token a "masked key hash", which is why it went unnoticed. Fixed by
   `redact_api_key` applied at both HTTP boundaries (`client.py` +
   `real.py`), with regression guards verified to go red without it.
   The ERP router was already clean (fixed strings, not `str(exc)`).
   **Open:** key rotation is a separate decision — it was exposed before
   2026-08-05.
2. **Endpoint-status drift (§ 4.2, § 4.5, § 4.6).** `/clientes/pesquisar`
   was recorded 🔒 but is ❌ 404; six ❓ client sub-routes confirmed ❌ 404;
   thirteen families confirmed ❌ 404. `/imoveis/fotos` is **405
   write-only**, not 404/`tier_gated`. Established the read-only
   405-vs-404 technique for mapping a write surface without issuing writes.
3. **`PROBE_ENDPOINTS` forked at N=2 (§ 5.3).** The same list was
   hand-copied into `mcp/vista/tools/diagnostics.py` and
   `vista_showcase_service.py`, and both carried the same two stale labels.
   Lifted to seed-canonical `VISTA_ENDPOINT_BASELINE`; both now consume it.
   The probe also gained `expected_http_status`/`as_expected`/`unexpected`,
   retiring a permanent false alarm on `/imoveis/listarConteudo`.

Live tenant numbers at probe time: **1,928 properties** (964 pages), 10
users, 1 agency. `Latitude`/`Longitude` are returned but empty on every row
(a data-entry gap at the agency, not an API gap).

Support-request content derived from this probe → § 9.

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

---

## 9. Support request to Vista — what to ask for, and why

> **Derived from the 2026-08-05 live probe (§ 4, § 8).** Ordered by cost to
> Vista, cheapest first, so the easy wins are not held hostage by the hard
> questions. Tier 1 is a config flag; Tier 2 is a question; Tier 3 depends
> on Tier 2's answer.
>
> **Ask per METHOD, not per resource.** Vista's authorization is
> method-scoped — the 401 body literally names `Método: clientes/listar`.
> A request phrased as "give us access to clients" is ambiguous; a request
> naming `clientes/listar` + `clientes/detalhes` is a one-line change on
> their side.

### Tier 1 — grant these on our existing key (no contract change)

| Method | Today | Why we need it |
|---|---|---|
| `clientes/listar` | ✅ **200** (granted 2026-08-21) | Client roster — the base for any CRM-side view |
| `clientes/detalhes` | ✅ **200** (granted 2026-08-21) | Per-client record |
| `corretores/listar` | 🔒 **401 — still open** | Broker roster (partially substitutable — see § 4.5) |

These three are the **only** routes a permission grant can unlock; every
other gap below is a 404, where permission is not the blocker.

> **Status 2026-08-21 — ✅ 2 of 3 granted; the tier stays open on one.**
> Vista re-applied the permissions on key `…644c` and cleared their system
> cache; `clientes/listar` and `clientes/detalhes` now return 200, verified
> by live probe in a fresh process (§ 4.2). No key rotation was involved —
> the same `…644c` key works, which retires the whole "which key did they
> grant?" question that blocked this from 2026-08-05 to 2026-08-19.
>
> **`corretores/listar` did not open.** Asked in the same ticket, on the same
> key, granted the same day — so this is a per-method decision, not
> propagation lag. Re-ask naming *only* this method, quoting the live 401
> (**with our key redacted**) and noting that its two siblings did land. Weigh
> § 4.5 first: `/usuarios/listar` already returns the broker roster ungated,
> so this is a completeness ask, not a blocker.
>
> **The credential-echo rotation (§ 4) is still outstanding** and still
> desirable on its own merits — it is now decoupled from this tier, since no
> new key is needed to use the grant.

### Tier 2 — questions that decide whether Tier 3 exists

For each of the following, ask: **(a)** a separately-contracted module,
**(b)** available in a newer API version we are not pointed at, or
**(c)** not offered at all?

- `clientes/historico` — client interaction timeline
- `clientes/porcorretor` / `clientes/cadcor` — broker↔client assignment
- `clientes/lead` — inbound lead submission
- `imoveis/campos` + `clientes/campos` — the "available fields" introspection
  routes. Both 404 here, which is why field discovery has to be done by
  reading 400 error messages (§ 4.2). Cheap for them, high value for us.
- `negociacoes/*`, `propostas/*`, `vendas/*` — the deal pipeline

**The version question is now much stronger — lead with it.** Re-sweeping
the *published* method names on 2026-08-21 showed the mismatch runs both
ways, which a "these features don't exist" explanation cannot account for:

- Documented by Vista, **404 here**: `imoveis/listas`, `imoveis/campos`,
  `imoveis/historico`, `imoveis/docs`, `imoveis/porcorretor`,
  `imoveis/poragencia`, and every `/imoveis` write route
  (`cadastrar`, `update`, `cadfoto`, `caddoc`, `cadhis`, `cadprop`, `cadcor`).
- **Live here, documented nowhere**: `/imoveis/listarConteudo`,
  `/clientes/listarConteudo`, `/usuarios/listar`, `/agencias/listar`,
  `/corretores/listar`.

A tenant that is missing half the published surface *and* serving five
methods that appear in no public doc is running a **different API version**,
not a reduced feature set. So ask outright: **which REST version is
`oneconsu` on, is there a newer base URL, and where is the documentation for
the version we are actually served?** If they name a newer base URL, treat
it as a new integration surface — re-probe all of § 4 and expect response
shapes to move (§ 7.2 of the project doc).

### Tier 3 — the write path (only if Tier 2 says it is available)

`clientes/lead` (POST) and `clientes/cadastrar` (POST). This is the one
that changes the architecture: **without it there is no API path to write a
captured lead back into Vista**, so any lead-capture flow we build
terminates in our own database and the agency has two places to look. If
Vista cannot offer it, that is a product decision to surface, not a
technical detail.

### Tier 4 — ask regardless (operational)

1. **Page-size cap.** `quantidade` is capped server-side at 50, enforced with
   an explicit `400 "O limite de resultados por página deve ser 50"`
   (confirmed live 2026-08-21 by requesting 200). At 1,943 properties that is
   39 requests; at **42,960 clients it is 860**. The clientes number is the
   one that makes this worth asking — ask whether the cap is raisable.
2. ~~**Delta sync.**~~ ✅ **ANSWERED — no longer an ask for `/imoveis`.**
   `filter` on `DataAtualizacao` already does it, in both operator and range
   form, confirmed live 2026-08-21 (§ 2). **Still an ask for `/clientes`**,
   which exposes no `DataAtualizacao` field — so a 42,960-row family can only
   be full-crawled. Ask them to expose it there.
3. **🔴 Credential echo.** Report it as a security defect on their side:
   *the 401 response body contains the caller's API key in plaintext.* Any
   customer logging error bodies is persisting a credential. We redact on
   receipt (§ 3), but the fix belongs upstream.
4. **Key rotation.** Ask for the rotation procedure — ours has been exposed
   in logs/agent contexts and should be rotated once Tier 1 lands.

### What we deliberately did NOT do

- **No write probes.** The write surface was mapped read-only via the
  405-vs-404 distinction (§ 4.2). Never POST to a live CRM to discover a
  route.
- **No `/clientes` data pulled — still true after the grant (2026-08-21).**
  The 401 is gone, so LGPD is now the *only* thing holding this line, and it
  holds it just as firmly: **a permission grant is not authorization to
  ingest.** The field set in § 4.2 was mapped by reading which names Vista's
  400 *rejects*, so the whole family was characterised without reading a
  client record. Prefer that technique — it answers "what is in here?"
  before the intake, rather than requiring the intake to answer it.
  Bulk ingestion stays blocked on the data-category intake
  (`KB § PATTERNS/security/lgpd.md`) and the user's go-ahead.
