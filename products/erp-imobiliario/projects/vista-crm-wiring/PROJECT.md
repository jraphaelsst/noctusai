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
- **Status:** ✅ Done — all phases closed 2026-05-02. Vista CRM showcase shipped: backend adapter + audit-log + admin-only proxy router + frontend page with 7 sub-tabs + sidebar nav + LGPD-aware framing + live tenant verified end-to-end (1,783 properties, 10 users, 1 agency reachable). Late-day Phase 4.5 hardening pass on 2026-05-02 re-calibrated the field sets after a `[502] Vista respondeu erro 400` UI failure surfaced that Phase 1's smoke probe never tested the full field bundle in one request — see §11 entry of same date.
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
- **LGPD posture** — the Vista payloads include personal data (lead/client names, contact details, possibly CPF/CNPJ and address). Admin-only access is the v1 **mitigation**, not an exemption. *This means: no payload leaves ERP backend unlogged, no LLM summarization or cache of personal fields in v1, no copy to a second product schema, and access audit is part of the feature — not a later add-on.* An LGPD concern is filed via `noctus.dev.lgpd_flag` at project creation so the retention/access-log/export decisions land on `LGPD-WARNINGS.md` for explicit resolution before Phase 3 ships.

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

### Discovery results — confirmed Vista API surface (2026-05-01)

(See §6 Phase 1 for the discovery work itself; this section captures the findings.)

**Tenant.** `https://oneconsu-rest.vistahost.com.br` (One Consultoria Imobiliária — Cotia/SP). Credentials live in the gitignored root `.env` as `VISTA_BASE_URL` + `VISTA_API_KEY`. Backend-only — never `VITE_`-prefixed.

**Auth contract** (confirmed against the live tenant):
- `?key=<API_KEY>` query parameter on every call.
- `Accept: application/json` header required.
- No bearer / OAuth / cookie. Single API key per tenant.

**Query convention.** Most endpoints take `pesquisa=<JSON>` carrying `{fields, filter, order, paginacao, advFilter}`. Some endpoints (`/imoveis/detalhes`) require ID parameters at the **top level** (`?imovel=<Codigo>`), NOT inside `pesquisa`.

**Pagination.** `paginacao={"pagina":N,"quantidade":N}` — max 50/page. Add `&showtotal=1` to get `total` + `paginas` in the response envelope.

**Response shape for collections.** Items are returned as a top-level dict keyed by primary id (e.g. `{"CA2830": {...}, "TE0080": {...}, "total": 1784, "paginas": 595, "pagina": 1, "quantidade": 3}`) — NOT a JSON array. Normalizers must dict-iterate, not array-iterate.

**Endpoint inventory — what this tenant's key actually reaches:**

| Endpoint | Status | Notes |
|---|---|---|
| `/imoveis/listar` | ✅ 200 | Property catalog. **1,784 properties.** Confirmed fields: `Codigo, Cidade, Bairro, Categoria, Endereco, Numero, CEP, Estado, ValorVenda, ValorLocacao, AreaTotal, AreaPrivativa, AreaConstruida, Dormitorios, Suites, Vagas, Banheiros, Status, DataCadastro, DataAtualizacao, Latitude, Longitude, Caracteristicas (large nested object), TituloSite, Empreendimento, Construtora, Corretor, CodigoImobiliaria, Foto, FotoDestaque, Slug, PalavrasChave`. |
| `/imoveis/detalhes` | ✅ 200 | `?imovel=<Codigo>` (top-level), plus `pesquisa.fields[]`. Returns full record. **`Foto` field is NOT available on detalhes** even though it's available on `listar` — Phase 2 must use `Foto` from the listing path, not detalhes. |
| `/imoveis/listarConteudo` | ✅ 200 | Metadata for filter dropdowns. `pesquisa.fields=["Status","Categoria","Cidade","Bairro"]` returns enum values. Useful for the filter UI. |
| `/usuarios/listar` | ✅ 200 | Vista's internal users (16+ rows on this tenant). Confirmed fields: `Codigo, Nome, Email, Foto, Setor`. **NOT available**: `Apelido, Login, FotoPequena, DataCadastro, CodigoImobiliaria` (returns 400 "Campo X não está disponível"). |
| `/agencias/listar` | ✅ 200 | Agency metadata (1 row — "ONE CONSULTORIA IMOBILIARIA"). Confirmed fields: `Codigo, Nome, Endereco, Cidade, Bairro, Site`. **NOT available**: `Estado, UF, CEP, Telefone, Email, Foto, Logo, Status, DataCadastro`. |
| `/clientes/listar` | 🔒 401 | Endpoint exists; **this key has no permission**. Vista responds `Permissão Negada`. |
| `/clientes/detalhes` | 🔒 401 | Same — exists, no permission. |
| `/corretores/listar` | 🔒 401 | Same — exists, no permission. |
| `/imoveis/fotos` | ❌ 404 | Re-probed 2026-05-02 (Phase 4 smoke): live tenant returns 404 "No route found", NOT 401. Phase 1 misclassified — endpoint isn't enabled for this subscription tier. **Workaround**: photos appear in `/imoveis/listar` via the `Foto` field — use the URL there. |
| `/imoveis/historico`, `/imoveis/proximos`, `/imoveis/buscar`, `/imoveis/pesquisar`, `/imoveis/destaque` | ❌ 404 | Not exposed on this tenant. |
| `/leads/*`, `/atendimentos/*`, `/agendamentos/*`, `/negociacoes/*`, `/propostas/*`, `/vendas/*`, `/condominios/*`, `/empreendimentos/*`, `/bairros/*`, `/cidades/*`, `/categorias/*`, `/tabelas/*`, `/portais/*`, `/ancillary-revenue/*` | ❌ 404 | Not exposed on this tenant. The public `vistasoft.com.br/api` surface is broader; this tenant subscribes only to the property catalog + admin metadata. |

**v1 tab plan — open question 1 resolved.**

| Tab | Endpoint(s) | Purpose |
|---|---|---|
| **Imóveis** (catalog) | `/imoveis/listar` + `/imoveis/listarConteudo` | Browse property catalog with filters (Status, Categoria, Cidade, Bairro). Card list paginated. Default v1 view. |
| **Detalhes** (drill-down) | `/imoveis/detalhes` | Per-property drill-down opened from the Imóveis tab. Includes `Caracteristicas` rendering + raw-JSON inspect mode (per Open Q3). |
| **Usuários** (internal) | `/usuarios/listar` | Vista's internal team — name + email + setor + photo. Useful for cross-referencing the `Corretor` field on properties. |
| **Agência** (metadata) | `/agencias/listar` | Agency name + address. Single row on this tenant; serves as the "you're connected" panel. |

**Deferred / blocked tabs (LGPD note required in UI):**

- **Clientes**, **Corretores**, **Fotos** — endpoints exist but the API key lacks permission. UI should render the tab placeholder with a "Permissão pendente — solicite expansão de chave junto à Vista" message + the 401 status code visible (so the user knows it's a Vista-side ACL, not an integration bug).

**Out-of-scope (no route on this tenant):** leads, atendimentos, agendamentos, negociações, propostas, vendas, condominios, empreendimentos, ancillary-revenue. The page should NOT advertise these as "coming soon" — they'd require a different Vista subscription tier.

**LGPD access-audit decision.** Per Open Q's request to resolve this before Phase 2 begins: **use ERP's existing `erp.user_actions_log` table** (defined in `001_erp_imobiliario.sql`, with `tipo_acao` + `tipo_entidade` enums) — not a Vista-scoped sink. Rationale: (a) audit table already exists in ERP with the right RLS posture (org-scoped, append-only, indexed); (b) cross-feature reporting wants one audit destination per product, not per integration; (c) LGPD principle of data-minimization — the audit row records `{tipo_acao='consulta_externa', tipo_entidade='integracao_vista', entidade_id=<Codigo>, descricao, detalhes (metadata only), usuario_id, created_at}` and nothing else from Vista. The Vista *response payload itself* must NEVER be persisted (live-read constraint). Phase 2 reuses the existing `app.dependencies.log_action(...)` helper (which wraps `noctusai_lib.domain.action_log.log_action`) — no new audit helper needed. Migration `023_vista_audit_enums.sql` extends `tipo_acao` with `consulta_externa` and `tipo_entidade` with `integracao_vista`. *(Earlier draft of this document referred to the table as `audit_logs`; the Phase 0 audit on 2026-05-02 confirmed the actual name is `user_actions_log` — corrected here.)*

### Migration seam — what the future import phase can reuse

Phase 1-4 deliberately built the read path so a future *import* phase
(Vista → ERP canonical tables) can reuse most of it without rewriting:

**Reusable as-is:**
- `app.integrations.vista.client.VistaClient` — typed HTTP client, error
  hierarchy, dict-keyed-by-id awareness via `extract_items()`. The same
  client serves a one-shot importer.
- `app.integrations.vista.client.PAGINATION_KEYS` + `extract_items()` —
  centralized handling of Vista's unusual response shape. An importer
  paginates through 1,784 properties without needing to re-discover this.
- The whole `app.integrations.vista.normalizers` module — `vista_imovel_to_showcase`,
  `vista_imovel_detalhes_to_showcase`, `vista_usuario_to_showcase`,
  `vista_agencia_to_showcase`. Each carries the full `raw: dict` for
  field-level mapping decisions in the importer.
- The audit-log path in `vista_showcase_service._audit(...)` — an importer
  also wants to log every outbound call for LGPD; reuse this helper, just
  pass the importer's user/job id.
- `IMOVEL_LIST_FIELDS` / `IMOVEL_DETAIL_FIELDS` field-set constants —
  these are the per-tenant-confirmed safe field sets. Don't re-discover.

**Minimal delta between showcase DTO and ERP canonical tables:**
- `ShowcaseImovel` → `erp.ativos`. Mapping deltas:
  - `codigo` (Vista) → keep as `vista_codigo` provenance column on
    `erp.ativos` (so re-import is idempotent and auditable).
  - `categoria` (Vista) → ERP categoria enum (CASA, APTO, TERRENO, …). Vista
    values (e.g. "Casa", "Terreno") need mapping table (see ERP enum in
    `001_erp_imobiliario.sql`).
  - `valor_venda`, `valor_locacao` → `erp.ativos.valor` / pricing columns.
  - `cidade`, `bairro`, `endereco`, `cep`, `estado`, `latitude`, `longitude`
    → already match ERP columns.
  - `caracteristicas` → JSONB column on `erp.ativos` (Vista's nested object
    is too sparse for first-class columns).
- `ShowcaseUsuario` → no direct ERP equivalent. Vista's internal users are
  Loft/Vista employees, not ERP profiles. Keep as reference data only.
- `ShowcaseAgencia` → `erp.filiais` if the tenant decides to migrate. Single-
  row on this tenant; trivial mapping.
- **What's missing for a clean import:** a `vista_codigo` provenance column
  on `erp.ativos` (and on any other table imported from Vista). This is a
  one-column migration in the future import project.

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
- **LGPD-WARNINGS entry filed.** An `noctus.dev.lgpd_flag` entry covering "admin-only showcase of Vista personal data — retention/access-log/export model TBD before Phase 3" is the standing open item for this feature; it gets resolved when the access-audit sink and the retention contract are both in place.

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

### Phase 1 — Discovery baseline ✅ (2026-05-01)
- [x] Verified the real Vista API surface available to this tenant. Credentials stored in gitignored root `.env` (`VISTA_BASE_URL` + `VISTA_API_KEY`). Auth = `?key=` query param + `Accept: application/json` header.
- [x] Captured endpoint inventory in §5 with HTTP status per endpoint, allowed/disallowed fields (per-endpoint), pagination conventions (max 50/page, dict-keyed-by-id response shape, not array), notable caveats (`imovel` is top-level not inside `pesquisa`; `Foto` works on `listar` but NOT on `detalhes`).
- [x] Mapped 4 v1 tabs (Imóveis catalog + Detalhes drill-down + Usuários + Agência), 3 deferred-pending-permission (Clientes / Corretores / Fotos — all 401), and the rest out-of-scope (no route).
- [x] Resolved LGPD audit decision in §5: use ERP's existing `audit_logs` table; record `{action, resource_type=vista_<tab>, resource_id=<Codigo>, user_id, created_at}` per outbound Vista call; **never persist the Vista response payload** (live-read constraint).

**Improvements:**
- Vista's response shape (top-level dict keyed by primary id, with pagination fields siblings of items) is unusual — most REST APIs return `{"data": [...], "pagination": {...}}`. Phase 2 normalizers must dict-iterate (skipping `total`/`paginas`/`pagina`/`quantidade` keys). Worth a single comment in `normalizers.py` so a future agent doesn't re-discover this.
- The 401 responses on `/clientes/*`, `/corretores/*`, `/imoveis/fotos` are **expected for this tenant's subscription tier**, not a credential bug. UI should surface a "Permissão pendente — solicite expansão junto à Vista" placeholder (per the §5 plan), so a future user expanding the API key sees the tabs come alive without needing code changes.
- The `vistasoft.com.br/api/` public docs advertise endpoints (leads, atendimentos, agendamentos, etc.) that this tenant does NOT have. The `/doc/` URL on the live tenant returns a JS-rendered SPA that WebFetch can't read. Phase 2 should NOT trust the public docs as the source of truth — only the live probe results captured in this project's §5 are reliable for THIS tenant.

### Phase 2 — Backend adapter foundation ✅ (2026-05-02)
- [x] Add `VISTA_BASE_URL` + `VISTA_API_KEY` to the single root `.env` and wire them through the existing ERP `settings` object — never hardcoded, never frontend-exposed. *(ERPSettings.vista_base_url / vista_api_key in `app/config.py`; backend-only.)*
- [x] Implement the Vista-specific ERP backend adapter (`client`, typed errors, config wiring), including the access-audit log per request (Phase 1 decision). *(`app/integrations/vista/{client,types,normalizers}.py`; typed errors VistaConfigError / VistaUpstreamError / VistaPermissionDenied / VistaNotFound / VistaFieldNotAvailable / VistaTimeout; lenient `__init__`, fail-at-request-time per FastAPI dep-factory rule.)*
- [x] Implement normalized showcase DTOs for each approved v1 tab family (retain Vista source id + origin metadata). *(`app/integrations/vista/types.py`: ShowcaseImovel, ShowcaseImovelDetalhes, ShowcaseUsuario, ShowcaseAgencia, ShowcaseEnvelope, ShowcaseTabStatus, ShowcaseDiagnostic. Every DTO carries `raw: dict` so the future migration phase has the full source payload.)*
- [x] Add ERP backend proxy routes for tab listing and detail fetches, registered via the existing `create_product_app(...) routers=[...]` in `products/erp-imobiliario/backend/app/main.py` — no new app instance. *(`/api/vista-showcase/{tabs,imoveis,imoveis/{codigo},imoveis-conteudo,usuarios,agencias,diagnostico}`. Mounted as `vista_showcase.router` alongside the other 50+ ERP routers — no `main.py` fork.)*
- [x] Admin-only gating via the ERP role system already threaded through the seed — no bespoke guard. *(`require_admin` dependency: `resolve_sso_role` first, then `erp_role`/`noctus_role` fallback. Reuses noctusai_lib.api.auth.resolve_sso_role.)*
- [x] Add tests for auth/config failure, timeout/error handling, pagination, access-audit write, and at least one happy path per approved tab family. *(`tests/routers/test_vista_showcase_router.py`: 18 tests covering admin gating · tabs catalog (with-creds vs not-configured) · imóveis happy path / filter passthrough / detalhes happy path · usuários · agências · 401→403, 404→404, timeout→504, upstream-5xx→502, 503-on-no-creds · diagnóstico. All passing.)*
- [x] Audit-log enum extension migration — added `consulta_externa` to `erp.tipo_acao` and `integracao_vista` to `erp.tipo_entidade` via `migrations/023_vista_audit_enums.sql` (also applied via Supabase MCP per "MCP migrations mirror the file" rule).

**Improvements:**
- *(corrected during Phase 0 audit)* Phase 1 documented the audit table as `audit_logs`; the actual table is `erp.user_actions_log` (per `001_erp_imobiliario.sql`). §5 LGPD section + this Change Log corrected. The helper `app.dependencies.log_action` (which wraps `noctusai_lib.domain.action_log.log_action`) was already perfectly suited for the Vista audit path — reused instead of writing a new helper. No new audit infrastructure.
- The `MockSupabaseClient(validate_schema=False)` fixture (per ERP's tests/conftest.py rationale) means our tests don't catch insert-shape drift against the real `user_actions_log` schema. Acceptable for Phase 2 (migration applied + audit row metadata is small). When the broader `erp-schema-drift-reconciliation` project flips ERP to `validate_schema=True`, the Vista audit path will need to validate against the real `user_actions_log` columns. Filed for follow-up.
- Audit-log writes happen on BOTH success and failure paths (every `_audit(user_id=..., result=..., error=...)` call in the service). This means the access trail is honest: a 401 from Vista still leaves a row saying "ERRO GET /clientes/listar" with the error class. Useful for LGPD (every access attempt is recorded, not just successes).
- The dict-keyed-by-id Vista response shape (top-level keys mixed with pagination siblings) is centralized in `extract_items()` — one place to know about it. Future MCP authors should NOT re-discover this; VISTA-API.md § 3 documents it.

### Phase 3 — Single-page showcase UI ✅ (2026-05-02)
- [x] Add one admin-only route/page in ERP for the Vista showcase, registered via the existing `createProductApp({ routes: [...] })` in `products/erp-imobiliario/frontend/src/App.tsx` — no `App.tsx` fork. *(Route `/integracoes/vista` → `pages/VistaShowcase.tsx`. Lazy-imported alongside other ERP pages.)*
- [x] Implement sub-tabs for every approved v1 domain. *(7 sub-tabs: Imóveis · Usuários · Agência · Clientes · Corretores · Fotos · Diagnóstico — using shadcn `<Tabs>` primitive.)*
- [x] Implement list/detail browsing, search, filters, pagination, and explicit fetch metadata via the shared `@noctusai/lib` API client + TanStack Query patterns. *(`hooks/useVistaShowcase.ts`: useVistaTabs, useVistaImoveis, useVistaImovelDetalhes, useVistaImoveisConteudo, useVistaUsuarios, useVistaAgencias, useVistaDiagnostico. Filter bar with Status/Categoria/Cidade/Bairro/Finalidade. Pagination bar with prev/next + total + paginas + fetched-at timestamp.)*
- [x] Add a raw payload inspection mode where useful for migration preparation (behind a debug affordance, not always-on). *(Imóvel Detalhes dialog has "Mostrar payload bruto (debug)" toggle. Diagnóstico tab shows tenant base URL + per-endpoint probe table with HTTP status + latency.)*
- [x] Ensure the page communicates that the data is external, live-read, and non-canonical. *(Page header: "Janela somente-leitura sobre o CRM externo da agência. Os dados permanecem sob a autoridade da Vista; nada é gravado em ERP nesta fase. Acesso restrito a administradores; cada chamada à Vista é registrada em erp.user_actions_log." LGPD-aware framing throughout.)*
- [x] Confirm the standing LGPD flag for this feature has been resolved (access audit shipped + retention contract documented) before flipping this phase to `✅`. *(Access audit shipped in Phase 2 — `_audit()` writes one row per outbound Vista call. Retention contract: live-read only; no Vista payload persists; `detalhes` JSONB stores only metadata. Documented in § 5 of this PROJECT.md and § 5 of VISTA-API.md.)*
- [x] Sidebar link added — new NAV_GROUP "Integrações" with one item "Vista CRM" (route `/integracoes/vista`). Future integrations expand here.

**Improvements:**
- The frontend admin gate (`useIsAdmin()` from `@/hooks/useUserRole`) blocks render before any backend call, but the backend `require_admin` is the actual security boundary. Frontend gate is UX-only; security lives at the router. Worth a comment in the page so a future agent doesn't lean on the frontend check.
- The "Diagnóstico" tab probes 7 endpoints sequentially via `client.probe(...)` calls. For 7 endpoints × ~200ms each, that's ~1.4s. Acceptable for an admin debug tool, but if/when this grows to many tenants or endpoints, parallelize via `asyncio.gather`. Filed as a non-urgent perf note.
- `KNOWN_TABS` is a static catalog inside the service. When live tenant behavior diverges from the catalog (as it just did with `/imoveis/fotos` — Phase 1 said 401, live says 404), the catalog goes stale silently. Consider: at boot or on Diagnóstico-tab refresh, run the probes and *update* the catalog's status field for the running session. Trade-off: more network calls per boot vs. faster trust calibration. Filed for Phase 4 bundled proposal.
- The dict-keyed-by-id response shape works fine for usuários (numeric keys "16", "46", "56") and agência (single key "1") — confirmed live. The normalizer is shape-agnostic. Worth a one-line comment in `extract_items` so a future agent knows numeric-string keys are valid.
- `VistaShowcase.tsx` is one page with seven inline tab components (~620 lines). At this size it's still readable, but a 7-tab page is the right time to consider splitting each tab into `components/vista/<TabName>Tab.tsx`. Not urgent; flagged for the next time someone touches the page.

### Phase 4 — Hardening and migration seam ✅ (2026-05-02)
- [x] Verify behavior for all approved tabs against the real Vista tenant. *(Live smoke probe — script in `/tmp/vista_smoke.py` and now deleted; the Diagnóstico tab is the canonical replacement — against `oneconsu-rest.vistahost.com.br`: `/imoveis/listar` ✅ 200 1784 properties · `/imoveis/listarConteudo` ✅ 200 · `/usuarios/listar` ✅ 200 · `/agencias/listar` ✅ 200 · `/clientes/listar` 🔒 401 · `/corretores/listar` 🔒 401 · `/imoveis/fotos` ❌ 404 (not 401 as Phase 1 doc said — corrected in §5 + VISTA-API.md + KNOWN_TABS).)*
- [x] Document which DTOs and normalization functions are safe to reuse in a later import/seeding phase. *(See § "Migration seam" in §5.)*
- [x] Identify the minimal delta between "showcase DTO" and future ERP import mapping. *(See § "Migration seam".)*
- [x] Synthesize phase-end bundled proposal via `noctus.dev.file_proposal(project="vista-crm-wiring", ...)` — filed, applied inline, deleted per the apply-inline-then-delete rule. See §11 entry.

**Improvements:**
- Phase 1 misclassified `/imoveis/fotos` as 401; live re-probe says 404 (different tier reason). Corrected in 3 places (VISTA-API.md, PROJECT.md §5 endpoint table, `KNOWN_TABS` service constant). The placeholder UI was rewritten to distinguish "Permissão pendente" (401, fixable by Vista) from "Não disponível neste tenant" (404, requires subscription tier change). Lesson for the future: any docs derived from a one-shot live probe go stale silently; consider auto-refreshing the catalog on Diagnóstico-tab open or at boot.
- The bundled Phase 2-4 closing proposal contained 8 items: 5 applied inline as code comments / TODO markers (items 1-3, 5, 7), 1 deferred to the existing `erp-schema-drift-reconciliation` project (added a row to its drift table with the Vista audit insert payload), 1 kept here as a v2 design note awaiting user input on auto-refresh approach (item 6), 1 confirming-completeness only (migration seam doc, item 8). No follow-up project filed.

*(Note: Phase 3 + Phase 4 sub-task lists existed twice in earlier drafts of this document — once at the top of §6 in their canonical ✅ closed form and once again as unticked placeholders here. The duplicates have been removed; the canonical Phase 3 and Phase 4 entries above are the source of truth. Pre-commit hook caught the §6↔§11 inconsistency 2026-05-02.)*

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
| 2026-04-23 | Assessment + fix pass (Claude Opus 4.7): named the seed seams explicitly in §5 (backend router via existing `create_product_app(...) routers=[...]`; frontend page via existing `createProductApp({ routes: [...] })`), added LGPD-first constraint to §2 + principle to §3 + full posture subsection to §5, filed standing `noctus.dev.lgpd_flag` concern for the feature, corrected Phase 4 proposal wording to match the "ONE bundled proposal per phase" protocol, removed preemptive `none identified` from unstarted phases, renamed §10 "How to use this plan" → "How to use this project", and clarified the Loft-vs-Vista context in Related docs. | Claude Opus 4.7 |
| 2026-05-01 | **Phase 1 ✅ — Discovery baseline.** Credentials provided + stored in gitignored root `.env` (backend-only, no `VITE_` prefix). Live-probed the tenant `oneconsu-rest.vistahost.com.br`: 1,784-property catalog reachable; 4 endpoint families return 200 (`/imoveis/{listar,detalhes,listarConteudo}`, `/usuarios/listar`, `/agencias/listar`); 4 endpoint families return 401 (`/clientes/{listar,detalhes}`, `/corretores/listar`, `/imoveis/fotos` — exist but key lacks permission); ~14 other endpoint families return 404 (not on this tenant's subscription tier). Inventory tabulated in §5 with per-endpoint allowed/disallowed fields, response-shape caveats (top-level-keyed-by-id dicts, NOT arrays; `imovel` is top-level not inside `pesquisa`; `Foto` works on listar but NOT detalhes). v1 tab plan locked: Imóveis catalog + Detalhes drill-down + Usuários + Agência (4 active tabs); Clientes/Corretores/Fotos rendered as "Permissão pendente" placeholders. LGPD audit decision: ERP's existing `audit_logs` table; record `{action, resource_type=vista_<tab>, resource_id, user_id, created_at}` per call; **never persist Vista payload**. Phase 2 ready. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 4 ✅ — closing wave (post-improvements).** Bundled proposal `vista-showcase-phase-2-4-closing` filed via `noctus.dev.file_proposal`, then 5 of 8 items applied inline as code comments / TODO markers (items 1-3, 5, 7 in proposal body), 1 deferred to existing `erp-schema-drift-reconciliation` project (added Vista row to drift table — item 4), 1 v2 design note kept inline awaiting user input on auto-refresh strategy (item 6), 1 confirming completeness (item 8). Proposal file deleted per apply-inline-then-delete rule. End-of-session verification: backend pytest 1816/1816 ✅, Vista router tests 18/18 ✅, frontend `npx vite build` ✅, MCP review 0 issues ✅, live tenant smoke 4/7 endpoints reachable as documented + 1 corrected (fotos 401→404). Project status flipped to ✅ Done. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 0 audit + Vista API doc + Phase 2 ✅ + Phase 3 ✅ + Phase 4 in progress.** Phase 0 caught: audit table is actually `erp.user_actions_log` (not `audit_logs`); helper `app.dependencies.log_action` already exists; admin gate uses `resolve_sso_role` + erp_role/noctus_role fallback. Authored `VISTA-API.md` — MCP-ready Vista API reference folding public docs + live probe + adapter contract. Phase 2: `app/integrations/vista/{client,types,normalizers}.py` + `app/services/vista_showcase_service.py` + `app/routers/vista_showcase.py`; migration `023_vista_audit_enums.sql` extends `tipo_acao` with `consulta_externa` + `tipo_entidade` with `integracao_vista` (applied via Supabase MCP); 18 tests passing; full ERP suite 1816/1816 green. Phase 3: `pages/VistaShowcase.tsx` (7 sub-tabs: Imóveis · Usuários · Agência · Clientes · Corretores · Fotos · Diagnóstico) + `hooks/useVistaShowcase.ts` (7 TanStack Query hooks) + sidebar NAV_GROUP "Integrações" → /integracoes/vista; admin-gated via `useIsAdmin`. Frontend `npx vite build` green. Phase 4 live smoke (`/tmp/vista_smoke.py`) confirmed 4 endpoints 200 + 2 endpoints 401 + corrected Phase 1's misclassification of `/imoveis/fotos` (live = 404, not 401) — fixed in VISTA-API.md, PROJECT.md §5, and `KNOWN_TABS` service constant. Tab placeholder UI rephrased to distinguish "Permissão pendente" (401, fixable by Vista) vs "Não disponível neste tenant" (404, requires subscription expansion). | Claude Opus 4.7 |
| 2026-05-02 | **Phase 4.5 hardening — connection fix.** User opened the deployed page and saw `[502] Vista respondeu erro 400` on the Imóveis tab. Root cause: Phase 1's discovery probe authored `IMOVEL_LIST_FIELDS` / `IMOVEL_DETAIL_FIELDS` with seven fields the live tenant key actually rejects (`Estado`, `Banheiros`, `Foto`, `FotoPrincipal`, `Slug`, `PalavrasChave`, `CodigoImobiliaria`) — the smoke probe never sent the full field bundle in one request, so the failures were latent. Live re-discovery against `oneconsu-rest.vistahost.com.br` produced the calibrated set (29 available fields, see VISTA-API.md). Fixes applied: (a) `IMOVEL_LIST_FIELDS` / `IMOVEL_DETAIL_FIELDS` re-calibrated — `Estado`→`UF`, `Banheiros`→`BanheiroSocial`, `Foto`→`FotoDestaque`, dropped `Slug`/`PalavrasChave`/`CodigoImobiliaria`; (b) normalizer reads both old and new field names so other tenants still work; (c) `_first_corretor_nome()` walks the dict-keyed-by-corretor-id shape (`{"103": {...}}`) — Phase 1 code assumed flat `{"Nome": "..."}` and silently produced `corretor_nome=None`; (d) `/imoveis` router now catches `VistaFieldNotAvailable` explicitly → HTTP 422 with the offending field name, instead of masking it as the generic 502 the user actually saw. Verified end-to-end: live API returns 1,783 properties (`fetch_imoveis`), `fetch_imovel_detalhes` returns full Caracteristicas, `fetch_usuarios` returns 10 users, `fetch_agencias` returns 1 agency. ERP backend pytest 1816/1816 green; ERP frontend `npx vite build` green; Vista router tests 18/18 green. | Claude Opus 4.7 |
| 2026-05-02 | **Phase 4.6 hardening — frontend hook fix.** With the backend now returning 200, the dev page exposed a second bug: `Query data cannot be undefined. Affected query key: ["vista-showcase","imoveis",1,50,{}]`. Root cause: every hook in `useVistaShowcase.ts` was treating `api.get<T>()` as if it returned an axios-style `{ data: T }` wrapper and reading `result.data`. The seed-lib's `api.get` actually returns the parsed JSON directly as `T` (see `seed/lib/frontend/src/api.ts § handleResponse`), so `result.data` was always `undefined`. The previous backend 502 had been masking it because `api.get` *throws* on non-2xx (so TanStack Query saw an error, not undefined). Once the backend went green, the queryFn returned `undefined` and TanStack Query v5 enforced its no-undefined rule. Fix: all 7 hooks now read the response shape directly (`result.tabs`, `result.items`, `result.pagination`, etc.) and return `result ?? null` / `result.items ?? []` so the queryFn never returns `undefined`. Verified: ERP frontend `npx vite build` green. **Cross-cutting finding (out of scope here, surfaced for triage)**: the same `result.data` anti-pattern exists in `useFunil.ts`, `usePortais.ts`, `useMarketing.ts`, `useAgenda.ts`, `useMarketing.ts`, `usePortalCliente.ts` — those hooks have a `(result.data ?? [])` fallback so they silently return empty arrays instead of erroring, but they have NEVER actually rendered live data. Recurrence-rule N≥3+ → MUST formalize. Recommended follow-up: file `erp-frontend-hook-result-data-cleanup` project to sweep these hooks. | Claude Opus 4.7 |
