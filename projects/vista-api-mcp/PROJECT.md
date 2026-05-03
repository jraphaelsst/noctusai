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
- **Last updated:** 2026-05-03 (documentation moved into KB; documentation track refreshed; MCP Phase 1 implementation in progress)
- **Status:** ⏳ EXECUTING — documentation track active (Vista API spec lives in `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` as durable home); repo-root portable guide refresh in progress; MCP server build (Phase 1) starting per user directive 2026-05-03.
- **Owner / stakeholders:** Raphael · external-environment agent (consumer of `VISTA-API-MCP-GUIDE.md`) · future zero-context execution agent in this repo
- **Related docs:** `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` (**durable source-of-truth** — Vista API contract folding public docs + live-probe results + adapter behavior; lives in KB so it survives deletion of this project folder at close); `VISTA-API-MCP-GUIDE.md` (repo root — portable Vista reference for an external agent building a Vista MCP, derived from the KB doc); `products/erp-imobiliario/backend/app/integrations/vista/` (typed adapter — the working reference implementation; survives folder deletion as production code); `KNOWLEDGE-BASE/INSTRUCTIONS/02-MCP.md` (MCP server design patterns); `KNOWLEDGE-BASE/CONTEXT/PATTERNS/mcp-tool-conventions.md` (3-segment dotted naming, Pydantic schemas, hierarchical registration — the conventions the in-repo Vista MCP must follow).
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
| 2026-05-03 | **Vista client formalized into `noctusai_lib.integrations.vista` (post-Phase-1 absorption).** Driven by the user's "reconsider your accept-with-rationale" + "we got a new rule on that" prompt. **What was wrong with the Phase 1 framing:** §11 entry below claimed "recurrence rule: now lives in TWO places → formalize at seed-lib absorption time" — this was silent debt: no catalog entry, no follow-up project filed, no concrete revisit trigger. Per `KB § PATTERNS/accept-with-rationale.md` line 63-65 ("transient divergence with planned follow-up = deferred-formalize, not accept") and the new rule "promote permanent accepts to the catalog before project folder is deleted," this was neither a real accept nor a real deferred-formalize. **Formalize evidence:** (a) `_detect_unavailable_field` bug had to be fixed in TWO files the same morning — proves duplication harms; (b) §7 Q3 γ recommendation said "absorb to seed-lib if MCP ships within ~2 weeks of activation" — fired today; (c) `noctusai_lib/integrations/` already exists with `email/`, `llm/`, `database.py` — Vista's natural home. **What landed:** `seed/backend/lib/noctusai_lib/integrations/vista/{__init__,client,normalizers,types}.py` (canonical home — VistaClient + 7-class errors + extract_items + 4 normalizers + 4 showcase DTOs). Both consumers updated: `mcp/vista/` deleted its `client.py` + `normalizers.py`, trimmed `types.py` to MCP-tool-IO schemas only, and re-pointed all 6 tool modules + calibration.py + tests to import from seed-lib. ERP-side: `app/integrations/vista/` folder DELETED; `app/services/vista_showcase_service.py` + `app/routers/vista_showcase.py` re-pointed to seed-lib; ERP-router-specific response wrappers (ShowcasePagination/Envelope/TabStatus/Diagnostic) moved to new `app/services/vista_showcase_types.py` (they're showcase-shape, not Vista-protocol — correctly stay in the ERP product). **Catalog audit completed in same session:** flipped one stale entry — `noctusai_count_tokens MCP tool ~~does not yet exist~~ — FORMALIZED 2026-05-03` (the tool exists at `mcp/noctusai/tools/cost_evaluation.py` + server.py:265; the trigger fired but the catalog wasn't updated). Removed the stub note at `KB § PATTERNS/project-execution.md § 2.8 § Measurement discipline`. Other 22 active entries scanned — no other staleness detected. **Verification:** mcp/vista smoke tests (12/12 green); live e2e against `oneconsu-rest` reproduces identical behavior (1,783 properties, ONE10006 sample with valor_venda=2350000.0, calibration drops the same 7 known-bad fields ending at 25 valid). All 16 touched files parse; no dead `app.integrations.vista` refs remain. Catalog entry filed at `KB § PATTERNS/accept-with-rationale.md § Vista CRM client + normalizers + showcase DTOs duplicated at N=2 — FORMALIZED 2026-05-03`. KB vista.md §5 updated with the new layout. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1 shipped — `mcp/vista/` MCP server + per-tenant calibration routine + JSON-escaped-body detector bug fix.** Per user "implement the mcp phase" directive. **What landed (15 files in `mcp/vista/`):** client.py (ported VistaClient + 7-class error hierarchy + extract_items), normalizers.py (4 mappers + helpers), types.py (Pydantic In/Out + showcase DTOs), settings.py (per-tenant config separate from platform .env per PROJECT.md §3.5), calibration.py (NEW — addresses the §6 gap; lazy probe-and-drop with nested-sub-field handling, cached per process), server.py (stdio entry), tools/{__init__, imoveis, usuarios, agencias, clientes, corretores, diagnostics}.py (8 tools using vista.<service>.<action> dotted naming per `KB § PATTERNS/mcp-tool-conventions.md`), tests/test_smoke.py (12 tests, all green), README.md. **§7 questions resolved with recommendations:** Q1=A (`mcp/vista/`), Q2=I (Python), Q3=β (port now, absorb to seed-lib later when `mcp-server-expansion` substrate lands). **Real bug surfaced + fixed during live verification:** Phase 4.5's 422 surface in the showcase router NEVER FIRED because the `VistaFieldNotAvailable` detector substring-searched the raw HTTP body for `"não está disponível"`, but Vista's wire body uses JSON unicode escapes (`não está disponível`) — never matched. Fixed in BOTH `mcp/vista/client.py` AND `products/erp-imobiliario/backend/app/integrations/vista/client.py` (parse-message-then-search; handles array-shaped messages). Regression test in mcp/vista smoke suite. Recurrence rule: now lives in TWO places → formalize at seed-lib absorption time. **Live verification end-to-end:** `vista.imoveis.list` returned 1,783 properties correctly; calibration dropped exactly the 7 known-bad fields (Estado, Banheiros, Foto, FotoPrincipal, Slug, PalavrasChave, CodigoImobiliaria) ending at 25 valid fields including the nested {Corretor: [Nome, Email]}; valor_venda coerced as 2350000.0 (float). **Phase 2-5 deferred:** keeper detector for guide↔adapter drift; full integration tests against live tenant; nested-sub-field proactive discovery; per-endpoint probe sentinels (the generic `["Codigo"]` probe trips a benign 400 on /imoveis/listarConteudo — UX nit, not a functional bug). | Claude Opus 4.7 |
| 2026-05-03 | **Documentation track refresh + relocation to durable KB home + Phase 1 reactivation.** Two user directives this date: (1) *"the showcase adapter learned new things, and i want you to document this, then reprobe it against the real api ... im gonna evolve this api"* (initial doc refresh request); (2) *"make sure to properly doc vista inside our docs, keep in mind that when the project is deleted, the project folder is gonna get deleted and we will lose the files inside it ... Proceed updating the vista api mcp guide, then implement the mcp phase. 1 yes 2 sounds a good idea"* (move to KB + answer to my Q1=refresh-the-guide / Q2=file-per-tenant-calibration-as-followup). **What was done:** (a) **Gap analysis** of the showcase adapter vs the doc — Explore agent surfaced ~22 gaps with file:line citations. (b) **Live re-probe** (8 endpoints + 1 negative test) against `oneconsu-rest`; all known statuses still hold; new findings folded in. (c) **Doc relocated** from `projects/vista-api-mcp/VISTA-API.md` (461 lines, ephemeral — would be lost when this project closes) → **`KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` (816 lines, durable home).** New folder `KB/CONTEXT/INTEGRATIONS/` established as namespace for vendor-integration references; INDEX.md updated (Layout tree + By-topic + By-situation tables); CLAUDE.md updated (Map: new "Integrations (KB depth)" subsection; When-to-read: new "Touching Vista CRM" row). (d) **Doc refreshed** end-to-end: fixed wrong `extract_items` signature, added `VistaError` base + corrected the 7-class inheritance + catch-order rule; expanded `/imoveis/detalhes` quirks with the listing-prefetch + merge orchestration; added §5.1-5.6 (5 field-set constants table; full normalizer field-mapping contract; diagnostic probe surface; audit-log payload schema with the actual `detalhes` dict; router HTTP status mapping with rationales; admin-gating); NEW §6 explicitly noting per-tenant calibration is design intent NOT implemented in the adapter; sketched the calibration routine the in-repo MCP server must ship; folded all live-probe findings (uniform `{message,status}` envelope, 400-as-array, 404 Symfony shape, 401 with key hash, `Corretor_Codigo`/`CodigoImobiliaria` auto-included, `Status` enum exhaustive, `Cidade` casing duplicates). (e) **Source-code docstrings updated** (3 files: client.py, vista_showcase_service.py, vista_showcase.py) to point to the new KB doc location; added per-tenant-calibration honesty note to the field-set comment block. (f) **PROJECT.md `Related docs` updated** to make KB doc the primary pointer; status header updated. **Phase 1 implementation starting** per directive 2 — `mcp/vista/` scaffold using §7 recommendations (location=A, language=Python, reuse=port-from-showcase) and `KB § PATTERNS/mcp-tool-conventions.md` for naming/registration patterns. Per-tenant calibration routine WILL ship as part of Phase 1 (this addresses the §6 gap). **Probe script** at `/tmp/vista_reprobe.py` (one-shot, deleted; recipe in vista.md §8 for re-creation). | Claude Opus 4.7 |
| 2026-05-02 | **Project filed.** User directive at the close of `projects/methodology-extraction/` step (a): *"after finishing step a, file a project for vista's api documenting and mcp creation, if it doesnt exist already."* Filed at root `projects/vista-api-mcp/` (cross-product / platform-infra scope). §1-§5 + §7 + §10 populated; §6 intentionally empty pending §7 resolution + user reactivation. The companion repo-root artifact `VISTA-API-MCP-GUIDE.md` (904 lines, calibrated against the live `oneconsu-rest` tenant 2026-05-02) is the active deliverable; the in-repo MCP server build is the deferred deliverable. **Interlock noted with `methodology-extraction` Phase 5** — that phase closed by filing this project per the user's same-day directive. | Claude Opus 4.7 |
