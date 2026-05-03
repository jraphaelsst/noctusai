# Vista API MCP — Documentation + MCP Server Build

> **This is a living document, not a rigid checklist.**
> Filed 2026-05-02 at the close of `methodology-extraction` step (a),
> per user directive *"after finishing step a, file a project for
> vista's api documenting and mcp creation, if it doesnt exist
> already."* The companion authoring artifact
> `VISTA-API-MCP-GUIDE.md` already lives at repo root for transport
> to the external environment that will build the MCP server. This
> project tracks (a) keeping that guide accurate as Vista API
> knowledge grows, and (b) the future build of a Vista MCP server
> as a first-party tool inside this repo.
>
> **Status: Concept — interrogation pending.** §6 is intentionally
> empty. The §7 questions resolve the build-or-buy + scope
> decisions. The repo-root guide is the immediate deliverable; the
> in-repo MCP server is the eventual one.

- **Created:** 2026-05-02
- **Last updated:** 2026-05-02
- **Status:** Concept — interrogation pending. The repo-root guide (`VISTA-API-MCP-GUIDE.md`) is shipped and ready to transport. In-repo MCP server build is deferred pending §7 resolution.
- **Owner / stakeholders:** Raphael · external-environment agent (consumer of `VISTA-API-MCP-GUIDE.md`) · future zero-context execution agent in this repo
- **Related docs:** `VISTA-API-MCP-GUIDE.md` (repo root — the portable Vista reference for an external agent building a Vista MCP); `projects/vista-api-mcp/VISTA-API.md` (project-internal reference — moved here 2026-05-02 from the now-deleted `vista-crm-wiring` showcase project; produced from the live-probe data in commit `146abe3`); `products/erp-imobiliario/backend/app/integrations/vista/` (typed adapter — the working reference implementation; survives folder deletion as production code); `KNOWLEDGE-BASE/INSTRUCTIONS/02-MCP.md` (MCP server design patterns).
- **Project slug:** `vista-api-mcp` — cross-product / platform-infra scope, lives at root `projects/`.

---

## 1. Context & Purpose

The user has two distinct deliverables tied to Vista CRM that this
project owns:

1. **The Vista API documentation** — a portable, complete reference
   for the Vista REST API as it actually behaves (per-tenant
   permissions included), folding public docs + live-probe results
   + adapter contract + LGPD posture. The first deliverable already
   shipped 2026-05-02 as `VISTA-API-MCP-GUIDE.md` at repo root,
   designed for the user to copy out and feed an external-
   environment agent that will build a Vista MCP server. This
   project keeps that guide accurate as more is learned (new
   endpoints probed, new tenants connected, public-doc updates).
2. **The Vista MCP server** — a first-party MCP server, hosted
   either inside this repo (e.g.
   `mcp/vista/`) or in a sibling repo, that exposes Vista's
   property / client / agency / user endpoints as typed MCP tools
   for any agent to consume. This is parallel to the work being
   done in the external environment; if both ship, they should
   share the same `VISTA-API-MCP-GUIDE.md` as the schema source.

Why filed now (vs at the start of the Vista showcase project):
the showcase project (`products/erp-imobiliario/projects/vista-crm-wiring/`)
deliberately scoped to a read-only ERP-internal showcase — building
a generic MCP server was explicitly out of scope. With the
adapter, the live-probe results, the typed-error model, and the
calibrated field sets all in place, the MCP-server work has a
ready-to-use foundation. Filing it now (deferred) preserves that
context so a future agent doesn't re-derive what's already been
proven.

---

## 2. Confirmed constraints (what the user *has* said)

> **Source note:** the bullets below paraphrase user statements
> from the 2026-04-23 → 2026-05-02 conversations that produced the
> showcase implementation + the repo-root guide. Future agents: if
> a constraint feels ambiguous, ask the user to confirm.

- **The repo-root `VISTA-API-MCP-GUIDE.md` is intentionally
  portable.** Zero relative pointers into this repo. An external-
  environment agent reads it and builds an MCP server with no
  further context. Future updates to it must preserve this
  property — never inline references like
  `products/erp-imobiliario/...` into the guide.
- **The user will copy the repo-root guide out and delete it from
  here.** Per the same-day directive. So this project must be able
  to *re-author* the guide on demand (when new findings land) by
  pulling from the project-internal `VISTA-API.md` + adapter
  contract — it's a derived artifact, not the source of truth.
- **Source of truth lives inside the showcase project.**
  `projects/vista-api-mcp/VISTA-API.md`
  is the authoritative project-internal reference. The repo-root
  guide is a transport-shaped derivative.
- **The MCP server (when built) targets the live-probed endpoint
  surface first.** Tenant-permission-blocked endpoints (clientes,
  corretores) ship as typed-error responses, not unimplemented
  tools — different tenants have different permissions and the
  server should surface that explicitly per `VistaPermissionDenied`.
- **Per-tenant calibration is mandatory.** The Phase 4.5 hardening
  bug (the deployed UI showed `[502] Vista respondeu erro 400`
  because Phase-1's smoke probe never sent the full field bundle
  in one request) proved that hard-coding the public-doc field
  set is the wrong move. The MCP server must run a probe routine
  at boot and cache per-tenant safe field sets.
- **LGPD-first remains non-negotiable.** Vista clientes payloads
  carry CPF / addresses / phones — anything personal-data-shaped
  needs explicit consent gating, audit-log per call, no payload
  persistence.

---

## 3. Design principles (provisional — confirm with §7 answers)

1. **One contract, two consumers.** The repo-root guide and the
   in-repo MCP server (when built) read from the same schema —
   the calibrated endpoint inventory, field sets, error model.
   Drift between the two is forbidden.
2. **Typed errors at the MCP boundary.** Mirror the adapter's
   error hierarchy (`VistaConfigError`, `VistaTimeout`,
   `VistaUpstreamError`, `VistaPermissionDenied`,
   `VistaFieldNotAvailable`, `VistaNotFound`) as structured tool-
   error payloads, never raw 4xx text.
3. **Normalize the dict-keyed-by-id collection shape at the MCP
   boundary.** Vista returns `{"<id>": {...}, "total": N, "paginas":
   N}` — the MCP wrapper exposes `{items: [...], pagination: {...}}`
   so the host LLM never has to re-discover the unusual envelope.
4. **Probe-gated tool registration.** Each tool registers with a
   `probe_status` field (`live_probed | doc_only | referenced`) so a
   host operator can filter to only-known-good tools.
5. **Per-tenant config as MCP secrets.** The MCP server reads its
   per-tenant `VISTA_BASE_URL` + `VISTA_API_KEY` from its own
   secrets store; never inherits from this repo's `.env`.
6. **Reuse the adapter's normalizers.** The
   `vista_imovel_to_showcase` etc. functions in the showcase
   adapter are the canonical Vista→DTO mappings; the MCP server
   either ports them or imports them.

---

## 3a. Seed-first analysis

Mandatory per CLAUDE.md. This project is **about an external
integration** — Vista is third-party software with its own API
contract. The seed-first question is whether any part of the work
should land in the platform's seed library.

- The **typed-error model** (`VistaConfigError`,
  `VistaUpstreamError`, etc.) could become a generic
  `noctusai_lib.integrations.<vendor>.errors` shape if a 2nd
  integration adopts the same pattern (recurrence rule). For now,
  it lives in `products/erp-imobiliario/backend/app/integrations/vista/`.
- The **dict-keyed-by-id response normalizer** (`extract_items`)
  is Vista-specific; not seed material.
- The **probe-gated MCP-tool-registration** pattern, if generalized
  beyond Vista, could become an MCP-toolkit-side helper for any
  vendor integration. Defer until a 2nd integration ships.

Per-product code-count litmus: **0** lines of new per-product
code. The MCP server (when built) is platform infrastructure, not
product code. The repo-root guide is methodology / transport, not
product code.

---

## 4. Scope

**In scope** (once §7 is resolved):

- Keep `VISTA-API-MCP-GUIDE.md` accurate as Vista API knowledge
  grows. Refresh whenever the showcase adapter learns new field
  permissions, response shapes, or error patterns.
- Re-author the repo-root guide on demand (after the user's
  copy-and-delete cycle) by pulling from
  `projects/vista-api-mcp/VISTA-API.md`
  + the live adapter.
- Build a first-party Vista MCP server (location TBD — §7 Q1):
  - One MCP tool per live-probed endpoint family (imoveis, usuarios,
    agencias initially; clientes / corretores when permission lands).
  - Typed-error responses per the adapter's error hierarchy.
  - Probe-gated registration with `probe_status` per tool.
  - Per-tenant secret handling via the MCP server's own config.
- Maintain the keeper detector for the guide (catch drift between
  the showcase adapter's calibrated field sets and the guide).

**Out of scope:**

- Replacing the showcase adapter at
  `products/erp-imobiliario/backend/app/integrations/vista/` — that
  remains ERP's source-of-truth for Vista access. The MCP server
  is a parallel surface, not a replacement.
- Building tooling for Vista write operations (POST `/imoveis/cadastrar`,
  PUT `/imoveis/alterar`, etc.) — write surface deferred until a
  product use-case actually needs writes.
- A Vista admin UI inside the platform — this is an MCP-server +
  documentation project, not a product feature.

---

## 5. Architecture / data model — sketch

```
┌───────────────────────────────────────────────────────────────────┐
│ SOURCE OF TRUTH                                                    │
│ projects/vista-api-mcp/VISTA-API.md    │
│ + products/erp-imobiliario/backend/app/integrations/vista/         │
│   ├── client.py        — typed HTTP client + error hierarchy       │
│   ├── types.py         — Vista DTO + Showcase DTO shapes           │
│   └── normalizers.py   — Vista → ERP showcase mappers              │
└────────────────────┬──────────────────────────────────────────────┘
                     │ derive
                     ▼
┌───────────────────────────────────────────────────────────────────┐
│ TRANSPORT ARTIFACT (re-authored on demand)                         │
│ VISTA-API-MCP-GUIDE.md (repo root, gitignored after handoff)       │
│   - public docs + live probe + adapter contract folded together    │
│   - portable: zero relative pointers into this repo                │
│   - the user copies this out and feeds it to the external agent    │
└─────────────────────────┬─────────────────────────────────────────┘
                          │ (parallel paths)
              ┌───────────┴──────────────┐
              ▼                          ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ EXTERNAL ENVIRONMENT        │  │ THIS REPO (deferred)        │
│ (user's other workspace)    │  │ mcp/vista/  ← TBD §7 Q1     │
│ Builds a Vista MCP server   │  │ Builds a parallel Vista     │
│ from the guide.             │  │ MCP server, sharing the     │
│                             │  │ schema with the external    │
│                             │  │ one.                        │
└─────────────────────────────┘  └─────────────────────────────┘
```

**MCP tool surface (provisional — finalize at execution):**

| MCP tool | Backed by | Input | Output |
|---|---|---|---|
| `vista_list_imoveis` | `/imoveis/listar` | filter, fields, page, page_size | items[] + pagination |
| `vista_get_imovel` | `/imoveis/detalhes` | codigo, fields | Imovel |
| `vista_list_imoveis_filters` | `/imoveis/listarConteudo` | fields | enum dict |
| `vista_list_usuarios` | `/usuarios/listar` | fields | items[] |
| `vista_list_agencias` | `/agencias/listar` | fields | items[] |
| `vista_list_clientes` | `/clientes/pesquisar` (when authorized) | filter, fields, page | items[] |
| `vista_get_cliente` | `/clientes/detalhes` | codigo, fields | Cliente |
| `vista_probe` | meta | path, params? | status + latency + body summary |
| `vista_list_known_endpoints` | meta | — | array of {path, status, last_probed_at} |

---

## 6. Implementation phases

**Intentionally empty.** §7 must resolve first. The repo-root
guide is already shipped; further work is gated on the §7
decisions and on user reactivation.

When activated, expect at minimum:
- **Phase 0** — audit the current state: re-probe Vista against
  the live tenant; diff against the repo-root guide; refresh both
  as needed. Decide MCP server location (§7 Q1).
- **Phase 1** — scaffold the MCP server skeleton at the chosen
  location. Tool list, error model, probe-on-boot routine.
- **Phase 2** — implement the live-probed endpoint family tools
  (imoveis, usuarios, agencias).
- **Phase 3** — implement the permission-gated families (clientes,
  corretores) as 401-typed responses, with the upgrade path
  documented for tenants that have permission.
- **Phase 4** — write tooling: `vista_probe`,
  `vista_list_known_endpoints`, optional cache layer.
- **Phase 5** — keeper detector for guide ↔ adapter drift; smoke
  tests; close.

---

## 7. Open questions (the unblock list)

Each question paired with a recommendation. The user explicitly
deferred answering these — do NOT pretend they're resolved.

1. **Where does the in-repo MCP server live?**
   - **(A)** Inside `mcp/vista/` — sibling to `mcp/noctusai/`,
     keeps all MCP servers under one dir.
   - **(B)** Inside `products/erp-imobiliario/mcp/` — owned by the
     product that produced the adapter.
   - **(C)** Separate repo entirely (`noctusai-vista-mcp`) — fully
     external, can ship to PyPI / npm.
   *Recommendation: **(A) `mcp/vista/`** — keeps cross-vendor MCP
   servers under one umbrella, makes the `VISTA-API-MCP-GUIDE.md`
   easier to share between this repo's server and the external
   one (both reference the same path).*

2. **Implementation language for the MCP server.**
   - **(I)** Python — matches `mcp/noctusai/`, uses the existing
     anthropic SDK + tools pattern.
   - **(II)** TypeScript — matches the broader MCP-server
     ecosystem.
   *Recommendation: **(I) Python** — consistency with
   `mcp/noctusai/`, lower context-switching cost. The `httpx`
   async client + typed errors port directly from the showcase
   adapter.*

3. **Reuse vs reimplement vs port the showcase adapter.**
   - **(α)** Import from the showcase adapter directly — `from
     products.erp_imobiliario.backend.app.integrations.vista
     import client` — coupling.
   - **(β)** Port the typed client + normalizers into `mcp/vista/`
     — duplication but independent.
   - **(γ)** Move the adapter to `noctusai_lib.integrations.vista`
     (seed lib) — both ERP and the MCP server import it.
   *Recommendation: **(γ) move to seed-lib** if the MCP server
   ships within ~2 weeks of activation, **(β) port** otherwise.
   The recurrence-rule trigger fires when a 2nd consumer (the MCP
   server) needs the same code — that's exactly the absorption
   threshold.*

4. **Tokenizer / token-cost integration with `project-history-ledger`.**
   - When the ledger ships and consumes per-project token counts,
     the Vista MCP server's per-call token cost (host LLM ↔ MCP
     tool ↔ Vista) is a useful feature for the AI training data.
     Should the MCP server emit token-cost telemetry?
   *Recommendation: ship the MCP server without telemetry first;
   add an opt-in `record_call_cost` flag in v2 once
   `project-history-ledger` defines the data shape.*

5. **What triggers a refresh of `VISTA-API-MCP-GUIDE.md`?**
   - **(p)** Manual — user asks, we re-author from
     `VISTA-API.md`.
   - **(q)** Automated — keeper detector flags drift between
     showcase-adapter field sets and guide content; runs as part
     of `--review`.
   *Recommendation: **(p) manual** for v1; the guide changes
   slowly enough that automation is overhead. Move to (q) if the
   project ships ≥3 refreshes in a year.*

6. **Reactivation trigger — what evidence makes this project
   ready to start?**
   - User explicitly asks to build the MCP server, OR
   - The external-environment build hits a Vista API surface
     this repo's adapter hasn't probed yet (so the in-repo build
     becomes the canonical reference), OR
   - A 2nd product needs Vista access (recurrence rule).
   *Recommendation: wait for any of the three to fire. Until
   then, the repo-root guide + showcase adapter cover the actual
   use case.*

---

## 8. Dependencies & blockers

- **Repo-root `VISTA-API-MCP-GUIDE.md` is the active deliverable**
  — keep it accurate as long as it lives at root. Once the user
  copies it out and deletes it, the next refresh re-authors from
  `projects/vista-api-mcp/VISTA-API.md`.
- **No external blockers for the documentation track.** The
  guide can be refreshed at any time.
- **MCP server build blocker (§7 Q1, Q2, Q3) — needs user input
  before any code lands.**
- **Per-tenant access** — building / testing the MCP server needs
  a real Vista tenant key. The current `oneconsu-rest` key works
  for `imoveis / usuarios / agencias`; expanded permission would
  unlock testing of `clientes / corretores`.

---

## 9. Success criteria

When this project ships:

- The repo-root guide stays up-to-date with the showcase adapter's
  calibrated field sets and probe results — drift caught either
  manually (refresh on demand) or via keeper (if §7 Q5 lands at
  (q)).
- An MCP server exists at the agreed location (per §7 Q1)
  exposing the live-probed Vista endpoints as typed MCP tools.
- Typed-error responses surface `VistaPermissionDenied`,
  `VistaFieldNotAvailable`, `VistaNotFound`, `VistaTimeout`,
  `VistaUpstreamError` distinctly to the host.
- A `vista_probe` meta-tool lets host operators verify per-tenant
  endpoint availability at runtime.
- The MCP server's tests + keeper-review run as part of
  `cd mcp/noctusai && pytest tests/` (or wherever it lands per
  §7 Q1).

---

## 10. How to use this project

- **Don't draft §6 phases until §7 resolves.** The user
  explicitly deferred this; reactivation is gated on any of the
  three triggers in §7 Q6.
- **Keep `VISTA-API-MCP-GUIDE.md` accurate** — when the showcase
  adapter learns new permissions, response shapes, or error
  patterns, refresh the guide as a deliverable inside this
  project. Add a §11 entry per refresh.
- **Cross-link with the showcase project.** The
  `products/erp-imobiliario/projects/vista-crm-wiring/` project
  was closed and its folder deleted 2026-05-02; the VISTA-API.md spec
  was relocated here as the authoritative
  source for any guide refresh.

Suggested commands:

```bash
# Read this project + the source-of-truth Vista doc
sed -n '1,200p' projects/vista-api-mcp/PROJECT.md
sed -n '1,300p' projects/vista-api-mcp/VISTA-API.md

# Re-author the repo-root guide (when the user asks for a refresh)
# (manual — pull from VISTA-API.md, fold public docs, ship)
ls VISTA-API-MCP-GUIDE.md  # exists if not yet copied out

# When the MCP server is ready to start (§7 Q1 + Q2 + Q3 resolved)
mkdir -p mcp/vista  # per recommendation
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | **Project filed.** User directive at the close of `projects/methodology-extraction/` step (a): *"after finishing step a, file a project for vista's api documenting and mcp creation, if it doesnt exist already."* Filed at root `projects/vista-api-mcp/` (cross-product / platform-infra scope). §1-§5 + §7 + §10 populated; §6 intentionally empty pending §7 resolution + user reactivation. The companion repo-root artifact `VISTA-API-MCP-GUIDE.md` (904 lines, calibrated against the live `oneconsu-rest` tenant 2026-05-02) is the active deliverable; the in-repo MCP server build is the deferred deliverable. **Interlock noted with `methodology-extraction` Phase 5** — that phase closed by filing this project per the user's same-day directive. | Claude Opus 4.7 |
