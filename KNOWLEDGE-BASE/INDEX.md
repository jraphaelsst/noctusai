# Knowledge Base — Index

> **Purpose:** This is the structural catalog of the NoctusAI Knowledge Base. Agents and developers use it to answer: *"where is X?"*.
> For *"what is this place?"* — read `AGENT-CONTEXT.md` instead (prose onboarding).
>
> **Sync rule:** Kept in sync with `CLAUDE.md`'s map section. If you add, rename, or delete a file in the KB, update both.

---

## Layout

```
KNOWLEDGE-BASE/
├── INDEX.md                ← this file (the catalog)
├── AGENT-CONTEXT.md        ← "what is this place" (onboarding prose)
├── CONTEXT/                ← deep technical + architectural context
│   ├── 01-PHILOSOPHY.md    ← engineering principles (elaborated)
│   ├── 02-LANDSCAPE.md     ← products, schemas, ports, stack
│   ├── 03-SEED-ARCHITECTURE.md  ← the spine
│   ├── 04-SHARED-LIBRARY.md     ← reusable components catalog
│   ├── 05-INFRASTRUCTURE.md     ← deployment + self-hosted services
│   ├── 06-AGENTS.md        ← MCP dev toolkit (Claude-side agents)
│   ├── 07-GAMIFICATION.md  ← cross-product UX philosophy
│   ├── PATTERNS/           ← how-to technical patterns
│   │   ├── backend.md
│   │   ├── frontend.md
│   │   ├── testing.md
│   │   ├── database-rls.md
│   │   ├── environment.md
│   │   ├── notifications.md
│   │   ├── shared-library-conventions.md
│   │   ├── project-execution.md
│   │   ├── proposals-and-improvements.md  ← two-system protocol (improvements per-project, ONE bundled proposal per phase)
│   │   ├── lgpd.md
│   │   ├── llm-usage.md       ← Phase 15 DB-backed usage sink + admin endpoints
│   │   ├── logging.md         ← level guide, no-`# silent-ok` rule, correlation IDs
│   │   ├── seed-lib-layout.md ← 6-layer model + decision tree
│   │   ├── seed-fake-real-adapter.md ← canonical Protocol+Fake+Real+factory shape for IO-touching seed modules
│   │   ├── agent-reading-discipline.md ← narrow-read first; Explore delegation (forthcoming)
│   │   ├── webhook-signatures.md ← four shapes (Hub-Signature / hex HMAC / Svix / Stripe SDK); helpers in noctusai_lib.security.webhook_signatures
│   │   ├── accept-with-rationale.md ← pattern definition + durable catalog of every active accept-with-rationale on the platform
│   │   ├── ast.md                  ← AST-first toolchain (libcst / ts-morph / tree-sitter) + recipes + anti-patterns + boundary rule
│   │   ├── mcp-tool-conventions.md ← 3-segment dotted naming + Pydantic In/Out + hierarchical registration + lazy context + MCP-first principle
│   │   ├── seed-workspace.md   ← sibling consume-only workspace; "templates cannot modify noc" rule + 3-layer defense + promotion manifest
│   │   ├── llm-tool-audit.md       ← per-product tool_call_audits table + AuditRecord/AuditWriter + LGPD redaction + adoption checklist
│   │   ├── llm-bot-security.md     ← defense trio (sanitization / arg-validation / rate-limit) + confidence thresholds + prompt-injection mitigation + baseline checklist
│   │   ├── digest-seed.md          ← noctusai_lib.domain.digest — BaseDigestService template-method base + DigestWindow/DigestResult; 4-adopter cluster (audit/weekly-review/campaign-debrief/monthly-narrative)
│   │   ├── metas-seed.md           ← noctusai_lib.domain.metas — Goal/Target/Progress/Period value objects + state machine + period date-math + GoalRepository Protocol; lifted from PF/ERP/daily-life N=3
│   │   ├── scheduling-seed.md      ← noctusai_lib.domain.scheduling — engine + Conflict/Scorer/TravelLookup Protocols + wiring recipe
│   │   ├── whatsapp-chatbot-seed.md ← noctusai_lib.{integrations.whatsapp,domain.chatbot,integrations.{google_calendar,google_maps}} — connector + framework + adapters wiring recipe
│   │   ├── master-tree-parallel-batches.md ← multi-product orchestrator running same-shape phases as synchronized batches; live cross-pollination via shared scratchpad; divergent-batch carve-out
│   │   ├── branching-and-merging.md   ← end-to-end git workflow: branching (when, how, push semantics, mental model, naming, anti-patterns) + merging (non-FF integration, multi-branch convergence, conflict resolution discipline, long-running branch maintenance, recovery from bad merges)
│   │   ├── dev-team.md                ← agno multi-agent dev team (engine at dev_team/ + product at products/dev-team/); MCP exposure noctus.team.*; charter / tools / memory / telemetry / configs surfaces; "switch flip" UX
│   │   ├── seed-absorption.md         ← noctus.seed.* MCP tools (scan_repetition / list_capabilities / audit_drift / absorb_file / specify_capability / report / scan_fusions / scan_optimizations — the absorption+fusion+optimization trio) + noctus.hound.scan trio orchestrator + 4 absorption strategies (delete dead code / move to seed + re-export / factory / template + runtime substitution) + per-candidate loop + safety rules
│   │   └── containerization.md         ← multi-layer Docker compose: per-product fragments + root orchestrator with `include:` + shared `noctus-net` + Redis/WAHA/tunnel profiles; canonical pattern at products/seed/; ./start.sh as Docker-default with tunnel <slug> mode (cloudflare quick-tunnel for OAuth callbacks / webhook testing / shared demos); native preserved as legacy; build/network/security/troubleshooting; improvement backlog
│   ├── GUIDES/             ← task-oriented guides
│   │   ├── setup.md
│   │   ├── new-product.md
│   │   ├── seed-first-design.md
│   │   └── deploy-workspace-online.md  ← "put X online" drill: verify docker artifacts → fill .env → docker compose up → verify; trigger phrases
│   ├── INTEGRATIONS/       ← per-vendor integration references (auth, endpoints, error model, adapter contract)
│   │   └── vista.md        ← Vista CRM REST API — public docs + live-probe results + adapter contract folded into one
│   ├── backend/            ← per-product backend details
│   │   ├── 01-CORE.md
│   │   ├── 02-ERP.md
│   │   ├── 03-PF.md
│   │   ├── 04-DATABASE.md
│   │   ├── 05-AI-FEATURES.md
│   │   ├── 06-THERAPY.md
│   │   ├── 07-AUTH-SECURITY.md
│   │   └── 08-DAILY-LIFE.md
│   └── frontend/           ← per-product frontend details
│       ├── 01-CORE.md
│       ├── 02-ERP.md
│       ├── 03-PF.md
│       └── 04-THERAPY.md
├── INSTRUCTIONS/           ← agent development / skill design
│   ├── 00-MASTER.md
│   ├── 01-SKILLS.md
│   ├── 02-MCP.md
│   ├── 03-AGENTIC-WORKFLOWS.md
│   ├── 04-DESIGN-PHASES.md
│   ├── 05-TESTING-EVALS.md
│   ├── 06-TECH-STACK.md
│   └── 07-TEMPLATES.md
├── EVALS/                  ← eval config + cases
├── SKILLS/                 ← skill definitions
├── WORKFLOWS/              ← multi-step workflows
└── MCP-SERVERS/            ← MCP server references
```

---

## By topic — "where do I find…"

| Topic | File |
|---|---|
| Engineering rules (seed-first, no quick fixes, DRY, etc.) | `CONTEXT/01-PHILOSOPHY.md` |
| Product landscape (names, ports, schemas, stack) | `CONTEXT/02-LANDSCAPE.md` |
| Seed framework APIs (`create_product_app`, `createProductApp`, etc.) | `CONTEXT/03-SEED-ARCHITECTURE.md` |
| Reusable components catalog (before writing anything) | `CONTEXT/04-SHARED-LIBRARY.md` |
| Infrastructure (ports, Docker, WAHA, LiveKit, n8n) | `CONTEXT/05-INFRASTRUCTURE.md` |
| MCP dev toolkit (heal loop, proposals, tools) | `CONTEXT/06-AGENTS.md` |
| Gamification philosophy (ranks, points, subtle UX) | `CONTEXT/07-GAMIFICATION.md` |
| Backend patterns (auth, SSO, RLS, N+1, services) | `CONTEXT/PATTERNS/backend.md` |
| Frontend patterns (mobile-first, TanStack Query, hooks) | `CONTEXT/PATTERNS/frontend.md` |
| Testing discipline (3 layers, mocking, auth boundary) | `CONTEXT/PATTERNS/testing.md` |
| RLS + DB rules (`auth.uid()` subquery, search_path) | `CONTEXT/PATTERNS/database-rls.md` |
| Environment vars (single `.env`, VITE_ prefix, CORS) | `CONTEXT/PATTERNS/environment.md` |
| Notifications (`public.notifications`, field mapping) | `CONTEXT/PATTERNS/notifications.md` |
| Shared-library conventions (privatize / absorb / rename; catalog tool) | `CONTEXT/PATTERNS/shared-library-conventions.md` |
| Project execution (phase-header ticks, improvements block, improvements.md retrospective tool) | `CONTEXT/PATTERNS/project-execution.md` |
| Proposals & improvements (two systems — per-project folders, ONE bundled proposal per phase, promote boundary) | `CONTEXT/PATTERNS/proposals-and-improvements.md` |
| LGPD awareness (keeper principle, the five questions, noctus.dev.lgpd_flag tool) | `CONTEXT/PATTERNS/lgpd.md` |
| LLM usage tracking (SupabaseUsageSink, /api/llm/usage, cost estimation, RLS scoping) | `CONTEXT/PATTERNS/llm-usage.md` |
| Logging convention (when-to-log, level guide, no-`# silent-ok` rule, correlation IDs) | `CONTEXT/PATTERNS/logging.md` |
| Seed-lib layout (6 layers — primitives/config/testing/integrations/domain/api — where to put new helpers, where to find existing ones) | `CONTEXT/PATTERNS/seed-lib-layout.md` |
| Agent reading & research discipline (narrow-read first; Explore delegation rule forthcoming) | `CONTEXT/PATTERNS/agent-reading-discipline.md` |
| Webhook signature verification (the four shapes: Hub-Signature / hex HMAC / Svix / Stripe SDK; constant-time compare; helper module in `noctusai_lib.security.webhook_signatures`) | `CONTEXT/PATTERNS/webhook-signatures.md` |
| Accept-with-rationale catalog (durable home for every legitimate divergence on the platform — survives project folder deletion; how to add / retire entries) | `CONTEXT/PATTERNS/accept-with-rationale.md` |
| AST-driven code edits (libcst for Python / ts-morph for TypeScript / tree-sitter cross-language; recipes for rename / find-callers / codemods; anti-patterns; boundary rule) | `CONTEXT/PATTERNS/ast.md` |
| MCP tool conventions (3-segment dotted naming `noctus.dev.* / noctus.business.* / google.* / openai.*`, Pydantic In/Out per tool, hierarchical registration, lazy `NoctusContext` for business-logic tools, settings shim, MCP-first principle) | `CONTEXT/PATTERNS/mcp-tool-conventions.md` |
| Seed workspace (sibling-of-noc consume-only workspace; symlinks all 8 noc surfaces; pre-commit hook + chmod + KB rule = three-layer "templates can't modify noc" defense; promotion manifest for additions; bootstrap script + workspace.py resolver + `noctus.dev.promote_from_seed_workspace` MCP tool) | `CONTEXT/PATTERNS/seed-workspace.md` |
| LLM tool-call audit (`tool_call_audits` per-product table; `noctusai_lib.domain.ai.tool_audit::AuditRecord` + `make_audit_writer`; best-effort write; LGPD redaction at consumer; common BI queries) | `CONTEXT/PATTERNS/llm-tool-audit.md` |
| LLM bot security (defense trio: output sanitization + Pydantic-arg validation + rate-limit; confirm-then-execute for destructive tools; prompt-injection mitigation via instruction sandboxing + allowlists; baseline checklist) | `CONTEXT/PATTERNS/llm-bot-security.md` |
| Digest service primitive (`noctusai_lib.domain.digest`: `BaseDigestService` template-method base + `DigestWindow`/`DigestResult` types; 4-adopter cluster — core/audit, daily-life/weekly-review, mailing/campaign-debrief, PF/monthly-narrative; non-fits: ERP/metas-digest + daily-life/daily-brief documented) | `CONTEXT/PATTERNS/digest-seed.md` |
| Scheduling primitive (`noctusai_lib.domain.scheduling`: engine + `TravelLookup`/`Conflict`/`Scorer` Protocols + `ZeroTravelLookup`/`DefaultConflict`/`DefaultScorer` defaults; wiring recipe; what stays consumer-side) | `CONTEXT/PATTERNS/scheduling-seed.md` |
| Metas / goals primitive (`noctusai_lib.domain.metas`: `Goal`/`Target`/`Progress`/`Period`/`Contribution` value objects, `GoalStatus`/`PeriodKind` enums, `compute_progress` / `accumulate_contribution` / `period_bounds` / `proportional_target` / `next_status` pure functions, `GoalRepository` Protocol seam; lifted from PF/ERP/daily-life N=3 MUST-FORMALIZE; wiring recipe + status mapping + what stays consumer-side) | `CONTEXT/PATTERNS/metas-seed.md` |
| WhatsApp connector + chatbot framework (`noctusai_lib.integrations.whatsapp` WAHA parser/sender/router + `noctusai_lib.domain.chatbot` buffer/worker/dispatcher/summary + `noctusai_lib.integrations.{google_calendar,google_maps}` adapters; wiring recipe; debounce-race documented; what stays consumer-side) | `CONTEXT/PATTERNS/whatsapp-chatbot-seed.md` |
| Master-tree parallel batches (multi-product orchestrator: same-shape phases across N children execute as synchronized batches; live patterns log + absorption catalog as shared scratchpad; sync-gates pre/mid/post; divergent-batch carve-out; agent collaboration mechanics) | `CONTEXT/PATTERNS/master-tree-parallel-batches.md` |
| Branching and merging methodology — end-to-end git workflow (when to branch, how to branch from `origin/main`, push semantics — branch-to-branch + branch-tip-to-main fast-forward, naming convention, mental-model upgrade, anti-patterns; non-FF integration, multi-branch convergence, conflict resolution discipline, long-running branch maintenance, recovery from bad merges) | `CONTEXT/PATTERNS/branching-and-merging.md` |
| Seed Fake+Real adapter pattern — canonical shape (Protocol + Fake + Real + factory) for IO-touching seed modules; gold-standard reference modules; exemption test for pure-logic/pure-crypto modules; backfill audit trail | `CONTEXT/PATTERNS/seed-fake-real-adapter.md` |
| Seed absorption methodology + tools — the **absorption + fusion + optimization trio** (cross-product / cross-tool / intra-file scopes): `noctus.seed.scan_repetition` / `list_capabilities` / `audit_drift` / `absorb_file` / `specify_capability` / `report` rollup / `scan_fusions` meta-detector / `scan_optimizations` intra-file detector + **`noctus.hound.scan`** trio orchestrator (keeper-analog for code hygiene); four absorption strategies (delete dead code / move-and-re-export / factory / template + runtime substitution); per-candidate loop (scan → evaluate → self-audit → absorb → re-scan → build-verify); safety rules; relation to DRY recurrence rule + delete_product symmetry | `CONTEXT/PATTERNS/seed-absorption.md` |
| Containerization (multi-layer Docker: per-product `docker-compose.yml` + root orchestrator with `include:` + shared `noctus-net` fabric + per-product isolation networks; canonical Dockerfile/compose pattern at `products/seed/`; `./start.sh` Docker-default with `tunnel <slug>` cloudflare quick-tunnel mode for OAuth/webhook/demo testing; native legacy mode preserved; build process / layering / image footprint / network security model / troubleshooting / improvement backlog) | `CONTEXT/PATTERNS/containerization.md` |
| First clone + starting servers | `CONTEXT/GUIDES/setup.md` |
| Creating a new product | `CONTEXT/GUIDES/new-product.md` |
| Seed-first design checklist (cross-product projects — REQUIRED at authoring time) | `CONTEXT/GUIDES/seed-first-design.md` |
| Putting a workspace product online for testing — the "deploy" drill (verify docker artifacts → fill `.env` → `docker compose up` → verify); trigger phrases the agent should recognise | `CONTEXT/GUIDES/deploy-workspace-online.md` |
| Vista CRM REST API (auth, query convention, response envelope, error hierarchy, endpoint inventory, adapter contract, per-tenant calibration gap) | `CONTEXT/INTEGRATIONS/vista.md` |
| Core backend (routers, services, tables) | `CONTEXT/backend/01-CORE.md` |
| ERP backend | `CONTEXT/backend/02-ERP.md` |
| PF backend | `CONTEXT/backend/03-PF.md` |
| Database inventory per schema | `CONTEXT/backend/04-DATABASE.md` |
| AI features (OpenAI, embeddings, summaries) | `CONTEXT/backend/05-AI-FEATURES.md` |
| Therapy backend | `CONTEXT/backend/06-THERAPY.md` |
| Auth + security deep-dive | `CONTEXT/backend/07-AUTH-SECURITY.md` |
| Daily Life backend | `CONTEXT/backend/08-DAILY-LIFE.md` |
| Core frontend | `CONTEXT/frontend/01-CORE.md` |
| ERP frontend | `CONTEXT/frontend/02-ERP.md` |
| PF frontend | `CONTEXT/frontend/03-PF.md` |
| Therapy frontend | `CONTEXT/frontend/04-THERAPY.md` |
| Skill design (composable agent units) | `INSTRUCTIONS/01-SKILLS.md` |
| MCP integration patterns | `INSTRUCTIONS/02-MCP.md` |
| Agentic workflows | `INSTRUCTIONS/03-AGENTIC-WORKFLOWS.md` |
| Eval strategy | `INSTRUCTIONS/05-TESTING-EVALS.md` |
| Tech stack details | `INSTRUCTIONS/06-TECH-STACK.md` |
| Artifact templates | `INSTRUCTIONS/07-TEMPLATES.md` |

---

## By situation — "when I'm doing X, read Y"

| Situation | Start here |
|---|---|
| Fresh agent, zero context | `AGENT-CONTEXT.md` → `CONTEXT/01-PHILOSOPHY.md` → `CONTEXT/02-LANDSCAPE.md` |
| About to write new backend code | `CONTEXT/PATTERNS/backend.md` + product-specific `CONTEXT/backend/0X-*.md` |
| About to write new frontend code | `CONTEXT/PATTERNS/frontend.md` + product-specific `CONTEXT/frontend/0X-*.md` |
| Touching any DB migration | `CONTEXT/PATTERNS/database-rls.md` + `CONTEXT/backend/04-DATABASE.md` |
| Adding a new product | `CONTEXT/GUIDES/new-product.md` + `CONTEXT/03-SEED-ARCHITECTURE.md` |
| Adding a shared component | `CONTEXT/04-SHARED-LIBRARY.md` (check existing first) |
| Working on tests | `CONTEXT/PATTERNS/testing.md` |
| Adding a `try/except` (production code) | `CONTEXT/PATTERNS/logging.md` (level guide, the no-`# silent-ok` rule) |
| Adding a new keeper detector | `CONTEXT/PATTERNS/testing.md § Regression-test-the-detector` + `CONTEXT/06-AGENTS.md § Detectors` |
| Adding a helper to seed lib (deciding which layer it lives in) | `CONTEXT/PATTERNS/seed-lib-layout.md § Where to put a new helper` |
| Looking for an existing seed-lib helper | `CONTEXT/PATTERNS/seed-lib-layout.md § Where to look` + `CONTEXT/04-SHARED-LIBRARY.md` (catalog) |
| Working on env / deployment | `CONTEXT/PATTERNS/environment.md` + `CONTEXT/05-INFRASTRUCTURE.md` |
| Touching UI with performance data / gamification | `CONTEXT/07-GAMIFICATION.md` |
| Reading a large/unfamiliar file (default — narrow-read first) | `CONTEXT/PATTERNS/agent-reading-discipline.md § Narrow-read first` |
| About to edit `.py` / `.ts` / `.tsx` source — rename, codemod, find-callers, anything beyond a 1-line targeted edit | `CONTEXT/PATTERNS/ast.md` (AST-first; never sed/regex on source) |
| Adding any helper or function an agent might want to call (Claude Code / future bot / future product agent) | `CONTEXT/01-PHILOSOPHY.md § MCP-first` (default surface is `mcp/noctusai/`) |
| Designing a new agent / skill / MCP | `INSTRUCTIONS/00-MASTER.md` |
| Touching Vista CRM (adapter, MCP server, endpoint surface, field-set calibration) | `CONTEXT/INTEGRATIONS/vista.md` |

---

## Sync with `CLAUDE.md`

`CLAUDE.md` at the repo root is the **outer map** — slim, loaded every Claude session, contains behavioral rules + pointers into this KB.

This `INDEX.md` is the **inner map** — the KB's own authoritative self-description. Kept in sync with CLAUDE.md's map section.

Sync enforcement (pick any/all):
1. **Rule** — when you change `CLAUDE.md`'s map or any KB file/folder, update both this INDEX and CLAUDE.md. Documented in `CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`.
2. **Script** — `scripts/verify-kb-sync.sh` validates that CLAUDE.md pointers resolve to real files and all KB files are indexed. Run pre-commit.
3. **MCP tool** — `python mcp/noctusai/cli.py verify-kb-sync` (same check, integrated into the heal loop).
