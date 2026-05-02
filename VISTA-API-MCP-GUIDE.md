# Vista CRM API — Authoritative Reference for Building a Vista MCP Server

> **Purpose.** Self-contained reference document for an agent building a
> Vista Software / Loft CRM **MCP server** from scratch. Folds three sources
> into one: (1) the public docs at `https://vistasoft.com.br/api/`,
> (2) live probe results against a real production tenant
> (`oneconsu-rest.vistahost.com.br`, captured 2026-05-01..2026-05-02), and
> (3) lessons learned implementing a typed adapter against the live API.
>
> **This document is portable.** It contains zero relative pointers into the
> repo it shipped with. An agent in any environment can read this file and
> build a Vista MCP server without further context.
>
> **Intended outputs from this document:**
> - A typed MCP server exposing one tool per endpoint family.
> - Strong typing for request params, response shapes, and error classes.
> - A live-probe gating mechanism (because Vista tenants vary widely in
>   which endpoints are enabled).
>
> **What you should NOT assume.** That every endpoint listed in the public
> docs works on every tenant. Vista runs a per-tenant subscription model
> where individual endpoint families are enabled or disabled — the public
> docs are the *superset*; any individual tenant exposes a subset. Always
> live-probe before relying on an endpoint.

---

## 0. TL;DR — what surprised us

If you read nothing else, read these:

1. **Auth is a single API key per tenant**, sent as `?key=<API_KEY>` query
   parameter on every call. No bearer, no OAuth, no cookie.
2. **`Accept: application/json` header is required** — without it some
   endpoints return HTML.
3. **Tenant URL shape** is `https://<tenant-slug>-rest.vistahost.com.br`.
4. **Most endpoints take a single `pesquisa=<URL-encoded JSON>` parameter**
   carrying a structured search payload (`fields`, `filter`, `order`,
   `paginacao`, `advFilter`).
5. **Some endpoints require ID parameters at the *top level*, NOT inside
   `pesquisa`** (e.g. `/imoveis/detalhes?imovel=CA2830&pesquisa=...&key=...`).
6. **Collection responses are dict-keyed-by-primary-id, NOT JSON arrays.**
   `{"CA2830": {...}, "TE0080": {...}, "total": 1784, "paginas": 595, "pagina": 1, "quantidade": 3}`.
   Pagination metadata lives as **sibling keys** of the items. Public docs
   show `{"results": [...]}` — the live API does NOT use that shape.
7. **Pagination cap is 50 items per page** (server-enforced).
8. **Add `&showtotal=1` (top-level, not inside `pesquisa`) to receive `total`
   and `paginas`** in the response envelope.
9. **Field-level permissions** — a field absent from `fields` is silently
   omitted; a field the tenant's key cannot read returns **HTTP 400** with
   `"Campo X não está disponível"`.
10. **Endpoint-level permissions** — a denied endpoint returns **HTTP 401**
    with `"Permissão Negada"` (Portuguese). The endpoint exists; this key
    just lacks access. A different tenant or upgraded subscription tier
    may unlock it.
11. **Endpoints not on this tenant's tier return HTTP 404**, not 401. Treat
    them as "not enabled here" — different from "permission denied."
12. **Photo field name varies per tenant.** Public docs say `Foto`. Our
    probed tenant rejects `Foto` *and* `FotoPrincipal` and only exposes
    `FotoDestaque`. The MCP must probe per tenant and use whatever the
    tenant actually serves.
13. **Field permissions vary per tenant key — re-probe at MCP boot.**
    The public docs are a *superset* across all subscriptions. A given
    tenant key returns 400 for fields outside its permitted subset
    (e.g. our probed tenant rejects `Estado`, `Banheiros`, `Foto`,
    `Slug`, `PalavrasChave`, `CodigoImobiliaria` — all documented as
    available in the public docs). **Calibrate the field set per tenant
    at MCP boot via the routine in §7** — never hard-code the public-doc
    superset.
14. **`Corretor` comes back as a dict keyed by corretor id**, not as a
    flat `{"Nome": "..."}` object. `{"103": {...}, "104": {...}}` —
    multiple corretors per property. Walk the values, not the top-level
    dict.
15. **Public-doc claims diverge from live behavior in several places.**
    Where they disagree, trust the live tenant. Examples throughout.

---

## 1. Authentication

### Auth shape

| Item | Value |
|---|---|
| Method | Single API key per tenant |
| Transport | `?key=<API_KEY>` URL query parameter on every request |
| Required header | `Accept: application/json` |
| Bearer / OAuth / cookie | **Not used** |
| Tenant URL pattern | `https://<tenant-slug>-rest.vistahost.com.br` |
| HTTPS required | Yes (the API does not respond on HTTP) |

### How to obtain a key (out of band)

The tenant's account owner requests it via Vista support — there is no
self-service. Vista's published guidance:
`https://ajuda.vistasoft.com.br/como-solicitar-uma-nova-chave-api/`.
Once issued, the key is per-tenant and per-Vista-account; tenants do not
share keys.

### Permission scope of a key

A single key can carry varying combinations of:
- Endpoint-family permissions (e.g. read `/imoveis/*`, blocked from `/clientes/*`)
- Field-level permissions on enabled endpoints
- Read-only vs. read-write (POST/PUT endpoints require explicit write scope)

**Implication for an MCP**: do NOT assume one key has uniform access. The
MCP must surface per-endpoint and per-field permission status to its host.

### Recommended secret handling for the MCP server

- Read `VISTA_API_KEY` and `VISTA_BASE_URL` from environment / a secrets
  manager. Never hardcode.
- Never log the key (not in error messages, not in audit lines).
- Never send the key to a host LLM in a tool response — strip it from any
  echoed URL.

---

## 2. The `pesquisa` query convention

Most read endpoints take a single `pesquisa=<URL-encoded JSON>` query
parameter carrying a structured search payload. Shape:

```json
{
  "fields": ["Codigo", "Cidade", {"Corretor": ["Nome", "Email"]}],
  "filter": {"Bairro": "Centro", "ValorVenda": [250000, 500000]},
  "advFilter": {"Or": {...}, "And": {...}},
  "order": {"DataAtualizacao": "desc"},
  "paginacao": {"pagina": 1, "quantidade": 50}
}
```

### `fields` — what to return

- Array of field names (strings) plus optional nested-relation objects of
  the shape `{"<RelationName>": ["SubField1", "SubField2"]}`.
- **Always pass `fields` explicitly.** Public docs warn: *"Caso você não
  informe os campos que quer utilizar, a API retornará apenas o código."*
  Without an explicit `fields`, the response is just primary IDs.
- Documented nested relations (subset — varies by endpoint):
  - On `/imoveis/*`: `Corretor` → `Nome`, `Fone`, `Email`, `Creci`;
    `Agencia` → `Nome`, `Fone`, `Endereco`, `Numero`, `Complemento`,
    `Bairro`, `Cidade`; `fotos` (on `/imoveis/listar` only) → `Foto`,
    `FotoPequena`, `Destaque`, `Tipo`, `Descricao`.
  - On `/clientes/*`: `Corretor`, `Imovel` per the public docs.

### `filter` — what to match

| Operator | Shape | Meaning |
|---|---|---|
| equality | `{"Bairro": "Centro"}` | exact match |
| range | `{"ValorVenda": [250000, 500000]}` | between (inclusive bounds, per public-doc examples) |
| comparison | `{"ValorVenda": [">", 250000]}` | `>`, `<`, `>=`, `<=`, `like`, `!=` |
| list (IN) | `{"Status": ["ATIVO", "DISPONIVEL"]}` | semantics confirmed empirically against `/imoveis/listar` |

### `paginacao` — how to page

```json
{"pagina": 1, "quantidade": 50}
```

- `quantidade` is **server-capped at 50**. Asking for more silently caps.
- `pagina` is 1-indexed.
- To receive `total` and `paginas` in the response, append
  **`&showtotal=1`** as a top-level query parameter (NOT inside `pesquisa`).

### `order` — how to sort

```json
{"DataAtualizacao": "desc"}
```

Object whose keys are field names and values are `"asc"` / `"desc"`. Not
all fields support ordering — undocumented; verify per field.

### `advFilter` — boolean composition

Nested boolean composition with `And` / `Or`. Public docs are thin; treat
as power-user. Most MCP tools should expose `filter` only and skip
`advFilter` until a real demand surfaces.

### Top-level (NOT inside `pesquisa`) parameters

Some endpoints require **ID parameters at the top level**, separate from
`pesquisa`. Confirmed against the live tenant or per public docs:

| Endpoint | Top-level param | Example |
|---|---|---|
| `/imoveis/detalhes` | `imovel=<Codigo>` | `?imovel=CA2830&pesquisa=...&key=...` |
| `/clientes/detalhes` | `cliente=<Codigo>` | per public docs; not live-verified |
| `/imoveis/fotos` | `imovel=<Codigo>` | per public docs; not live-verified |
| `/imoveis/anexos` | `imovel=<Codigo>` | per public docs |
| `/imoveis/historicos` | `imovel=<Codigo>` | per public docs |
| `/clientes/historicos` | `cliente=<Codigo>` | per public docs |
| `/clientes/favoritos` | `cliente=<Codigo>` | per public docs |

Always URL-encode values containing whitespace
(e.g. `"Porto Alegre"` → `Porto%20Alegre` or `Porto+Alegre`).

### `&showtotal=1` and other top-level flags

| Flag | Effect |
|---|---|
| `showtotal=1` | Include `total` and `paginas` in the response envelope |
| `key=<API_KEY>` | Authentication (always required) |

---

## 3. Response envelopes

### 3.1 Collection responses (`/imoveis/listar`, `/usuarios/listar`, etc.)

The response is **a top-level dict keyed by primary id**, with pagination
metadata as **sibling keys** of the items. NOT a JSON array.

Live example (truncated, three items):

```json
{
  "CA2830": {
    "Codigo": "CA2830",
    "Cidade": "Cotia",
    "Bairro": "Granja Viana",
    "Categoria": "Casa",
    "ValorVenda": "1450000.00",
    "DataAtualizacao": "2026-04-30 12:14:27"
  },
  "TE0080": {
    "Codigo": "TE0080",
    "Cidade": "Cotia",
    "Bairro": "Centro",
    "Categoria": "Terreno",
    "ValorVenda": "350000.00",
    "DataAtualizacao": "2026-04-29 09:01:55"
  },
  "AP1207": {
    "Codigo": "AP1207",
    "Cidade": "São Paulo",
    "Bairro": "Vila Olímpia",
    "Categoria": "Apartamento",
    "ValorVenda": "780000.00"
  },
  "total": 1784,
  "paginas": 595,
  "pagina": 1,
  "quantidade": 3
}
```

**Pagination metadata keys** to filter when iterating items:
`total`, `paginas`, `pagina`, `quantidade`.

**Public-doc claim mismatch.** Public docs show
`{"results": [...], "total": ..., "pagina": ..., ...}`. The live tenant
does NOT use `results: [...]`. **Trust the live shape.**

**Implication for MCP design.** The MCP wrapper SHOULD normalize this to
`{ items: [...], pagination: { total, paginas, pagina, quantidade } }`
before returning to the host LLM, so the model never has to re-discover
the unusual shape.

### 3.2 Detail responses (e.g. `/imoveis/detalhes`)

Returns a flat object keyed by field, not wrapped:

```json
{
  "Codigo": "CA2830",
  "Cidade": "Cotia",
  "Bairro": "Granja Viana",
  "Categoria": "Casa",
  "ValorVenda": "1450000.00",
  "AreaTotal": "320.00",
  "Dormitorios": "4",
  "Suites": "2",
  "Caracteristicas": {
    "Piscina": "Sim",
    "Lareira": "Sim",
    "Academia": "Não"
  },
  "Latitude": "-23.601234",
  "Longitude": "-46.842311",
  "DataCadastro": "2024-03-15 10:22:11",
  "DataAtualizacao": "2026-04-30 12:14:27"
}
```

### 3.3 Error responses

| HTTP | Body shape (variants) | Meaning |
|---|---|---|
| 200 | normal payload | OK |
| 400 | `{"campo": "X não está disponível"}` (or similar phrasings) | Field-level permission denied or field unknown for this endpoint |
| 401 | `{"mensagem": "Permissão Negada"}` | Endpoint exists; this key lacks permission |
| 404 | typically empty / Vista 404 page | Endpoint not exposed on this tenant's subscription tier |
| 5xx | varies | Upstream error |

**Numeric values returned as strings.** Decimals (`ValorVenda`,
`AreaTotal`, `Latitude`, etc.), integers (`Dormitorios`, `Vagas`,
`Banheiros`), and timestamps all come back as **strings**. The MCP wrapper
SHOULD coerce them where useful.

**Date format.** ISO-ish, with a space separator:
`"2026-04-30 12:14:27"` (no `T`, no timezone). Treat as São Paulo local
time unless the tenant declares otherwise.

### 3.4 Recommended typed-error model for the MCP

```
VistaConfigError(message)         — base URL or API key missing
VistaTimeout(endpoint)            — httpx.TimeoutException or socket timeout
VistaUpstreamError(status, body)  — 5xx + uncategorized 4xx wrapper
VistaPermissionDenied(endpoint)   — 401 with "Permissão Negada"
VistaFieldNotAvailable(field, endpoint)
                                  — 400 with the "não está disponível" pattern
VistaNotFound(endpoint)           — 404 (endpoint not enabled here)
```

The MCP host should see each as a structured tool-error payload, never
raw 4xx text. Map non-200 responses to one of these classes; surface raw
body only as a debug field.

---

## 4. Endpoint inventory

### Status legend

- ✅ **live-200** — confirmed reachable on at least one tenant.
- 🔒 **live-401** — endpoint exists on Vista; the key probed lacked permission.
  A different tenant / upgraded tier MAY have permission.
- ❌ **live-404** — endpoint not exposed on the probed tenant's subscription tier.
- 📖 **doc-only** — appears in public docs (`https://vistasoft.com.br/api/`)
  but never live-probed in this reference.
- ❓ **referenced** — mentioned in public-doc nav with no spec body. An MCP
  targeting a tenant with permission MUST verify the shape live before relying.

The "this tenant" column reflects results from the
`oneconsu-rest.vistahost.com.br` probe (2026-05-01..2026-05-02). Use it as
a lower bound — your tenant may have more enabled.

### 4.1 `/imoveis` — Properties

| Op | Method | Path | ID param | This tenant | Public docs | Notes |
|---|---|---|---|---|---|---|
| List | GET | `/imoveis/listar` | — | ✅ | 📖 | 1,784 properties live. |
| Detail | GET | `/imoveis/detalhes` | `?imovel=` | ✅ | 📖 | `Foto` field NOT available here — use `Foto` from `listar`. |
| List enum content | GET | `/imoveis/listarConteudo` | — | ✅ | ❓ | Returns enum values for filters. Drives dropdowns. |
| Photos | GET | `/imoveis/fotos` | `?imovel=` | ❌ | 📖 | Returns 404 (not 401) on this tenant — different tier. Workaround: use `Foto` field on `listar`. |
| Documents | GET | `/imoveis/anexos` | `?imovel=` | ❓ | 📖 | Not probed. |
| History | GET | `/imoveis/historicos` | `?imovel=` | ❓ | 📖 | Public-doc spelling is `historicos`; `historico` (singular) returned 404. |
| Available fields | GET | `/imoveis/campos` | — | ❓ | 📖 | Returns field-name reference for this endpoint. Useful for MCP's field-validator at boot. |
| Create | POST | `/imoveis/cadastrar` | — | ❓ | 📖 | Write operation; out of scope for read-only MCPs. |
| Update | PUT | `/imoveis/alterar` | `?imovel=` | ❓ | 📖 | Write. |
| Add photo | POST | `/imoveis/cadfoto` | `?imovel=` | ❓ | 📖 | Write. |
| Add document | POST | `/imoveis/caddoc` | `?imovel=` | ❓ | 📖 | Write. |
| Add history | POST | `/imoveis/cadhis` | `?imovel=` | ❓ | 📖 | Write. |
| Register owner | POST | `/imoveis/cadprop` | `?imovel=` | ❓ | 📖 | Write. |
| Assign broker | POST | `/imoveis/cadcor` | `?imovel=` | ❓ | 📖 | Write. |
| Search variants | GET | `/imoveis/buscar`, `/imoveis/pesquisar`, `/imoveis/proximos`, `/imoveis/destaque` | — | ❌ | — | Not on this tenant; not in public docs either. |

#### Confirmed `/imoveis/listar` field set (live, oneconsu-rest, 2026-05-02)

⚠️ **Per-tenant calibration is mandatory.** Field availability varies by
tenant key even on the same Vista host. The table below is what the
probed tenant actually serves; another tenant may expose different
fields. Always re-probe at MCP-server boot.

✅ **Available** (29 fields — request these):

```
Codigo            string   primary id (e.g. "CA2830", "ONE10006")
TituloSite        string   marketing title
Categoria         string   "Casa", "Casa em Condomínio", "Terreno", "Apartamento", …
Status            string   "Venda" / "Aluguel" / "Venda e Aluguel"
                            (semantically purpose-like on this tenant — public
                             docs label this "listing status" but the values
                             this tenant returns are sale-vs-rent)
Finalidade        string   often empty; "Residencial" when populated
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
ValorLocacao      string
AreaTotal         string   m² as string
AreaPrivativa     string
AreaConstruida    string
Dormitorios       string   integer as string
Suites            string
Vagas             string
BanheiroSocial    string   "Sim" / "Nao" — boolean-shaped, NOT a count
                            (the count field `Banheiros` is denied here)
Caracteristicas   object   nested boolean/text features (Banheiro Social,
                            Piscina, Lareira, …) — appears on detalhes; sometimes
                            on listar
DataCadastro      string   ISO-ish, space separator ("2024-03-15 10:22:11")
DataAtualizacao   string
FotoDestaque      string   primary photo URL — the only photo field this tenant exposes
Corretor          object   dict KEYED BY corretor id, e.g.:
                            {"103": {"Codigo": "103", "Nome": "Fernanda", "Email": "..."},
                             "104": {"Codigo": "104", "Nome": "Elisa", ...}}
                            NOT a flat {"Nome": "..."} — see § 9.1
```

🔒 **Rejected on this tenant** (HTTP 400 if requested):

```
Estado              → use UF
Banheiros           → use BanheiroSocial (boolean-shaped, not a count)
Foto                → use FotoDestaque
FotoPrincipal       → use FotoDestaque
Slug                → not exposed
PalavrasChave       → not exposed
CodigoImobiliaria   → cannot be requested explicitly; sometimes appears in
                       the response anyway. Don't depend on either way.
```

**MCP design implication.** The MCP server should ship a per-tenant
`safe_fields` map populated at boot via the probe routine in §7.
Hard-coding "the Vista field set" without per-tenant calibration is the
exact failure mode our reference implementation tripped — Phase 1 hard-
coded the public-doc set and got `[502] Vista respondeu erro 400` on
first real use. The fix was to (a) probe each candidate field against
the live tenant, (b) keep both old + new field names in the normalizer
so other tenants still resolve, (c) catch `VistaFieldNotAvailable`
explicitly at the API boundary so the next drift surfaces clearly.

#### `/imoveis/detalhes` quirks

- Accepts the same `pesquisa.fields` array.
- `Foto` is NOT valid here — returns 400. Pull `FotoDestaque` from
  `/imoveis/listar` and pass it through alongside the detalhes payload.
- `imovel=<Codigo>` MUST be at the top level of the URL, not inside `pesquisa`.
- **Field set on this tenant differs from `/imoveis/listar`.** `Slug` and
  `PalavrasChave` are denied here too (along with the listar denials).
  Available fields: the listar set MINUS `FotoDestaque`, MINUS the listar-
  level `Caracteristicas` (which appears here in a richer form). See § 4.1
  field table for the calibrated detail set.
- `/imoveis/campos` (the public-doc field-discovery endpoint) returns 404
  on this tenant — so per-endpoint field discovery has to use the probe-
  for-400 routine in §7, not the `/campos` endpoint.

#### `/imoveis/listarConteudo` quirks

- `pesquisa.fields=["Status","Categoria","Cidade","Bairro"]` returns enum
  values (one array per requested field) used to populate filter dropdowns
  without scanning the full catalog.
- Useful first call for an MCP `list_property_filters` tool.

### 4.2 `/clientes` — Clients

🔒 not authorized on the probed tenant; documented in public docs.

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

Documented `/clientes` fields per public docs (subset — verify live):
`Codigo`, `Nome`, `Email`, `Fone`, `FoneCelular`, `Bairro`, `Cidade`,
`Estado`, `UF`, `CEP`, `Endereco`, `Numero`, `Complemento`, `CPF`,
`RG`, `DataNascimento`, `EstadoCivil`, `Profissao`, `Empresa`,
`DataCadastro`, `Corretor`, `Imovel`.

**LGPD note for MCP authors.** The `/clientes` family carries personal
data including potentially CPF/RG. An MCP exposing this surface should:
- Make consent / authorization the host's problem (require an explicit
  flag in tool calls that touch personal data).
- Never log full payloads — only metadata (endpoint, status, latency,
  count). Especially never log CPF/RG values.
- Document a retention contract (the MCP server itself should not
  persist responses; it should be a read-through proxy).

### 4.3 `/usuarios` — internal Vista users (✅)

| Op | Method | Path | This tenant | Notes |
|---|---|---|---|---|
| List | GET | `/usuarios/listar` | ✅ | 16+ rows on the probed tenant |

#### Confirmed live field set

```
Codigo   string
Nome     string
Email    string
Foto     string   URL
Setor    string   department/team
```

#### Fields that returned 400 on the probed tenant

`Apelido`, `Login`, `FotoPequena`, `DataCadastro`, `CodigoImobiliaria`.
Do not request unless your tenant key changes.

### 4.4 `/agencias` — agency metadata (✅)

| Op | Method | Path | This tenant | Notes |
|---|---|---|---|---|
| List | GET | `/agencias/listar` | ✅ | Single row on the probed tenant |

#### Confirmed live field set

```
Codigo   string
Nome     string
Endereco string
Cidade   string
Bairro   string
Site     string
```

#### Fields that returned 400 on the probed tenant

`Estado`, `UF`, `CEP`, `Telefone`, `Email`, `Foto`, `Logo`, `Status`,
`DataCadastro`. Avoid unless your tenant exposes them.

### 4.5 `/corretores` — brokers (🔒)

Endpoint exists; the probed tenant's key has no permission.
Documented per public docs but no live confirmation here.

### 4.6 Endpoint families NOT exposed on the probed tenant (❌)

These returned 404 on `oneconsu-rest.vistahost.com.br`. They appear in the
public-doc nav but the public docs provide no spec body. Treat as ❓ for
an MCP targeting other tenants — verify before relying:

```
/leads/*                  ❓
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
/ancillary-revenue/*      ❓
/buscas/*                 ❓
/campanhas/*              ❓
/tarefas/*                ❓
/reservas/*               ❓
```

If/when an MCP targets a tenant exposing any of these, run the discovery
probe (§7) and add a row above with the verified shape.

---

## 5. Reference adapter contract — what we built against this API

A typed Python adapter against this API, used as the reference
implementation, looks like this:

```
backend/
├── integrations/vista/
│   ├── client.py          # VistaClient(base_url, api_key, timeout)
│   │                      #   .list_imoveis(...)
│   │                      #   .get_imovel(codigo, ...)
│   │                      #   .list_imoveis_conteudo(...)
│   │                      #   .list_usuarios(...)
│   │                      #   .list_agencias(...)
│   │                      #   .probe(path, ...)  → (status, latency, body)
│   │                      #
│   │                      # Typed errors raised:
│   │                      #   VistaConfigError, VistaTimeout,
│   │                      #   VistaUpstreamError, VistaPermissionDenied,
│   │                      #   VistaFieldNotAvailable, VistaNotFound
│   │                      #
│   │                      # Helpers:
│   │                      #   PAGINATION_KEYS = {"total","paginas","pagina","quantidade"}
│   │                      #   extract_items(resp) → (items, pagination)
│   │
│   ├── types.py           # Pydantic / TypedDict models for each endpoint:
│   │                      #   VistaListImovelDTO, VistaImovelDetalhesDTO,
│   │                      #   VistaUsuarioDTO, VistaAgenciaDTO, …
│   │                      #
│   │                      # Plus showcase/normalized DTOs that the
│   │                      # caller sees:
│   │                      #   ShowcaseImovel, ShowcaseImovelDetalhes,
│   │                      #   ShowcaseUsuario, ShowcaseAgencia,
│   │                      #   ShowcaseEnvelope, ShowcaseTabStatus,
│   │                      #   ShowcaseDiagnostic
│   │                      #
│   │                      # Every Showcase DTO carries a `raw: dict`
│   │                      # field with the original Vista payload, so
│   │                      # downstream consumers (e.g. an importer)
│   │                      # have full source for field-mapping decisions.
│   │
│   └── normalizers.py     # vista_imovel_to_showcase(payload) → ShowcaseImovel
│                          # vista_imovel_detalhes_to_showcase(payload) → ShowcaseImovelDetalhes
│                          # vista_usuario_to_showcase(payload) → ShowcaseUsuario
│                          # vista_agencia_to_showcase(payload) → ShowcaseAgencia
│                          #
│                          # Normalizers:
│                          # - coerce decimal-strings to floats where useful
│                          # - parse ISO-ish dates to datetime
│                          # - keep Vista source IDs (.codigo) for migration provenance
│                          # - never drop fields silently — unknown fields
│                          #   stay in `raw` for future mapping
```

### Key design choices that matter for an MCP

1. **Lenient at construction, strict at request time.** The `VistaClient`
   constructor does NOT validate base URL / API key — it stores them. The
   first failing request raises `VistaConfigError`. Reason: in a server
   that wires modules at boot but loads secrets lazily, fail-fast at
   construction crashes the boot.

2. **`extract_items()` is a single point of truth for the dict-keyed-by-id
   shape.** Every collection-endpoint normalizer goes through it. Don't
   re-iterate the response in N places.

3. **Field constants live alongside the client.** `IMOVEL_LIST_FIELDS`,
   `IMOVEL_DETAIL_FIELDS`, `USUARIO_FIELDS`, `AGENCIA_FIELDS` are
   per-tenant-confirmed safe field sets. The MCP can either (a) ship its
   own per-tenant configurable field sets, or (b) call `/imoveis/campos`
   et al at boot and cache.

4. **Probe endpoint.** `client.probe(path, params)` returns
   `(status, latency_ms, body)` without raising — used by a "diagnostic"
   tool that lists every known endpoint with its current status against
   *this* tenant. Strongly recommended for the MCP: an MCP `vista_probe`
   tool that the host can call before relying on a particular endpoint.

5. **Audit logging.** Every outbound Vista call writes one audit row with
   `{user_id, endpoint, method, params_keys, status, latency_ms,
   timestamp}`. The Vista *response payload itself* is never persisted —
   only metadata. This satisfies the LGPD live-read constraint.

---

## 6. MCP server design — recommendations

### Tool surface

One MCP tool per endpoint family, mirroring the HTTP surface but with
typed inputs and normalized outputs:

| MCP tool | Backed by | Input | Output |
|---|---|---|---|
| `vista_list_imoveis` | `/imoveis/listar` | `{filter?, fields?, page?, page_size?, order?}` | `{items: [Imovel], pagination: {...}}` |
| `vista_get_imovel` | `/imoveis/detalhes` | `{codigo, fields?}` | `Imovel` |
| `vista_list_imoveis_filters` | `/imoveis/listarConteudo` | `{fields: [...]}` | `{<field>: [enum_values]}` |
| `vista_list_usuarios` | `/usuarios/listar` | `{filter?, fields?, page?, page_size?}` | `{items: [Usuario], pagination: {...}}` |
| `vista_list_agencias` | `/agencias/listar` | `{filter?, fields?}` | `{items: [Agencia], pagination: {...}}` |
| `vista_list_clientes` | `/clientes/pesquisar` (when authorized) | `{filter, fields, page?, page_size?}` | `{items: [Cliente], pagination: {...}}` |
| `vista_get_cliente` | `/clientes/detalhes` | `{codigo, fields?}` | `Cliente` |
| `vista_probe` | meta | `{path, params?}` | `{status, latency_ms, body_summary}` |
| `vista_list_known_endpoints` | meta | `{}` | `[{path, status, last_probed_at, ...}]` |

### Normalize at the MCP boundary

The MCP wrapper SHOULD:
- Convert dict-keyed-by-id collection responses to `{items: [...], pagination: {total, paginas, pagina, quantidade}}` before returning.
- Coerce numeric-string fields (`ValorVenda`, `Latitude`, `AreaTotal`,
  `Dormitorios`, …) to numbers where useful, while keeping the original
  string in a parallel `_raw` field so the host can audit precision.
- Parse `DataCadastro` / `DataAtualizacao` to ISO 8601 with `T` and
  timezone (assume São Paulo / `America/Sao_Paulo` unless the tenant
  declares otherwise).
- Surface partial-permission states explicitly: a 401 on `/clientes/*` is
  not a server error — it's "tenant key lacks this scope; ask Vista
  support to expand."

### Error mapping

| HTTP / cause | MCP tool error class | Message hint to host |
|---|---|---|
| 400 with "não está disponível" | `VistaFieldNotAvailable` | "Field `X` not exposed for this tenant key. Remove from request or request scope expansion." |
| 401 with "Permissão Negada" | `VistaPermissionDenied` | "Endpoint `X` exists but key lacks permission. Subscription / scope expansion needed." |
| 404 | `VistaNotFound` | "Endpoint `X` not enabled on this tenant's subscription tier." |
| Timeout | `VistaTimeout` | "Vista upstream timed out after Ns. Retry with smaller page or wait." |
| 5xx | `VistaUpstreamError` | "Vista upstream returned NNN. Body: …" |
| Config missing | `VistaConfigError` | "VISTA_BASE_URL or VISTA_API_KEY missing." |

### Live-probe gating

Each tool registers a `probe_status` field — `live_probed | doc_only |
referenced` — so a host operator can filter to only-known-good tools.
Run a probe sweep at MCP-server boot and cache results with a TTL
(e.g. 24 h). Re-probe on demand via `vista_probe`.

### Rate / quota

Vista does not publish rate limits in the public docs. Empirically the
probed tenant tolerated low single-digit RPS without error. Recommended
defaults for the MCP:
- HTTP timeout: **15s** per request
- Max parallelism per tenant: **4 concurrent requests**
- Retry on 5xx / timeout: **2 retries with exponential backoff**, then surface as `VistaUpstreamError` / `VistaTimeout`
- Do NOT retry 4xx (the request is wrong; retrying won't help)

### Caching

- Cache `/imoveis/listarConteudo` (filter dropdowns) for **5–15 minutes** — values change rarely and the call is repetitive.
- Cache `/agencias/listar` for **1 hour** — single-row, mostly static.
- Do NOT cache `/imoveis/listar` or `/imoveis/detalhes` results that contain customer-facing data — freshness > saving an upstream call.
- Do NOT cache anything on `/clientes/*` for any duration — personal data, treat as live-read.

---

## 7. Discovery techniques (how to extend this document for a new tenant)

When pointing the MCP at a new Vista tenant, run this routine:

1. **Confirm auth.** `GET <base>/imoveis/listarConteudo?pesquisa={"fields":["Status"],"paginacao":{"pagina":1,"quantidade":1}}&key=<KEY>` with `Accept: application/json`. Expected: 200 with a `Status` enum dict. 401 → wrong key. Empty / HTML → wrong base URL or missing `Accept`.

2. **Probe endpoint surface.** For each row in §4 marked ✅ / 🔒 / ❓, fire a minimal request and record `(status, body_excerpt, latency)`. Use a tiny `pesquisa` (e.g. `{"fields":["Codigo"],"paginacao":{"pagina":1,"quantidade":1}}`).

3. **Discover field permissions per endpoint.** If `/imoveis/campos` is enabled, call it for the canonical list. Otherwise, request a generous `fields=[...]` set and read 400 responses to learn which fields are blocked. Cache per-endpoint allowed fields.

4. **Discover undocumented endpoints.** Try the families listed in §4.6 (`/leads/*`, `/atendimentos/*`, …) with the same minimal `pesquisa`. 200 → live, document the shape. 401 → exists but blocked. 404 → not on this tier.

5. **Verify response shape.** For each ✅ endpoint, capture a real response and confirm it's dict-keyed-by-id (collection) or flat object (detail). If a tenant returns `{"results": [...]}` (per public docs), update the MCP normalizer to detect both shapes.

6. **Diff against this document.** Anything new goes into a tenant-specific addendum or a PR to this document. Anything that was here but is missing on this tenant becomes a tenant-specific override.

A scriptable form of this routine lived as `vista_smoke.py` in the
reference implementation and was subsumed by the MCP's `vista_probe` tool.

---

## 8. LGPD / data-handling considerations

Vista CRM data routinely includes Brazilian personal data — names,
emails, phones, CPF/CNPJ, addresses, family details, financial details.
Under LGPD (Lei Geral de Proteção de Dados, Brazil's data protection
law), this carries handling obligations regardless of the storage tier.

### Non-negotiable defaults for an MCP serving Vista data

1. **The MCP server is a proxy, not a store.** Do not persist Vista
   response payloads (no DB mirror, no in-memory cache keyed on personal
   fields, no log capture of full bodies). Live-read only.
2. **Audit every outbound call** with metadata only: `(user_id_or_session,
   endpoint, method, params_keys, status, latency_ms, timestamp)`. Never
   audit field values.
3. **Treat 401s on `/clientes/*` as a feature**, not a bug — they prevent
   accidental data flow. If a tenant unlocks `/clientes/*`, the MCP must
   re-evaluate whether the host environment has a documented basis to
   surface that data to the model.
4. **Do not summarize personal data through an LLM by default.** A
   `vista_get_cliente` tool that returns to the host LLM should be gated
   behind an explicit tool input flag like `acknowledge_personal_data:
   true`. Otherwise return a redacted projection.
5. **Document a retention / export contract** in the MCP server's README:
   what is logged, for how long, who sees it, how it's deleted.

### Article 11 (sensitive personal data)

Vista's standard property/CRM payloads do NOT typically contain
Art. 11-class data (health, racial origin, religion, biometrics, sexual
life). If a custom Vista deployment captures any of these, the MCP must
enforce explicit consent at the call site — not assume defaults are safe.

---

## 9. Worked examples — actual request/response pairs

### 9.1 List 3 properties

**Request URL:**
```
https://oneconsu-rest.vistahost.com.br/imoveis/listar
  ?showtotal=1
  &pesquisa={"fields":["Codigo","Cidade","Bairro","Categoria","ValorVenda","DataAtualizacao"],"paginacao":{"pagina":1,"quantidade":3}}
  &key=<API_KEY>
```

(URL-encode the JSON in real calls; expanded here for readability.)

**Headers:** `Accept: application/json`

**200 Response body** (live, captured 2026-05-02):
```json
{
  "CA2830": {"Codigo": "CA2830", "Cidade": "Cotia", "Bairro": "Granja Viana", "Categoria": "Casa", "ValorVenda": "1450000.00", "DataAtualizacao": "2026-04-30 12:14:27"},
  "TE0080": {"Codigo": "TE0080", "Cidade": "Cotia", "Bairro": "Centro", "Categoria": "Terreno", "ValorVenda": "350000.00", "DataAtualizacao": "2026-04-29 09:01:55"},
  "AP1207": {"Codigo": "AP1207", "Cidade": "São Paulo", "Bairro": "Vila Olímpia", "Categoria": "Apartamento", "ValorVenda": "780000.00", "DataAtualizacao": "2026-04-28 16:48:02"},
  "total": 1784,
  "paginas": 595,
  "pagina": 1,
  "quantidade": 3
}
```

### 9.2 Property detail

**Request URL:**
```
https://oneconsu-rest.vistahost.com.br/imoveis/detalhes
  ?imovel=CA2830
  &pesquisa={"fields":["Codigo","Cidade","Bairro","Categoria","ValorVenda","AreaTotal","Dormitorios","Suites","Caracteristicas","Latitude","Longitude","DataAtualizacao"]}
  &key=<API_KEY>
```

**200 Response** (flat, NOT wrapped — partial):
```json
{
  "Codigo": "CA2830",
  "Cidade": "Cotia",
  "Bairro": "Granja Viana",
  "Categoria": "Casa",
  "ValorVenda": "1450000.00",
  "AreaTotal": "320.00",
  "Dormitorios": "4",
  "Suites": "2",
  "Caracteristicas": {"Piscina": "Sim", "Lareira": "Sim", "Academia": "Não"},
  "Latitude": "-23.601234",
  "Longitude": "-46.842311",
  "DataAtualizacao": "2026-04-30 12:14:27"
}
```

### 9.3 Filter dropdown enum

**Request URL:**
```
https://oneconsu-rest.vistahost.com.br/imoveis/listarConteudo
  ?pesquisa={"fields":["Status","Categoria"]}
  &key=<API_KEY>
```

**200 Response** (truncated):
```json
{
  "Status": ["ATIVO", "INATIVO", "VENDIDO", "RESERVADO", "ALUGADO"],
  "Categoria": ["Casa", "Apartamento", "Terreno", "Sala Comercial", "Galpão", "Cobertura"]
}
```

### 9.4 Field-permission denial (400)

**Request:** request a field the tenant key does not authorize on `/usuarios/listar`:
```
?pesquisa={"fields":["Codigo","Apelido"],...}&key=<API_KEY>
```

**400 Response body:**
```json
{"campo": "Apelido não está disponível"}
```

(Phrasing varies — sometimes `{"mensagem": "Campo Apelido não está disponível."}`. The MCP error matcher should be lenient — substring match `"não está disponível"` is the reliable signal.)

### 9.5 Endpoint-permission denial (401)

**Request:** any request to `/clientes/listar` with a key that lacks
client-scope permission.

**401 Response body:**
```json
{"mensagem": "Permissão Negada"}
```

### 9.6 Endpoint not on this tier (404)

**Request:** any request to `/imoveis/fotos` on a tenant whose
subscription tier doesn't include the photos endpoint.

**404 Response body:** typically empty or a Vista 404 page (HTML). The
content is not load-bearing — the status code is the signal.

---

## 10. Known unknowns / open questions

These are open as of 2026-05-02. An MCP author hitting any of these
should document the answer and update this file (or its downstream copy):

1. **Rate limits.** Vista does not publish official rate limits. The
   probed tenant tolerated ~4 RPS without error; we have no upper bound.
2. **Webhook / push API.** Vista's public docs do not advertise webhooks.
   If they exist, they're undocumented. An MCP wanting "push" semantics
   has to poll.
3. **Bulk export.** No documented bulk-export endpoint. The 50-item
   pagination cap holds for `/imoveis/listar`; a 1,784-property tenant
   needs ~36 pages to dump.
4. **Image download.** `/imoveis/fotos` was the documented entry point;
   it returned 404 on the probed tenant. Photo URLs returned in
   `FotoDestaque` (and on other tenants `Foto` / `FotoPrincipal`) point
   to Vista-hosted CDN URLs (`cdn.vistahost.com.br/<tenant>/...`) that
   can be fetched directly with a public GET (no API key required) — but
   verify before relying.
5. **Write surface.** `/imoveis/cadastrar`, `/imoveis/alterar`, etc.
   are documented but never live-probed. An MCP exposing writes must run
   the discovery routine first.
6. **OAuth / multi-key.** No live evidence of OAuth or multi-key per
   tenant. If Vista introduces these, the auth model in §1 changes.
7. **Field mutability.** Public docs do not mark fields read-only vs.
   writable. An MCP exposing PUT/POST should treat all fields as
   potentially read-only until verified.
8. **Internationalization.** The probed tenant returns Brazilian
   Portuguese in fields like `Setor`, `Status` enums. We have not
   probed a non-pt-BR tenant — assume pt-BR until proven otherwise.

---

## 11. Provenance

- **Public docs source.** `https://vistasoft.com.br/api/` (deep documents
  for `/imoveis` and `/clientes`; navigation references for the rest).
- **Help-center references.**
  - `https://ajuda.vistasoft.com.br/para-que-serve-a-api/`
  - `https://ajuda.vistasoft.com.br/como-solicitar-uma-nova-chave-api/`
- **Live probe environment.** `oneconsu-rest.vistahost.com.br` (One
  Consultoria Imobiliária — Cotia/SP), 2026-05-01..2026-05-02.
- **Reference adapter.** Built into a real ERP integration; the typed
  classes, normalizers, and audit-log path described above are the same
  shapes used in production.

---

## 12. Document maintenance

When extending this document:

1. **Always cite the probe origin** — "live-probed against tenant `<X>`,
   `<date>`" — so future readers know whether to re-verify.
2. **Never widen a cell without evidence.** Moving a row from ❓ to ✅
   requires a captured request/response pair (paste it into §9 or a
   per-tenant addendum).
3. **Honor the status legend.** ✅ means *we saw it work*. 🔒 means
   *we hit it; it returned 401*. ❌ means *we hit it; it returned 404*.
   📖 / ❓ are weaker — never promote without live evidence.
4. **Diff with the prior version.** When a tenant exposes new fields,
   keep the old rows (mark them with the older tenant's name) and add a
   new column or addendum — multi-tenant MCPs need both.

---

*End of document.*
