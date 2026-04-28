# Vista CRM Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log. A project that survives execution
> unchanged is either trivial work or ignored information. See
> `CLAUDE.md → Engineering Philosophy → Projects are living documents`.
>
> **Before drafting or revising this project document: interrogate the user first.** Ask
> clarifying questions, confirm constraints, surface edge cases. Never assume.
> Document each answer in §2 so future agents inherit the reasoning.
>
> **Write for a zero-context reader.** Assume the next agent to pick up this
> project has not seen the conversation that produced it. Inline context in §1,
> quote the user in §2, name files with paths in §5, pair every §7 Open Question
> with an evidence-backed recommendation, and make §10 commands copy-paste
> ready. Full guidance in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §10`.
>
> **Terminology:** NoctusAI uses *project* for what other teams call a "plan"
> (the design-and-execution doc for a focused piece of work). The template
> replaces the former `PLAN-TEMPLATE.md`. Existing `*-PLAN.md` files may still
> exist until renamed in follow-up passes — treat them as projects regardless.

- **Created:** 2026-04-23
- **Last updated:** 2026-04-23
- **Status:** Design locked → Phase 1 ready
- **Owner / stakeholders:** Raphael · ERP Imobiliario · future zero-context execution agent
- **Related docs:** `CLAUDE.md`; `OPENAI.md`; `KNOWLEDGE-BASE/CONTEXT/03-SEED-ARCHITECTURE.md`; `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`; `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`; `products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql`; `products/erp-imobiliario/backend/migrations/004_mvp_expansion.sql`; Vista API docs `https://www.vistasoft.com.br/api/`; Vista help `https://ajuda.vistasoft.com.br/para-que-serve-a-api/`; Vista help `https://ajuda.vistasoft.com.br/como-solicitar-uma-nova-chave-api/`; Loft (parent brand of the user's current CRM — background only, not the integration target) `https://loft.com.br/para-imobiliarias/crm-para-imobiliarias/`
- **Project slug:** `vista-crm-wiring` (`products/erp-imobiliario/projects/vista-crm-wiring/`)

---

## 1. Context & Purpose

The ERP Imobiliario product needs a first integration with the user's current operational CRM, Loft/Vista CRM. The immediate goal is **not** migration and **not** write-back. The goal is to let ERP act as a **read-only showcase layer** over the data that currently lives in Vista, so the team can browse that external CRM data inside NoctusAI and decide what is worth keeping, mapping, or later importing into the ERP domain.

This first phase is intentionally narrow in data authority and broad in browseability. The user already has the Vista API key, tenant/base URL, and permission to access the needed API surface. The product should therefore consume Vista live, expose that data through ERP-owned backend proxy routes, and render it on a **single admin-only page** organized into **sub-tabs**. The architecture should deliberately leave a seam for a later phase where this same connector becomes the basis for seeding NoctusAI's own database during migration.

---

## 2. Confirmed constraints

Things the user told us that shape the design. Document the reasoning, not just the answer.

> **Source note:** the bullets below paraphrase answers the user gave during the 2026-04-23 interrogation that preceded this project file. They are not verbatim quotes. Future agents: if a constraint feels ambiguous, ask the user to confirm before acting — don't treat a paraphrase as an exact contract.

- **Current objective** — phase 1 is a **showcase only**. ERP consumes Vista API and displays the data. *This rules out local canonical persistence, write-back flows, and premature migration logic.*
- **Authority** — Vista remains the source of truth for now. *This means ERP must present external data as external, and any local caching must be treated as non-canonical if introduced later.*
- **UI shape** — the experience must be a **single-page display with sub-tabs**. *This rules out scattering the integration across multiple ERP modules in v1.*
- **Initial breadth** — the user wants to see **all accessible data categories first**, then decide what stays. *This favors wide endpoint coverage in the showcase, even if some tabs later get removed or narrowed.*
- **Visibility** — the feature is **admin-only** for now. *This sharply reduces RLS and UX scope for v1 and keeps the tool positioned as a controlled internal evaluation surface.*
- **Data freshness** — reads should be **live** for now. *This rules out a database mirror in phase 1 and means the backend must tolerate upstream latency/failure explicitly.*
- **Access readiness** — the user already has the **Vista API key**, **base URL**, and **permission** to access it. *This removes the external dependency of “wait for Loft/Vista enablement” from phase 1.*
- **Feature depth** — the user wants **all of it** for v1 browsing: list/detail, search, filters, pagination, status signals, and enough surface to decide what remains later. *The project should not artificially underscope the explorer UX.*
- **Business posture** — the page serves **both** as a future commercial showcase and as an internal tool, but it is **primarily an internal migration-prep tool** now. *This means the UX should optimize for inspection and understanding first, polish second.*
- **Adapter strategy** — start with a **Vista-specific adapter**, not a generic multi-CRM abstraction. *This keeps v1 smaller and avoids abstracting a second provider that does not exist yet.*
- **Future intent** — a later phase will use this connection to **populate NoctusAI's own DB**. *The current read-only implementation should therefore isolate API mapping, normalization, and error handling in a reusable seam instead of baking it into page components.*
- **LGPD posture** — the Vista payloads include personal data (lead/client names, contact details, possibly CPF/CNPJ and address). Admin-only access is the v1 **mitigation**, not an exemption. *This means: no payload leaves ERP backend unlogged, no LLM summarization or cache of personal fields in v1, no copy to a second product schema, and access audit is part of the feature — not a later add-on.* An LGPD concern is filed via `noctusai_lgpd_flag` at project creation so the retention/access-log/export decisions land on `LGPD-WARNINGS.md` for explicit resolution before Phase 3 ships.

---

## 3. Design principles

1. **Read-only first, authority explicit.** Phase 1 does not create or mutate ERP business rows from Vista payloads.
2. **Backend-mediated integration.** ERP frontend never calls Vista directly; ERP backend proxies, authenticates, normalizes, paginates, and logs access to the external CRM.
3. **Single explorer surface.** One admin page with sub-tabs gives the user a controlled, comparable, inspection-oriented view of the external CRM.
4. **Wide coverage before curation.** It is acceptable to initially expose more tabs/data than will survive long-term because the user explicitly wants breadth first, pruning second.
5. **Future import seam without premature migration.** The Vista adapter should be written so later import jobs can reuse endpoint clients and normalization logic, but no migration writes happen in v1.
6. **No silent degradation.** If a Vista endpoint is unavailable, permission-gated, slow, or shape-incompatible, surface that explicitly in the UI and project log instead of hiding the gap.
7. **LGPD-first, admin-only is the mitigation not the exemption.** Every surface that handles personal data passes through the LGPD lens before functionality or polish: access logged at the backend proxy, no persistence of personal fields in v1, no LLM summarization of client names/contacts, no cross-product export. The Vista data is Loft/Vista's source-of-truth — ERP is a read-only window onto it.
8. **Seed-compliant wiring, no custom mains.** The new router attaches to ERP's existing `create_product_app(...)` call in `products/erp-imobiliario/backend/app/main.py`; the new page attaches to the existing `createProductApp({ routes: [...] })` call in `products/erp-imobiliario/frontend/src/App.tsx`. Admin-only gating uses the ERP role system already wired through the seed, not a bespoke guard.

---

## 4. Scope

**In scope:**
- Create a Vista-specific backend adapter inside ERP.
- Add ERP backend proxy routes that call Vista API using the user's configured base URL and API key.
- Build a single admin-only ERP page for external CRM exploration.
- Organize the page into sub-tabs covering all materially accessible Vista domains needed for evaluation.
- Support broad browseability in v1: list/detail, search, filters, pagination, status metadata, and raw-response inspection where useful.
- Represent upstream fetch state explicitly: loading, empty, unauthorized, upstream error, malformed payload, rate-limited, etc.
- Design the code so a future import/seeding phase can reuse adapter and normalization logic.

**Out of scope (for now — with reason):**
- Writing ERP canonical rows from Vista payloads — deferred to the later migration-seed project the user explicitly postponed.
- Bi-directional sync or write-back into Vista — deferred because v1 is showcase-only.
- Background sync jobs, webhooks, cron ingestion, or persistent cache tables — deferred because the user asked for live-read now.
- Customer-facing/public listing exposure — deferred because access is admin-only in phase 1.
- Generic multi-CRM abstraction — deferred because the user explicitly chose a Vista-specific adapter first.
- Automatic field-by-field migration reconciliation — deferred until the future DB-population phase.

---

## 5. Architecture / Data Model

### Existing ERP destination model the future migration phase will likely care about

Phase 1 does **not** write to these tables, but the follow-up agent must understand the eventual landing zone. Relevant existing ERP entities include:

- `erp.ativos` — property inventory in `products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql`
- `erp.clientes` — CRM contacts / leads
- `erp.negociacoes` — pipeline / deal flow
- `erp.propostas` — proposals
- `erp.contratos` and `erp.contratos_locacao` — sales/rental contracts
- `erp.eventos` — visits / meetings / scheduling
- `erp.documentos` — attached/generated documents
- `erp.campanhas` — marketing activity
- `erp.filiais` — branch structure

Phase 1 should not mutate these tables. Their importance here is architectural: the adapter and page should expose Vista data in a way that can later be mapped onto these ERP entities.

### Proposed v1 structure

#### Backend

Add a Vista adapter layer inside ERP, for example:

- `backend/app/integrations/vista/client.py`
- `backend/app/integrations/vista/types.py`
- `backend/app/integrations/vista/normalizers.py`
- `backend/app/services/vista_showcase_service.py`
- `backend/app/routers/vista_showcase.py`

Responsibilities:

- `client.py`
  - stores the tenant/base URL + API key usage contract
  - performs authenticated HTTP calls
  - handles pagination, request params, timeouts, and typed upstream errors
  - logs every outbound Vista request for LGPD access-audit purposes (who, when, which tab, which id) — this is a phase-1 requirement, not deferred
- `types.py`
  - documents the subset of Vista response shapes we rely on
- `normalizers.py`
  - converts Vista payloads into ERP-friendly "showcase DTOs"
  - this is the future seam for import mapping
  - MUST NOT drop Vista's source id/origin metadata — future mapping needs the trace
- `vista_showcase_service.py`
  - coordinates per-tab fetches
  - exposes list/detail/search/filter operations in ERP terms
  - does NOT cache personal data in v1 (live-read constraint from §2)
- `vista_showcase.py`
  - ERP-owned `/api/vista-showcase/*` endpoints for the frontend
  - admin-only dependency via the ERP role system already wired through seed (do not invent a bespoke guard)

**Seed wiring (mandatory — not optional).** The router is registered through the seed factory that already drives the product — **do not create a second `main.py` entrypoint or a bespoke app instance**:

- Import the new router and add it to the existing `routers=[...]` list in `products/erp-imobiliario/backend/app/main.py`'s `create_product_app(...)` call (see `noctusai_seed.create_product_app`). No `standard_routers=[...]` change needed — Vista is a product-owned router, not a seed-standard one.
- Credentials (`VISTA_BASE_URL`, `VISTA_API_KEY`) go in the single root `.env` consumed by ERP's existing `settings` object (`products/erp-imobiliario/backend/app/config.py`); never hardcode and never surface to the frontend. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md`.
- If startup-time validation of Vista credentials is desired, hook it into the existing `lifespan_startup=_startup` seam — do not add a new lifespan.

#### Frontend

Add one ERP page, for example:

- `frontend/src/pages/VistaShowcase.tsx`

Potential supporting files:

- `frontend/src/hooks/useVistaShowcase.ts`
- `frontend/src/components/vista/VistaTabTable.tsx`
- `frontend/src/components/vista/VistaDetailPanel.tsx`
- `frontend/src/components/vista/VistaPayloadDebug.tsx`

Responsibilities:

- one route in ERP navigation, admin-only
- one page shell with sub-tabs
- shared list/detail/filter/pagination mechanics reused across tabs
- explicit "external CRM / live data" framing

**Seed wiring (mandatory — not optional).** The page registers through the existing `createProductApp({ routes: [...] })` call in `products/erp-imobiliario/frontend/src/App.tsx` — **do not fork `App.tsx` or instantiate a second app root**:

- Add one entry to the `routes` array, e.g. `{ path: "/admin/vista-showcase", component: VistaShowcase }`. Admin-gating uses the ERP role system already threaded through the seed layout — surface it via the existing admin-route pattern (see the `/admin` route already present in `App.tsx`), not a bespoke check inside the page.
- Data fetching uses the shared `@noctusai/lib` API client + TanStack Query patterns already used by other ERP pages. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/frontend.md`.
- Navigation/sidebar entry (if needed) flows through the ERP layout's existing admin-menu extension; no custom layout wrapper.

### LGPD posture (phase 1)

The Vista showcase surfaces personal data (names, emails, phones, potentially CPF/CNPJ, addresses of leads and clients). Admin-only is the v1 mitigation — not an exemption. Non-negotiable controls for phase 1:

- **Access audit.** Every Vista proxy call is logged at the ERP backend with the calling user, timestamp, tab, and id (if a detail fetch). This is implemented in `client.py`, not deferred.
- **No personal-data cache.** No DB mirror, no in-memory cache keyed on personal fields. Live-read only.
- **No LLM summarization of personal fields in v1.** If a tab later benefits from AI assist, it re-enters the LGPD lens at that time.
- **No cross-schema copy.** Vista payloads stay bounded to this feature's surface — they do not flow into `erp.*` canonical tables until the future migration project owns that decision.
- **Frontend blind to secrets.** `VISTA_API_KEY` never reaches the browser; validated by the `VITE_`-prefix security rule in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md`.
- **LGPD-WARNINGS entry filed.** An `noctusai_lgpd_flag` entry covering "admin-only showcase of Vista personal data — retention/access-log/export model TBD before Phase 3" is the standing open item for this feature; it gets resolved when the access-audit sink and the retention contract are both in place.

### Proposed v1 tabs

Because the user said “all of it” for discovery, start broad and prune later. The exact tab list must be validated against the real Vista tenant permissions and documented endpoint coverage, but the initial intent is to include every materially useful domain exposed by the user's access.

Recommended first-pass tab families:

- `Imoveis`
- `Clientes`
- `Atendimentos / Negociacoes`
- `Propostas`
- `Agenda / Eventos`
- `Filiais / Equipes / Estruturas comerciais`
- `Documentos / anexos / mídia`
- `Campanhas / marketing`, if the tenant and API actually expose them
- `Debug / metadata`, if needed to inspect payloads during migration prep

The executing agent must verify the real endpoint list against the official docs and the user's tenant access before freezing the tabs.

### API shape in ERP

Keep the ERP API consumer-friendly and explicit about external origin. Example shape:

- `GET /api/vista-showcase/tabs`
- `GET /api/vista-showcase/{tab}`
- `GET /api/vista-showcase/{tab}/{id}`

Recommended response envelope:

```json
{
  "source": "vista",
  "tab": "imoveis",
  "live": true,
  "fetched_at": "2026-04-23T12:34:56Z",
  "page": 1,
  "page_size": 50,
  "total": 1234,
  "items": [],
  "raw_available": true,
  "warnings": []
}
```

### Authentication / configuration

Do **not** hardcode the Vista base URL or API key in the page.

Recommended configuration posture:

- store credentials in ERP backend env/config first
- keep frontend completely blind to the secret
- if a later admin UI for connector settings is needed, defer it to a later phase unless it is required to ship phase 1

### Error model

Surface upstream conditions explicitly:

- invalid API key
- base URL misconfigured
- endpoint unauthorized by tenant permissions
- upstream timeout
- malformed or drifting payload
- pagination/param mismatch
- rate limiting

This is not optional because phase 1 is also a migration-discovery tool; hidden failures destroy the value of the page.

---

## 6. Implementation phases

Phases are suggestive, not strict. Reorder if repository evidence demands it.

### Phase 1 — Discovery baseline
- [ ] Verify the real Vista API surface available to this tenant and enumerate which domains are actually reachable with the user's credentials.
- [ ] Capture the exact endpoint inventory, auth method, pagination conventions, and notable response-shape caveats in this project file.
- [ ] Map each confirmed Vista domain to one of: "show in v1", "show later", or "out of scope / inaccessible".
- [ ] Resolve the LGPD access-audit sink choice (ERP's existing audit log vs. a Vista-scoped one) and record it in §5 before Phase 2 writes the client.

### Phase 2 — Backend adapter foundation
- [ ] Add `VISTA_BASE_URL` + `VISTA_API_KEY` to the single root `.env` and wire them through the existing ERP `settings` object — never hardcoded, never frontend-exposed.
- [ ] Implement the Vista-specific ERP backend adapter (`client`, typed errors, config wiring), including the access-audit log per request (Phase 1 decision).
- [ ] Implement normalized showcase DTOs for each approved v1 tab family (retain Vista source id + origin metadata).
- [ ] Add ERP backend proxy routes for tab listing and detail fetches, registered via the existing `create_product_app(...) routers=[...]` in `products/erp-imobiliario/backend/app/main.py` — no new app instance.
- [ ] Admin-only gating via the ERP role system already threaded through the seed — no bespoke guard.
- [ ] Add tests for auth/config failure, timeout/error handling, pagination, access-audit write, and at least one happy path per approved tab family.

### Phase 3 — Single-page showcase UI
- [ ] Add one admin-only route/page in ERP for the Vista showcase, registered via the existing `createProductApp({ routes: [...] })` in `products/erp-imobiliario/frontend/src/App.tsx` — no `App.tsx` fork.
- [ ] Implement sub-tabs for every approved v1 domain.
- [ ] Implement list/detail browsing, search, filters, pagination, and explicit fetch metadata via the shared `@noctusai/lib` API client + TanStack Query patterns.
- [ ] Add a raw payload inspection mode where useful for migration preparation (behind a debug affordance, not always-on).
- [ ] Ensure the page communicates that the data is external, live-read, and non-canonical.
- [ ] Confirm the standing LGPD flag for this feature has been resolved (access audit shipped + retention contract documented) before flipping this phase to `✅`.

### Phase 4 — Hardening and migration seam
- [ ] Verify behavior for all approved tabs against the real Vista tenant.
- [ ] Document which DTOs and normalization functions are safe to reuse in a later import/seeding phase.
- [ ] Identify the minimal delta between "showcase DTO" and future ERP import mapping.
- [ ] At phase end, synthesize the standard **ONE bundled proposal** for this phase via `noctusai_file_proposal(project="vista-crm-wiring", ...)` covering any of {background sync, staging cache, mapping extraction, field-mapping expansion, LGPD retention policy} the phase-4 evidence actually supports. If the evidence shows none, file nothing and write `**Improvements:** none identified.` here — do not invent bundle items.

---

## 7. Open questions

Unresolved items. Each includes a recommendation so a future agent can move with evidence instead of guessing.

1. **Which exact Vista endpoint families are reachable with this tenant's credentials?** — needs answer before Phase 1 ends / decided by execution against the real tenant.
   Recommendation: treat the official docs as the candidate inventory, but freeze the tab list only after live credential verification because tenant permissions may expose a narrower surface than the docs.

2. **What is the safest home for the Vista credentials in phase 1: existing ERP env config only, or a future admin-managed connector config?** — needs answer before Phase 2 / decided by user + repo conventions.
   Recommendation: use backend env/config first to keep v1 smaller and safer; defer a UI-managed connector settings screen unless phase 1 is blocked without it.

3. **Should every tab expose raw JSON inspection, or only a subset?** — can be decided during Phase 3 / decided by execution agent with user confirmation if the UI becomes noisy.
   Recommendation: enable raw payload view selectively behind a debug affordance, because this is primarily a migration-prep tool and raw source inspection is valuable during field mapping.

4. **Do any Vista domains require special pagination, nested fetch choreography, or per-item expansion calls that make “all tabs in v1” too expensive?** — needs answer during Phase 1 / decided by live API exploration.
   Recommendation: if one domain is disproportionately expensive or poorly documented, keep the page shell broad but mark that tab as deferred/experimental instead of blocking the entire showcase.

5. **Should the page include side-by-side “future ERP landing entity” hints in v1?** — can be decided in Phase 3 / decided by user after first browse.
   Recommendation: add lightweight labels such as “future landing: `erp.ativos`” only if it improves migration understanding without cluttering the page.

6. **What request volume / latency is acceptable for live-read admin browsing?** — can be answered in Phase 4 after real-tenant testing / decided by measured behavior.
   Recommendation: do not introduce DB caching preemptively; measure first. If live-read is too slow, propose a non-canonical cache as a follow-up improvement rather than changing phase 1's contract silently.

---

## 8. Dependencies & blockers

- **Real Vista tenant access from the execution environment** — the implementing agent must be able to run authenticated requests against the user's real Vista base URL with the provided API key.
- **Credential handling decision** — backend config must have a clear place for the Vista base URL and API key.
- **Official endpoint verification** — the executor must confirm which documented domains are truly enabled for this tenant before freezing tabs.
- **Admin route / role gating alignment in ERP** — the page must be visible only to ERP admins in phase 1.

---

## 9. Success criteria

- An ERP admin can open one dedicated page and browse the approved Vista domains through sub-tabs.
- The page reads Vista data live through ERP backend proxy routes; the frontend never handles the secret directly.
- The page supports broad evaluation ergonomics: list/detail, search, filters, pagination, and explicit upstream-state messaging.
- No ERP canonical business rows are created or mutated from Vista payloads in phase 1.
- The adapter and normalization layer are documented clearly enough that a later project can reuse them for DB population.
- The project file records which Vista domains were confirmed, deferred, inaccessible, or intentionally excluded.

---

## 10. How to use this project

- **Single source of truth for progress.** Update this file as work progresses.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` immediately, not in batches.
- **Phase-by-phase by default.** Execute one phase, then pause for user approval before the next phase unless the user explicitly authorizes multi-phase throughput.
- **Revise when evidence changes.** If Vista's real API surface is narrower or stranger than the docs suggest, update §4, §5, and §7 instead of forcing the original assumption.
- **Verify with the real tenant before claiming coverage.** Documentation alone is insufficient for this project.

Suggested execution commands once implementation begins:

```bash
# Read this project first
sed -n '1,260p' products/erp-imobiliario/projects/vista-crm-wiring/PROJECT.md

# Inspect ERP schema targets
rg -n "CREATE TABLE (IF NOT EXISTS )?erp\\.(ativos|clientes|negociacoes|propostas|contratos|eventos|documentos|campanhas|filiais)" \
  products/erp-imobiliario/backend/migrations/001_erp_imobiliario.sql \
  products/erp-imobiliario/backend/migrations/004_mvp_expansion.sql

# Run ERP backend tests after backend work
cd products/erp-imobiliario/backend && pytest

# Run ERP frontend build after frontend work
cd products/erp-imobiliario/frontend && npx vite build

# Run MCP review after changes
python mcp/noctusai/cli.py --review
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-23 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after interrogating the user. Locked scope: admin-only single-page live Vista showcase in ERP, Vista-specific adapter first, future DB population explicitly deferred. | Codex |
| 2026-04-23 | Assessment + fix pass (Claude Opus 4.7): named the seed seams explicitly in §5 (backend router via existing `create_product_app(...) routers=[...]`; frontend page via existing `createProductApp({ routes: [...] })`), added LGPD-first constraint to §2 + principle to §3 + full posture subsection to §5, filed standing `noctusai_lgpd_flag` concern for the feature, corrected Phase 4 proposal wording to match the "ONE bundled proposal per phase" protocol, removed preemptive `none identified` from unstarted phases, renamed §10 "How to use this plan" → "How to use this project", and clarified the Loft-vs-Vista context in Related docs. | Claude Opus 4.7 |
