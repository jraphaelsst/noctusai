# `mcp/omie` — Omie ERP connector MCP

Agent access to **[Omie](https://www.omie.com.br)**, the Brazilian ERP —
customers, products, receivables/payables, sales orders, NF-e/NFS-e,
inventory, service orders, CRM and the accountant's document feed.

Composes `mcp/_kit` like every other `mcp/<vendor>` connector.

> **Coverage: complete.** 134 endpoints · **461 methods** · 1757 complex
> types — the entire published Omie API is reachable, not a curated
> subset. See § The completeness claim.

---

## 1 · Why this connector looks the way it does

Four properties of Omie drove every design decision here.

**One envelope, the whole API.** Every Omie resource is the same POST:

```jsonc
POST https://app.omie.com.br/api/v1/<family>/<resource>/
{"call": "ListarClientes", "app_key": "…", "app_secret": "…",
 "param": [ { "pagina": 1, "registros_por_pagina": 50 } ]}
```

So one correct transport covers all 461 methods. The tool layer is about
ergonomics and safety, not per-resource plumbing.

**An "environment" is a company.** Omie has *no sandbox*. Each company
(`empresa`) issues its own `app_key`/`app_secret`, so a multi-company
operator holds N credential pairs and the worst available mistake is
writing to the wrong one. Hence: every tool takes `environment`,
environments can be pinned `readonly`, and the default is never guessed
when it is ambiguous.

**Faults are not HTTP statuses.** Failures come back as a SOAP-flavoured
body — and Omie will do this *with HTTP 200*:

```json
{"faultstring": "A chave de acesso não está preenchida ou não é válida.",
 "faultcode": "SOAP-ENV:Server"}
```

(Verified live 2026-08-05: an invalid key answers **HTTP 403** with that
body.) The meaning lives in a Portuguese string, so `errors.py`
classifies it once into typed errors the host LLM can branch on, and the
success path is inspected for faults too.

**Rate limits bite hard.** Omie publishes 960 req/min per IP, 240/min per
IP+app_key+method, 4 concurrent per that triple — and **blocks a method
for ~30 minutes (HTTP 425) after 10 consecutive failures**. A naive retry
loop earns a half-hour outage, so the client throttles *before* sending
and opens a local circuit at 6 failures.

---

## 2 · Configure

Credentials come from the process env or a co-located `mcp/omie/.env`
(env wins). Copy `.env.example` to `.env` to start.

**Single company:**

```bash
OMIE_APP_KEY=1234567890
OMIE_APP_SECRET=abcdef0123456789abcdef0123456789
```

**Multiple companies** — the canonical form:

```bash
OMIE_ENVIRONMENTS='{
  "acme-prod":  {"app_key":"…","app_secret":"…","label":"Acme Ltda",
                 "cnpj":"12.345.678/0001-90","readonly":true},
  "acme-lab":   {"app_key":"…","app_secret":"…","label":"Acme sandbox co."}
}'
OMIE_DEFAULT_ENVIRONMENT=acme-lab
```

Or flat vars, for secret stores that can't hold JSON
(`OMIE_ENV__ACME_PROD__APP_KEY` → environment `acme-prod`):

```bash
OMIE_ENV__ACME_PROD__APP_KEY=…
OMIE_ENV__ACME_PROD__APP_SECRET=…
OMIE_ENV__ACME_PROD__READONLY=true
```

| Variable | Default | Meaning |
|---|---|---|
| `OMIE_ENVIRONMENTS` | — | JSON map of environment → credentials |
| `OMIE_ENV__<NAME>__*` | — | Flat per-environment vars (`APP_KEY`, `APP_SECRET`, `LABEL`, `CNPJ`, `READONLY`) |
| `OMIE_APP_KEY` / `OMIE_APP_SECRET` | — | Single-company shorthand → environment `default` |
| `OMIE_DEFAULT_ENVIRONMENT` | — | Used when a tool omits `environment` |
| `OMIE_READONLY` | `false` | Pin the shorthand environment readonly |
| `OMIE_TOOL_PROFILE` | `full` | `core` advertises only the 12 orientation tools (see §5) |
| `OMIE_TIMEOUT_SECONDS` | `45` | HTTP timeout |
| `OMIE_BASE_URL` | `https://app.omie.com.br/api/v1` | Override the API root |

The server **starts cleanly with no credentials**; tool calls then return
a typed `OmieConfigError` and `omie.diagnostics.connection_status`
explains what to set. Secrets never cross the MCP boundary — environments
are reported with an `app_key` suffix only.

Register it (already added to `.mcp.json`):

```jsonc
"omie": {"command": "mcp/noctusai/.venv/bin/python", "args": ["mcp/omie/server.py"]}
```

---

## 3 · Tool surface

### Orient — which company am I on?

| Tool | Does |
|---|---|
| `omie.environments.list` | Every configured environment, redacted, + which is default |
| `omie.environments.describe` | Resolve one (or the default) — no API call |
| `omie.environments.check` | Verify credentials live via `ListarEmpresas` (a read); `all=true` checks every environment concurrently |

### Discover — the whole API, offline

Omie publishes no OpenAPI spec. It *does* serve an HTML doc page from
each endpoint's own URL on GET, so `scripts/harvest_catalog.py` parses all
134 into `data/catalog.json.gz` (198 KB) — including the **live request
example Omie ships per method** (458 of 461 have one).

| Tool | Does |
|---|---|
| `omie.catalog.search` | Keyword search over all 461 methods (PT or EN) |
| `omie.catalog.describe_method` | Full param schema w/ types, max lengths, PT docs, nested complex types, return shape, **and the live example** |
| `omie.catalog.list_endpoints` | All 134 endpoints, filterable by family |
| `omie.catalog.endpoint_methods` | Every method on one endpoint |
| `omie.catalog.status` | Catalog provenance — when harvested, what it covers |

None of these spends an API request. Discovery must never eat the rate
budget or risk the 30-minute block.

### Act — everything

| Tool | Does |
|---|---|
| `omie.call.invoke` | Call **any** of the 461 methods. Endpoint resolved from the catalog; unknown names rejected with suggestions *before* a request is spent |
| `omie.call.paginate` | Walk any list method; handles the 100/page cap, auto-detects the record array, stops cleanly at end-of-data |

### Curated CRUD — the high-traffic 28 resources

`omie.<resource>.{list,get,upsert,delete}` for: `clientes` ·
`produtos` · `categorias` · `departamentos` · `projetos` · `vendedores` ·
`empresas` · `contas_correntes` · `contas_pagar` · `contas_receber` ·
`lancamentos_cc` · `extrato` · `pix` · `pedidos_venda` ·
`pedidos_compra` · `notas_fiscais` · `ordens_producao` · `estoque` ·
`estoque_ajustes` · `estoque_locais` · `servicos` · `ordens_servico` ·
`contratos` · `nfse` · `crm_contas` · `crm_oportunidades` ·
`crm_contatos` · `crm_tarefas` · `documentos_fiscais`.

Pagination is pre-wired and each tool's description names the useful
filters. The resource table in `tools/resources.py` **is** the code — one
`Resource(...)` row generates its tools.

### Diagnose

`omie.diagnostics.connection_status` (config + catalog + throttle state,
no API call) · `omie.diagnostics.rate_limit_status` (documented limits vs.
live counters and open circuits).

---

## 4 · Safety model

Omie has **no undo and no sandbox**, so writes are guarded twice:

1. **Readonly environments** — a mutating call against one is refused
   outright, before any request.
2. **Confirm-then-execute** — every mutating call needs `confirm=true`;
   without it the tool returns a 412 and performs *no* side-effect.

What counts as mutating is a **prefix rule** (`Incluir`, `Alterar`,
`Excluir`, `Upsert`, `Cancelar`, `Lancar`, …), and anything unrecognised
is treated as mutating. Fail-safe on purpose: a verb Omie adds tomorrow
trips the guard rather than slipping past it.

Rate-limit posture: throttle at 90% of the published ceilings, cap
concurrency per method, and open a local circuit after 6 consecutive
failures — before Omie's own 10-failure/30-minute block. HTTP 425 is
never retried into.

Truncation is always reported: paginated results carry `truncated`,
`pages_fetched` and `next_page`, so a partial list can't read as a
complete one.

**LGPD** — `clientes`, `vendedores`, `crm_contas`, `crm_contatos` carry
CPF/CNPJ, addresses and phones; their tool descriptions say so. This
server persists nothing.

---

## 5 · The completeness claim, precisely

Two layers, and the guarantee lives in the lower one:

* **`omie.call.invoke` / `omie.call.paginate` reach all 461 methods.**
  Anything Omie can do, this connector can do.
* The **89 curated tools** are ergonomics on top — they save an agent
  from having to discover that "overdue receivables" means
  `ListarContasReceber` on `/financas/contareceber/`.

`OMIE_TOOL_PROFILE=core` drops the curated descriptors to 12 advertised
tools for hosts on a tight context budget. **Capability is unchanged** —
the generic seam still reaches everything, and the curated handlers stay
registered and callable; only what is *advertised* shrinks.

Every curated method name was read out of the harvested catalog, and
`tests/test_smoke.py::test_curated_methods_exist_in_catalog` re-verifies
all of them against it — a typo or an upstream rename fails the suite
instead of failing live.

### Refreshing the catalog

```bash
python mcp/omie/scripts/harvest_catalog.py     # writes catalog.json
gzip -9c catalog.json > mcp/omie/data/catalog.json.gz
```

`omie.catalog.status` reports `harvested_at`, so a stale snapshot is
visible rather than silently trusted. For a method newer than the
snapshot, `omie.call.invoke` accepts `escape_hatch=true` with an explicit
`endpoint` — and flags the result `validated=false`.

---

## 6 · Tests

```bash
cd mcp && python -m pytest omie/tests/ -q      # 62 tests, no network
```

Covers registry coherence, the exact wire envelope, both write guards,
fault classification (incl. the fault-inside-HTTP-200 case), environment
resolution + secret redaction, pagination (end-of-data, truncation, page
cap), catalog truth, the typo-suggestion path, and rate-limit circuits.
The only patched boundary is `_kit.transport.urlopen`; our own code is
never patched.

---

## 7 · Note for `mcp/_kit`

This connector introduced `request_json(..., on_http_error=…)` — the
vendor error-body hook `_kit/README.md` flagged as the **N=2 revisit
trigger** (cloudflare's `errors[0].code` was N=1; omie's
`faultstring`/`faultcode` is N=2). It is additive and defaults to `None`,
so the five connectors that don't pass it are byte-for-byte unchanged
(covered by `test_transport_hook_defaults_to_prior_behavior`).

**Follow-up, not done here:** `mcp/cloudflare/api.py` still carries its
own hand-rolled transport for exactly this reason and can now fold onto
the shared seam — which would close the accept-with-rationale entry in
`KB § PATTERNS/accept-with-rationale.md`. Left out of this branch
deliberately: it touches a fleet-facing connector and deserves its own
slice.
